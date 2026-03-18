import os
import time
import json
import threading
from werkzeug.utils import secure_filename

from LMS.common import Session



class MediaService:
    @staticmethod
    def process_upload(file, user_id, upload_folder):
        """파일 저장 및 DB 초기 레코드 생성"""
        filename = secure_filename(file.filename)
        stored_path = os.path.join(upload_folder, filename)
        os.makedirs(upload_folder, exist_ok=True)
        file.save(stored_path)

        file_type = 'IMAGE' if filename.split('.')[-1].lower() in ['jpg', 'jpeg', 'png', 'gif'] else 'VIDEO'

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 1. media_files 테이블 저장
                sql = "INSERT INTO media_files (member_id, file_name, stored_path, file_type) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (user_id, filename, stored_path, file_type))
                media_id = cursor.lastrowid

                # 2. analysis_results 테이블 초기화
                sql_analysis = "INSERT INTO analysis_results (media_id, status) VALUES (%s, 'PENDING')"
                cursor.execute(sql_analysis, (media_id,))
                conn.commit()

                # 3. 비동기 분석 시작
                thread = threading.Thread(target=MediaService.simulate_ai_analysis, args=(media_id,))
                thread.start()

                return media_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def simulate_ai_analysis(media_id):
        """
        AI 분석을 시뮬레이션하는 함수입니다.
        실제 AI 모델이 없으므로, 5초 동안 기다린 후
        결과를 'SUCCESS'로 업데이트하고 더미 JSON 데이터를 삽입합니다.
    """
        print(f"[{media_id}] AI 분석 시작...")
        time.sleep(5)

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                dummy_result = {
                    "objects": [
                        {"box": [10, 20, 80, 90], "label": "cat", "score": 0.95},
                        {"box": [100, 120, 180, 200], "label": "dog", "score": 0.91}
                    ]
                }
                sql = "UPDATE analysis_results SET status = 'SUCCESS', result_json = %s WHERE media_id = %s"
                cursor.execute(sql, (json.dumps(dummy_result), media_id))
                conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_status(media_id):
        """분석 상태 조회"""
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT status, result_json FROM analysis_results WHERE media_id = %s"
                cursor.execute(sql, (media_id,))
                return cursor.fetchone()
        finally:
            conn.close()