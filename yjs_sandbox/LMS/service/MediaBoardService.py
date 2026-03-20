from LMS.common.Session import Session
from LMS.domain.MediaBoard import MediaBoard

class MediaBoardService:
    @staticmethod
    def get_analyze_list(user_id):
        """사용자의 전체 분석 내역을 MediaBoard 객체 리스트로 반환합니다."""
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                """ ID 충돌 방지를 위해 별칭(Alias)을 사용한다. 이유는
                MediaFile.from_db와 AnalyzeResult.from_db가 'id'라는 키를 찾기 때문
                """
                sql = """
                    SELECT 
                        m.*, 
                        r.id AS analysis_id, 
                        r.status, 
                        r.result_json
                    FROM media_files m
                    LEFT JOIN analysis_results r ON m.id = r.media_id
                    WHERE m.member_id = %s

                """
                cursor.execute(sql, (user_id,))
                rows = cursor.fetchall()

                boards = [MediaBoard.from_join(row) for row in rows]
                return [board.to_front_dict() for board in boards]

        finally:
            conn.close()