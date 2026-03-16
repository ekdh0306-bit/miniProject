
from LMS.common.Session import Session
from LMS.domain.Member import Member


class MemberService:

    @classmethod
    def login(cls):
        print("\n[로그인]")
        uid = input("아이디: ")
        pw = input("비밀번호: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                sql = "select * from members where uid = %s and pw = %s"
                cursor.execute(sql, (uid, pw))

                row = cursor.fetchone()

                if row:
                    member = Member.from_db(row)

                    if not member.active:
                        print("비활성화된 계정입니다.")
                        return

                    Session.login(member)
                    print(f"{member.name}님 로그인 되었습니다.")

                else:
                    print("아이디 또는 비밀번호가 일치하지 않습니다.")

        except Exception as e:
            print(f"로그인 오류: {e}")

        finally:
            conn.close()


    # 아이디 찾기 기능
    @classmethod
    def find_id(cls):
        print("\n[아이디 찾기]")
        name = input("이름 입력: ")
        email = input("이메일 입력: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                sql = "select uid from members where name = %s and email = %s"
                cursor.execute(sql, (name, email))
                row = cursor.fetchone()

                if row:
                    print(f"회원님의 아이디는 {row['uid']}입니다.")

                else:
                    print("일치하는 회원 정보가 없습니다.")

        finally:
            conn.close()

    # 비밀번호 찾기 / 변경
    @classmethod
    def reset_pw(cls):
        print("\n[비밀번호 변경]")
        uid = input("아이디 입력: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:

                # 아이디가 존재하는지 확인
                sql = "select uid from members where uid = %s"
                cursor.execute(sql, (uid,))
                row = cursor.fetchone()

                if not row:
                    print("존재하지 않는 아이디입니다.")
                    return

                # 새 비밀번호 입력
                new_pw = input("새 비밀번호: ")

                update_sql = "update members set pw = %s where uid = %s"
                # Members 테이블에서 uid가 입력한 uid와 같은 사용자의 비번을 수정해라
                cursor.execute(update_sql, (new_pw, uid))

                conn.commit()
                print("비밀번호가 변경되었습니다.")

        finally:
            conn.close()


    @classmethod
    def logout(cls):

        if not Session.is_login():
            print("로그인 상태가 아닙니다.")
            return

        Session.logout()
        print("로그아웃 되었습니다.")