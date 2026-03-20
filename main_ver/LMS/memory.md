### `templates/analyze.html`

**1. 서버 -> HTML로 전달되는 변수**

| 변수명 | 설명 |
| --- | --- |
| 없음 | 이 페이지는 `render_template` 호출 시 서버로부터 직접 전달받는 변수가 없습니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| `image_file` | 사용자가 업로드하는 이미지 파일입니다. | POST |
| `video_file` | 사용자가 업로드하는 비디오 파일입니다. | POST |
| `description` | 업로드하는 파일에 대한 메모 또는 설명입니다. | POST |

**3. JavaScript 동작 방식**

*   **타입 전환:** '이미지'와 '영상' 버튼 클릭 시 `toggleUploadType` 함수가 호출되어 해당 업로드 UI(파일 입력, 미리보기)를 보여주거나 숨깁니다.
*   **미리보기:** 사용자가 파일을 선택하면 `previewFile` 함수가 `FileReader`를 사용하여 선택된 이미지나 비디오의 미리보기를 화면에 렌더링합니다.
*   **분석 요청:** '분석 시작' 버튼을 클릭하면 `uploadFileWithProgress` 함수가 실행됩니다. 이 함수는 `FormData` 객체를 생성하여 선택된 파일과 메모 내용을 담고, `XMLHttpRequest`를 통해 `/analyze/result` 엔드포인트로 **POST** 요청을 비동기적으로 보냅니다. 요청이 진행되는 동안 로딩 스피너를 표시하고, 서버로부터 분석 결과를 받으면 해당 내용을 화면에 출력합니다.
*   **상세 페이지 이동:** '자세히 보기' 버튼 클릭 시, `goToDetailPage` 함수는 현재 미리보기 중인 미디어의 소스(src), 메모, 분석 결과 텍스트를 객체로 묶어 `localStorage`에 'temp_analysis_data'라는 키로 저장한 후, `/analyze/analysis` 페이지로 이동시킵니다.

---

### `templates/analyze_analysis.html`

**1. 서버 -> HTML로 전달되는 변수**

| 변수명 | 설명 |
| --- | --- |
| 없음 | 이 페이지는 서버에서 직접 변수를 전달받지 않습니다. 이전 페이지(`analyze.html` 또는 `analyze_list.html`)에서 JavaScript의 `localStorage`를 통해 `type`, `mediaSrc`, `memo`, `result` 데이터를 전달받아 화면에 표시합니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| 없음 | 이 페이지는 서버로 데이터를 전송하는 기능이 없습니다. | N/A |

**3. JavaScript 동작 방식**

*   **데이터 로드:** 페이지가 로드될 때 (`window.onload`), `localStorage`에서 'temp_analysis_data' 키로 저장된 데이터를 읽어옵니다.
*   **콘텐츠 표시:** 읽어온 데이터를 JSON으로 파싱한 후, `type`(image/video)에 따라 미디어(이미지 또는 비디오)를 화면에 렌더링하고, 저장된 메모와 분석 결과를 각각의 요소에 텍스트로 채워 넣어 상세 리포트를 동적으로 완성합니다. 데이터가 없을 경우 경고창을 띄우고 메인 페이지로 이동시킵니다.

---

### `templates/analyze_board.html`

**1. 서버 -> HTML로 전달되는 변수**

| 변수명 | 설명 |
| --- | --- |
| 없음 | 해당 파일은 내용이 거의 비어있으며, `app.py`의 라우트와 연결되어 사용되지 않는 것으로 보입니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| 없음 | 해당 파일은 내용이 비어있습니다. | N/A |

**3. JavaScript 동작 방식**

*   없음

---

### `templates/analyze_list.html`

**1. 서버 -> HTML로 전달되는 변수**

| 변수명 | 설명 |
| --- | --- |
| `analyze_list` | 사용자의 전체 분석 기록 리스트입니다. 각 항목은 분석 상태, 파일 경로, 메모 등의 정보를 포함하는 딕셔너리 객체입니다. |

**2. HTML -> 서버로 전송되는 데이터**

| `name` 속성 | 설명/기능 | 요청 방식(메서드) |
| --- | --- | --- |
| 없음 | 이 페이지는 직접적인 폼 데이터 전송은 없습니다. 각 항목의 삭제 버튼 클릭 시 JavaScript를 통해 `/media/delete/<media_id>` 경로로 **POST** 요청을 보내 해당 항목을 삭제합니다. | POST |

**3. JavaScript 동작 방식**

*   **상세 리포트 이동:** 사용자가 분석 기록 카드 중 하나를 클릭하면 `handleCardClick` 함수가 실행됩니다. 이 함수는 클릭된 카드의 `data-*` 속성(type, path, memo, result) 값을 읽어와 `localStorage`에 'temp_analysis_data'라는 키로 저장한 후, 상세 리포트 페이지인 `/analyze/analysis`로 이동시킵니다.
*   **기록 삭제:** 각 카드의 '삭제' 버튼을 클릭하면 `deleteHistory` 함수가 실행됩니다. 이 함수는 먼저 사용자에게 삭제 여부를 확인하는 `confirm` 대화상자를 띄웁니다. 사용자가 확인을 누르면, JavaScript는 동적으로 `<form>` 요소를 생성하여 `method`를 **POST**로, `action`을 `/media/delete/<media_id>`로 설정한 뒤, 이 폼을 자동으로 제출하여 해당 기록의 삭제를 서버에 요청합니다. `event.stopPropagation()`을 사용하여 카드 클릭 이벤트가 동시에 발생하는 것을 방지합니다.
