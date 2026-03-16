import pymysql
class Session:
    current_user = None

    @staticmethod
    def get_connection():
        return pymysql.connect(
            host='192.168.0.173',
            user='yjs',
            password='1234',
            db='miniproject',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

    @classmethod
    def check_login(cls, member):
        cls.current_user = member

    @classmethod
    def check_logout(cls):
        cls.current_user = None

    @classmethod
    def is_logged_in(cls): # 현재 로그인 상태인지
        return cls.current_user is not None

    @classmethod
    def is_admin(cls): # 관리자인지 확인
        return cls.is_logged_in() and cls.current_user.role == "admin"

    @classmethod
    def is_manager(cls): # 매니저인지 확인
        return cls.is_logged_in() and cls.current_user.role in ("admin", "manager")

