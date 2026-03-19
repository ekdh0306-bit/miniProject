class Member:

    def __init__(self, id, uid, pw, name, role="user", active=True, created_at = None):
        self.id = id # DB의 PK -> AUTO_INCREMENT 자동번호 생성
        self.uid = uid
        self.pw = pw
        self.name = name
        self.role = role
        self.active = active
        self.created_at = created_at

    @classmethod # self대신 cls라는 객체를 사용 (주소대신 객체)
    def from_db(cls, row: dict):
        """
        DictCursor로부터 전달받은 딕셔너리 데이터를 Member객체로 변환힙니다.
        """
        if not row: # cls로 전달된 값이 없으면
            return None

        return cls( # db에 있는 정보를 dict 타입으로 받아와 id에 넣음
            id = row.get('id'),
            uid = row.get('uid'),
            pw = row.get('password'),
            name = row.get('name'),
            role = row.get('role'),
            active = row.get('active'), # active : 1 -> True
            created_at = row.get('created_at')
        )
    def is_admin(self):
        return self.role == "admin"

    def __str__(self): # member객체를 문자열로 출력할 때 사용(테스트용)
        return f"{self.name}({self.uid}:{self.pw})[{self.role}]"