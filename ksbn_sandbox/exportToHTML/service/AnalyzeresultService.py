import json

from common.Session import Session
from domain.AnalysisResult import AnalysisResult


class AnalyzeresultService:
    @staticmethod
    def get_formatted_result(result_json_str):
        """JSON 문자열을 프론트에서 바로 보여줄 수 있는 텍스트로 변환"""
        if not result_json_str:
            return "분석 결과가 없습니다."

        try:
            data = json.loads(result_json_str)  # DB의 JSON 문자열을 다시 딕셔너리로
            objects = data.get('objects', [])

            if not objects:
                return "검출된 객체가 없습니다."

            # 프론트엔드에 보여줄 텍스트 직접 구성
            lines = []
            for i, obj in enumerate(objects, 1):
                line = f"[{i}] {obj['label']} (신뢰도: {obj['score'] * 100:.1f}%)"
                lines.append(line)

            return "\n".join(lines)  # 줄바꿈 문자로 합쳐서 '하나의 문자열'로 반환
        except Exception:
            return "데이터 형식 오류"
    @staticmethod
    def get_status(media_id):
        """단순 상태 확인 (객체 반환)"""
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM analysis_results WHERE media_id = %s"
                cursor.execute(sql, (media_id,))
                row = cursor.fetchone()

                # dict를 AnalysisResult 객체로 변환해서 반환한다
                return AnalysisResult.from_db(row)
        finally:
            conn.close()

    @staticmethod
    def get_analysis_detail(media_id):
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                        SELECT m.*, r.status, r.result_json 
                        FROM media_files m
                        JOIN analysis_results r ON m.id = r.media_id
                        WHERE m.id = %s
                    """
                cursor.execute(sql, (media_id,))
                row = cursor.fetchone()

                # 수정: raw dict 대신 MediaBoard 객체로 변환하여 반환
                from domain.MediaBoard import MediaBoard
                return MediaBoard.from_join(row) if row else None
        finally:
            conn.close()