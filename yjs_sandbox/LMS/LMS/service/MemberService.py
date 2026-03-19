from LMS.common.Session import Session
from LMS.domain.Member import Member

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
            print('/join 메서드 오류 발생')
            print(f"회원가입 에러: {e}")
            raise e

        finally:
            conn.close() # 데이터 베이스 연결 종료

    @staticmethod
    def login(uid, password):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 보안상 필요한 정보만 가져온다 (id, name, uid, email, role)
                sql = "SELECT id, name, uid, email, role FROM members WHERE uid = %s AND password = %s"
                cursor.execute(sql, (uid, password))
                return cursor.fetchone() # 조회 결과를 하나씩 반환

        except Exception as e:
            print('/login 메서드 오류 발생')
            print(f"로그인 에러:{e}")
            raise e

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

        except Exception as e:
            print('/login 메서드 오류 발생')
            print(e)
            raise e

        finally:
            conn.close()

    @staticmethod
    def update_member(user_id, uid, name, email, password=None):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 비밀번호가 입력되었을 경우와 아닌경우를 구분해서 sql작성
                if password:
                    sql = "UPDATE members SET uid = %s, name = %s, email = %s, password = %s WHERE id = %s"
                    cursor.execute(sql, (uid, name, email, password, user_id ))
                else:
                    sql = "UPDATE members SET uid = %s, name = %s, email = %s WHERE id = %s"
                    cursor.execute(sql, (uid, name, email, user_id))
                # print(f"받은 user_id: {user_id}")
                # print(f"받은 user_id type: {type(user_id)}")
                # print(f"실행 SQL: UPDATE members SET uid = {uid}, name={name}, email = {email} WHERE id = {user_id}") 콘솔에 데이터입력 확인
                conn.commit() # 데이터 변경사항 저장
                return True


        except Exception as e:

            print('/login 메서드 오류 발생')
            print(f"로그인 에러:{e}")
            raise e

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

    # 회원 탈퇴 로직
    @staticmethod
    def delete_member(user_id):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM members WHERE id = %s", (user_id,))
                conn.commit()
                return True

        except Exception as e:
            print(f"회원 탈퇴 중 오류: {e}")

            conn.rollback() # 에러시 롤백
            return False

        finally:
            conn.close()



