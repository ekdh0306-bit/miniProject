import json # 탐지결과를 json 딕셔너리타입으로 변환
class AnalysisResult:
    def __init__(self, id, media_id, status, result_json):

        self.id = id
        self.media_id = media_id
        self.status = status # 분석 상태 : 'PENDING', 'SUCCESS', 'FAIL'
        # DB에 JSON 문자열이 존재하면 dict 객체로 역직렬화(Deserialization)
        # 만약 이미 딕셔너리 형태라면 그대로 사용하고, 문자열이면 json.loads 실행
        self.result_json = result_json if isinstance(result_json, dict)  else json.loads(result_json or '{}')

    @classmethod
    def from_db(cls, row: dict):
        # DB에서 조회한 row(dict)데이터를 객체로 변환하는 메서드
        if not row:
            return None
        return cls(
            id=row.get("id"),
            media_id=row.get("media_id"),
            status=row.get("status"),
            result_json=row.get("result_json")
        )