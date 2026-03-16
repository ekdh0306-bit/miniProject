class Member:
    def __init__(self, id, uid, pw, name, email, role = "user", active = True):

        self.id = id # DB의 PK AUTO_INCREMENT 자동번호를 생성한다
        self.uid = uid
        self.pw = pw
        self.name = name
        self.email = email
        self.role = role
        self.active = active

    @classmethod # self 대신 cls 객체 사용
    def from_db(cls, row = dict): # dict 타입으로 가져와 member 객체로 변환
        if not row:
            return None
        return cls(
            id = row.get("id"),
            uid = row.get("uid"),
            pw=row.get("password"),
            name=row.get("name"),
            email=row.get("email"),
            role = row.get("role"),
            active = bool(row.get("active"))
        )
