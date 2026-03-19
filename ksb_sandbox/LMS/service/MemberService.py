
from LMS.common.Session import Session
from LMS.domain.Member import Member


class MemberService:

    # 로그인
    @classmethod
    def login(cls):
        print("\n[로그인]")
        uid = input("아이디: ")
        password = input("비밀번호: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                sql = "select * from members where uid = %s and password = %s"
                cursor.execute(sql, (uid, password))

                row = cursor.fetchone()

                if row:
                    member = Member.from_db(row) # db에서 가져온 데이터를 Member 객체로 변환

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


    # 아이디 찾기 기능///
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

    # 비밀번호 찾기 / 변경///
    @classmethod
    def reset_password(cls):
        print("\n[비밀번호 변경]")
        uid = input("아이디 입력: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:

                # 아이디가 존재하는지 확인
                sql = "select uid from members where uid = %s"
                # members 테이블에서 uid가 입력한 uid와 같은 회원의 uid를 가져온다.
                cursor.execute(sql, (uid,))
                # 위에서 만든 sql문을 실행하면서 %s 자리에 uid 값을 넣어라
                row = cursor.fetchone() # sql 실행 결과 중에서 한 행을 가저와서 row 변수에 넣는다.

                if not row:
                    print("존재하지 않는 아이디입니다.")
                    return

                # 새 비밀번호 입력
                new_password = input("새 비밀번호: ")

                sql = "update members set password = %s where uid = %s"
                # Members 테이블에서 uid가 입력한 uid와 같은 사용자의 비번을 수정해라
                cursor.execute(sql, (new_password, uid))
                conn.commit()
                print("비밀번호가 변경되었습니다.")

        finally:
            conn.close()


    # 로그아웃
    @classmethod
    def logout(cls):

        if not Session.is_login():
            print("로그인 상태가 아닙니다.")
            cls.login() # 로그인 페이지로 이동
            return

        Session.logout()
        print("로그아웃 되었습니다.")


    # 회원가입
    @classmethod
    def signup(cls):
        print("\n[회원가입]")
        uid = input("아이디: ")

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 1. 중복 체크
                check_sql = "SELECT id FROM members WHERE uid = %s"
                cursor.execute(check_sql, (uid,))
                if cursor.fetchone():
                    print("이미 존재하는 아이디입니다.")
                    return

                password = input("비밀번호: ")
                name = input("이름: ")
                email = input("이메일: ")

                # 2. 데이터 삽입
                insert_sql = "INSERT INTO members (uid, password, name, email) VALUES (%s, %s, %s, %s)"
                cursor.execute(insert_sql, (uid, password, name, email))
                conn.commit()
                print("회원가입 완료! 로그인해 주세요.")
        except Exception as e:
            conn.rollback()
            print(f"회원가입 오류: {e}")
        finally:
            conn.close()


    # 회원 수정
    @classmethod
    def modify(cls):
        if not Session.is_login():
            print("로그인 후 이용 가능합니다.")
            return

        member = Session.login_member
        print(f"내정보확인 : {member}")  # Member.__str__()
        print("\n[내 정보 수정]\n1. 이름 변경  2. 비밀번호 변경 3. 탈퇴 0. 취소")
        sel = input("선택: ")

        new_name = member.name
        new_password = member.password

        if sel == "1":
            new_name = input("새 이름: ")
        elif sel == "2":
            new_password = input("새 비밀번호: ")
        elif sel == "3":
            print("탈퇴를 진행합니다.")
            cls.delete()
        else:
            return

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "UPDATE members SET name = %s, password = %s WHERE id = %s"
                cursor.execute(sql, (new_name, new_password, member.id))
                conn.commit()

                # 메모리(세션) 정보도 동기화
                member.name = new_name
                member.password = new_password
                print("정보 수정 완료")
        finally:
            conn.close()


    # 탈퇴
    @classmethod
    def delete(cls):
        if not Session.is_login():
            print("로그인이 필요합니다.")
            cls.login()  # 로그인 페이지로 이동
            return

        member = Session.login_member
        print("\n[회원 탈퇴]\n1.탈퇴하기\n2.계정 비활성화")
        sel = input("선택: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                if sel == "1":
                    sql = "delete from members where uid = %s"
                    cursor.execute(sql, (member.uid,))
                    conn.commit()
                    Session.logout()
                    print("탈퇴가 완료되었습니다.")
                    return

                elif sel == "2":
                    sql = "update members set active = False where uid = %s"
                    cursor.execute(sql, (member.uid,))
                    conn.commit()
                    Session.logout()
                    print("계정이 비활성화 되었습니다.")
                    return

                else:
                    print("잘못된 선택입니다.")

        finally:
            conn.close()


# ----------------------------------------------------------------------------------------------------------------------------------------------

    # 관리자
    @classmethod
    def admin_menu(cls):
        if not Session.is_login() or not Session.login_member.is_admin():
        # 로그인이 되어있지 않거나 권한이 관리자가 아닐 때
            print("관리자만 접근 가능합니다.")
            return

    # 회원 검색 기능
    @classmethod
    def search_member(cls):
        print("\n[회원 검색]")
        uid = input("검색 할 아이디: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                sql = "select uid, name, email, active from members where uid = %s"
                # members 테이블에서 uid가 입력한 uid와 같은 사용자의 uid, name, email, active를 가져온다.
                cursor.execute(sql, (uid,))
                row = cursor.fetchone()

                if row:
                    print("아이디: ", row["uid"])
                    print("이름: ", row["name"])
                    print("이메일: ", row["email"])
                    print("계정 활성화: ", row["active"])

                else:
                    print("회원이 존재하지 않습니다.")
                    return

        finally:
            conn.close()


    # 권한 변경
    @classmethod
    def change_role(cls):
        uid = input("아이디: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                sql = "select uid, role from members where uid = %s"
                # members 테이블에서 uid가 입력한 uid와 같은 회원에 아이디와 권한을 가져온다.
                cursor.execute(sql, (uid,))
                row = cursor.fetchone()

                if row:
                    new_role = input("admin / manager / user: ")
                    sql = "update members set role = %s where uid = %s"
                    # members 테이블에서 uid가 입력한 uid와 같은 회원에 권한을 수정한다.
                    cursor.execute(sql, (new_role, uid))
                    conn.commit() # db에 저장
                    print("권한 변경이 완료되었습니다.")
                    return

                else:
                    print("회원이 존재하지 않습니다.")

        finally:
            conn.close()


    # 블랙리스트 처리
    @classmethod
    def block_member(cls):
        uid = input("아이디: ")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                sql = "select uid, active from members where uid = %s"
                cursor.execute(sql, (uid,))
                row = cursor.fetchone()

                if row:
                    sql = "update members set active = False where uid = %s"
                    cursor.execute(sql, (uid,))
                    conn.commit()
                    print("블랙리스트로 변경되었습니다.")
                    return

                else:
                    print("회원이 존재하지 않습니다.")

        finally:
            conn.close()


    # 전체 회원 목록 조회
    @classmethod
    def member_list(cls):
        if not Session.is_login() or not Session.login_member.is_admin():
            print("관리자만 접근 가능합니다.")
            return

        print("\n[회원 목록]")

        conn = Session.get_connection()

        try:
            with conn.cursor() as cursor:
                sql = "select uid, name, email, active from members"
                # members 테이블에서 회원의 아이디, 이름, 이메일, 활성화 여부를 가져온다.
                cursor.execute(sql)
                rows = cursor.fetchall() # 여러개의 결과가 나옴

                for r in rows:
                    print(r["uid"], r["name"], r["email"], r["active"])

        finally:
            conn.close()