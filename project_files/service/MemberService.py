
from project_files.common.session import Session
from project_files.domain.Member import Member


class MemberService:
    @staticmethod
    def join(uid, password, name, email):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO members (uid, password, name, email) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (uid, password, name, email))
                conn.commit()
                return True
        except Exception as e:  # 예외발생시 실행문
            print(f"회원가입 에러: {e}")
            return "가입 도중 오류가 발생하였습니다. join 메서드를 확인하세요"
        finally:
            conn.close() # 데이터 베이스 연결 종료

    @staticmethod
    def check_login(uid, upw):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 보안상 필요한 정보만 가져온다 (id, name, uid, role)
                sql = "SELECT id, name, uid, role FROM members WHERE uid = %s AND password = %s"
                cursor.execute(sql, (uid, upw))
                return cursor.fetchone() # 조회 결과를 하나씩 반환
        finally:
            conn.close()

    @staticmethod
    def is_duplicate_uid(uid):
        """
                아이디 중복 여부 확인
                uid: 중복 체크할 아이디
                return: 중복이면 True, 사용 가능하면 False
                """
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM members WHERE uid = %s", (uid,))
                # 결과가 존재하면(is not None) True 반환
                return cursor.fetchone() is not None
        finally:
            conn.close()

    @staticmethod
    def update_member(user_id, name, email,password=None):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 비밀번호가 입력되었을 때와 아닐 때를 구분해서 sql작성
                if password:
                    sql = "UPDATE members SET name = %s, password = %s, email = %s WHERE id = %s"
                    cursor.execute(sql, (name, password, email, user_id))
                else:
                    sql = "UPDATE members SET name = %s, email = %s WHERE id = %s"
                    cursor.execute(sql, (name, email, user_id))
                conn.commit() # 데이터 변경사항 저장
                return True

        except Exception as e:  # 예외발생시 실행문
            print(f"회원수정 에러:{e}")
            return False

        finally:
            conn.close()

    @staticmethod
    def get_user_info(user_id):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM members WHERE id = %s", (user_id,))

                row = cursor.fetchone()
                return Member.from_db(row)
        finally:
            conn.close()



