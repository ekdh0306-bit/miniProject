import os
import json
import time
from flask import Flask, render_template, request, url_for, redirect,  session,  jsonify,send_from_directory

from LMS.service import MediafileService, MediaBoardService
from LMS.service import AnalyzeresultService
from LMS.service import MemberService

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

    user_id = session['user_id']

    # ==========================================
    # 1. 내 정보 가져오기
    # ==========================================
    user_info = MemberService.get_user_info(user_id)

    # ==========================================
    # 2. 최근 분석 결과 마이페이지에 가져오기
    # ==========================================
    all_boards = MediaBoardService.get_analyze_list(user_id)
    recent_results = []

    for board in all_boards[:5]:

        score = 0
        summary = board.get('description') or board.get('file_type') or "제목 없음"

        date_str = board.get('uploaded_at', '최근')[:10]

        if board.get('status') == 'done':
            res_json = board.get('analysis_result')

            # JSON 문자열이라면 딕셔너리로 변환
            if isinstance(res_json, str) and res_json != "분석 중입니다.":
                try:
                    res_json = json.loads(res_json)
                except Exception as e:
                    print(f"JSON : {e}")

            # 딕셔너리에서 객체와 신뢰도(점수) 가져오기
            if isinstance(res_json, dict) and 'objects' in res_json:
                objects = res_json['objects']
                if len(objects) > 0:
                    score = int(objects[0].get('score', 0) * 100)  # 0.95 -> 95
                    summary = f"{objects[0].get('label')} 탐지됨"  # "cat 탐지됨"

        recent_results.append({
            "date": date_str,
            "summary": summary,
            "score": score
        })

    # print(f" 내 정보: {user_info}")
    # print(f" 최근 분석: {recent_results}")

    return render_template('mypage.html', user=user_info, analysis_results=recent_results)

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

    # 프론트의 currentType에 따라 image_file 혹은 video_file로 데이터가 옵니다.
    file = request.files.get('image_file') or request.files.get('video_file')
    description = request.form.get('description', '')  # 메모(설명)

    if not file or file.filename == '':
        return jsonify({"status": "error", "message": "파일이 선택되지 않았습니다."}), 400

    try:
        media_id = MediafileService.mediafile_uploads(
            file, session['user_id'], app.config['UPLOAD_FOLDER'], app.config
        )

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

@app.route('/analysis')
def analysis_detail():
    return render_template('analyze_analysis.html')  # 상세보기 페이지

@app.route('/media/delete/<int:media_id>', methods=['POST'])
def mediafile_delete(media_id):

    if 'user_id' not in session:
        return "<script>alert('로그인이 필요한 서비스입니다.'); location.href='/login';</script>"

    try:
        # 1. 서비스 호출 (DB + 물리 파일 삭제 수행)
        success = MediafileService.mediafile_delete(media_id, session['user_id'])

        if success:
            # 삭제 성공 시 분석 리스트 페이지로 이동
            return "<script>alert('파일과 분석 결과가 서버에서 완전히 삭제되었습니다.'); location.href='/analyze/list';</script>"
        else:
            # 삭제를 실패할 경우 이전 페이지로
            return "<script>alert('삭제 권한이 없거나 이미 존재하지 않는 파일입니다.'); history.back();</script>"

    except Exception as e:
        # 4. 예외 발생 시 에러 출력 및 이전 페이지로
        print(f"파일 삭제 오류: {e}")
        return "<script>alert('오류로 인해 삭제를 실패하였습니다.'); history.back();</script>"

@app.route('/uploads/<filename>')
def upload_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/analyze/list')
def analyze_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    analyze_list_data = MediaBoardService.get_analyze_list(session['user_id'])

    return render_template('analyze_list.html', analyze_list=analyze_list_data)

@app.route('/analyze/analysis/')
def analyze_detail():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('analyze_analysis.html')

@app.route('/')
def index():
    return render_template('main.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
