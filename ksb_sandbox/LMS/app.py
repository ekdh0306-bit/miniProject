from flask import Flask, render_template, request, redirect, url_for, session
from LMS.common.Session import Session
from LMS.domain.Member import Member
from LMS.service.MemberService import MemberService

import os


app = Flask(__name__)

# 세션을 사용하기 위해 보안키 설정 (아무 문자열이나 입력)
app.secret_key = 'your_secret_key'

# 로그인
@app.route('/login', methods=['GET', 'POST']) # (GET: 폼 보여주기, POST: 저장 처리)
def login():
    if request.method == 'GET':
        return render_template('login.html')
        # templates 폴더에 있는 login.html 파일을 찾아서 브라우저에서 보여준다.

    uid = request.form.get('uid')
    password = request.form.get('password')

    conn = Session.get_connection()

    try:
        with conn.cursor() as cursor:
            # 1. 회원 정보 조회
            sql = "select id, uid, name, role from members where uid = %s and password=%s"
            # members 테이블에서 uid와 password가 입력한 값과 같은 회원 정보를 가져온다.
            cursor.execute(sql, (uid, password))
            user = cursor.fetchone()

            if user:
                # 2. 로그인 성공: 세션에 사용자 정보 저장
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['user_uid'] = user['uid']
                session['user_role'] = user['role']
                return redirect(url_for('index'))
                # index 페이지로 이동
                #      redirect(주소): 페이지를 그 주소로 이동시킨다.
                # url_for(): Flask route 함수 이름으로 URL 주소를 만들어주는 함수

            else:
                return "<script>alert('아이디 또는 비밀번호가 틀렸습니다.');history.back();</script>"

    finally:
        conn.close()

# 로그아웃
@app.route('/logout')
def logout():
    session.clear() # 세션 비우기
    return redirect(url_for('login'))
    # 로그인 페이지로 이동

# 회원가입
@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'GET':
        return render_template('join.html')

    uid = request.form.get('uid') # get() -> 값 없으면 None
    password = request.form.get('password')
    name = request.form.get('username')
    email = request.form['email']

    conn = Session.get_connection()

    try:
        with conn.cursor() as cursor:
            # 아이디 중복 체크
            cursor.execute("select id from members where uid = %s", (uid,))
            if cursor.fetchone():
                return "<script>alert('이미 존재하는 아이디입니다.');history.back();</script>"

            # 회원 정보 저장 (role, active는 기본값이 들어감)
            sql = "insert into members (uid, password, name, email) values (%s, %s, %s, %s)"
            # members 테이블에 입력한 아이디, 비번, 이름을 넣어라
            cursor.execute(sql, (uid, password, name, email))
            conn.commit()
            return "<script>alert('회원가입이 완료되었습니다.');location.href='/login';</script>"
            #                                                 로그인 페이지 화면으로 이동

    except Exception as e:
        print(f"회원가입 에러: {e}")
        return "회원가입 중 오류가 발생했습니다."

    finally:
        conn.close()

# 회원수정
@app.route('/member/edit', methods=['GET', 'POST'])
def member_edit():
    if 'user_id' not in session: # 세션에 user_id가 없으면
        return redirect(url_for('login')) # 로그인 페이지로 이동

    conn = Session.get_connection()
    try:
        with conn.cursor() as cursor:
            if request.method == 'GET':
                # 기존 정보 불러오기
                cursor.execute("select * from members where id = %s", (session['user_id'],))
                user_info = cursor.fetchone()
                return render_template('member_edit.html', user=user_info)

            # post 요청: 정보 업데이트
            new_name = request.form.get('name')
            new_password = request.form.get('password')

            if new_password: # 폼에서 비밀번호 입력칸이 비어있지 않을 때만 실행(빈칸이면 실행 안함)
                sql = "update members set password = %s where id = %s"
                # members 테이블에서 id가 특정값인 회원에 이름과 비번을 수정한다.
                cursor.execute(sql, (new_password, session['user_id']))

            else: # 이름만 변경
                sql = "update members set name = %s where id = %s"
                cursor.execute(sql, (new_name, session['user_id']))

                conn.commit()
                session['user_name'] = new_name # 세션 이름 정보도 갱신
                return "<script>alert('정보가 수정되었습니다.');location.href='/mypage';</script>"

    finally:
        conn.close()

# 마이페이지
@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = Session.get_connection()

    try:
        with conn.cursor() as cursor:
            # 내 상세 정보 보기
            cursor.execute("select * from members where id = %s", (session['user_id'],))
            user_info = cursor.fetchone()
            return render_template('mypage.html', user=user_info)

            # 2. 내가 쓴 게시글 개수 조회

    finally:
        conn.close()

# 게시글 목록(분석 게시판)
@app.route('/analyze')
def analyze():
        return render_template('analyze.html')

# 글쓰기 페이지




# 게시글 상세보기




# 게시글 삭제


# 사이트 소개
@app.route('/introduce')
def about():
    return render_template('introduce.html')

# ---------------------------------------------------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('main.html')

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)