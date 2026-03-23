## [공통 전역 객체 및 유틸리티]

모든 템플릿(`layout.html` 포함)에서 별도의 서버 인자 전달 없이 기본적으로 접근 가능한 데이터와 함수입니다.

| 객체/함수명 | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| `session` | `user_id`, `user_name`, `user_role`, `user_email` | 서버 세션에 저장된 로그인 사용자 정보입니다. (브라우저 쿠키 기반) |
| `request` | `request.path` | 현재 요청된 URL 경로 정보입니다. |
| `get_flashed_messages` | (카테고리, 메시지) | Flask의 `flash()` 함수로 전송된 일회성 알림 메시지 리스트입니다. |
| `url_for` | (함수명, 인자) | 라우트 함수명을 기반으로 URL을 생성하는 유틸리티입니다. |

---

### `templates/layout.html` (공통 레이아웃)

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| 없음 | 레이아웃은 전역 객체(`session`, `get_flashed_messages`)만 사용합니다. | N/A |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| 없음 | 레이아웃 파일은 직접 데이터를 전송하지 않습니다. | N/A |

---

### `templates/menu_layout.html` (메뉴 포함 레이아웃)

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| 없음 | 메뉴 레이아웃은 전역 객체(`session`, `request`)만 사용합니다. | N/A |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| 없음 | 레이아웃 파일은 직접 데이터를 전송하지 않습니다. | N/A |

---

### `templates/main.html`

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| `user_image_path` | (객체 전체 사용) | (현재 라우트 미전달) 실시간 분석 결과 예시 이미지를 출력합니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| 없음 | 메인 페이지는 직접 데이터를 전송하지 않습니다. | N/A |

---

### `templates/login.html`

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| `error` | (객체 전체 사용) | 로그인 실패 시 서버에서 전달한 에러 메시지를 표시합니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| `uid` | 아이디 입력 필드입니다. | POST |
| `pw` | 비밀번호 입력 필드입니다. | POST |

---

### `templates/join.html`

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| 없음 | 서버로부터 전달받아 사용하는 별도 변수가 없습니다. | N/A |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| `uid` | 회원가입할 아이디입니다. | POST |
| `email` | 회원가입할 이메일 주소입니다. | POST |
| `username` | 사용자의 실제 이름입니다. | POST |
| `pw` | 사용할 비밀번호입니다. | POST |
| `confirm_password` | 비밀번호 확인 필드입니다. | POST (클라이언트 검증용) |

---

### `templates/member_edit.html`

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| `user` | `user.uid`, `user.name`, `user.email` | (현재 HTML 미사용 중이나 서버에서 전달함) 기존 회원 정보를 폼에 미리 채우는 용도입니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| `new_uid` | 변경할 새 아이디입니다. | POST |
| `new_name` | 변경할 새 이름입니다. | POST |
| `pw` | 변경할 새 비밀번호입니다. | POST |
| `email` | 변경할 새 이메일 주소입니다. | POST |

---

### `templates/mypage.html`

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| `user` | `user.uid`, `user.name`, `user.email` | 현재 로그인된 사용자의 상세 정보를 표시합니다. |
| `analysis_results` | `result.id`, `result.status`, `result.uploaded_at`, `result.memo` | 최근 5개의 분석 기록 리스트를 반복문으로 순회하며 표시합니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| 없음 | 마이페이지는 직접 데이터를 전송하지 않습니다. | N/A |

---

### `templates/analyze.html`

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| 없음 | 해당 페이지는 서버로부터 직접 변수를 전달받지 않습니다. | N/A |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| `image_file` | 업로드할 이미지 파일 객체입니다. | POST |
| `video_file` | 업로드할 영상 파일 객체입니다. | POST |
| `description` | 사용자가 입력한 메모 내용입니다. | POST |

---

### `templates/analyze_list.html`

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| `analyze_list` | `item.id`, `item.file_type`, `item.stored_path`, `item.memo`, `item.result_json`, `item.uploaded_at`, `item.status` | 전체 분석 기록 리스트를 그리드 형태로 표시하고 삭제/상세보기 기능에 필요한 데이터를 제공합니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| `mediaId` (경로변수) | 삭제 버튼 클릭 시 `/media/delete/<mediaId>` 경로로 전달되어 해당 기록을 삭제합니다. | POST |

---

### `templates/analyze_analysis.html`

**1. 서버 -> HTML (직접 전달 인자)**

| 전달 변수명 (서버) | 상세 사용 속성 (HTML) | 설명 |
| --- | --- | --- |
| `analysis_data` | `analysis_data.stored_path`, `analysis_data.file_type`, `analysis_data.memo`, `analysis_data.formatted_result` | 특정 분석 건에 대한 상세 결과 리포트를 구성하는 데 사용됩니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| 없음 | 상세 페이지는 서버로 데이터를 전송하는 기능이 없습니다. | N/A |
