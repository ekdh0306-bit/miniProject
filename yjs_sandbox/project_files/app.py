from flask import Flask, render_template, request, redirect, url_for, session


from project_files.service import MemberService


app = Flask(__name__)
app.secret_key = 'you_secret_key'


@app.route('/join', methods=['GET', 'POST']) # get메서드(화면출력) post(화면폼을 처리하는 용도)

def join():
    if request.method == 'GET':
        return render_template('join.html')
    uid = request.form.get('uid')
    password = request.form.get('password')
    name = request.form.get('username')
    email= request.form.get('email')

    if MemberService.is_duplicate_uid(uid):
        return "<script>alert('이미 존재하는 아이디 입니다.'); history.back();</script>"

    if MemberService.join(uid, password, name, email):
        return "<script>alert('회원가입이 완료 되었습니다.'); location.href='/login';</script>"

    return "가입 도중 오류가 발생하였습니다."

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    uid = request.form['uid']
    upw = request.form['password']


    user = MemberService.login(uid,upw)

    if user:
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        session['user_uid'] = user['uid']
        session['user_role'] = user['role']
        return redirect(url_for('index'))
    else:
        return "<script>alert('아이디 또는 비밀번호가 틀렸습니다.');history.back();</script>"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/member/edit', methods=['GET', 'POST'])
def member_edit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'GET':
        user_info = MemberService.get_user_info(session['user_id'])
        return render_template('member_edit.html', user=user_info)

    # POST 요청 처리 (수정 실행)
    new_uid = request.form.get('new_uid')
    new_email = request.form.get('email')
    new_pw = request.form.get('pw')
    print(f"session user_id: {session['user_id']}")
    print(f"session user_id type: {type(session['user_id'])}")

    if MemberService.update_member(session['user_id'], new_uid, new_email, new_pw):
        return "<script>alert('정보 수정이 완료되었습니다.'); location.href = '/mypage';</script>"
    return "수정 도중 오류가 발생했습니다."

@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_info = MemberService.get_user_info(session['user_id'])


    return render_template('mypage.html', user=user_info)

# 회원 삭제 로직
@app.route('/member/delete/<int:user_id>', methods=['GET'])
def member_delete(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if MemberService.delete_member(session['user_id']):
        session.clear()
        return "<script>alert('회원 탈퇴가 완료되었습니다.'); location.href='/'</script>"
    return "탈퇴 처리 중 오류 발생"

@app.route("/") # url 생성용 코드
def index():
    return render_template('main.html')

if __name__ == "__main__":

    app.run(host='0.0.0.0', port=5350, debug=True)
