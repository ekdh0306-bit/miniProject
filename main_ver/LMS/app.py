import os
import json
import uuid
import secrets
import time
import cv2  # 비디오 처리를 위한 OpenCV 임포트. 프레임 단위 처리 및 바운딩 박스 그리기에 사용됨.
from ultralytics import YOLO  # YOLOv8 모델 임포트. 객체 탐지에 사용됨.
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, url_for, redirect, session, jsonify, send_from_directory
from dotenv import load_dotenv
from supabase_auth.errors import AuthApiError

from common.Session import Session
from common.SupabaseClient import (
    SupabaseConfigurationError,
    create_admin_client,
    create_public_client,
)

load_dotenv(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env.local'),
    override=True,
)

app = Flask(__name__)
configured_flask_secret = os.environ.get('FLASK_SECRET_KEY')
if not configured_flask_secret:
    os.makedirs(app.instance_path, exist_ok=True)
    local_secret_path = os.path.join(app.instance_path, 'flask-secret')
    try:
        with open(local_secret_path, 'x', encoding='utf-8') as secret_file:
            secret_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    with open(local_secret_path, encoding='utf-8') as secret_file:
        configured_flask_secret = secret_file.read().strip()
    app.logger.warning(
        'FLASK_SECRET_KEY is not configured; using the persistent local '
        'development key from the ignored instance directory.'
    )
app.config['SECRET_KEY'] = configured_flask_secret
app.config['SESSION_COOKIE_NAME'] = 'safecar_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_PATH'] = '/'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_IMAGE_SIZE'] = 20 * 1024 * 1024
app.config['MAX_VIDEO_SIZE'] = 500 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024


@app.before_request
def use_canonical_localhost():
    """Keep local session cookies on one host during development."""
    host_name, separator, port = request.host.partition(':')
    if host_name.lower() != 'localhost':
        return None

    canonical_host = '127.0.0.1'
    if separator and port:
        canonical_host = f'{canonical_host}:{port}'
    path = request.full_path
    if path.endswith('?'):
        path = path[:-1]
    return redirect(f'{request.scheme}://{canonical_host}{path}', code=302)


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


def get_auth_profile(user_id):
    response = (
        create_admin_client()
        .table('profiles')
        .select('id, uid, name, role, active, bio, profile_image_path, login_email')
        .eq('id', str(user_id))
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    profile = response.data[0]
    profile['profile_image'] = profile.get('profile_image_path')
    profile['email'] = profile.pop('login_email', None)
    return profile


def normalize_auth_user_id(user_id):
    try:
        return str(uuid.UUID(str(user_id)))
    except (TypeError, ValueError, AttributeError):
        return None


def ensure_session_secret():
    if not app.config.get('SECRET_KEY'):
        raise SupabaseConfigurationError(
            '서버 환경변수 FLASK_SECRET_KEY 설정이 필요합니다.'
        )


def is_auth_email_rate_limit(error):
    status = getattr(error, 'status', None)
    code = str(getattr(error, 'code', '') or '')
    message = str(getattr(error, 'message', '') or '').lower()
    return (
        str(status) == '429'
        or 'rate_limit' in code
        or 'rate' in code
        or 'rate limit' in message
    )


def can_use_local_signup_fallback():
    return request.remote_addr in {'127.0.0.1', '::1'}


def create_local_confirmed_auth_user(email, password, uid, name):
    response = create_admin_client().auth.admin.create_user({
        'email': email,
        'password': password,
        'email_confirm': True,
        'user_metadata': {
            'uid': uid,
            'name': name,
        },
    })
    if not response.user:
        raise RuntimeError('Supabase Admin API did not return a user')
    return response.user


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


def upload_analysis_to_supabase(file, user_id, config, memo=None):
    owner_id = normalize_auth_user_id(user_id)
    if not owner_id:
        raise ValueError("로그인 정보가 올바르지 않습니다. 다시 로그인해 주세요.")

    filename = secure_filename(file.filename)
    if not filename:
        raise ValueError("올바른 파일을 선택해 주세요.")
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    extension = filename.rsplit('.', 1)[-1].lower()
    is_image = extension in ['jpg', 'jpeg', 'png', 'gif']
    file_type = 'IMAGE' if is_image else 'VIDEO'
    limit = config.get('MAX_IMAGE_SIZE') if is_image else config.get('MAX_VIDEO_SIZE')
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > limit:
        limit_mb = limit // (1024 * 1024)
        raise ValueError(f"{file_type} 파일은 {limit_mb}MB를 초과할 수 없습니다.")

    storage_path = f"{owner_id}/{unique_filename}"
    admin = create_admin_client()
    storage = admin.storage.from_('analysis-media')
    uploaded = False
    try:
        storage.upload(
            storage_path,
            file.read(),
            {
                'content-type': file.mimetype or 'application/octet-stream',
                'upsert': 'false',
            },
        )
        uploaded = True
        media_response = admin.table('media_files').insert({
            'owner_id': owner_id,
            'original_name': filename,
            'storage_path': storage_path,
            'file_type': file_type,
            'memo': (memo or '').strip() or None,
        }).execute()
        if not media_response.data:
            raise RuntimeError('media_files insert returned no row')
        media_id = media_response.data[0]['id']

        status = 'PENDING' if yolo_model is not None else 'UNAVAILABLE'
        result_json = None
        if status == 'UNAVAILABLE':
            result_json = {
                'message': '현재 로컬 환경에서 AI 분석 기능을 사용할 수 없습니다.'
            }
        admin.table('analysis_results').insert({
            'media_id': media_id,
            'status': status,
            'result_json': result_json,
        }).execute()
        return media_id
    except Exception:
        if uploaded:
            try:
                storage.remove([storage_path])
            except Exception as cleanup_error:
                app.logger.warning(
                    'Analysis upload cleanup failed: type=%s',
                    type(cleanup_error).__name__,
                )
        raise


def mediafile_uploads(file, user_id, upload_folder, config, memo=None):
    return upload_analysis_to_supabase(file, user_id, config, memo)

    # Legacy MySQL/local-file implementation retained below for reference only.
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

    uid = (request.form.get('uid') or '').strip()
    password = request.form.get('pw')
    confirm_password = request.form.get('confirm_password')
    name = (request.form.get('username') or '').strip()
    email = (request.form.get('email') or '').strip().lower()

    if not uid or not password or not name or not email:
        return "<script>alert('필수 정보를 모두 입력해주세요.'); history.back();</script>"

    if password != confirm_password:
        return "<script>alert('비밀번호 확인이 일치하지 않습니다.'); history.back();</script>"

    try:
        profile_response = (
            create_admin_client()
            .table('profiles')
            .select('id')
            .eq('uid', uid)
            .limit(1)
            .execute()
        )
        if profile_response.data:
            return "<script>alert('이미 존재하는 아이디 입니다.'); history.back();</script>"

        auth_response = create_public_client().auth.sign_up({
            'email': email,
            'password': password,
            'options': {
                'data': {
                    'uid': uid,
                    'name': name,
                }
            },
        })
        if not auth_response.user:
            raise RuntimeError('Supabase Auth did not return a user')

        return (
            "<script>alert('회원가입이 완료 되었습니다. "
            "이메일 인증이 필요한 경우 인증 후 로그인해주세요.'); "
            "location.href='/login';</script>"
        )
    except SupabaseConfigurationError:
        app.logger.error('Supabase authentication environment is not configured.')
        return "<script>alert('인증 서버 설정이 필요합니다.'); history.back();</script>"
    except AuthApiError as exc:
        status = getattr(exc, 'status', None)
        code = str(getattr(exc, 'code', '') or '')
        internal_message = str(getattr(exc, 'message', '') or '').lower()
        app.logger.warning(
            'Supabase signup rejected: status=%s code=%s',
            status,
            code,
        )

        if is_auth_email_rate_limit(exc) and can_use_local_signup_fallback():
            try:
                create_local_confirmed_auth_user(
                    email,
                    password,
                    uid,
                    name,
                )
                app.logger.info(
                    'Local signup completed through the rate-limit fallback.'
                )
                return (
                    "<script>alert('회원가입이 완료 되었습니다.'); "
                    "location.href='/login';</script>"
                )
            except Exception as fallback_error:
                app.logger.warning(
                    'Local signup fallback failed: %s',
                    type(fallback_error).__name__,
                )
                return (
                    "<script>alert('로컬 회원가입을 처리할 수 없습니다.'); "
                    "history.back();</script>"
                )

        if is_auth_email_rate_limit(exc):
            message = '가입 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.'
        elif (
            code in {'email_exists', 'user_already_exists'}
            or 'already registered' in internal_message
            or 'already exists' in internal_message
        ):
            message = '이미 가입된 이메일입니다.'
        elif 'weak_password' in code or 'password' in internal_message:
            message = '비밀번호 보안 기준을 충족하지 않습니다.'
        elif 'signup_disabled' in code:
            message = '현재 신규 회원가입이 비활성화되어 있습니다.'
        elif 'database' in code or 'database' in internal_message:
            message = '회원정보 생성 설정을 확인해야 합니다.'
        else:
            message = '회원가입을 처리할 수 없습니다. 잠시 후 다시 시도해 주세요.'

        return f"<script>alert('{message}'); history.back();</script>"
    except Exception as exc:
        app.logger.warning('Supabase signup failed: %s', type(exc).__name__)
        return (
            "<script>alert('회원가입을 처리할 수 없습니다. 잠시 후 다시 시도해 주세요.'); "
            "history.back();</script>"
        )


@app.route('/check_uid')  # /check_uid URL로 접속하면 이 함수 실행 GET방식으로 요청 받음
def check_uid():
    uid = (request.args.get('uid') or '').strip()
    if not uid:
        return {"error": "아이디를 입력해 주세요."}, 400
    try:
        response = (
            create_admin_client()
            .table('profiles')
            .select('id')
            .eq('uid', uid)
            .limit(1)
            .execute()
        )
        return {"exists": bool(response.data)}
    except SupabaseConfigurationError:
        app.logger.error('Supabase authentication environment is not configured.')
        return {"error": "인증 서버 설정이 필요합니다."}, 503
    except Exception as exc:
        app.logger.warning('Supabase UID check failed: %s', type(exc).__name__)
        return {"error": "아이디 확인을 처리할 수 없습니다."}, 503


@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    uid = (request.form.get('uid') or '').strip()
    upw = request.form.get('pw') or ''
    try:
        ensure_session_secret()
        admin_client = create_admin_client()
        profile_response = (
            admin_client
            .table('profiles')
            .select('id, uid, name, role, active, login_email')
            .eq('uid', uid)
            .limit(1)
            .execute()
        )
        profile = profile_response.data[0] if profile_response.data else None
        recovered_profile = False
        if not profile:
            auth_users = admin_client.auth.admin.list_users(
                page=1,
                per_page=1000,
            )
            matching_user = next(
                (
                    auth_user
                    for auth_user in auth_users
                    if str((auth_user.user_metadata or {}).get('uid', '')).strip()
                    == uid
                ),
                None,
            )
            if matching_user and matching_user.email:
                metadata = matching_user.user_metadata or {}
                profile = {
                    'id': str(matching_user.id),
                    'uid': uid,
                    'name': str(metadata.get('name') or uid)[:50],
                    'role': 'user',
                    'active': True,
                    'login_email': matching_user.email,
                }
                recovered_profile = True

        if not profile:
            return (
                "<script>alert('로그인 계정 정보를 찾지 못했습니다. "
                "회원가입한 아이디를 확인해 주세요. [LOGIN-01]'); "
                "history.back();</script>"
            )

        if not profile.get('active', True):
            return (
                "<script>alert('현재 비활성화된 계정입니다. [LOGIN-02]'); "
                "history.back();</script>"
            )

        auth_user_lookup = admin_client.auth.admin.get_user_by_id(
            str(profile['id'])
        )
        auth_user = getattr(auth_user_lookup, 'user', None)
        if not auth_user or not auth_user.email:
            return (
                "<script>alert('인증 계정 정보를 찾지 못했습니다. "
                "[LOGIN-10]'); history.back();</script>"
            )
        profile['login_email'] = auth_user.email

        auth_response = create_public_client().auth.sign_in_with_password({
            'email': profile['login_email'],
            'password': upw,
        })
        if not auth_response.user or str(auth_response.user.id) != str(profile['id']):
            return (
                "<script>alert('아이디 또는 비밀번호가 일치하지 않습니다. "
                "[LOGIN-03]'); history.back();</script>"
            )

        session.clear()
        session['user_id'] = str(auth_response.user.id)
        session['user_name'] = profile['name']
        session['user_email'] = auth_response.user.email
        session['user_uid'] = profile['uid']
        session['user_role'] = profile['role']
        session.modified = True

        if recovered_profile:
            try:
                admin_client.table('profiles').upsert(
                    profile,
                    on_conflict='id',
                ).execute()
            except Exception as profile_error:
                app.logger.warning(
                    'Authenticated user profile recovery failed: type=%s code=%s',
                    type(profile_error).__name__,
                    str(getattr(profile_error, 'code', '') or 'none'),
                )

        return redirect(url_for('index'))
    except SupabaseConfigurationError:
        app.logger.error('Supabase authentication environment is not configured.')
        return render_template(
            'login.html',
            error="인증 서버 설정이 필요합니다. [LOGIN-04]",
        )
    except AuthApiError as exc:
        code = str(getattr(exc, 'code', '') or '')
        status = str(getattr(exc, 'status', '') or '')
        internal_message = str(getattr(exc, 'message', '') or '').lower()
        app.logger.warning(
            'Supabase login rejected: status=%s code=%s',
            status or 'none',
            code or 'none',
        )
        if (
            code == 'email_not_confirmed'
            or 'email not confirmed' in internal_message
        ):
            message = '이메일 인증이 완료되지 않았습니다. [LOGIN-05]'
        elif (
            code in {'invalid_credentials', 'user_not_found'}
            or 'invalid login credentials' in internal_message
            or 'invalid credentials' in internal_message
        ):
            message = '아이디 또는 비밀번호가 일치하지 않습니다. [LOGIN-06]'
        elif is_auth_email_rate_limit(exc):
            message = '로그인 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요. [LOGIN-07]'
        else:
            message = '인증 서버가 로그인을 거부했습니다. [LOGIN-08]'
        return f"<script>alert('{message}'); history.back();</script>"
    except Exception as exc:
        app.logger.warning(
            'Supabase login failed: type=%s code=%s',
            type(exc).__name__,
            str(getattr(exc, 'code', '') or 'none'),
        )
        return (
            "<script>alert('로그인 처리 중 서버 오류가 발생했습니다. "
            "[LOGIN-09]'); history.back();</script>"
        )


@app.route('/find_id', methods=['GET', 'POST'])
def find_id():
    if request.method == 'GET':
        return render_template("find_id.html")

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()

    if not name or not email or len(name) > 50 or len(email) > 254:
        return jsonify({"success": False, "message": "일치하는 계정이 없습니다."})

    try:
        response = (
            create_admin_client()
            .table('profiles')
            .select('uid')
            .eq('name', name)
            .eq('login_email', email)
            .limit(1)
            .execute()
        )
        if response.data:
            return jsonify({"success": True, "uid": response.data[0]["uid"]})
        return jsonify({"success": False, "message": "일치하는 계정이 없습니다."})
    except SupabaseConfigurationError:
        app.logger.error('Supabase authentication environment is not configured.')
    except Exception as exc:
        app.logger.warning('Supabase find-ID failed: %s', type(exc).__name__)
    return jsonify({"success": False, "message": "아이디 찾기를 처리할 수 없습니다."}), 503


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/member/edit', methods=['GET', 'POST'])
def member_edit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = normalize_auth_user_id(session.get('user_id'))
    if not user_id:
        session.clear()
        return redirect(url_for('login'))

    try:
        user_info = get_auth_profile(user_id)
        if not user_info or not user_info.get('active', True):
            session.clear()
            return redirect(url_for('login'))

        if request.method == 'GET':
            return render_template('member_edit.html', user=user_info)

        submitted_name = (request.form.get('new_name') or '').strip()
        new_name = submitted_name or user_info['name']
        new_bio = (request.form.get('bio') or '').strip()

        if not new_name or len(new_name) > 50:
            return "<script>alert('이름은 1자 이상 50자 이하로 입력해주세요.'); history.back();</script>"
        if len(new_bio) > 255:
            return "<script>alert('한 줄 소개는 255자 이하로 입력해주세요.'); history.back();</script>"

        response = (
            create_admin_client()
            .table('profiles')
            .update({'name': new_name, 'bio': new_bio})
            .eq('id', user_id)
            .execute()
        )
        if not response.data:
            raise RuntimeError('Profile update returned no row')

        session['user_name'] = new_name
        return "<script>alert('회원정보 수정을 완료했습니다.'); location.href = '/mypage';</script>"
    except SupabaseConfigurationError:
        app.logger.error('Supabase authentication environment is not configured.')
    except Exception as exc:
        app.logger.warning('Supabase profile update failed: %s', type(exc).__name__)
    return "<script>alert('수정 도중 오류가 발생했습니다.'); history.back();</script>", 503


@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    try:
        user_info = get_auth_profile(user_id)
    except Exception as exc:
        app.logger.warning('Supabase profile lookup failed: %s', type(exc).__name__)
        session.clear()
        return redirect(url_for('login'))

    if not user_info or not user_info.get('active', True):
        session.clear()
        return redirect(url_for('login'))

    # Analysis records remain on MySQL until the dedicated migration phase.
    return render_template('mypage.html', user=user_info, analysis_results=[])


def render_member_delete(error=None, status=200):
    csrf_token = secrets.token_urlsafe(32)
    session['member_delete_csrf'] = csrf_token
    return render_template(
        'member_delete.html',
        csrf_token=csrf_token,
        error=error,
    ), status


@app.route('/member/delete', methods=['GET', 'POST'])
def member_delete_route():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = normalize_auth_user_id(session.get('user_id'))
    if not user_id:
        session.clear()
        return redirect(url_for('login'))

    if request.method == 'GET':
        return render_member_delete()

    submitted_csrf = request.form.get('csrf_token') or ''
    expected_csrf = session.pop('member_delete_csrf', '')
    if (
        not submitted_csrf
        or not expected_csrf
        or not secrets.compare_digest(submitted_csrf, expected_csrf)
    ):
        return render_member_delete(
            '요청을 확인할 수 없습니다. 다시 시도해 주세요.',
            400,
        )

    password = request.form.get('password') or ''
    confirmed = request.form.get('confirm_delete') == 'on'
    if not password:
        return render_member_delete('현재 비밀번호를 입력해 주세요.', 400)
    if not confirmed:
        return render_member_delete('탈퇴 안내 확인이 필요합니다.', 400)

    try:
        profile = get_auth_profile(user_id)
        if not profile or not profile.get('active', True) or not profile.get('email'):
            return render_member_delete('회원탈퇴를 처리할 수 없습니다.', 400)

        auth_response = create_public_client().auth.sign_in_with_password({
            'email': profile['email'],
            'password': password,
        })
        if (
            not auth_response.user
            or str(auth_response.user.id) != user_id
        ):
            return render_member_delete('현재 비밀번호를 확인해 주세요.', 400)

        admin_client = create_admin_client()
        admin_client.auth.admin.delete_user(user_id)
    except SupabaseConfigurationError:
        app.logger.error('Supabase authentication environment is not configured.')
    except Exception as exc:
        app.logger.warning('Supabase account deletion failed: %s', type(exc).__name__)
    else:
        # Auth deletion is the account-deletion commit point. Never retain or
        # recreate the authenticated Flask session after this point.
        session.clear()

        cascade_confirmed = False
        cascade_checked = False
        try:
            for attempt in range(2):
                remaining = (
                    admin_client
                    .table('profiles')
                    .select('id')
                    .eq('id', user_id)
                    .limit(1)
                    .execute()
                )
                cascade_checked = True
                if not remaining.data:
                    cascade_confirmed = True
                    break
                if attempt == 0:
                    time.sleep(0.15)
        except Exception as exc:
            app.logger.warning(
                'Supabase profile cascade verification unavailable: %s',
                type(exc).__name__,
            )

        if cascade_checked and not cascade_confirmed:
            app.logger.warning(
                'Supabase profile row remained after Auth user deletion.'
            )

        return "<script>alert('회원탈퇴가 완료되었습니다.'); location.href='/';</script>"

    return render_member_delete('현재 비밀번호를 확인해 주세요.', 400)


@app.route('/member/delete/<user_id>', methods=['GET'])
def legacy_member_delete_route(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('member_delete_route'))


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

def render_supabase_analysis_detail(media_id):
    user_id = normalize_auth_user_id(session.get('user_id'))
    normalized_media_id = normalize_auth_user_id(media_id)
    if not user_id:
        session.clear()
        return redirect(url_for('login'))
    if not normalized_media_id:
        return "분석 데이터를 찾을 수 없습니다.", 404
    try:
        admin = create_admin_client()
        query = admin.table('media_files').select(
            'id, owner_id, storage_path, file_type, memo, uploaded_at'
        ).eq('id', normalized_media_id)
        if session.get('user_role') != 'admin':
            query = query.eq('owner_id', user_id)
        media_response = query.limit(1).execute()
        if not media_response.data:
            return "분석 데이터를 찾을 수 없거나 접근 권한이 없습니다.", 404
        analysis_data = media_response.data[0]
        result_response = admin.table('analysis_results').select(
            'status, result_json'
        ).eq('media_id', normalized_media_id).limit(1).execute()
        analysis_data.update(
            result_response.data[0] if result_response.data else {}
        )
        signed = admin.storage.from_('analysis-media').create_signed_url(
            analysis_data['storage_path'], 3600
        )
        analysis_data['media_url'] = (
            signed.get('signedURL')
            or signed.get('signedUrl')
            or signed.get('signed_url')
        )
        result_json = analysis_data.get('result_json') or {}
        if analysis_data.get('status') == 'UNAVAILABLE':
            analysis_data['formatted_result'] = result_json.get(
                'message',
                '현재 로컬 환경에서 AI 분석 기능을 사용할 수 없습니다.',
            )
        else:
            objects = result_json.get('objects', [])
            analysis_data['formatted_result'] = (
                '\n'.join(
                    f"[{index}] {item.get('label', '객체')} "
                    f"(신뢰도: {float(item.get('score', 0)) * 100:.1f}%)"
                    for index, item in enumerate(objects, 1)
                )
                if objects else '분석 결과가 없거나 처리 중입니다.'
            )
        return render_template('analyze_analysis.html', analysis_data=analysis_data)
    except Exception as exc:
        app.logger.warning(
            'Supabase analysis detail failed: type=%s code=%s',
            type(exc).__name__,
            str(getattr(exc, 'code', '') or 'none'),
        )
        return "분석 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.", 503


@app.route('/analyze/analysis/<media_id>')
def analysis_detail(media_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_supabase_analysis_detail(media_id)

    conn = Session.get_connection()
    analysis_data = None
    try:
        with conn.cursor() as cursor:
            # media_files와 analysis_results 테이블을 조인하여 필요한 정보를 가져옵니다.
            # 이 쿼리는 특정 사용자의 특정 미디어 ID에 대한 모든 정보를 안전하게 조회합니다.
            if session.get('user_role') == 'admin':
                sql = """
                    SELECT
                        m.stored_path, m.file_type, m.memo,
                        r.status, r.result_json
                    FROM media_files m
                    LEFT JOIN analysis_results r ON m.id = r.media_id
                    WHERE m.id = %s
                """
                cursor.execute(sql, (media_id,))
            else:
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


def delete_supabase_analysis(media_id):
    user_id = normalize_auth_user_id(session.get('user_id'))
    normalized_media_id = normalize_auth_user_id(media_id)
    if not user_id:
        session.clear()
        return redirect(url_for('login'))
    if not normalized_media_id:
        return "<script>alert('삭제할 분석 기록을 찾을 수 없습니다.'); history.back();</script>", 404
    try:
        admin = create_admin_client()
        response = admin.table('media_files').select(
            'id, storage_path'
        ).eq('id', normalized_media_id).eq(
            'owner_id', user_id
        ).limit(1).execute()
        if not response.data:
            return "<script>alert('삭제 권한이 없거나 기록이 존재하지 않습니다.'); history.back();</script>", 404
        storage_path = response.data[0]['storage_path']
        admin.storage.from_('analysis-media').remove([storage_path])
        admin.table('media_files').delete().eq(
            'id', normalized_media_id
        ).eq('owner_id', user_id).execute()
        return "<script>alert('분석 기록과 업로드 파일을 삭제했습니다.'); location.href='/analyze/list';</script>"
    except Exception as exc:
        app.logger.warning(
            'Supabase analysis delete failed: type=%s code=%s',
            type(exc).__name__,
            str(getattr(exc, 'code', '') or 'none'),
        )
        return "<script>alert('분석 기록을 삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.'); history.back();</script>", 503


@app.route('/media/delete/<media_id>', methods=['POST'])
def delete_media_file(media_id):
    return delete_supabase_analysis(media_id)

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
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = normalize_auth_user_id(session.get('user_id'))
    if not user_id:
        session.clear()
        return redirect(url_for('login'))

    try:
        admin = create_admin_client()
        media_response = admin.table('media_files').select(
            'id, storage_path, file_type, memo, uploaded_at'
        ).eq('owner_id', user_id).order('uploaded_at', desc=True).execute()
        media_rows = media_response.data or []
        media_ids = [row['id'] for row in media_rows]
        results_by_media = {}
        if media_ids:
            result_response = admin.table('analysis_results').select(
                'id, media_id, status, result_json'
            ).in_('media_id', media_ids).execute()
            results_by_media = {
                row['media_id']: row for row in (result_response.data or [])
            }

        analysis_list_data = []
        storage = admin.storage.from_('analysis-media')
        for row in media_rows:
            result = results_by_media.get(row['id'], {})
            signed = storage.create_signed_url(row['storage_path'], 3600)
            media_url = (
                signed.get('signedURL')
                or signed.get('signedUrl')
                or signed.get('signed_url')
            )
            analysis_list_data.append({
                'id': row['id'],
                'stored_path': row['storage_path'],
                'media_url': media_url,
                'file_type': row['file_type'],
                'memo': row.get('memo'),
                'uploaded_at': row.get('uploaded_at'),
                'analysis_id': result.get('id'),
                'status': result.get('status', 'PENDING'),
                'result_json': result.get('result_json'),
            })
        return render_template(
            'analyze_list.html',
            analyze_list=analysis_list_data,
        )
    except Exception as exc:
        app.logger.warning(
            'Supabase analysis list failed: type=%s code=%s',
            type(exc).__name__,
            str(getattr(exc, 'code', '') or 'none'),
        )
        return render_template(
            'analyze_list.html',
            analyze_list=[],
            analysis_error='분석 게시판 데이터베이스를 준비해야 합니다.',
        )



@app.route('/board/list')
def board_list():
    try:
        response = create_admin_client().table('inquiries').select(
            'id, title, author_name, created_at, view_count'
        ).order('created_at', desc=True).execute()
        rows = [{
            'id': row['id'],
            'title': row['title'],
            'writer_name': row.get('author_name') or 'SafeCar 사용자',
            'regdate': row.get('created_at'),
            'readcount': row.get('view_count', 0),
        } for row in (response.data or [])]
        return render_template('board_list.html', boards=rows)
    except SupabaseConfigurationError:
        app.logger.error(
            'Supabase inquiry configuration is incomplete. '
            'Required environment variables were not loaded.'
        )
        return render_template(
            'board_list.html',
            boards=[],
            board_error='문의 게시판 연결 설정을 확인하고 있습니다.',
        )
    except Exception as e:
        app.logger.warning('Supabase inquiry list failed: %s', type(e).__name__)
        error_code = str(getattr(e, 'code', '') or '')
        message = (
            '문의 게시판 테이블을 준비해야 합니다.'
            if error_code == 'PGRST205'
            else '문의 게시판 데이터를 불러오지 못했습니다.'
        )
        return render_template(
            'board_list.html',
            boards=[],
            board_error=message,
        )


@app.route('/board/write', methods=['GET'])
def board_write():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('board_write.html')


@app.route('/board/write_pro', methods=['POST'])
def board_write_pro():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    title = (request.form.get('title') or '').strip()
    content = (request.form.get('content') or '').strip()
    member_id = normalize_auth_user_id(session.get('user_id'))
    if not member_id:
        session.clear()
        return redirect(url_for('login'))
    if not title or not content:
        return "<script>alert('제목과 내용을 모두 입력해 주세요.'); history.back();</script>"

    try:
        admin_client = create_admin_client()
        auth_user_response = admin_client.auth.admin.get_user_by_id(member_id)
        auth_user = getattr(auth_user_response, 'user', None)
        if not auth_user or str(auth_user.id) != member_id:
            session.clear()
            return (
                "<script>alert('로그인 정보가 만료되었습니다. 다시 로그인해 주세요.'); "
                "location.href='/login';</script>"
            )

        response = admin_client.table('inquiries').insert({
            'author_id': member_id,
            'author_name': (session.get('user_name') or 'SafeCar 사용자')[:80],
            'title': title[:200],
            'content': content[:10000],
        }).execute()
        if not response.data:
            raise RuntimeError('Supabase inquiry insert returned no row')
        return redirect(url_for('board_list'))
    except SupabaseConfigurationError:
        app.logger.error('Supabase inquiry write configuration is incomplete.')
        return (
            "<script>alert('문의 게시판 연결 설정이 없습니다. 서버를 다시 실행해 주세요.'); "
            "history.back();</script>"
        )
    except Exception as e:
        error_code = str(getattr(e, 'code', '') or '')
        app.logger.warning(
            'Supabase inquiry create failed: type=%s code=%s',
            type(e).__name__,
            error_code or 'none',
        )
        if error_code == '23503':
            session.clear()
            message = '로그인 계정을 확인할 수 없습니다. 다시 로그인해 주세요.'
            destination = "location.href='/login';"
        elif error_code in {'42501', 'PGRST301'}:
            message = '문의 게시판 저장 권한 설정을 확인해 주세요.'
            destination = 'history.back();'
        elif error_code in {'23514', '23502', '22001'}:
            message = '제목 또는 내용의 입력값을 확인해 주세요.'
            destination = 'history.back();'
        else:
            message = '문의글을 저장하지 못했습니다. 다시 로그인한 뒤 시도해 주세요.'
            destination = 'history.back();'
        return f"<script>alert('{message}'); {destination}</script>"


@app.route('/board/view/<board_id>')
def board_view(board_id):
    board_id = normalize_auth_user_id(board_id)
    if not board_id:
        return "<script>alert('존재하지 않는 문의글입니다.'); location.href='/board/list';</script>"
    try:
        client = create_admin_client()
        response = client.table('inquiries').select(
            'id, author_id, author_name, title, content, created_at, view_count'
        ).eq('id', board_id).limit(1).execute()
        if not response.data:
            return "<script>alert('존재하지 않는 문의글입니다.'); location.href='/board/list';</script>"
        row = response.data[0]
        next_count = int(row.get('view_count') or 0) + 1
        client.table('inquiries').update({
            'view_count': next_count,
        }).eq('id', board_id).execute()
        board = {
            'id': row['id'],
            'member_id': row['author_id'],
            'writer_name': row.get('author_name') or 'SafeCar 사용자',
            'title': row['title'],
            'content': row['content'],
            'regdate': row.get('created_at'),
            'readcount': next_count,
        }
        return render_template('board_view.html', board=board, comments=[])
    except Exception as e:
        app.logger.warning('Supabase inquiry detail failed: %s', type(e).__name__)
        return "<script>alert('문의글을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'); history.back();</script>"


@app.route('/board/edit/<board_id>')
def board_edit(board_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    board_id = normalize_auth_user_id(board_id)
    current_user_id = normalize_auth_user_id(session.get('user_id'))
    if not board_id or not current_user_id:
        return "<script>alert('수정 권한이 없습니다.'); history.back();</script>"
    try:
        response = create_admin_client().table('inquiries').select(
            'id, author_id, title, content'
        ).eq('id', board_id).limit(1).execute()
        if not response.data:
            return "<script>alert('문의글을 찾을 수 없습니다.'); location.href='/board/list';</script>"
        row = response.data[0]
        is_owner = str(row['author_id']) == current_user_id
        is_admin = session.get('user_role') == 'admin'
        if not is_owner and not is_admin:
            return "<script>alert('수정 권한이 없습니다.'); history.back();</script>"
        board = {
            'id': row['id'],
            'member_id': row['author_id'],
            'title': row['title'],
            'content': row['content'],
        }
        return render_template('board_edit.html', board=board)
    except Exception as e:
        app.logger.warning('Supabase inquiry edit load failed: %s', type(e).__name__)
        return "<script>alert('문의글을 불러오지 못했습니다.'); history.back();</script>"


@app.route('/board/edit_pro', methods=['POST'])
def board_edit_pro():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    board_id = normalize_auth_user_id(request.form.get('id'))
    current_user_id = normalize_auth_user_id(session.get('user_id'))
    title = (request.form.get('title') or '').strip()
    content = (request.form.get('content') or '').strip()
    if not board_id or not current_user_id:
        return "<script>alert('수정 권한이 없습니다.'); history.back();</script>"
    if not title or not content:
        return "<script>alert('제목과 내용을 모두 입력해 주세요.'); history.back();</script>"
    try:
        client = create_admin_client()
        response = client.table('inquiries').select('author_id').eq(
            'id', board_id
        ).limit(1).execute()
        row = response.data[0] if response.data else None
        is_owner = row and str(row['author_id']) == current_user_id
        is_admin = session.get('user_role') == 'admin'
        if not row or (not is_owner and not is_admin):
            return "<script>alert('수정 권한이 없습니다.'); history.back();</script>"
        client.table('inquiries').update({
            'title': title[:200],
            'content': content[:10000],
        }).eq('id', board_id).execute()
        return f"<script>alert('정상적으로 수정되었습니다.'); location.href='/board/view/{board_id}';</script>"
    except Exception as e:
        app.logger.warning('Supabase inquiry update failed: %s', type(e).__name__)
        return "<script>alert('수정 중 오류가 발생했습니다.'); history.back();</script>"


@app.route('/board/delete/<board_id>')
def board_delete(board_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    board_id = normalize_auth_user_id(board_id)
    current_user_id = normalize_auth_user_id(session.get('user_id'))
    if not board_id or not current_user_id:
        return "<script>alert('삭제 권한이 없습니다.'); history.back();</script>"
    try:
        client = create_admin_client()
        response = client.table('inquiries').select('author_id').eq(
            'id', board_id
        ).limit(1).execute()
        row = response.data[0] if response.data else None
        if not row or str(row['author_id']) != current_user_id:
            return "<script>alert('삭제 권한이 없습니다.'); history.back();</script>"
        client.table('inquiries').delete().eq('id', board_id).eq(
            'author_id', current_user_id
        ).execute()
        return "<script>alert('문의글을 삭제했습니다.'); location.href='/board/list';</script>"
    except Exception as e:
        app.logger.warning('Supabase inquiry delete failed: %s', type(e).__name__)
        return "<script>alert('삭제 중 오류가 발생했습니다.'); history.back();</script>"


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
