from LMS.domain.Member import Member
from LMS.common.session import Session
import pymysql
import os
from werkzeug.utils import secure_filename

class MemberService:
    class MemberService:
        # 등록된 회원 수
        @classmethod
        def load(cls): # db에 연결 테스트 목적으로 생성
            conn = Session.get_connection()  # lms db를 가져와서 conn에 넣음
            # 예외발생가능 있음
            try:
                with conn.cursor() as cursor:  # db에서 가져온 객체 1줄을 cursor라고 함
                    cursor.execute("select count(*) as cnt from members")
                    #               Member 테이블에서 개수나온 것을 cnt변수에 넣어라
                    # cursor.execute() sql문 실행용
                    count = cursor.fetchone()['cnt']  # dict 타입으로 나옴 cnt : 5
                    #             .fetchone() 1개의 결과가 나올때 readone
                    #             .fetchall() 여러개의 결과가 나올때 readall
                    #             .fetchmany(3) 3개의 결과만 보고 싶을 때 (최상위3개)
                    print(f"시스템에 현재 등록된 회원수는 {count}명 입니다. ")

            except Exception as e:  # 예외발생 문구
                print(f"MemberService.load() 오류: {e}")

            finally:  # 항상 출력되는 코드
                print("데이터베이스 접속 종료됨....")
                conn.close()

    # 로그인
    @classmethod
    def login(cls):
        print("\n[로그인]")
        uid = input("아이디: ")
        password = input("비밀번호: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                # 1. 아이디와 비밀번호가 일치하는 회원 조회
                sql = "SELECT * FROM members WHERE uid = %s AND password = %s"
                print("sql =" + sql)
                cursor.execute(sql, (uid, password))
                row = cursor.fetchone()

                if row:
                    member = Member.from_db(row)
                    # 2. 계정 활성화 여부 체크
                    if not member.active:
                        print("비활성화된 계정입니다. 관리자에게 문의하세요.")

                    Session.login(member)
                    print(f"{member.name}님 로그인 성공 ({member.role})")

                else:
                    print("아이디 또는 비밀번호가 틀렸습니다.")

        except pymysql.MySQLError as e:
            print(f"MemberService.load()메서드 오류 발생: {e}")
        finally :
            conn.close()

    # 로그아웃
    @classmethod
    def logout(cls):
        # 1. 먼저 세션에 로그인 정보가 있는지 확인
        if not Session.is_login() :
            print("\n[알림] 현재 로그인 상태가 아닙니다.")
            return

        # 2. 세션의 로그인 정보 삭제
        Session.logout()
        print("\n[성공] 로그아웃 되었습니다. 안녕히 가세요!")

    # 회원가입
    @classmethod
    def signup(cls, uid, password,  name, email):
        """
        웹에서 전달받은 uid, password, name, email으로 회원가입 처리
        """
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 1. 중복 체크
                cursor.execute("SELECT id FROM members WHERE uid = %s", (uid,))
                if cursor.fetchone():
                    # 이미 존재하는 아이디
                    raise ValueError("이미 존재하는 아이디입니다.")

                # 2. DB에 회원 정보 저장
                cursor.execute(
                    "INSERT INTO members (uid, password, name, email) VALUES (%s, %s, %s, %s)",
                    (uid, password, name, email)
                )
                conn.commit()
                return True  # 회원가입 성공
        except Exception as e:
            conn.rollback()
            raise e  # Flask 라우트에서 처리하도록 예외 전달
        finally:
            conn.close()

# =====================================

    # -----------------------------
    # 모든 회원 조회 (관리자 회원 검색)
    # -----------------------------
    @staticmethod
    def get_all_members(): # db에 연결 테스트 목적으로 생성
        conn = Session.get_connection()  # lms db를 가져와서 conn에 넣음
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, uid, name, email, role FROM members")
                return cursor.fetchall()
        finally:
            conn.close()

    # -----------------------------
    # 회원 상세 조회 (관리자 회원관리 페이지)
    # -----------------------------

    @staticmethod
    def get_user_info(user_id):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM members WHERE id=%s", (user_id,))
                return cursor.fetchone()
        finally:
            conn.close()

    # -----------------------------
    # 게시글 수 조회
    # -----------------------------
    @staticmethod
    def get_board_count(user_id):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as board_count FROM boards WHERE member_id=%s", (user_id,))
                return cursor.fetchone()['board_count']
        finally:
            conn.close()

    # -----------------------------
    # 아이디 중복 체크
    # -----------------------------
    @staticmethod
    def check_uid_exists(uid): # 입력한 아이디(uid)가 이미 DB에 있는지 확인
        conn = Session.get_connection() # 데이터베이스 연결
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM members WHERE uid=%s", (uid,))
                # member 테이블에서 해당 uid가 있는지 찾음
                return cursor.fetchone() is not None # 중복 아이디 있음
        finally:
            conn.close()

    # -----------------------------
    # 프로필 이미지 저장
    # -----------------------------
    @staticmethod
    def save_profile_file(file):
        # 사용자가 업로드한 파일을 서버의 uploads 폴더에 저장하고 파일명 반환
        os.makedirs("uploads", exist_ok=True)
        # uploads 폴더 없으면 생성 있으면 그냥 넘어감 (에러 안 남)
        filename = secure_filename(file.filename)
        # 업로드 파일 이름을 안전하게 바꿔줌
        file_path = os.path.join("uploads", filename) # 최종 경로: uploads/파일명
        file.save(file_path) # 실제로 서버에 파일 저장됨
        return filename # DB에 저장할 때 사용

    # -----------------------------
    # 회원 정보 수정
    # -----------------------------

    @staticmethod
    def update_member(member_id, new_name=None, new_password=None, new_email=None):
        # 특정 회원의 이름(name)과 비밀번호(password)를 수정
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "UPDATE members SET name=%s, password=%s, email=%s WHERE id=%s"
                # members테이블에서 해당 id회원의 정보를 수정
                cursor.execute(sql, (new_name, new_password,new_email, member_id)) # 전달값
                conn.commit() #DB에 반영됨
        finally:
            conn.close()

    # -----------------------------
    # 마이페이지
    # -----------------------------
    @staticmethod
    # 특정 사용자 1명을 기준으로 필요한 정보 2개(회원정보 + 게시글 수)를 가져옴
    def get_mypage_data(user_id):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 1. 회원 정보 조회
                cursor.execute(
                    "SELECT * FROM members WHERE id = %s",
                    (user_id,)
                )
                user_info = cursor.fetchone() # 한명만 조회

                # 2. 게시글 수 조회
                cursor.execute(
                    "SELECT COUNT(*) as board_count FROM boards WHERE member_id = %s",
                    (user_id,)
                )
                board_count = cursor.fetchone()['board_count'] # 이 사람이 쓴 게시글 개수

                return user_info, board_count # 회원정보랑 게시글 수 같이 반환
        finally:
            conn.close()

    # # 회원 탈퇴
    # @classmethod
    # def delete(cls):
    #     if not Session.is_login() : return
    #     member = Session.login_member
    #
    #     print("\n[회원 탈퇴]\n 1.완전 탈퇴 2.계정 비활성화")
    #     sel = input("선택: ")
    #
    #     conn = Session.get_connection()
    #     try:
    #         with conn.cursor() as cursor:
    #             if sel == "1":
    #                 sql = "DELETE FROM members WHERE id = %s"
    #                 cursor.execute(sql, (member.id,))
    #                 print("회원 탈퇴 완료")
    #             elif sel == "2":
    #                 sql = "UPDATE members SET active = FALSE WHERE id = %s"
    #                 cursor.execute(sql, (member.id,))
    #                 print("계정 비활성화 완료")
    #
    #             conn.commit()
    #             Session.logout()
    #     finally:
    #         conn.close()

    # # -----------------------------
    # # 회원 비활성화/삭제 (app에 안만듬)
    # # -----------------------------
    #
    # @staticmethod
    # def deactivate_or_delete_member(member_id, delete=False):
    #     conn = Session.get_connection()
    #     try:
    #         with conn.cursor() as cursor:
    #             if delete:
    #                 cursor.execute("DELETE FROM members WHERE id=%s", (member_id,))
    #             else:
    #                 cursor.execute("UPDATE members SET active=FALSE WHERE id=%s", (member_id,))
    #             conn.commit()
    #     finally:
    #         conn.close()