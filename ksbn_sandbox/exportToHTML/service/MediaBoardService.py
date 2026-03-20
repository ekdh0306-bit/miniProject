from common.Session import Session
from domain.MediaBoard import MediaBoard

class MediaBoardService:
    @staticmethod
    def get_analyze_list(user_id):
        """사용자의 전체 분석 내역을 MediaBoard 객체 리스트로 반환합니다."""
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 💡 m.id를 'id'로 명시하고, 결과 테이블의 id는 'analysis_id'로 분리합니다.
                sql = """
                    SELECT 
                        m.id, 
                        m.file_path, 
                        m.file_type, 
                        m.description, 
                        m.created_at,
                        r.id AS analysis_id, 
                        r.status, 
                        r.result_json
                    FROM media_files m
                    LEFT JOIN analysis_results r ON m.id = r.media_id
                    WHERE m.member_id = %s
                    ORDER BY m.id DESC
                """
                cursor.execute(sql, (user_id,))
                rows = cursor.fetchall()

                # row 데이터 확인용 로그 (디버깅 시 주석 해제)
                # print(f"DEBUG: first row keys -> {rows[0].keys() if rows else 'No data'}")

                return [MediaBoard.from_join(row) for row in rows]
        finally:
            conn.close()