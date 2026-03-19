import os
import re
import requests
from github import Github, Auth

# 환경 변수 설정
GH_TOKEN = os.environ.get("GH_TOKEN")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DB_ID = os.environ.get("NOTION_DB_ID")
NOTION_STATUS_DB_ID = os.environ.get("NOTION_STATUS_DB_ID")
REPO_NAME = os.environ.get("REPO_NAME")

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
        
        results = res.json().get('results', [])

        if not results:
            print(f" {match.group()}에 해당하는 페이지가 없습니다.")
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
        print(f" 상태 업데이트 에러 발생: {e}")

def commit_to_notion(msg, author, url, date):
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
        print(f"로그 DB 오류: {e}")

def sync_to_notion():
    print("스크립트 실행 시작")
    print(f"REPO_NAME: {REPO_NAME}")
    print(f"NOTION_DB_ID 수신 여부: {'수신 완료' if NOTION_DB_ID else '미수신'}")
    print(f"NOTION_STATUS_DB_ID 수신 여부: {'수신 완료' if NOTION_STATUS_DB_ID else '미수신'}")
    print(f"GH_TOKEN 수신 여부: {'수신 완료' if GH_TOKEN else '미수신'}")
    print(f"NOTION_TOKEN 수신 여부: {'수신 완료' if NOTION_TOKEN else '미수신'}")

    if not all([GH_TOKEN, NOTION_TOKEN, NOTION_DB_ID, NOTION_STATUS_DB_ID, REPO_NAME]):
        print("하나 이상의 필수 환경변수가 설정되지 않았습니다. 워크플로우를 확인해주세요.")
        return

    try:
        g = Github(auth=Auth.Token(GH_TOKEN))
        repo = g.get_repo(REPO_NAME)
        # 최신 커밋 1개만 가져오기
        latest_commit = repo.get_commits()[0]
       
        msg = latest_commit.commit.message
        print(f"최신 커밋 메시지: {msg}")
        
        commit_to_notion(msg, latest_commit.commit.author.name, latest_commit.html_url, latest_commit.commit.author.date.isoformat())
        update_task_status(msg)
       
    except Exception as e:
        print(f"전체 프로세스 에러: {e}")

if __name__ == "__main__":
    sync_to_notion()
