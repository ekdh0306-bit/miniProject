from flask import Flask, render_template, request, redirect, url_for, session
from LMS.common.session import Session

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# ================= 로그인 =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    uid = request.form['uid']
    password = request.form['password']

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT id, name, uid, role FROM members WHERE uid=%s AND password=%s"
            cursor.execute(sql, (uid, password))
            user = cursor.fetchone()

        if user:
            # 세션 저장
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_uid'] = user['uid']
            session['user_role'] = user['role']

            return redirect(url_for('index'))
        else:
            return "<script>alert('아이디 또는 비밀번호가 틀렸습니다.'); history.back();</script>"

    except Exception as e:
        print(f"로그인 오류 발생: {e}")

    finally:
        conn.close()


# ================= 로그아웃 =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ================= 회원가입 =================
@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'GET':
        return render_template('join.html')

    uid = request.form.get('uid')
    password = request.form.get('password')
    name = request.form.get('name')
    email = request.form.get('email')

    if not uid or not password or not name:
        return "<script>alert('모든 항목을 입력하세요.'); history.back();</script>"

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM members WHERE uid=%s", (uid,))
            if cursor.fetchone():
                return "<script>alert('이미 존재하는 아이디입니다.'); history.back();</script>"

            sql = "INSERT INTO members (uid, password, name, email) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (uid, password, name, email))
            conn.commit()

            return "<script>alert('회원가입 완료! 로그인하세요'); location.href='/login';</script>"
    finally:
        conn.close()


# ================= 메인 =================
@app.route('/')
def index():
    return render_template(
        "main.html",
        name=session.get('name')  # ✅ 로그인 정보 전달
    )

# ================= 마이페이지 =================
@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM members WHERE id=%s", (session['user_id'],))
            user_info = cursor.fetchone()

        return render_template('mypage.html', user=user_info)
    finally:
        conn.close()


# ================= 회원 수정 =================
@app.route('/member/edit', methods=['GET', 'POST'])
def member_edit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                cursor.execute("SELECT * FROM members WHERE id=%s", (session['user_id'],))
                user_info = cursor.fetchone()
                return render_template('member_edit.html', user=user_info)

            new_name = request.form.get('name')
            new_password = request.form.get('password')
            new_email = request.form.get('email')  # ✅ 수정됨

            if new_password:
                sql = "UPDATE members SET name=%s, password=%s, email=%s WHERE id=%s"
                cursor.execute(sql, (new_name, new_password, new_email, session['user_id']))
            else:
                sql = "UPDATE members SET name=%s, email=%s WHERE id=%s"
                cursor.execute(sql, (new_name, new_email, session['user_id']))

            conn.commit()

            session['name'] = new_name

            return "<script>alert('수정 완료'); location.href='/mypage';</script>"
    finally:
        conn.close()
# 게시글 목록(분석 게시판)
@app.route('/analyze')
def analyze():
    return render_template('analyze.html')

# 게시글 업로드
# @app.route('/board/upload', methods=['GET', 'POST'])
# def board_upload():
#     return "upload page"
# from flask import request, render_template

@app.route('/board/upload', methods=['GET', 'POST'])
def board_upload():
    if request.method == 'GET':
        return render_template('upload.html')

    # POST (파일 업로드 처리)
    file = request.files.get('file')

    if not file:
        return "파일 없음"

    file.save(f'uploads/{file.filename}')
    return "업로드 성공"
# ================= 실행 =================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)


#=====================================

boards = [
    {"id": 1, "title": "첫 번째 글", "content": "안녕하세요!"},
    {"id": 2, "title": "두 번째 글", "content": "Flask 게시판입니다."},
]

# 게시글 목록
@app.route('/board/list')
def board_list():
    return render_template('board_list.html', boards=boards)

# 게시글 상세보기
@app.route('/board/view/<int:id>')
def board_view(id):
    board = next((b for b in boards if b['id'] == id), None)
    if not board:
        return "게시글이 없습니다.", 404
    return render_template('board_view.html', board=board)

# 글쓰기 페이지

# 게시글 상세보기

# 게시글 삭제


# 사이트 소개
@app.route('/introduce')
def about():
    return render_template('introduce.html')

#==================
#===================== 여기서부터 추가 기능 ==========================

# 마이페이지
@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login')) # 로그인 안 했으면 못 들어옴

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

# 아이디 중복 체크
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

# 회원 활동 추정 : 회원별로 게시글 많이 쓴 회원  / 관리자 입장에서 활동추정 가능
# 회원 ID (숫자) | 아이디 | 이름 | 게시글 수 ->  1줄에 저렇게 나옴

# 관리자 회원 검색 (회원 검색 기능)
@app.route('/admin/member_search')
def member_search():
    # 권리자 권한 체크
    if session.get('user_role') != 'admin':
        return "관리자만 접근 가능"
    # 로그인한 사람의 권한 확인 / admin 아니면 차단
    keyword = request.args.get('keyword', '')
    # request.args → GET 방식 데이터
    # URL에서 keyword라는 이름으로 전달된 값을 가져와라
    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor: # SQL 실행할 도구
            cursor.execute("""
                SELECT id, uid, name, role
                FROM members
                WHERE uid LIKE %s OR name LIKE %s
            """, (f"%{keyword}%", f"%{keyword}%"))

            users = cursor.fetchall() # 결과값 리스트에 딕셔너리 값으로 여러개 나옴
            return render_template("member_list.html", users=users) # 결과를 HTML로 넘김
    finally:
        conn.close()

# 회원별 게시글 수를 보여주는 관리자 통계 페이지 (누가 글을 많이 썼는지 순위 보여주는 기능)
# 회원별 글쓰기 갯수 순위
@app.route('/admin/member_stats')
def member_stats():
# stats안에 SELECT m.id, m.uid, m.name, COUNT(b.id) AS board_count의 결과가 들어있음
# 결과 형태 (리스트안에 딕셔너리 여러개 들어있는 구조) stats = 회원 목록 + 게시글 개수 데이터
    if session.get('user_role') != 'admin':
        return "관리자만 접근 가능"
    # user_role → 사용자 권한
    conn = Session.get_connection()

    try:
        with conn.cursor() as cursor: # cursor → SQL 실행하는 객체
            cursor.execute("""
                SELECT m.id, m.uid, m.name,
                       COUNT(b.id) AS board_count 
                FROM members m
                LEFT JOIN boards b ON m.id = b.member_id
                GROUP BY m.id
                ORDER BY board_count DESC
            """)
            # COUNT(b.id) → 게시글 개수 세는 거
            # members 테이블에서 회원번호, 아이디, 이름 가져옴
            # COUNT(b.id) AS board_count : board 테이블에서 회원이 작성한 게시글 수 계산
            # 회원 테이블 + 게시글 테이블 연결 LEFT JOIN 하는 이유 : 게시글 없는 회원도 포함할려고
            # GROUP BY m.id 회원별로 묶어서 게시글 개수 계산
            # 게시글 많은 순서 정렬 DESC
            stats = cursor.fetchall()
            # SQL 결과를 리스트로 가져옴
            return render_template("member_stats.html", stats=stats)
            # member_stats.html 페이지로 stats 데이터 전달
    finally:
        conn.close()

# 홈페이지 화면을 출력
@app.route('/')
def index():
    return render_template("main.html")

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)






