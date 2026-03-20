import os
import json
import time
from flask import Flask, render_template, request, url_for, redirect,  session,  jsonify

from service.MediafileService import MediafileService
from service.MediaBoardService import  MediaBoardService
from service.AnalyzeresultService import AnalyzeresultService
from service.MemberService import MemberService

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_IMAGE_SIZE'] = 20 * 1024 * 1024   # 20MB (차량 이미지)
app.config['MAX_VIDEO_SIZE'] = 500 * 1024 * 1024  # 500MB (CCTV 영상)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB

@app.errorhandler(413)
def file_too_large(e):
    max_bytes = app.config['MAX_CONTENT_LENGTH']

    # GB 단위로 표시할지 MB로 표시할지 자동으로 판단
    if max_bytes >= 1024 * 1024 * 1024:
        max_size = f"{max_bytes // (1024 * 1024 * 1024)}GB"
    else:
        max_size = f"{max_bytes // (1024 * 1024)}MB"

    return jsonify({
        "status": "error",
        "message": f"업로드 가능한 최대 용량({max_size})을 초과했습니다."
    }), 413

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
        new_name = request.form.get('new_name')
        new_email = request.form.get('email')
        new_pw = request.form.get('pw')
        print(f"session user_id: {session['user_id']}")
        print(f"session user_id type: {type(session['user_id'])}")

        if MemberService.update_member(session['user_id'], new_uid, new_name, new_email, new_pw):
            session['user_uid'] = new_uid
            session['user_email'] = new_email
            session['user_name'] = new_name
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
            media_id = MediafileService.mediafile_uploads(file, session['user_id'], app.config['UPLOAD_FOLDER'],app.config )
            return jsonify({"status": "pending", "media_id": media_id})

        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return render_template('analyze.html')


@app.route('/board/result', methods=['POST'])
def board_result():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401

    file = request.files.get('image_file') or request.files.get('video_file')
    description = request.form.get('description', '')  # 폼 데이터 가져오기

    if not file or file.filename == '':
        return jsonify({"status": "error", "message": "파일이 선택되지 않았습니다."}), 400

    try:
        # 💡 중요: description을 서비스 함수에 전달해야 합니다!
        media_id = MediafileService.mediafile_uploads(
            file, session['user_id'], app.config['UPLOAD_FOLDER'], app.config)

        # 분석 완료될 때까지 대기 (최대 30초)
        for _ in range(15):
            time.sleep(2)
            result = AnalyzeresultService.get_status(media_id)
            if result and result.status == 'SUCCESS':
                return jsonify({
                    "status": "success",
                    "media_id": media_id,
                    "analysis_result": result.result_json
                })

        # 30초 지나도 안 되면
        return jsonify({"status": "pending", "media_id": media_id, "analysis_result": "분석 시간 초과"})

    except ValueError as e:  # 용량 초과...
        return jsonify({"status": "error", "message": str(e)}), 400

    except Exception as e:
        print(f"업로드 오류: {e}")
        return jsonify({"status": "error", "message": "서버 오류가 발생했습니다."}), 500




@app.route('/api/analysis/status/<int:media_id>')
def get_analysis_status(media_id):
    result = AnalyzeresultService.get_status(media_id)

    if result:
        formatted_text = AnalyzeresultService.get_formatted_result(json.dumps(result.result_json))
        return jsonify({
            "status": result.status,
            "result": result.result_json,
            "formatted": formatted_text
        })
    return jsonify({"status": "not_found"}), 404

@app.route('/analyze/analysis')
def analysis_detail():
    return render_template('analyze_analysis.html')  # 상세보기 페이지


@app.route('/media/update/<int:media_id>', methods=['POST'])
def file_update(media_id):
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Login required"}), 401

    new_file = request.files.get('file')  # 폼에서 보낸 파일 객체

    if MediafileService.media_file_update(media_id, session['user_id'], new_file, app.config['UPLOAD_FOLDER']):
        return jsonify({"status": "success", "message": "파일이 교체되어 다시 분석을 시작합니다."})
    else:
        return jsonify({"status": "error", "message": "파일 교체를 실패하였습니다"}), 400


@app.route('/media/delete/<int:media_id>', methods=['POST'])
def delete_media_file(media_id):

    if 'user_id' not in session:
        return "<script>alert('로그인이 필요한 서비스입니다.'); location.href='/login';</script>"

    try:
        # 1. 서비스 호출 (DB + 물리 파일 삭제 수행)
        success = MediafileService.delete_mediafile(media_id, session['user_id'])

        if success:
            # 삭제 성공 시 분석 리스트 페이지로 이동
            return "<script>alert('파일과 분석 결과가 서버에서 완전히 삭제되었습니다.'); location.href='/analysis/list';</script>"
        else:
            # 삭제를 실패할 경우 이전 페이지로
            return "<script>alert('삭제 권한이 없거나 이미 존재하지 않는 파일입니다.'); history.back();</script>"

    except Exception as e:
        # 4. 예외 발생 시 에러 출력 및 이전 페이지로
        print(f"파일 삭제 오류: {e}")
        return "<script>alert('오류로 인해 삭제를 실패하였습니다.'); history.back();</script>"

@app.route('/analyze/list')
def analyze_list():
    # 1. 세션에서 user_id 가져오기
    user_id = session.get('user_id')

    # 2. 데이터 가져오기 (리스트 형태인지 확인)
    analysis_list = MediaBoardService.get_analyze_list(user_id)
    print(analysis_list)

    # 3. 템플릿으로 전달 (이때 이름이 'analyze_list'여야 함)
    return render_template('analyze_list.html', analyze_list=analysis_list)

@app.route('/')
def index():
    return render_template('main.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)