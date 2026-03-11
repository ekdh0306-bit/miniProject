import os
import re
import requests
from dotenv import load_dotenv

# 1. 환경 변수 로드
load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
# 깃허브 액션으로부터 커밋 메시지 수신
COMMIT_MESSAGE = os.getenv("COMMIT_MESSAGE", "[MBC-1] 테스트 커밋 #doing")

# 2. 노션 API 헤더 설정
headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 3. 상태 매핑 (노션의 '상태' 컬럼 옵션명과 똑같이 맞추세요)
STATUS_MAP = {
    "#doing": "진행 중",
    "#wip": "진행 중",
    "#done": "완료",
    "#fix": "완료",
    "#review": "검토 중"
}


def get_page_id_by_task_id(task_id_number):
    """MBC-123에서 숫자 123만 받아 노션 페이지 ID를 찾는 함수"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"

    # 노션의 'ID' 속성(Unique ID)을 이용해 필터링
    payload = {
        "filter": {
            "property": "ID",  # ⚠️ 노션 표의 컬럼 이름이 'ID'여야 합니다.
            "unique_id": {
                "equals": int(task_id_number)
            }
        }
    }

    response = requests.post(url, headers=headers, json=payload)

    # 에러 발생 시 로그 출력 (디버깅용)
    if response.status_code != 200:
        print(f"❌ 노션 API 에러: {response.text}")
        return None

    results = response.json().get("results")
    if results:
        return results[0]["id"]
    return None


def update_task_status(page_id, new_status):
    """찾은 노션 페이지의 상태를 변경하는 함수"""
    url = f"https://api.notion.com/v1/pages/{page_id}"

    payload = {
        "properties": {
            "작업 상태": {  # ⚠️ 노션 표의 컬럼 이름이 '작업 상태'여야 합니다.
                "status": {
                    "name": new_status
                }
            }
        }
    }

    response = requests.patch(url, headers=headers, json=payload)
    return response.status_code == 200


def main():
    print(f"🔍 분석 중인 커밋 메시지: {COMMIT_MESSAGE}")

    # 🎯 [핵심 수정] TASK 대신 MBC-숫자 형식을 찾습니다.
    # 대소문자 구분 없이 찾기 위해 .upper()를 적용합니다.
    task_match = re.search(r"MBC-(\d+)", COMMIT_MESSAGE.upper())

    if not task_match:
        print("⏭️ MBC ID 형식을 찾을 수 없어 종료합니다. (예: [MBC-1])")
        return

    # 정규표현식에서 첫 번째 괄호 ( ) 에 잡힌 숫자만 가져옵니다.
    task_number = task_match.group(1)

    # 상태 키워드 추출 (#done 등)
    new_status = None
    msg_lower = COMMIT_MESSAGE.lower()
    for keyword, status_name in STATUS_MAP.items():
        if keyword in msg_lower:
            new_status = status_name
            break

    if not new_status:
        print(f"⏭️ MBC-{task_number} 감지됨. 하지만 상태 변경 키워드가 없어 종료합니다.")
        return

    # 실행
    print(f"⚙️ MBC-{task_number}를 '{new_status}' 상태로 변경 시도 중...")
    page_id = get_page_id_by_task_id(task_number)

    if page_id:
        if update_task_status(page_id, new_status):
            print(f"✅ 성공: MBC-{task_number}가 [{new_status}]로 업데이트되었습니다.")
        else:
            print(f"❌ 실패: 상태 업데이트 API 호출 중 오류가 발생했습니다.")
    else:
        print(f"❌ 실패: 노션 데이터베이스에서 MBC-{task_number}를 찾을 수 없습니다.")


if __name__ == "__main__":
    main()
