<<<<<<< HEAD:app.py
from flask import Flask, render_template, request, redirect, url_for, session
from LMS.common.session import Session

app = Flask(__name__)
# 내 브라우저에 저장된 로그인 정보가 안전하게 지켜지도록 잠금 장치 역할
app.secret_key = 'your_secret_key_here'

# 홈페이지 화면을 출력
@app.route('/')
def index():
    return render_template("index.html")

# 로그인
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    uid = request.form['uid']
    upw = request.form['upw']

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 회원 정보 조회
            sql = "SELECT id, name, uid, role FROM members WHERE uid = %s AND password = %s"
            cursor.execute(sql, (uid, upw))
            user = cursor.fetchone()

        if user:
            # 2. 로그인 성공 : 세션에 사용자 정보 저장
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['user_uid'] = user['uid']

            # 이제 DB에서 'role' 가져왔으니 에러없이 잘 들어감
            session['user_role'] = user['role']

            return redirect(url_for('index'))
        else:
            return "<script>alert('아이디 또는 비밀번호가 틀렸습니다.'); history.back();</script>"
    finally:
        conn.close()

# 로그아웃
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# 회원가입
@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'GET':
        return render_template('join.html')

    uid = request.form.get('uid')
    password = request.form.get('password')
    name = request.form.get('name')

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM members WHERE uid = %s", (uid, ))
            if cursor.fetchone():
                return "<script>alert('이미 존재하는 아이디입니다.'); history.back();</script>"

            # 회원 정보 저장
            sql = "INSERT INTO members (uid, password, name) VALUES (%s, %s, %s)"
            cursor.execute(sql, (uid, password, name))
            conn.commit()

            return "<script>alert('회원가입이 완료되었습니다.'); location.href='/login';</script>"
    except Exception as e:
        print(f"회원가입 에러: {e}")
        return "가입 중 오류가 발생했습니다."
    finally:
        conn.close()

# 회원 수정
@app.route('/member/edit', methods=['GET', 'POST'])
def member_edit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                # 기존 정보 불러오기
                cursor.execute("SELECT * FROM members WHERE id = %s", (session['user_id'], ))
                user_info = cursor.fetchone()
                return render_template('member_edit.html', user=user_info)

            # POST 요청: 정보 업데이트
            new_name = request.form.get('name')
            new_pw = request.form.get('password')

            if new_pw: # 비밀번호 입력 시에만 변경
                sql = "UPDATE members SET password = %s WHERE id = %s"
                cursor.execute(sql, (new_pw, session['user_id']))
            else: # 이름만 변경
                sql = "UPDATE members SET name = %s WHERE id = %s"
                cursor.execute(sql, (new_name, session['user_id']))

            conn.commit()
            session['name'] = new_name
            return "<script>alert('정보가 수정되었습니다.'); location.href='/mypage';</script>"
    finally:
        conn.close()
#===================== 여기서부터 추가 기능 ==========================

# 마이페이지
@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 내 상세 정보 조회
            cursor.execute("SELECT * FROM members WHERE id = %s", (session['user_id'], ))
            user_info = cursor.fetchone()

            # 2. 내가 쓴 게시글 개수 조회 (작성하신 boards 테이블 활용)
            cursor.execute("SELECT COUNT(*) as board_count FROM boards WHERE member_id = %s", (session['user_id'], ))
            board_count = cursor.fetchone()['board_count']

            return render_template('mypage.html', user=user_info, board_count=board_count)
    finally:
        conn.close()

# 아이디 중복 실시간 체크
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

# 프로필 이미지 업로드
@app.route('/upload_profile', methods=['POST'])
def upload_profile():
    import os
    from werkzeug.utils import secure_filename  # 안전하게 파일명 정리
    file = request.files['profile']
    # uploads 폴더가 없으면 생성
    os.makedirs("uploads", exist_ok=True)
    # 파일명 안전하게 변환
    filename = secure_filename(file.filename)
    # 파일 저장
    file.save(os.path.join("uploads", filename))
    # HTML 폼에서 <input type="file" name="profile">로 보낸 파일을 받음
    # request.files → Flask에서 파일 전송 데이터를 담는 객체
    return "업로드 완료"

# 관리자 회원관리 페이지
@app.route('/admin/members') # GET 방식
def member_list():

    if session.get('user_role') != 'admin':
        return "관리자만 접근 가능"
    # 로그인한 사용자의 역할(user_role)이 "admin"이 아니면 접근 차단
    conn = Session.get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id,uid,name,role FROM members")
            users = cursor.fetchall()
        # members 테이블에서 모든 회원 정보 조회
        # fetchall() → 결과를 리스트로 반환
            return render_template("member_list.html", users=users)
            # HTML 템플릿 member_list.html에 조회 결과 전달
            # 템플릿에서는 users 변수로 반복문 돌려서 회원 목록 출력 가능
            # return redirect(url_for('index'))
            # 일반 사용자 접근 시 에러 페이지로 redirect 추천
    finally:
        conn.close()

# 마이페이지의 board 테이블인데 워크벤치에 써야 오류 안남
# CREATE TABLE boards (
#     id INT AUTO_INCREMENT PRIMARY KEY,
#     member_id INT NOT NULL,
#     title VARCHAR(255) NOT NULL,
#     content TEXT,
#     created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
#     FOREIGN KEY (member_id) REFERENCES members(id)
# );


=======
import os
import re
import requests
from github import Github, Auth

# 환경 변수 설정
GH_TOKEN = os.environ.get("GH_TOKEN")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DB_ID = os.environ.get("NOTION_DB_ID")
NOTION_STATUS_DB_ID = os.environ.get("NOTION_STATUS_DB_ID")
REPO_NAME = os.environ.get("REPO_NAME")

STATUS_MAP = {
    "#idea": "아이디어",
    "#coding": "코딩중",
    "#review": "검토중",
    "#debug": "디버깅중",
    "#done": "완료"
}

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def update_task_status(msg):
    found_status = next((status for key, status in STATUS_MAP.items() if key in msg), None)
    match = re.search(r'STA-(\d+)', msg)
   
    if not found_status or not match:
        return

    task_number = match.group(1) # 숫자만 추출 (예: 5)
    clean_db_id = NOTION_STATUS_DB_ID.strip().replace("-", "")
   
    try:
        # [최적화] 필터링을 통해 해당 ID를 가진 페이지만 즉시 조회
        query_url = f"https://api.notion.com/v1/databases/{clean_db_id}/query"
        filter_payload = {
            "filter": {"property": "ID", "unique_id": {"equals": int(task_number)}}
        }
       
        res = requests.post(query_url, headers=HEADERS, json=filter_payload)
        results = res.json().get('results', [])

        if not results:
            print(f" {match.group()}에 해당하는 페이지가 없습니다.")
            return

        target_page_id = results[0]['id']
       
        # 상태 업데이트
        update_url = f"https://api.notion.com/v1/pages/{target_page_id}"
        update_payload = {
            "properties": {"상태": {"status": {"name": found_status}}}
        }
       
        res_up = requests.patch(update_url, headers=HEADERS, json=update_payload)
        if res_up.status_code == 200:
            print(f"[{match.group()}] 상태 업데이트 완료: {found_status}")
        else:
            print(f" 실패: {res_up.text}")
           
    except Exception as e:
        print(f" 에러 발생: {e}")

def commit_to_notion(msg, author, url, date):
    try:
        clean_log_db_id = NOTION_DB_ID.strip().replace("-", "")
        create_url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {"database_id": clean_log_db_id},
            "properties": {
                "Name": {"title": [{"text": {"content": msg}}]},
                "Author": {"rich_text": [{"text": {"content": author}}]},
                "URL": {"url": url},
                "Date": {"date": {"start": date}}
            }
        }
        res = requests.post(create_url, headers=HEADERS, json=payload)
        if res.status_code == 200:
            print(f"[로그 DB] 기록 완료")
    except Exception as e:
        print(f"로그 DB 오류: {e}")

def sync_to_notion():
    try:
        g = Github(auth=Auth.Token(GH_TOKEN))
        repo = g.get_repo(REPO_NAME)
        # 최신 커밋 1개만 가져오기
        latest_commit = repo.get_commits()[0]
       
        msg = latest_commit.commit.message
        commit_to_notion(msg, latest_commit.commit.author.name, latest_commit.html_url, latest_commit.commit.author.date.isoformat())
        update_task_status(msg)
       
    except Exception as e:
        print(f"전체 프로세스 에러: {e}")

if __name__ == "__main__":
    sync_to_notion()
>>>>>>> main:git_actions.py
