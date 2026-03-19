import os
import time
import json
import threading
from werkzeug.utils import secure_filename
import uuid
from LMS.common import Session


class MediafileService:
    @staticmethod
    def mediafile_uploads(file, user_id, upload_folder, config):
        # 1. 파일 확장자 및 타입 판별
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"


        # 2. 파일 타입 판별
        ext = filename.split('.')[-1].lower()
        is_image = ext in ['jpg', 'jpeg', 'png', 'gif']
        file_type = 'IMAGE' if is_image else 'VIDEO'

        # 2. 용량 제한 체크
        limit = config.get('MAX_IMAGE_SIZE') if is_image else config.get('MAX_VIDEO_SIZE')
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # 포인터 초기화

        if file_size > limit:
            limit_mb = limit // (1024 * 1024)
            raise ValueError(f"{file_type} 파일은 {limit_mb}MB를 초과할 수 없습니다.")

        # 3. 물리적 저장
        stored_path = os.path.join(upload_folder, unique_filename)
        os.makedirs(upload_folder, exist_ok=True)
        file.save(stored_path)

        # 4. DB 저장
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO media_files (member_id, file_name, stored_path, file_type) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (user_id, filename, stored_path, file_type))
                media_id = cursor.lastrowid

                cursor.execute("INSERT INTO analysis_results (media_id, status) VALUES (%s, 'PENDING')",
                               (media_id,))
                conn.commit()

                # 5. 비동기 분석 스레드 실행
                # daemon=True: 메인 프로그램 종료 시 스레드도 같이 종료
                thread = threading.Thread(target=MediafileService.simulate_ai_analysis,
                    args=(media_id,),
                    daemon=True)
                thread.start()

                return media_id

        except Exception as e:
            conn.rollback()
            if os.path.exists(stored_path):
                os.remove(stored_path)
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
                print(f"[{media_id}] 분석 완료!")  # ← 추가
        except Exception as e:
            print(f"[{media_id}] 분석 오류: {e}")  # ← 추가
        finally:
            conn.close()

    @staticmethod
    def media_file_update(media_id, user_id, new_file, upload_folder):
        """실제 파일 교체 + DB 정보 갱신 """
        if not new_file or new_file.filename == '':
            return False

        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # 1. 기존 파일 정보 가져오기 (삭제를 위해)
                sql_select = "SELECT stored_path FROM media_files WHERE id = %s AND member_id = %s"
                cursor.execute(sql_select, (media_id, user_id))
                old_row = cursor.fetchone()

                if not old_row:
                    return False  # 권한 없음 혹은 파일 없음

                old_file_path = old_row['stored_path']

                # 2. 새 파일 물리적 저장
                new_safe_filename = secure_filename(new_file.filename)
                new_filename = f"{uuid.uuid4().hex}_{new_safe_filename}"
                new_stored_path = os.path.join(upload_folder, new_filename)

                # 파일명이 겹칠 경우를 대비해 저장 전 체크 (필요시 이름 변경 로직 추가 가능)
                new_file.save(new_stored_path)

                # 3. DB 정보 업데이트 (파일 정보 수정 + 분석 상태 초기화)
                file_type = 'IMAGE' if new_filename.split('.')[-1].lower() in ['jpg', 'jpeg', 'png', 'gif'] else 'VIDEO'

                # media_files 정보 갱신
                sql_update_file = """
                        UPDATE media_files 
                        SET file_name = %s, stored_path = %s, file_type = %s 
                        WHERE id = %s AND member_id = %s
                    """
                cursor.execute(sql_update_file, (new_filename, new_stored_path, file_type, media_id, user_id))

                # 분석 결과를 초기화한다.
                sql_reset_analysis = """
                        UPDATE analysis_results 
                        SET status = 'PENDING', result_json = NULL 
                        WHERE media_id = %s
                    """
                cursor.execute(sql_reset_analysis, (media_id,))

                conn.commit()

                # 4. 이전 물리 파일 삭제 (DB 업데이트 성공 후에 지우는 것이 안전함)
                # 만약 새 파일과 예전 파일의 경로가 같다면 지우면 안 됨!
                if old_file_path != new_stored_path and os.path.exists(old_file_path):
                    os.remove(old_file_path)

                # 5. 새 파일에 대해 AI 분석 다시 시작
                thread = threading.Thread(
                    target=MediafileService.simulate_ai_analysis,
                    args=(media_id,),
                    daemon=True
                )
                thread.start()

                return True

        except Exception as e:
            conn.rollback()
            print(f"파일 교체 중 오류 발생: {e}")
            raise e

    @staticmethod
    def delete_mediafile(media_id, user_id):
        """
        1. DB에서 파일 경로 확인 및 소유권 검증
        2. DB 데이터 삭제 (성공 시 Commit)
        3. 물리적 파일 삭제 (절대 경로 활용)
        """
        conn = Session.get_connection()
        try:
            with conn.cursor() as cursor:
                # [1] 삭제 대상의 'stored_path' 가져오기 (본인 확인 포함)
                sql_select = "SELECT stored_path FROM media_files WHERE id = %s AND member_id = %s"
                cursor.execute(sql_select, (media_id, user_id))
                row = cursor.fetchone()

                if not row:
                    print(f"[삭제 실패] ID {media_id}에 해당하는 파일이 없거나 권한이 없습니다.")
                    return False

                # DB에 저장된 경로를 시스템 절대 경로로 변환 (파이참 동기화 오류 방지)
                file_path = os.path.abspath(row['stored_path'])

                # [2] DB 데이터 삭제 (자식 테이블인 analysis_results부터 삭제)
                cursor.execute("DELETE FROM analysis_results WHERE media_id = %s", (media_id,))
                cursor.execute("DELETE FROM media_files WHERE id = %s AND member_id = %s", (media_id, user_id))

                conn.commit()

                # [3] 물리적 파일 삭제 (DB 삭제가 성공한 후에 수행)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print(f"[삭제 성공] 물리 파일 제거 완료: {file_path}")
                    except OSError as e:
                        # 파일이 다른 프로세스에서 사용 중일 때 등에 대비
                        print(f"[경고] DB는 지워졌으나 파일 삭제 실패: {e}")
                else:
                    print(f"삭제할 파일이 존재하지 않습니다: {file_path}")

                return True

        except Exception as e:
            conn.rollback()  # DB 에러 발생 시 롤백
            print(f"[오류] 파일 삭제 도중 오류 발생: {e}")
            raise e

        finally:
            conn.close()

