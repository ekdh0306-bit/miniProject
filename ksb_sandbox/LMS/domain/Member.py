class Member:

    def __init__(self, id,  uid, pw, name, email, role="user", active=True, created_at=None):
        self.id = id
        self.uid = uid
        self.pw = pw
        self.name = name
        self.email = email
        self.role = role
        self.active = active
        self.created_at = created_at

    # db에서 가져온 데이터를 Member 객체로 바꾸기 위한 함수
    @classmethod
    def from_db(cls, row: dict):
        # from_db: db에서 데이터를 가져와서 객체로 만든다.
        # row: db에서 가져온 데이터
        if not row: # db에 데이터가 없을 때
            return None # None 반환


        return cls(
            id=row.get("id"),
            uid=row.get("uid"),
            name=row.get("name"),
            email=row.get("email"),
            role=row.get("role"),
            active=bool(row.get("active"))
            # bool: True / False를 변환하는 함수
        )


    def ls_admin(self):
        return self.role == "admin"

    def __str__(self):
        return f"{self.name}({self.uid}) [{self.role}]"