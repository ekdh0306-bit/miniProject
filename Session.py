
class Session:
    login_member = None

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