import os
import json
import uuid
import cv2  # 비디오 처리를 위한 OpenCV 임포트. 프레임 단위 처리 및 바운딩 박스 그리기에 사용됨.
from ultralytics import YOLO  # YOLOv8 모델 임포트. 객체 탐지에 사용됨.
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, url_for, redirect, session, jsonify, send_from_directory

from common.Session import Session

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_IMAGE_SIZE'] = 20 * 1024 * 1024
app.config['MAX_VIDEO_SIZE'] = 500 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024

# YOLOv8 모델 초기화 (커스텀 학습된 모델 로드)
# 아키텍처(CPU) 서버 환경 구동을 위해 변환된 ONNX 경량화 모델을 사용하며, 파일이 없으면 자동 변환합니다.
onnx_path = 'best (2).onnx'
pt_path = 'best (2).pt'

if not os.path.exists(onnx_path) and os.path.exists(pt_path):
    print("🚀 [최초 시작 감지] 경량화된 ONNX 모델이 없습니다. 자동 변환을 수행합니다... (수 분 소요됨)")
    try:
        temp_model = YOLO(pt_path)
        # FP16 양자화, 832 해상도 고정을 통해 서버 부하 최소화
        temp_model.export(format='onnx', half=True, imgsz=832, simplify=True)
        print("✅ [자동 변환] 완료되었습니다! 서버를 가동합니다.")
    except Exception as e:
        print(f"⚠️ 모델 변환 중 오류가 발생하여 기존 pt 모델을 사용합니다: {e}")
        onnx_path = pt_path  # 실패 시 안전하게 기존 모델로 폴백(fallback)

try:
    yolo_model = YOLO(onnx_path)  # FP16 추론이 적용된 경량 ONNX 모델 로드
except Exception as e:
    yolo_model = None
    print(f"YOLO 모델 로드 실패: {e}")


# ===============================================
# Helper Functions (Used by multiple routes or as dependencies)
# ===============================================

def get_user_info(user_id):
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM members WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            return row
    finally:
        conn.close()


def process_video_yolo(input_path, output_path):
    """
    업로드된 비디오를 읽어 프레임별로 YOLO 모델을 사용해 객체를 탐지하고,
    바운딩 박스가 그려진 새로운 비디오 파일을 생성하며, 프레임별 태그 정보를 반환합니다.
    (요구사항에 맞추어 비디오 내 객체를 식별하고 결과를 별도로 저장하기 위해 작성된 함수입니다.)
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise Exception("비디오 파일을 열 수 없습니다.")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or fps != fps:  # fps가 0이거나 NaN일 경우 대비 기본값 설정
        fps = 30.0

    # MP4 코덱을 사용하여 처리된 영상을 저장 (호환성을 위해 mp4v 사용) -> 웹 브라우저 호환성을 위해 H.264(avc1) 코덱으로 변경
    # 웹 브라우저는 mp4v 코덱을 네이티브로 재생하지 못하는 경우가 많아 영상 재생이 불가능할 수 있음
    # [수정] 사용자의 시스템에 OpenH264 라이브러리(.dll)가 누락되어 avc1 코덱 초기화 에러가 발생한 상황.
    # 별도 라이브러리 설치 없이도 웹에서 잘 호환되도록 코덱을 vp80(WebM)으로 변경함.
    fourcc = cv2.VideoWriter_fourcc(*'vp80')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_idx = 0
    results_json = {}

    # 🚀 [최적화 3단계] 3프레임 당 1번만 실제 AI 분석을 수행 (연산량 약 66% 감소)
    skip_frames = 3
    last_plotted_frame = None
    last_frame_tags = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        time_sec = round(frame_idx / fps, 2)

        if yolo_model:
            # 설정한 skip_frames(3프레임) 마다 모델 추론 진짜 수행
            if frame_idx % skip_frames == 0:
                # 🚀 [최적화 2단계] imgsz=1280 -> 832로 조정하여 연산량 및 메모리 사용량 반토막 감소
                results = yolo_model(frame, verbose=False, conf=0.15, imgsz=832)

                frame_tags = []
                for result in results:
                    for box in result.boxes:
                        cls_id = int(box.cls[0])
                        label = yolo_model.names[cls_id]
                        if label not in frame_tags:
                            frame_tags.append(label)
                    # YOLO 객체에 내장된 plot 기능을 활용하여 바운딩 박스를 간편하게 그림
                    frame = result.plot()

                # 분석한 현재 결과(프레임 이미지 + 태그)를 저장해둠
                last_plotted_frame = frame
                last_frame_tags = frame_tags
            else:
                # AI 분석을 쉬는 프레임은 직전에 분석해둔 화면을 그대로 재사용하여 속도 대폭 향상
                if last_plotted_frame is not None:
                    frame = last_plotted_frame
                    frame_tags = last_frame_tags

            results_json[str(time_sec)] = frame_tags

        # 바운딩 박스가 추가된 프레임을 새로운 비디오 파일에 기록
        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()
    return results_json


def process_image_yolo(input_path, output_path):
    """
    업로드된 이미지를 읽어 YOLO 모델을 사용해 객체를 탐지하고,
    바운딩 박스가 그려진 새로운 이미지 파일을 생성하며, 탐지된 객체 정보를 반환합니다.
    (실제 AI 모델을 통해 이미지 분석 결과를 도출하고 시각화된 결과를 저장하기 위해 추가됨)
    """
    img = cv2.imread(input_path)
    if img is None:
        raise Exception("이미지 파일을 읽을 수 없습니다.")

    objects = []
    if yolo_model:
        # 🚀 [최적화 2단계] 이미지 분석 시에도 imgsz=1280 -> 832로 변경하여 처리 속도 대폭 개선
        results = yolo_model(img, verbose=False, conf=0.15, imgsz=832)
        for result in results:
            for box in result.boxes:
                # 좌표, 신뢰도, 클래스 추출
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                label = yolo_model.names[cls_id]

                # 프론트엔드 포맷(objects 배열)에 맞게 구성
                objects.append({
                    "box": [x1, y1, x2, y2],
                    "label": label,
                    "score": conf
                })
            # YOLO가 제공하는 plot 기능을 통해 원본 이미지 위에 바운딩 박스를 덧그림
            img = result.plot()

    # 분석이 완료된 이미지를 파일로 저장
    cv2.imwrite(output_path, img)
    return objects


def execute_ai_analysis(media_id):
    """
    기존 더미 AI 분석 로직을 실제 YOLO 모델 분석으로 대체합니다.
    파일 타입이 VIDEO일 경우 process_video_yolo를, IMAGE일 경우 process_image_yolo를 호출하여 분석을 수행합니다.
    (mediafile_uploads에서 호출되어 실제 AI 추론 작업을 처리합니다.)
    """
    print(f"[{media_id}] 실제 AI 분석 시작...")
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 분석할 대상 파일의 경로 및 타입 조회
            cursor.execute("SELECT stored_path, file_type FROM media_files WHERE id = %s", (media_id,))
            row = cursor.fetchone()
            if not row:
                print(f"[{media_id}] 미디어 파일을 찾을 수 없습니다.")
                return

            stored_path = row['stored_path']
            file_type = row['file_type']

            if file_type == 'VIDEO':
                # 처리된 비디오 파일명 생성 로직 (원본 파일명 뒤에 _processed 추가)
                base_name, ext = os.path.splitext(stored_path)
                # [수정] 코덱을 vp80으로 변경함에 따라 호환되는 컨테이너 포맷인 .webm 확장자로 저장하도록 파일 확장자를 변경함.
                processed_path = f"{base_name}_processed.webm"

                try:
                    # YOLO를 이용한 비디오 분석 및 저장 수행
                    analysis_data = process_video_yolo(stored_path, processed_path)

                    # 프레임별 태그 정보와 생성된 비디오 파일 이름을 포함하여 JSON 생성
                    final_result = {
                        "processed_video_path": os.path.basename(processed_path),
                        "frame_tags": analysis_data
                    }

                    # 성공적으로 처리된 결과를 데이터베이스에 업데이트
                    sql = "UPDATE analysis_results SET status = 'SUCCESS', result_json = %s WHERE media_id = %s"
                    cursor.execute(sql, (json.dumps(final_result), media_id))
                    conn.commit()
                    print(f"[{media_id}] 비디오 AI 분석 완료!")
                except Exception as e:
                    print(f"[{media_id}] 비디오 처리 중 오류 발생: {e}")
                    cursor.execute("UPDATE analysis_results SET status = 'FAIL' WHERE media_id = %s", (media_id,))
                    conn.commit()
            else:
                # 이미지 파일에 대한 실제 AI 분석 수행 로직으로 교체
                base_name, ext = os.path.splitext(stored_path)
                processed_path = f"{base_name}_processed{ext}"

                try:
                    # process_image_yolo 함수를 통해 추론 및 이미지 생성 수행
                    objects_data = process_image_yolo(stored_path, processed_path)

                    # 프론트엔드가 요구하는 포맷으로 JSON 생성
                    final_result = {
                        "objects": objects_data,
                        "processed_image_path": os.path.basename(processed_path)
                    }

                    # DB에 분석 결과(JSON 형태)를 업데이트
                    sql = "UPDATE analysis_results SET status = 'SUCCESS', result_json = %s WHERE media_id = %s"
                    cursor.execute(sql, (json.dumps(final_result), media_id))
                    conn.commit()
                    print(f"[{media_id}] 이미지 AI 분석 완료!")
                except Exception as e:
                    print(f"[{media_id}] 이미지 처리 중 오류 발생: {e}")
                    cursor.execute("UPDATE analysis_results SET status = 'FAIL' WHERE media_id = %s", (media_id,))
                    conn.commit()

    except Exception as e:
        print(f"[{media_id}] 분석 DB 연동 오류: {e}")
    finally:
        conn.close()


def mediafile_uploads(file, user_id, upload_folder, config, memo=None):
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    ext = filename.split('.')[-1].lower()
    is_image = ext in ['jpg', 'jpeg', 'png', 'gif']
    file_type = 'IMAGE' if is_image else 'VIDEO'
    limit = config.get('MAX_IMAGE_SIZE') if is_image else config.get('MAX_VIDEO_SIZE')
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > limit:
        limit_mb = limit // (1024 * 1024)
        raise ValueError(f"{file_type} 파일은 {limit_mb}MB를 초과할 수 없습니다.")
    stored_path = os.path.join(upload_folder, unique_filename)
    os.makedirs(upload_folder, exist_ok=True)
    file.save(stored_path)
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO media_files (member_id, file_name, stored_path, file_type, memo) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (user_id, filename, stored_path, file_type, memo))
            media_id = cursor.lastrowid
            cursor.execute("INSERT INTO analysis_results (media_id, status) VALUES (%s, 'PENDING')", (media_id,))
            conn.commit()

            # [요청이 완료되면 넘어가도록 변경]
            # 기존에는 스레드를 사용하여 비동기로 분석을 처리하고 상태를 polling 했으나,
            # 요청 자체에서 분석이 완료될 때까지 대기하도록 동기 처리 방식으로 변경합니다.
            # thread = threading.Thread(target=execute_ai_analysis, args=(media_id,), daemon=True)
            # thread.start()
            execute_ai_analysis(media_id)

            return media_id
    except Exception as e:
        conn.rollback()
        if os.path.exists(stored_path):
            os.remove(stored_path)
        raise e
    finally:
        conn.close()


def get_status(media_id):
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM analysis_results WHERE media_id = %s"
            cursor.execute(sql, (media_id,))
            row = cursor.fetchone()
            if row and row.get('result_json'):
                # JSON 문자열을 Python 딕셔너리로 변환
                row['result_json'] = json.loads(row['result_json'])
            return row
    finally:
        conn.close()


# ===============================================
# Flask Routes
# ===============================================

@app.errorhandler(413)
def file_too_large(e):
    max_bytes = app.config['MAX_CONTENT_LENGTH']
    if max_bytes >= 1024 * 1024 * 1024:
        max_size = f"{max_bytes // (1024 * 1024 * 1024)}GB"
    else:
        max_size = f"{max_bytes // (1024 * 1024)}MB"
    return jsonify({"status": "error", "message": f"업로드 가능한 최대 용량({max_size})을 초과했습니다."}), 413


@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'GET':
        return render_template('join.html')

    # POST
    uid = request.form.get('uid')
    password = request.form.get('pw')
    name = request.form.get('username')
    email = request.form.get('email')
    try:
        # Check for duplicate UID
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM members WHERE uid = %s", (uid,))
                is_duplicate = cursor.fetchone() is not None
        finally:
            conn.close()

        if is_duplicate:
            return "<script>alert('이미 존재하는 아이디 입니다.'); history.back();</script>"

        # Join member
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO members (uid, password, name, email) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (uid, password, name, email))
                conn.commit()
                # 성공 시
                return "<script>alert('회원가입이 완료 되었습니다.'); location.href='/login';</script>"
        except Exception as e:
            print(f"회원가입 오류: {e}")
            return "<script>alert('가입 도중 오류가 발생하였습니다.'); history.back();</script>"
        finally:
            conn.close()

    except Exception as e:
        print(e)
        return "<script>alert('치명적인 오류가 발생했습니다. 다시 시도해주세요'); history.back();</script>"


@app.route('/check_uid')  # /check_uid URL로 접속하면 이 함수 실행 GET방식으로 요청 받음
def check_uid():
    uid = request.args.get('uid')

    conn = Session.get_connection()
    # Session 클래스에서 만들어둔 MySQL 연결 객체를 가져옴
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM members WHERE uid=%s",
                (uid,)
            )
            if cursor.fetchone():
                return {"exists": True}  # 아이디 이미 사용 중(다른 사람이 쓰는중)
            else:
                return {"exists": False}  # 사용 가능
    finally:
        conn.close()


@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    # POST
    uid = request.form['uid']
    upw = request.form['pw']
    try:
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT id, name, uid, email, role FROM members WHERE uid = %s AND password = %s"
                cursor.execute(sql, (uid, upw))
                user = cursor.fetchone()
        finally:
            conn.close()

        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            session['user_uid'] = user['uid']
            session['user_role'] = user['role']
            return "<script>alert('로그인에 성공했습니다'); location.href='/';</script>"
        else:
            return "<script>alert('아이디 또는 비밀번호가 잘못되었습니다.'); history.back();</script>"
    except Exception as e:
        print(e)
        return render_template('login.html', error="치명적 오류 발생, 다시 시도해주세요")


@app.route('/find_id', methods=['GET', 'POST'])
def find_id():
    if request.method == 'GET':
        return render_template("find_id.html")

    name = request.form.get("name")
    email = request.form.get("email")

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT uid FROM members WHERE name = %s AND email = %s"
            cursor.execute(sql, (name, email))
            row = cursor.fetchone()

            if row:
                return jsonify({"success": True, "uid": row['uid']})
            else:
                return jsonify({"success": False, "message": "일치하는 계정이 없습니다."})
    finally:
        conn.close()


@app.route('/logout')
def logout():
    session.clear()
    return "<script>alert('로그아웃을 성공했습니다!'); location.href='/';</script>"


@app.route('/member/edit', methods=['GET', 'POST'])
def member_edit():
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))

        if request.method == 'GET':
            user_info = get_user_info(session['user_id'])
            return render_template('member_edit.html', user=user_info)

        # POST
        new_uid = request.form.get('new_uid')
        new_name = request.form.get('new_name')
        new_email = request.form.get('email')
        new_pw = request.form.get('pw')
        new_memo = request.form.get('bio')

        # 기존 정보 보존 로직 추가: 빈 칸일 경우 기존 정보를 유지
        user_info = get_user_info(session['user_id'])
        if not new_uid: new_uid = user_info['uid']
        if not new_name: new_name = user_info['name']
        if not new_email: new_email = user_info['email']
        if not new_memo: new_memo = user_info['bio']

        # [수정] 회원정보 수정 시 프로필 이미지와 bio를 함께 처리하도록 로직 병합
        # 기존 /upload_profile에 있던 파일 저장 로직을 이곳으로 이동했습니다.
        file = request.files.get('profile')
        unique_filename = None
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                if new_pw:
                    # bio(인삿말) 필드도 데이터베이스에 함께 업데이트되도록 쿼리 수정
                    sql = "UPDATE members SET uid = %s, name = %s, email = %s, password = %s, bio = %s WHERE id = %s"
                    cursor.execute(sql, (new_uid, new_name, new_email, new_pw, new_memo, session['user_id']))
                else:
                    # [버그수정 및 반영] 기존 코드에서 파라미터 개수가 맞지 않던 부분을 수정하고 bio(new_memo)를 추가
                    sql = "UPDATE members SET uid = %s, name = %s, email = %s, bio = %s WHERE id = %s"
                    cursor.execute(sql, (new_uid, new_name, new_email, new_memo, session['user_id']))

                # [요구사항] 프로필 데이터 존재 여부에 따른 INSERT / UPDATE 분기 로직 유지
                if unique_filename:
                    check_sql = "SELECT profile_image FROM members WHERE id = %s"
                    cursor.execute(check_sql, (session['user_id'],))
                    result = cursor.fetchone()

                    if result:
                        sql = "UPDATE members SET profile_image = %s WHERE id = %s"
                        cursor.execute(sql, (unique_filename, session['user_id']))
                    else:
                        sql = "INSERT INTO members (id, profile_image) VALUES (%s, %s)"
                        cursor.execute(sql, (session['user_id'], unique_filename))

                conn.commit()
                updated = True
        except Exception as e:
            print(e)
            updated = False
        finally:
            conn.close()

        if updated:
            session['user_uid'] = new_uid
            session['user_email'] = new_email
            session['user_name'] = new_name
            return "<script>alert('회원정보 수정을 완료했습니다.'); location.href = '/mypage';</script>"
        else:
            return "<script>alert('수정 도중 오류가 발생했습니다.'); history.back();</script>"

    except Exception as e:
        print(f'치명적 오류 발생{e}')
        return redirect(url_for('login'))


@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    user_info = get_user_info(user_id)

    # 최근 분석 결과 5개를 가져오는 로직 추가
    conn = Session.get_connection()
    analysis_results = []
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    m.id, m.memo, m.uploaded_at,
                    r.status
                FROM media_files m
                LEFT JOIN analysis_results r ON m.id = r.media_id
                WHERE m.member_id = %s
                ORDER BY m.uploaded_at DESC
                LIMIT 5
            """
            cursor.execute(sql, (user_id,))
            analysis_results = cursor.fetchall()
    finally:
        conn.close()

    return render_template('mypage.html', user=user_info, analysis_results=analysis_results)


@app.route('/member/delete/<int:user_id>', methods=['GET'])
def member_delete_route(user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return redirect(url_for('login'))

    deleted = False
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM members WHERE id = %s", (session['user_id'],))
            conn.commit()
            deleted = True
    except Exception as e:
        print(f"회원 탈퇴 중 오류: {e}")
        conn.rollback()
    finally:
        conn.close()

    if deleted:
        session.clear()
        return "<script>alert('회원탈퇴를 완료했습니다!.'); location.href='/'</script>"
    else:
        return "탈퇴 처리 중 오류 발생"


@app.route('/analyze', methods=['GET', 'POST'])
def analyze():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        memo = request.form.get('description')
        file = request.files.get('image_file') or request.files.get('video_file')
        if not file or file.filename == '':
            return jsonify({"status": "error", "message": "No file"}), 400
        try:
            media_id = mediafile_uploads(file, session['user_id'], app.config['UPLOAD_FOLDER'], app.config, memo=memo)
            return jsonify({"status": "pending", "media_id": media_id})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return render_template('analyze.html')


@app.route('/analyze/result', methods=['POST'])
def analyze_result():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401
    memo = request.form.get('description')
    file = request.files.get('image_file') or request.files.get('video_file')
    if not file or file.filename == '':
        return jsonify({"status": "error", "message": "파일이 선택되지 않았습니다."}), 400
    try:
        # 클라이언트 요청 시 분석을 동기적으로 수행하여 완료될 때까지 대기합니다.
        # 기존의 백그라운드 스레드 및 폴링 방식 대신 분석이 끝나면 즉시 성공 상태를 반환합니다.
        media_id = mediafile_uploads(file, session['user_id'], app.config['UPLOAD_FOLDER'], app.config, memo=memo)
        # 즉시 pending 상태를 반환하던 부분을 success를 반환하도록 수정 (폴링 안함)
        return jsonify({"status": "success", "media_id": media_id})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        print(f"업로드 오류: {e}")
        return jsonify({"status": "error", "message": "서버 오류가 발생했습니다."}), 500


# [기존 폴링용 상태 확인 API 주석 처리 시작]
# 더 이상 비동기 폴링을 사용하지 않으므로 상태 확인 API를 비활성화합니다.
'''
@app.route('/api/analysis/status/<int:media_id>')
def get_analysis_status(media_id):
    result = get_status(media_id)
    if result:
        # get_status에서 이미 JSON을 파싱했으므로 json.dumps는 불필요
        result_json = result.get('result_json', {})
        formatted_text = ""
        if not result_json:
            formatted_text = "분석 결과가 없습니다."
        else:
            try:
                # result_json은 이미 딕셔너리
                objects = result_json.get('objects', [])
                if not objects:
                    formatted_text = "검출된 객체가 없습니다."
                else:
                    lines = []
                    for i, obj in enumerate(objects, 1):
                        line = f"[{i}] {obj['label']} (신뢰도: {obj['score'] * 100:.1f}%)"
                        lines.append(line)
                    formatted_text = "\n".join(lines)
            except Exception:
                formatted_text = "데이터 형식 오류"

        return jsonify({
            "status": result['status'],
            "result": result_json,
            "formatted": formatted_text
        })
    return jsonify({"status": "not_found"}), 404
'''


# [기존 폴링용 상태 확인 API 주석 처리 끝]

@app.route('/analyze/analysis/<int:media_id>')
def analysis_detail(media_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    analysis_data = None
    try:
        with conn.cursor() as cursor:
            # media_files와 analysis_results 테이블을 조인하여 필요한 정보를 가져옵니다.
            # 이 쿼리는 특정 사용자의 특정 미디어 ID에 대한 모든 정보를 안전하게 조회합니다.
            sql = """
                SELECT 
                    m.stored_path, m.file_type, m.memo,
                    r.status, r.result_json
                FROM media_files m
                LEFT JOIN analysis_results r ON m.id = r.media_id
                WHERE m.id = %s AND m.member_id = %s
            """
            cursor.execute(sql, (media_id, session['user_id']))
            analysis_data = cursor.fetchone()

            if analysis_data and analysis_data.get('result_json'):
                # 데이터베이스에서 가져온 JSON 문자열을 파이썬 객체로 변환합니다.
                # 이렇게 해야 템플릿이나 다른 로직에서 쉽게 접근할 수 있습니다.
                if isinstance(analysis_data['result_json'], str):
                    analysis_data['result_json'] = json.loads(analysis_data['result_json'])

                # AI 분석 결과(result_json)를 사람이 읽기 좋은 형태의 문자열로 가공합니다.
                # 비디오와 이미지에 따라 결과 구조가 다르므로 분기하여 처리합니다.
                try:
                    result_json = analysis_data['result_json']
                    if analysis_data['file_type'] == 'VIDEO':
                        # 비디오의 경우 frame_tags 데이터가 존재하면 프론트엔드에서 처리하도록 안내 메시지 출력
                        if result_json and 'frame_tags' in result_json and result_json['frame_tags']:
                            analysis_data['formatted_result'] = "비디오 분석이 완료되었습니다. 영상을 재생하여 프레임별 탐지 결과를 확인하세요."
                        else:
                            analysis_data['formatted_result'] = "검출된 객체가 없습니다."
                    else:
                        # 이미지의 경우 기존 로직 유지 (objects 배열 파싱)
                        objects = result_json.get('objects', [])
                        if not objects:
                            formatted_text = "검출된 객체가 없습니다."
                        else:
                            lines = [f"[{i}] {obj['label']} (신뢰도: {obj['score'] * 100:.1f}%)"
                                     for i, obj in enumerate(objects, 1)]
                            formatted_text = "\n".join(lines)
                        analysis_data['formatted_result'] = formatted_text
                except Exception:
                    analysis_data['formatted_result'] = "결과 포맷팅 중 오류 발생"

    finally:
        conn.close()

    if not analysis_data:
        # URL에 해당하는 분석 데이터가 없거나 다른 사용자의 데이터일 경우,
        # 접근을 차단하여 정보 보안을 유지합니다.
        return "분석 데이터를 찾을 수 없거나 접근 권한이 없습니다.", 404

    return render_template('analyze_analysis.html', analysis_data=analysis_data)


"""
@app.route('/media/update/<int:media_id>', methods=['POST'])
def file_update(media_id):
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Login required"}), 401
    new_file = request.files.get('file')

    if not new_file or new_file.filename == '':
        return jsonify({"status": "error", "message": "파일 교체를 실패하였습니다"}), 400

    success = False
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql_select = "SELECT stored_path FROM media_files WHERE id = %s AND member_id = %s"
            cursor.execute(sql_select, (media_id, session['user_id']))
            old_row = cursor.fetchone()
            if old_row:
                old_file_path = old_row['stored_path']
                new_safe_filename = secure_filename(new_file.filename)
                new_filename = f"{uuid.uuid4().hex}_{new_safe_filename}"
                new_stored_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                new_file.save(new_stored_path)
                file_type = 'IMAGE' if new_filename.split('.')[-1].lower() in ['jpg', 'jpeg', 'png', 'gif'] else 'VIDEO'
                sql_update_file = "UPDATE media_files SET file_name = %s, stored_path = %s, file_type = %s WHERE id = %s AND member_id = %s"
                cursor.execute(sql_update_file, (new_filename, new_stored_path, file_type, media_id, session['user_id']))
                sql_reset_analysis = "UPDATE analysis_results SET status = 'PENDING', result_json = NULL WHERE media_id = %s"
                cursor.execute(sql_reset_analysis, (media_id,))
                conn.commit()
                if old_file_path != new_stored_path and os.path.exists(old_file_path):
                    os.remove(old_file_path)
                thread = threading.Thread(target=execute_ai_analysis, args=(media_id,), daemon=True)
                thread.start()
                success = True
    except Exception as e:
        conn.rollback()
        print(f"파일 교체 중 오류 발생: {e}")
    finally:
        conn.close()

    if success:
        return jsonify({"status": "success", "message": "파일이 교체되어 다시 분석을 시작합니다."})
    else:
        return jsonify({"status": "error", "message": "파일 교체를 실패하였습니다"}), 400
"""


@app.route('/media/delete/<int:media_id>', methods=['POST'])
def delete_media_file(media_id):
    if 'user_id' not in session:
        return "<script>alert('로그인이 필요한 서비스입니다.'); location.href='/login';</script>"

    success = False
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 원본 파일 경로와 AI 분석 결과로 생성된 파생 파일 경로를 모두 조회하기 위해 JOIN 수행
            # 유령 파일(하드디스크에 남는 파일)을 방지하기 위함
            sql_select = """
                SELECT m.stored_path, r.result_json 
                FROM media_files m 
                LEFT JOIN analysis_results r ON m.id = r.media_id 
                WHERE m.id = %s AND m.member_id = %s
            """
            cursor.execute(sql_select, (media_id, session['user_id']))
            row = cursor.fetchone()

            if row:
                file_paths_to_delete = []

                # 1. 원본 미디어 파일 경로 추가
                if row.get('stored_path'):
                    file_paths_to_delete.append(os.path.abspath(row['stored_path']))

                # 2. 파생 파일 (AI 분석 결과 비디오 등) 경로 추출 및 추가
                if row.get('result_json'):
                    try:
                        result_data = json.loads(row['result_json']) if isinstance(row['result_json'], str) else row[
                            'result_json']
                        # process_video_yolo 등에서 생성하여 result_json에 저장한 파일명 키 확인
                        for key in ['processed_video_path', 'processed_image_path']:
                            if key in result_data and result_data[key]:
                                processed_filename = result_data[key]
                                processed_path = os.path.abspath(
                                    os.path.join(app.config['UPLOAD_FOLDER'], processed_filename))
                                file_paths_to_delete.append(processed_path)
                    except Exception as e:
                        print(f"[{media_id}] result_json 파싱 중 오류 발생 (파생 파일 확인 불가): {e}")

                # 3. 데이터베이스 레코드 삭제 (외래키 제약조건이 없으므로 자식 테이블부터 삭제)
                cursor.execute("DELETE FROM analysis_results WHERE media_id = %s", (media_id,))
                cursor.execute("DELETE FROM media_files WHERE id = %s AND member_id = %s",
                               (media_id, session['user_id']))
                conn.commit()

                # 4. 수집된 모든 파일들을 서버 파일 시스템에서 일괄 삭제 (예외 처리 포함)
                for f_path in file_paths_to_delete:
                    if os.path.exists(f_path):
                        try:
                            os.remove(f_path)
                        except OSError as e:
                            print(f"[경고] 파일 삭제 실패 ({f_path}): {e}")

                success = True
    except Exception as e:
        conn.rollback()
        print(f"파일 삭제 오류: {e}")
    finally:
        conn.close()

    if success:
        return "<script>alert('파일과 분석 결과가 서버에서 완전히 삭제되었습니다.'); location.href='/analyze/list';</script>"
    else:
        return "<script>alert('삭제 권한이 없거나 이미 존재하지 않는 파일입니다.'); history.back();</script>"


@app.route('/analyze/list')
def analyze_list():
    user_id = session.get('user_id')
    analysis_list_data = []
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    m.id, m.stored_path, m.file_type, m.memo, m.uploaded_at,
                    r.id AS analysis_id, r.status, r.result_json
                FROM media_files m
                LEFT JOIN analysis_results r ON m.id = r.media_id
                WHERE m.member_id = %s
                ORDER BY m.id DESC
            """
            cursor.execute(sql, (user_id,))
            rows = cursor.fetchall()
            # 이제 rows는 dict의 리스트이므로 그대로 사용
            analysis_list_data = rows
    finally:
        conn.close()
    return render_template('analyze_list.html', analyze_list=analysis_list_data)



@app.route('/board/list')
def board_list():
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 게시글 정보와 작성자 이름을 함께 JOIN하여 가져옴
            sql = """
                SELECT b.id, b.title, b.regdate, b.readcount, m.name as writer_name 
                FROM boards b
                JOIN members m ON b.member_id = m.id
                ORDER BY b.id DESC
            """
            cursor.execute(sql)
            rows = cursor.fetchall()
            return render_template('board_list.html', boards=rows)
    except Exception as e:
        print(f"게시판 목록 오류: {e}")
        return "<script>alert('게시판 목록을 불러오는 중 오류가 발생했습니다.'); history.back();</script>"
    finally:
        conn.close()


@app.route('/board/write', methods=['GET'])
def board_write():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('board_write.html')


@app.route('/board/write_pro', methods=['POST'])
def board_write_pro():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    title = request.form.get('title')
    content = request.form.get('content')
    member_id = session['user_id']
    
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO boards (member_id, title, content) VALUES (%s, %s, %s)"
            cursor.execute(sql, (member_id, title, content))
            conn.commit()
            return redirect(url_for('board_list'))
    except Exception as e:
        conn.rollback()
        print(f"게시글 작성 오류: {e}")
        return "<script>alert('글을 저장하는 중 오류가 발생했습니다.'); history.back();</script>"
    finally:
        conn.close()


@app.route('/board/view/<int:board_id>')
def board_view(board_id):
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 조회수 증가
            update_sql = "UPDATE boards SET readcount = readcount + 1 WHERE id = %s"
            cursor.execute(update_sql, (board_id,))
            conn.commit()
            
            # 게시글 상세 내용 가져오기
            select_sql = """
                SELECT b.*, m.name as writer_name 
                FROM boards b
                JOIN members m ON b.member_id = m.id
                WHERE b.id = %s
            """
            cursor.execute(select_sql, (board_id,))
            board = cursor.fetchone()
            
            if board:
                return render_template('board_view.html', board=board, comments=[])
            else:
                return "<script>alert('존재하지 않는 게시글입니다.'); location.href='/board/list';</script>"
    except Exception as e:
        print(f"게시글 조회 오류: {e}")
        return "<script>alert('글을 불러오는 중 오류가 발생했습니다.'); history.back();</script>"
    finally:
        conn.close()


@app.route('/board/edit/<int:board_id>')
def board_edit(board_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM boards WHERE id = %s"
            cursor.execute(sql, (board_id,))
            board = cursor.fetchone()
            
            if not board:
                return "<script>alert('게시글을 찾을 수 없습니다.'); location.href='/board/list';</script>"
                
            if board['member_id'] != session['user_id']:
                return "<script>alert('수정 권한이 없습니다.'); history.back();</script>"
                
            return render_template('board_edit.html', board=board)
    finally:
        conn.close()


@app.route('/board/edit_pro', methods=['POST'])
def board_edit_pro():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    board_id = request.form.get('id')
    title = request.form.get('title')
    content = request.form.get('content')
    
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 작성자 본인인지 2차 확인
            cursor.execute("SELECT member_id FROM boards WHERE id = %s", (board_id,))
            board = cursor.fetchone()
            
            if not board or board['member_id'] != session['user_id']:
                return "<script>alert('수정 권한이 없습니다.'); history.back();</script>"
                
            sql = "UPDATE boards SET title = %s, content = %s WHERE id = %s"
            cursor.execute(sql, (title, content, board_id))
            conn.commit()
            
            return f"<script>alert('정상적으로 수정되었습니다.'); location.href='/board/view/{board_id}';</script>"
    except Exception as e:
        conn.rollback()
        print(f"게시글 수정 오류: {e}")
        return "<script>alert('수정 중 오류가 발생했습니다.'); history.back();</script>"
    finally:
        conn.close()


@app.route('/board/delete/<int:board_id>')
def board_delete(board_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 권한 체크
            cursor.execute("SELECT member_id FROM boards WHERE id = %s", (board_id,))
            board = cursor.fetchone()
            
            if not board or board['member_id'] != session['user_id']:
                return "<script>alert('삭제 권한이 없습니다.'); history.back();</script>"
                
            cursor.execute("DELETE FROM boards WHERE id = %s", (board_id,))
            conn.commit()
            
            return "<script>alert('게시글이 삭제되었습니다.'); location.href='/board/list';</script>"
    except Exception as e:
        conn.rollback()
        print(f"게시글 삭제 오류: {e}")
        return "<script>alert('삭제 중 오류가 발생했습니다.'); history.back();</script>"
    finally:
        conn.close()


# ===============================================
# Admin Routes
# ===============================================

def admin_required():
    """관리자 권한 확인 헬퍼 함수. 권한 없으면 리다이렉트 응답 반환, 정상이면 None 반환."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('user_role') != 'admin':
        return "<script>alert('관리자만 접근할 수 있습니다.'); history.back();</script>"
    return None


@app.route('/admin/members')
def admin_members():
    guard = admin_required()
    if guard:
        return guard

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 비밀번호(password) 컬럼 제외하고 조회
            cursor.execute("""
                SELECT id, uid, name, email, role, active, bio, profile_image
                FROM members
                ORDER BY id DESC
            """)
            members = cursor.fetchall()
    finally:
        conn.close()
    return render_template('admin_members.html', members=members)


@app.route('/admin/boards')
def admin_boards():
    guard = admin_required()
    if guard:
        return guard

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT b.id, b.title, b.content, b.readcount, b.regdate,
                       m.name AS writer_name, m.uid AS writer_uid
                FROM boards b
                JOIN members m ON b.member_id = m.id
                ORDER BY b.id DESC
            """)
            boards = cursor.fetchall()
    finally:
        conn.close()
    return render_template('admin_boards.html', boards=boards)


@app.route('/admin/analyze')
def admin_analyze():
    guard = admin_required()
    if guard:
        return guard

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    mf.id, mf.file_name, mf.file_type, mf.memo, mf.uploaded_at, mf.stored_path,
                    ar.status, ar.result_json,
                    m.name AS uploader_name, m.uid AS uploader_uid
                FROM media_files mf
                LEFT JOIN analysis_results ar ON mf.id = ar.media_id
                JOIN members m ON mf.member_id = m.id
                ORDER BY mf.id DESC
            """)
            analyze_list = cursor.fetchall()
    finally:
        conn.close()
    return render_template('admin_analyze.html', analyze_list=analyze_list)


@app.route('/introduce')
def introduce():
    return render_template('introduce.html')


@app.route('/')
def index():
    return render_template('main.html')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """
    정적 파일이 아닌 'uploads' 디렉토리의 파일을 동적으로 제공하기 위한 라우트입니다.
    이 함수를 통해 템플릿에서 '/uploads/파일명' 형태로 미디어 파일에 접근할 수 있게 됩니다.
    보안을 위해 send_from_directory 함수를 사용하여 안전하게 파일만 제공합니다.
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

