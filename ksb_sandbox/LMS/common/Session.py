import pymysql

class Session:
    login_member = None

    @staticmethod
    def get_connection():
        print("get_connection()메서드 호출 - mysql에 접속됩니다.")

        return pymysql.connect(
            host='127.0.0.1',
            user='ksb',
            password='1234',
            db='miniproject',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )


    @staticmethod
    def login(member):
        Session.login_member = member

    @staticmethod
    def logout():
        Session.login_member = None

    @staticmethod
    def is_login():
        return Session.login_member is not None

    # 권한 체크 메서드
    @classmethod
    def is_admin(cls): # 관리자일 때
        return cls.is_login() and cls.login_member.role == "admin"

    @classmethod
    def is_manager(cls): # 매니저일 때
        return cls.is_login() and cls.login_member.role in ("manager", "admin")