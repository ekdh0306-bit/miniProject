import os
import re
import requests

# 환경 변수 설정
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DB_ID = os.environ.get("NOTION_DB_ID")
NOTION_STATUS_DB_ID = os.environ.get("NOTION_STATUS_DB_ID")
REPO_NAME = os.environ.get("REPO_NAME")
# 워크플로우에서 직접 전달받는 커밋 정보
COMMIT_MESSAGE = os.environ.get("COMMIT_MESSAGE")
COMMIT_AUTHOR = os.environ.get("COMMIT_AUTHOR")
COMMIT_URL = os.environ.get("COMMIT_URL")
COMMIT_DATE = os.environ.get("COMMIT_DATE")

STATUS_MAP = {
    "#idea": "아이디어",
    "#coding": "코딩중",
    "#review": "검토중",
    "#debug": "디버깅중",
    "#done": "완료"
}

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def update_task_status(msg):
    # 이 함수는 커밋 메시지를 분석하여 Notion DB의 작업 상태를 업데이트합니다.
    # 1. 커밋 메시지에서 상태 태그(예: #coding)와 작업 번호(예: STA-123)를 찾습니다.
    # 2. 작업 번호를 이용해 Notion 상태 관리 DB에서 해당 페이지를 쿼리합니다.
    # 3. 쿼리 성공 시, 찾은 페이지의 '상태' 속성을 커밋 메시지의 태그에 맞게 변경합니다.
    found_status = next((status for key, status in STATUS_MAP.items() if key in msg), None)
    match = re.search(r'STA-(\d+)', msg)
   
    if not found_status or not match:
        print("커밋 메시지에서 상태 태그 또는 작업 번호를 찾을 수 없습니다.")
        return

    task_number = match.group(1) # 숫자만 추출 (예: 5)
    clean_db_id = NOTION_STATUS_DB_ID.strip().replace("-", "")
   
    try:
        # [최적화] 필터링을 통해 해당 ID를 가진 페이지만 즉시 조회
        query_url = f"https://api.notion.com/v1/databases/{clean_db_id}/query"
        filter_payload = {
            "filter": {"property": "ID", "unique_id": {"equals": int(task_number)}}
        }
        print(f"상태 DB 조회 요청: {query_url}")
        print(f"상태 DB 필터: {filter_payload}")
       
        res = requests.post(query_url, headers=HEADERS, json=filter_payload)
        print(f"상태 DB 조회 응답 코드: {res.status_code}")
        
        # 디버깅 코드 추가: API 응답이 성공(200)이 아닐 경우, 상세 오류 메시지를 출력하고 종료합니다.
        # 이 코드는 Notion API가 왜 요청을 거부했는지 정확한 원인을 파악하기 위해 필수적입니다.
        if res.status_code != 200:
            print("!!! Notion API 오류 발생 !!!")
            print(f"오류 코드: {res.status_code}")
            print(f"상세 메시지: {res.text}")
            return
        
        results = res.json().get('results', [])

        if not results:
            # API 요청은 성공했으나, 조건에 맞는 페이지를 찾지 못한 경우입니다.
            print(f"'{match.group()}'에 해당하는 페이지를 Notion 상태 데이터베이스에서 찾을 수 없습니다. (API 조회는 성공했으나 결과가 없음)")
            print("페이지가 실제로 존재하고, 'ID' 속성에 올바른 값이 있는지 확인해주세요.")
            return

        target_page_id = results[0]['id']
       
        # 상태 업데이트
        update_url = f"https://api.notion.com/v1/pages/{target_page_id}"
        update_payload = {
            "properties": {"상태": {"status": {"name": found_status}}}
        }
        print(f"상태 업데이트 요청: {update_url}")
        print(f"상태 업데이트 페이로드: {update_payload}")
       
        res_up = requests.patch(update_url, headers=HEADERS, json=update_payload)
        if res_up.status_code == 200:
            print(f"[{match.group()}] 상태 업데이트 완료: {found_status}")
        else:
            print(f" 상태 업데이트 실패: {res_up.text}")
           
    except Exception as e:
        print(f" 상태 업데이트 처리 중 예외 발생: {e}")

def commit_to_notion(msg, author, url, date):
    # 이 함수는 새로운 커밋 정보를 Notion 로그 DB에 페이지로 생성합니다.
    try:
        clean_log_db_id = NOTION_DB_ID.strip().replace("-", "")
        create_url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {"database_id": clean_log_db_id},
            "properties": {
                "Name": {"title": [{"text": {"content": msg}}]},
                "Author": {"rich_text": [{"text": {"content": author}}]},
                "URL": {"url": url},
                "Date": {"date": {"start": date}}
            }
        }
        print(f"로그 DB 생성 요청: {create_url}")
        print(f"로그 DB 페이로드: {payload}")
        
        res = requests.post(create_url, headers=HEADERS, json=payload)
        if res.status_code == 200:
            print(f"[로그 DB] 기록 완료")
        else:
            print(f"[로그 DB] 기록 실패: {res.text}")
            
    except Exception as e:
        print(f"로그 DB 기록 중 예외 발생: {e}")

def sync_to_notion():
    print("스크립트 실행 시작")
    print(f"REPO_NAME: {REPO_NAME}")
    print(f"NOTION_DB_ID 수신 여부: {'수신 완료' if NOTION_DB_ID else '미수신'}")
    print(f"NOTION_STATUS_DB_ID 수신 여부: {'수신 완료' if NOTION_STATUS_DB_ID else '미수신'}")
    print(f"NOTION_TOKEN 수신 여부: {'수신 완료' if NOTION_TOKEN else '미수신'}")

    # 필수 환경변수 확인 (워크플로우에서 전달되는 커밋 정보 포함)
    required_vars = [NOTION_TOKEN, NOTION_DB_ID, NOTION_STATUS_DB_ID, REPO_NAME, COMMIT_MESSAGE, COMMIT_AUTHOR, COMMIT_URL, COMMIT_DATE]
    if not all(required_vars):
        print("하나 이상의 필수 환경변수가 설정되지 않았습니다. 워크플로우를 확인해주세요.")
        return

    try:
        print(f"처리할 커밋 메시지: {COMMIT_MESSAGE}")
        
        # Notion DB에 커밋 로그 기록
        commit_to_notion(COMMIT_MESSAGE, COMMIT_AUTHOR, COMMIT_URL, COMMIT_DATE)
        # 커밋 메시지 분석 후 Notion 상태 DB 업데이트
        update_task_status(COMMIT_MESSAGE)
       
    except Exception as e:
        print(f"전체 프로세스 에러: {e}")

if __name__ == "__main__":
    sync_to_notion()
