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

def simulate_ai_analysis(media_id):
    print(f"[{media_id}] AI 분석 시작...")
    time.sleep(5)
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
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
            thread = threading.Thread(target=simulate_ai_analysis, args=(media_id,), daemon=True)
            thread.start()
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
        finally:
            conn.close()

            return "가입 도중 오류가 발생하였습니다."

    except Exception as e:
        print(e)
        return "<script>alert('치명적인 오류가 발생했습니다. 다시 시도해주세요'); history.back();</script>"


@app.route("/login", methods=['GET', 'POST']) # 경로로 접근했을 때 접속방식에 따라 2가지 역할을 수행
def login():
    if request.method == 'GET': # 사용지가 url을 립력하거나 링크를 타고 들어왔을 때 실행(로그인 화면을 브라우저에 보여줌)
        return render_template('login.html')

    # POST (사용자가 아이디와 비밀번호를 입력하고 로그인)
    uid = request.form['uid']
    upw = request.form['pw']
    try:
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT id, name, uid, email, role FROM members WHERE uid = %s AND password = %s"
                # sql문을 사용하여 members 테이블에서 아이디와 비밀번호가 일치하는 회원을 찾는다.
                cursor.execute(sql, (uid, upw))
                user = cursor.fetchone()
        finally:
            conn.close()

        if user: # 로그인 성공 시(db에 일치하는 데이터가 있다면)
            session['user_id'] = user['id'] # 세션 객체에 유저 정보를 저장
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            session['user_uid'] = user['uid']
            session['user_role'] = user['role']
            return "<script>alert('로그인에 성공했습니다'); location.href='/';</script>" # 메인페이지로 이동
        else: # 실패 시(일치하는 데이터가 없으면)
            return "<script>alert('아이디 또는 비밀번호가 잘못되었습니다.'); history.back();</script>"
            # 경고창 띄우고 메인 페이지로 이동
    except Exception as e: # 예외 처리
        print(e)           # db 연결 오류 등 서버 내부 에러가 발생하면 에러 내용을 출력
        return render_template('login.html', error="치명적 오류 발생, 다시 시도해주세요") # 로그인 페이지를 다시 보여줌

@app.route('/logout')
def logout():
    session.clear() # 세션 초기화(현재 브라우저 세션에 저장된 모든 정보를 삭제)
    return "<script>alert('로그아웃을 성공했습니다!'); location.href='/';</script>" # 메인 페이지로 이동

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
        except Exception:
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
            # 업로드 파일 정보와 분석 결과 상태 테이블을 하나로 합쳐서 가져옴
            # 사용자가 파일을 올렸지만 아직 분석 결과가 없는 경우도 보여주기 위해서 LEFT JOIN 사용
            # ORDER BY m.uploaded_at DESC: 가장 최근에 올린 파일이 위로 오게 정렬
            cursor.execute(sql, (user_id,))
            analysis_results = cursor.fetchall()
    finally:
        conn.close()

    return render_template('mypage.html', user=user_info, analysis_results=analysis_results)

@app.route('/member/delete/<int:user_id>', methods=['GET']) #
def member_delete_route(user_id):
    if 'user_id' not in session or session['user_id'] != user_id: # 로그인이 안 되어 있거나 로그인한 아이디가 다르면
        return redirect(url_for('login'))                         # 로그인 페이지로 이동

    deleted = False
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM members WHERE id = %s", (session['user_id'],))
            conn.commit()
            deleted = True
    except Exception as e:
        print(f"회원 탈퇴 중 오류: {e}") # 삭제 도중 에러가 발생하면 작업을 취소하고
        conn.rollback()               # db 상태를 이전으로 되돌린다.
    finally:                          # db 연결을 닫아 서버 자원을 관리한다.
        conn.close()

    if deleted: # 삭제 성공 시
        session.clear() # 서버에 남아있는 사용자의 로그인 세션을 지운다.
        return "<script>alert('회원탈퇴를 완료했습니다!.'); location.href='/'</script>"
    else:
        return "탈퇴 처리 중 오류 발생"


# ------------------
# 아이디 찾기 기능
# ------------------
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

# ----------------
# 비밀번호 변경 기능
# ----------------
@app.route('/password/change', methods=['GET', 'POST'])
def change_password():

    if 'user_id' not in session:
        return redirect(url_for('login'))


    if request.method == 'GET':
        return render_template("change_password.html")

    # 새 비밀번호 받기
    new_pw = request.form.get("new_password")

    conn = Session.get_connection()

    try:
        with conn.cursor() as cursor:

            sql = "UPDATE members SET password = %s WHERE id = %s"
            cursor.execute(sql, (new_pw, session['user_id']))
            conn.commit()

            return "<script>alert('비밀번호가 변경되었습니다.'); location.href='/mypage';</script>"

    finally:
        conn.close()


# -------------
# 관리자 페이지
# -------------
@app.route('/admin')
def admin_page():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('user_role') != 'admin':
        return "<script>alert('관리자만 접근 가능합니다.'); history.back();</script>"

    conn = Session.get_connection()

    try:
        with conn.cursor() as cursor:

            sql = "SELECT id, uid, name, email, role FROM members"
            cursor.execute(sql)

            members = cursor.fetchall()

    finally:
        conn.close()

    return render_template(
        "admin_page.html",
        members=members
    )

# ---------------------
# 회원 목록 보기(관리자용)
# ---------------------
@app.route('/admin/members')
def admin_members():

    # 로그인 확인
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # 관리자 권한 확인 (예: role이 admin일 경우)
    if session.get('role') != 'admin':
        return "관리자만 접근 가능합니다.", 403

    conn = Session.get_connection()

    try:
        with conn.cursor() as cursor:

            sql = """
            SELECT id, name, email, created_at
            FROM members
            ORDER BY id DESC
            """

            cursor.execute(sql)
            members = cursor.fetchall()

    finally:
        conn.close()

    return render_template("admin_members.html", members=members)


@app.route('/analyze', methods=['GET', 'POST'])
# GET -> 파일 열기
# POST -> 파일 업로드 + 분석 요청

def analyze():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST': # 분석 시작
        memo = request.form.get('description') # 메모 가져오기
        file = request.files.get('image_file') or request.files.get('video_file') # 업로드 파일 가져오기
        if not file or file.filename == '':
            return jsonify({"status": "error", "message": "No file"}), 400 # 400: 잘못된 요청
        try:
            media_id = mediafile_uploads(file, session['user_id'], app.config['UPLOAD_FOLDER'], app.config, memo=memo)
            # 파일 업로드 처리
            return jsonify({"status": "pending", "media_id": media_id}) # 성공 시 응답(분석 진행 중)
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500 # 500: 서버 오류
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
        media_id = mediafile_uploads(file, session['user_id'], app.config['UPLOAD_FOLDER'], app.config, memo=memo)
        for _ in range(15): # 분석 결과 기다리기(최대 15번 반복)
            time.sleep(2)   # AI 분석 끝날 때까지 2초씩 기다림(최대 대기시간 30초)
            result = get_status(media_id)
            if result and result['status'] == 'SUCCESS': # 분석이 완료되면
                return jsonify({
                    "status": "success",
                    "media_id": media_id,
                    "analysis_result": result['result_json']
                })
        # 분석시간이 너무 오래 걸린 경우
        return jsonify({"status": "pending", "media_id": media_id, "analysis_result": "분석 시간 초과"})
        #                                                           30초 동안 결과 없으면 "분석 시간 초과"
    except ValueError as e: # 입력 오류 처리
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:  # 서버 오류 처리
        print(f"업로드 오류: {e}")
        return jsonify({"status": "error", "message": "서버 오류가 발생했습니다."}), 500

@app.route('/api/analysis/status/<int:media_id>')
def get_analysis_status(media_id):
    result = get_status(media_id) # 분석 결과 조회
    if result:
        # get_status에서 이미 JSON을 파싱했으므로 json.dumps는 불필요
        result_json = result.get('result_json', {})
        formatted_text = ""
        if not result_json:
            formatted_text = "분석 결과가 없습니다."
        else:
            try:
                # result_json은 이미 딕셔너리
                objects = result_json.get('objects', []) # 객체 목록 가져오기
                if not objects: # 객체가 없는 경우
                    formatted_text = "검출된 객체가 없습니다."
                else:
                    lines = [] # 결과를 한 줄씩 저장할 리스트
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
