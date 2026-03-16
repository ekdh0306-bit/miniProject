from LMS.common import Session
from LMS.domain import Member
import pymysql

class MemberService:

    @classmethod
    def load(cls):
        conn = Session.get_connection()  # lms db를 가져와서 conn에 넣음
        try:
            with conn.cursor() as cursor:
                cursor.execute("select count(*) as cnt from members")
                count = cursor.fetchone()['cnt']
                print(f"시스템에 현재 등록된 회원 수는 {count}명 입니다.")

        except Exception as e :
            print(f"MemberService.load()메서드 오류 발생: {e}")
        finally:
            print("데이터베이스 접속 종료됨")
            conn.close()
    @classmethod
    def login(cls):
        print("\n[로그인]")
        uid = input("아이디: ")
        pw = input("비밀번호: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM members WHERE uid = %s AND password = %s"
                print("sql =" + sql)
                cursor.execute(sql, (uid, pw))
                row = cursor.fetchone()

                if row:
                    member = Member.from_db(row)
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

    @classmethod
    def logout(cls):
        if not Session.is_login() :
            print("\n[알림] 현재 로그인 상태가 아닙니다.")
            return

        Session.logout()
        print("\n[성공] 로그아웃 되었습니다. 안녕히 가세요!")

    @classmethod
    def signup(cls):
        print("\n[회원가입]")
        uid = input("아이디: ")
 
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                check_sql = "SELECT id FROM members WHERE uid = %s"
                cursor.execute(check_sql, (uid,))
                if cursor.fetchone():
                    print("이미 존재하는 아이디입니다.")
                    return

                pw = input("비밀번호: ")
                name = input("이름: ")

                insert_sql = "INSERT INTO members (uid, password, name) VALUES (%s,%s, %s)"
                cursor.execute(insert_sql, (uid, pw, name))
                conn.commit()
                print("회원가입 완료! 로그인해 주세요.")
        except Exception as e:
            conn.rollback()
            print(f"회원가입 오류: {e}")
        finally :
            conn.close()

    @classmethod
    def modify(cls):
        if not Session.is_login() :
            print("로그인 후 이용 가능합니다.")
            return

        member = Session.login_member
        print(f"내 정보확인 : {member}")
        print("\n[내 정보 수정]\n 1.이름 변경 2.비밀번호 변경 3.계정비활성 및 탈퇴 0.취소")
        sel = input("선택: ")

        new_name = member.name
        new_pw = member.pw

        if sel == "1":
            new_name = input("새 이름: ")
        elif sel == "2":
            new_pw = input("새 비밀번호: ")
        elif sel == "3":
            print("회원 중지 및 탈퇴를 진행합니다.")
            cls.delete()
        else:
            return

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "UPDATE members SET name = %s, password = %s  WHERE id = %s"
                cursor.execute(sql, (new_name, new_pw, member.id))
                conn.commit()

                member.name = new_name
                member.pw = new_pw
                print("정보 수정 완료")
        finally:
            conn.close()

    @classmethod
    def delete(cls):
        if not Session.is_login() : return
        member = Session.login_member

        print("\n[회원 탈퇴]\n 1.완전 탈퇴 2.계정 비활성화")
        sel = input("선택: ")

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                if sel == "1":
                    sql = "DELETE FROM members WHERE id = %s"
                    cursor.execute(sql, (member.id,))
                    print("회원 탈퇴 완료")
                elif sel == "2":
                    sql = "UPDATE members SET active = FALSE WHERE id = %s"
                    cursor.execute(sql, (member.id,))
                    print("계정 비활성화 완료")

                conn.commit()
                Session.logout()
        finally:
            conn.close()