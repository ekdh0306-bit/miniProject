# -*- coding: utf-8 -*-
import re

def extract_google_drive_file_ids(urls):
    """
    Google Drive URL 목록에서 파일 ID를 추출합니다.

    Args:
        urls: Google Drive URL의 리스트입니다.

    Returns:
        추출된 파일 ID의 리스트입니다.
    """
    # file/d/ 뒤에 오는 파일 ID를 캡처하는 정규식입니다.
    # 이 정규식은 영숫자, 밑줄(_), 하이픈(-)을 포함하는 ID를 처리할 수 있습니다.
    regex = r"file/d/([a-zA-Z0-9_-]+)"
    file_ids = []
    for url in urls:
        # 정규식과 매치되는 부분을 찾습니다.
        match = re.search(regex, url)
        if match:
            # 첫 번째 캡처 그룹(파일 ID)을 리스트에 추가합니다.
            file_ids.append(match.group(1))
    return file_ids

if __name__ == "__main__":
    # 여기에 구글 드라이브 URL 리스트를 입력하세요.
    # 예: "https://docs.google.com/document/d/1AbC-dE2fGh3iJkL4mN5oPqRs6tUvWxYz/edit?usp=sharing"
    google_drive_urls = ["https://drive.google.com/file/d/15dF4dCESMExb501-eVJa7SjqjQyfpFX8/view?usp=drive_link"]
    if not google_drive_urls:
        print("URL 리스트가 비어있습니다. 'google_drive_urls' 리스트에 URL을 추가해주세요.")
    else:
        # 함수를 호출하여 파일 ID를 추출합니다.
        ids = extract_google_drive_file_ids(google_drive_urls)
        
        # 추출된 ID를 출력합니다.
        if ids:
            # 큰따옴표로 각 ID를 묶고 쉼표와 공백으로 구분하여 한 줄로 출력합니다.
            formatted_ids = [f'"{file_id}"' for file_id in ids]
            print(", ".join(formatted_ids))
        else:
            print("ID를 추출할 수 있는 유효한 URL이 리스트에 없습니다.")