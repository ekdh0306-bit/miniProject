import os
import threading
import time
import json



from flask import Flask, render_template, request, url_for, redirect, send_from_directory, session,  jsonify
from werkzeug.utils import secure_filename

from LMS.common.Session import Session

from LMS.service import *

app = Flask(__name__)
app.config['SECRET_KEY'] = 'afkbasfhbafbafbahfkqafkb14124214214'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')




@app.route('/join', methods=['GET', 'POST']) # get메서드(화면출력) post(화면폼을 처리하는 용도)

def join():
    if request.method == 'GET':
        return render_template('join.html')
    uid = request.form.get('uid')
    password = request.form.get('pw')
    name = request.form.get('username')
    email= request.form.get('email')

    try:
        if MemberService.is_duplicate_uid(uid):
            return "<script>alert('이미 존재하는 아이디 입니다.'); history.back();</script>"

        if MemberService.join(uid, password, name, email):
            return "<script>alert('회원가입이 완료 되었습니다.'); location.href='/login';</script>"

        return "가입 도중 오류가 발생하였습니다."

    except Exception as e:
        print(e)
        render_template('join.html')
        return "<script>alert('치명적인 오류가 발생했습니다. 다시 시도해주세요'); history.back();</script>"


@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    uid = request.form['uid']
    upw = request.form['pw']

    try:
        user = MemberService.login(uid, upw)

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
            user_info = MemberService.get_user_info(session['user_id'])
            return render_template('member_edit.html', user=user_info)

        # POST 요청 처리 (수정 실행)
        new_uid = request.form.get('new_uid')
        new_email = request.form.get('email')
        new_pw = request.form.get('pw')
        print(f"session user_id: {session['user_id']}")
        print(f"session user_id type: {type(session['user_id'])}")

        if MemberService.update_member(session['user_id'], new_uid, new_email, new_pw):
            session['user_uid'] = new_uid
            session['user_email'] = new_email
            return "<script>alert('회원정보 수정을 완료했습니다.'); location.href = '/mypage';</script>"
        return "수정 도중 오류가 발생했습니다."
    except Exception as e:
        print(f'치명적 오류 발생{e}')
        return redirect(url_for('login'))


@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_info = MemberService.get_user_info(session['user_id'])

    return render_template('mypage.html', user=user_info)

# 회원 탈퇴 로직
@app.route('/member/delete/<int:user_id>', methods=['GET'])
def member_delete(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if MemberService.delete_member(session['user_id']):
        session.clear()
        return "<script>alert('회원탈퇴를 완료했습니다!.'); location.href='/'</script>"
    return "탈퇴 처리 중 오류 발생"



@app.route('/analyze', methods=['GET', 'POST'])
def analyze():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # HTML 탭에 따라 image_file 혹은 video_file로 오므로 체크 필요
        file = request.files.get('image_file') or request.files.get('video_file')

        if not file or file.filename == '':
            return jsonify({"status": "error", "message": "No file"}), 400

        try:
            media_id = MediaService.process_upload(file, session['user_id'], app.config['UPLOAD_FOLDER'])
            return jsonify({"status": "pending", "media_id": media_id})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return render_template('analyze.html')

@app.route('/api/analysis/status/<int:media_id>')
def get_analysis_status(media_id):
    result = MediaService.get_status(media_id)
    if result:
        return jsonify({
            "status": result['status'],
            "result": json.loads(result['result_json']) if result['result_json'] else None
        })
    return jsonify({"status": "error", "message": "Not found"}), 404


@app.route('/')
def index():
    return render_template('main.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
