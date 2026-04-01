import os
import json
import time
import threading
import uuid
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, url_for, redirect, session, jsonify, send_from_directory

from common.Session import Session

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_IMAGE_SIZE'] = 20 * 1024 * 1024
app.config['MAX_VIDEO_SIZE'] = 500 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024

# Flask 서버 생성 / 이 앱은 어디에 파일 저장하고, 얼마나 크게 받을지 정함
# ===============================================
# Helper Functions (Used by multiple routes or as dependencies)
# ===============================================

def get_user_info(user_id):
    conn = Session.get_connection() # DB 연결 열기
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM members WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            return row
    finally:
        conn.close()

def simulate_ai_analysis(media_id):
    print(f"[{media_id}] AI 분석 시작...")
    time.sleep(5) # 5초 기다림
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor: # 가짜 분석 결과 생성
            dummy_result = {
                "objects": [
                    {"box": [10, 20, 80, 90], "label": "cat", "score": 0.95},
                    {"box": [100, 120, 180, 200], "label": "dog", "score": 0.91}
                ]
            }
            sql = "UPDATE analysis_results SET status = 'SUCCESS', result_json = %s WHERE media_id = %s"
            cursor.execute(sql, (json.dumps(dummy_result), media_id))
            conn.commit()
            print(f"[{media_id}] 분석 완료!")
    except Exception as e:
        print(f"[{media_id}] 분석 오류: {e}")
    finally:
        conn.close()

def mediafile_uploads(file, user_id, upload_folder, config, memo=None):
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{filename}" # 같은 파일명 충돌 방지 / uuid.uuid4() 랜덤 UUID 생성 함수
    ext = filename.split('.')[-1].lower()
    is_image = ext in ['jpg', 'jpeg', 'png', 'gif'] # 이미지 vs 영상 구분
    file_type = 'IMAGE' if is_image else 'VIDEO'
    limit = config.get('MAX_IMAGE_SIZE') if is_image else config.get('MAX_VIDEO_SIZE')
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > limit: # 너무 크면 업로드 막음
        limit_mb = limit // (1024 * 1024)
        raise ValueError(f"{file_type} 파일은 {limit_mb}MB를 초과할 수 없습니다.")
    stored_path = os.path.join(upload_folder, unique_filename)
    os.makedirs(upload_folder, exist_ok=True)
    file.save(stored_path) # 서버 폴더에 저장
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO media_files (member_id, file_name, stored_path, file_type, memo) VALUES (%s, %s, %s, %s, %s)"
            # INSERT INTO media_files 파일 정보 DB 기록
            cursor.execute(sql, (user_id, filename, stored_path, file_type, memo))
            media_id = cursor.lastrowid # 방금 저장된 파일의 ID
            cursor.execute("INSERT INTO analysis_results (media_id, status) VALUES (%s, 'PENDING')", (media_id,))
            # INSERT INTO analysis_results “이 파일 분석 시작했음 (아직 결과 없음)”
            conn.commit()
            thread = threading.Thread(target=simulate_ai_analysis, args=(media_id,), daemon=True)
            thread.start()
            # 업로드 끝나자마자 뒤에서 따로 AI 분석 돌림
            # -> “파일 업로드 + DB 저장 + AI 분석 시작까지 전부 처리”
            # thread : 동시에 여러 작업 하게 해주는 기능
            return media_id # 나중에 결과 조회할 때 사용
    except Exception as e:
        conn.rollback() # 문제 생기면 DB 취소
        if os.path.exists(stored_path):
            os.remove(stored_path) # 파일도 삭제 (깔끔 처리)
        raise e
    finally:
        conn.close()

# 특정 미디어의 분석 결과 요청
def get_status(media_id): # 분석 결과 가져오기
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM analysis_results WHERE media_id = %s"
            cursor.execute(sql, (media_id,))
            row = cursor.fetchone()
            if row and row.get('result_json'):
                try:
                    row['result_json'] = json.loads(row['result_json'])
                except json.JSONDecodeError:
                    row['result_json'] = {}

            return row
    finally:
        conn.close()
    #             # JSON 문자열을 Python 딕셔너리로 변환
    #             row['result_json'] = json.loads(row['result_json']) # 문자열 → JSON 변환
    #         return row
    # finally:
    #     conn.close()

# ===============================================
# Flask Routes
# ===============================================

@app.errorhandler(413)
# HTTP 413 에러 (Request Entity Too Large) 발생 시 실행되는 함수 등록
def file_too_large(e):
    print(f"413 에러 발생: {e}")
    max_bytes = app.config['MAX_CONTENT_LENGTH'] # Flask 설정값에서 최대 업로드 크기 가져옴
    if max_bytes >= 1024 * 1024 * 1024:
        max_size = f"{max_bytes // (1024 * 1024 * 1024)}GB"
    else:
        max_size = f"{max_bytes // (1024 * 1024)}MB"
    return jsonify({"status": "error", "message": f"업로드 가능한 최대 용량({max_size})을 초과했습니다."}), 413
    # JSON 형태로 에러 메시지 반환 / 뒤에 413 붙이는 이유: HTTP 상태 코드도 같이 반환하기 위해

####################### CRUD 시작 ##############################
# -----------------------------
# 회원가입
# -----------------------------
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

        if is_duplicate: # 중복이면 이전 페이지로 돌아감
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
        finally:
            conn.close()

    except Exception as e:
        print(e)
        return "<script>alert('치명적인 오류가 발생했습니다. 다시 시도해주세요'); history.back();</script>"

# -----------------------------
# 로그인
# -----------------------------
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

# -----------------------------
# 로그아웃
# -----------------------------
@app.route('/logout')
def logout():
    session.clear()
    return "<script>alert('로그아웃을 성공했습니다!'); location.href='/';</script>"

# -----------------------------
# 회원 수정
# -----------------------------
@app.route('/member/edit', methods=['GET', 'POST'])
def member_edit():
    try:
        if 'user_id' not in session:
            return redirect(url_for('login')) # 로그인 안 된 상태면 접근 차단
        # 현재 로그인된 사용자 정보 가져와서 수정 페이지에 뿌려줌
        if request.method == 'GET':
            user_info = get_user_info(session['user_id'])
            return render_template('member_edit.html', user=user_info)

        # POST
        new_uid = request.form.get('new_uid')
        new_name = request.form.get('new_name')
        new_email = request.form.get('email')
        new_pw = request.form.get('pw')

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                if new_pw:
                    sql = "UPDATE members SET uid = %s, name = %s, email = %s, password = %s WHERE id = %s"
                    cursor.execute(sql, (new_uid, new_name, new_email, new_pw, session['user_id']))
                else:
                    sql = "UPDATE members SET uid = %s, name = %s, email = %s WHERE id = %s"
                    cursor.execute(sql, (new_uid, new_name, new_email, session['user_id']))
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
             return "수정 도중 오류가 발생했습니다."

    except Exception as e:
        print(f'치명적 오류 발생{e}')
        return redirect(url_for('login'))

# -----------------------------
# 마이페이지
# -----------------------------
@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    user_info = get_user_info(user_id)

    # 최근 분석 결과 5개를 가져오는 로직 추가
    conn = Session.get_connection()
    # analysis_results = []
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
            # media_files = 내가 올린 파일
            # WHERE m.member_id = %s 내 데이터만 가져옴
            # ORDER BY m.uploaded_at DESC
            # LIMIT 5 -> 최신 활동 5개만 보여줌
            cursor.execute(sql, (user_id,))
            analysis_results = cursor.fetchall()
    finally:
        conn.close()

    return render_template('mypage.html', user=user_info, analysis_results=analysis_results)

# -----------------------------
# 회원 탈퇴
# -----------------------------
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

#======================추가 기능===========================

# -----------------------------
# 관리자 회원관리 페이지 (x)
# -----------------------------
@app.route('/admin/members')
def member_list():
    if session.get('user_role') != 'admin':
        return "관리자만 접근 가능"  # abort() 대신 문자열 반환
    # 여기부터 실제 관리자 기능
    with Session.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, uid, name, role FROM members")
            users = cursor.fetchall()
    return render_template("member_list.html", users=users)

# -----------------------------
# 관리자 회원 검색 (x)
# -----------------------------
@app.route('/admin/member_search')
def member_search():
    # 권리자 권한 체크
    if session.get('user_role') != 'admin':
        return "관리자만 접근 가능"
    # 로그인한 사람의 권한 확인 / admin 아니면 차단
    keyword = request.args.get('keyword', '')
    # request.args → GET 방식 데이터
    # URL에서 keyword라는 이름으로 전달된 값을 가져와라
    with Session.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, uid, name, role
                FROM members
                WHERE uid LIKE %s OR name LIKE %s
            """, (f"%{keyword}%", f"%{keyword}%"))
            users = cursor.fetchall()
    return render_template("member_list.html", users=users)

# -----------------------------
# 아이디 중복 확인
# -----------------------------
@app.route('/check_uid') # /check_uid URL로 접속하면 이 함수 실행 GET방식으로 요청 받음
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
                return {"exists": True} # 아이디 이미 사용 중(다른 사람이 쓰는중)
            else:
                return {"exists": False} # 사용 가능
    finally:
        conn.close()

# -----------------------------
# 프로필 이미지 업로드
# -----------------------------
@app.route('/upload_profile', methods=['POST'])
def upload_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    file = request.files.get('profile')

    if not file or file.filename == '':
        return "파일 없음", 400

    # 파일명 안전 처리 + 중복 방지
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{filename}"

    # 저장 경로
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

    # 파일 저장
    file.save(filepath)

    # 🔥 DB에 프로필 이미지 저장
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE members SET profile_image = %s WHERE id = %s"
            cursor.execute(sql, (unique_filename, session['user_id']))
            conn.commit()
    finally:
        conn.close()
    return "<script>alert('프로필 이미지 변경 완료'); location.href='/mypage';</script>"

# -----------------------------
# 사이트 소개
# -----------------------------
@app.route('/introduce')
def about():
    return render_template('introduce.html')

#====================================================================
@app.route('/analyze', methods=['GET', 'POST'])
def analyze():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST': # 파일 업로드는 POST로 들어옴
        memo = request.form.get('description') # 사용자가 입력한 설명(텍스트)
        file = request.files.get('image_file') or request.files.get('video_file')
        if not file or file.filename == '':
            return jsonify({"status": "error", "message": "No file"}), 400
        try:
            media_id = mediafile_uploads(file, session['user_id'], app.config['UPLOAD_FOLDER'], app.config, memo=memo)
            return jsonify({"status": "pending", "media_id": media_id})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        # 오류 나면 JSON으로 에러 반환
    return render_template('analyze.html')

@app.route('/analyze/result', methods=['POST'])
def analyze_result():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401
    memo = request.form.get('description')
    file = request.files.get('image_file') or request.files.get('video_file') # 설명 + 파일 받기
    if not file or file.filename == '':
        return jsonify({"status": "error", "message": "파일이 선택되지 않았습니다."}), 400 # 파일 없으면 에러
    try:
        media_id = mediafile_uploads(file, session['user_id'], app.config['UPLOAD_FOLDER'], app.config, memo=memo)
        for _ in range(15): # 2초씩 쉬면서 최대 15번 반복
            time.sleep(2)
            result = get_status(media_id) # DB에서 분석 상태 확인
            if result and result['status'] == 'SUCCESS':
                return jsonify({
                    "status": "success",
                    "media_id": media_id,
                    "analysis_result": result['result_json']
                })
        return jsonify({"status": "pending", "media_id": media_id, "analysis_result": "분석 시간 초과"})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        print(f"업로드 오류: {e}")
        return jsonify({"status": "error", "message": "서버 오류가 발생했습니다."}), 500


@app.route('/api/analysis/status/<int:media_id>')
def get_analysis_status(media_id):
    result = get_status(media_id)
    if result:
        # get_status에서 이미 JSON을 파싱했으므로 json.dumps는 불필요
        result_json = result.get('result_json', {})
        formatted_text = "분석 중.."
        if not result_json: # 객체가 업는 경우
            formatted_text = "분석 결과가 없습니다."
        else:
            try:
                # result_json은 이미 딕셔너리
                objects = result_json.get('objects', [])
                if not objects:
                    formatted_text = "검출된 객체가 없습니다."
                else:
                    lines = []
                    for i, obj in enumerate(objects, 1): # 객체가 있는 경우 하나씩 꺼내서
                        line = f"[{i}] {obj['label']} (신뢰도: {obj['score'] * 100:.1f}%)" # 문자열 생성
                        lines.append(line)
                    formatted_text = "\n".join(lines) # 줄바꿈으로 합침
            except (KeyError, TypeError, ValueError) as e:
                print(f"데이터 형식 오류: {e}")
                formatted_text = "데이터 형식 오류"

        return jsonify({
            "status": result['status'],
            "result": result_json,
            "formatted": formatted_text
        })
    return jsonify({"status": "not_found"}), 404 # DB 아예 없음

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
                # 상세 페이지에서 복잡한 JSON 객체 대신 깔끔하게 포맷된 텍스트를 보여주기 위함입니다.
                try:
                    objects = analysis_data['result_json'].get('objects', [])
                    if not objects:
                        formatted_text = "검출된 객체가 없습니다."
                    else:
                        lines = [f"[{i}] {obj['label']} (신뢰도: {obj['score'] * 100:.1f}%)" 
                                 for i, obj in enumerate(objects, 1)]
                        formatted_text = "\n".join(lines)
                    analysis_data['formatted_result'] = formatted_text
                except (KeyError, TypeError, ValueError) as e:
                    print(f"포맷팅 오류: {e}")
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
                thread = threading.Thread(target=simulate_ai_analysis, args=(media_id,), daemon=True)
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
            sql_select = "SELECT stored_path FROM media_files WHERE id = %s AND member_id = %s"
            cursor.execute(sql_select, (media_id, session['user_id']))
            row = cursor.fetchone()
            if row:
                file_path = os.path.abspath(row['stored_path'])
                cursor.execute("DELETE FROM analysis_results WHERE media_id = %s", (media_id,))
                cursor.execute("DELETE FROM media_files WHERE id = %s AND member_id = %s", (media_id, session['user_id']))
                conn.commit()
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError as e:
                        print(f"[경고] DB는 지워졌으나 파일 삭제 실패: {e}")
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

# -----------------------------
# 메인 화면
# -----------------------------
@app.route('/')
def index():
    return render_template('main.html')

# -----------------------------
# 파일 업로드
# -----------------------------
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
