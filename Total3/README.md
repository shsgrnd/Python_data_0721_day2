# Total3 · 분석 자동화 및 HTML 리포트 생성

판매 데이터를 정제·집계하여 Jinja2 기반 HTML 리포트를 생성하고 주기적으로 실행하는 종합 과제입니다.

## 기능

- 불변 설정 객체와 실행 위치에 독립적인 파일 경로
- 판매 데이터 결측값 보정 및 IQR 기반 이상치 처리
- 총매출, 주문수, 평균 주문액과 카테고리별 매출 집계
- Jinja2 템플릿 기반 타임스탬프 HTML 생성
- Plotly 인터랙티브 차트 임베드
- 직접 실행, 경량 루프, `schedule`, OS cron 지원
- SMTP 이메일 첨부 알림
- 실패 시 지수 백오프 재시도

## 구조

```text
Total3/
├─ config.py               # 불변 설정과 경로
├─ report.py               # 정제, 집계, 렌더링, 이메일, 재시도
├─ run_scheduler.py        # once, loop, schedule 실행 진입점
├─ test_report.py          # 확장 기능 단위 테스트
├─ templates/
│  └─ report.html          # Jinja2 템플릿
├─ output/
│  └─ sales_report_*.html  # 생성된 리포트
├─ report.png              # 실행 결과 참고 이미지
├─ report_html.png         # HTML 결과 참고 이미지
└─ README.md
```

## 처리 과정

1. `sales_raw.csv`를 읽고 필수 열을 검증합니다.
2. 음수 단가를 결측값으로 바꾸고 카테고리 중앙값으로 대체합니다.
3. 수량과 단가를 IQR 경계로 원저라이징합니다.
4. `수량 × 단가 × (1 - 할인율)`로 주문별 매출을 계산합니다.
5. KPI와 카테고리별 매출을 집계합니다.
6. Plotly 차트와 집계값을 Jinja2 템플릿에 삽입합니다.
7. 타임스탬프가 붙은 HTML 파일을 `output/`에 저장합니다.
8. SMTP가 설정되어 있으면 HTML 파일을 이메일에 첨부합니다.

모든 실행 방식은 `report.py`의 `run_once()`를 호출하므로 같은 결과를 생성합니다.

## 파일 역할

### `config.py`

`@dataclass(frozen=True)`로 설정 변경을 방지합니다. 데이터, 템플릿과 출력 경로는
`__file__`을 기준으로 계산하므로 어느 디렉터리에서 실행해도 같은 파일을 사용합니다.

이메일 수신자는 다음 주소로 설정되어 있습니다.

```text
hideonbush@faker.com
```

### `report.py`

다음 기능을 담당합니다.

- 데이터 로딩과 정제
- KPI 및 카테고리 집계
- Plotly HTML 조각 생성
- Jinja2 렌더링과 결과 저장
- SMTP 이메일 전송
- 리포트 생성 및 이메일 실패 재시도

Plotly 차트에는 종합 2의 데이터 로딩·검증·전처리 함수와 그래프 구성을 재사용합니다.

```python
from Total2 import capstrone02_eda_ml as total2
```

지수 백오프에는 Practice 3의 설정 상수를 직접 사용합니다.

```python
from practice3 import ex03_async_collector as practice3_retry
```

현재 `MAX_ATTEMPTS=3`, `BACKOFF_SECONDS=0.05`이므로 실패 후 `0.05초`,
다음 실패 후 `0.1초`를 기다립니다.

### `run_scheduler.py`

- `once`: 한 번 실행 후 종료
- `loop`: `time.sleep()` 기반 반복
- `schedule`: `schedule` 라이브러리 기반 반복

### `templates/report.html`

생성 시각, KPI 카드, Plotly 차트와 카테고리별 매출 표를 표현하는 Jinja2 템플릿입니다.

## 실행

프로젝트 루트에서 실행합니다.

### 직접 실행

```powershell
.\.venv\Scripts\python.exe Total3\report.py
```

### 스케줄러 1회 실행

```powershell
.\.venv\Scripts\python.exe Total3\run_scheduler.py --mode once
```

### 경량 반복 루프

실행 직후 한 번 생성하고 이후 60초마다 반복합니다.

```powershell
.\.venv\Scripts\python.exe Total3\run_scheduler.py --mode loop --interval 60
```

`loop`가 기본 모드이므로 다음 명령도 같습니다.

```powershell
.\.venv\Scripts\python.exe Total3\run_scheduler.py --interval 60
```

### schedule 방식

```powershell
.\.venv\Scripts\python.exe Total3\run_scheduler.py --mode schedule --interval 60
```

반복 실행은 `Ctrl+C`로 종료합니다.

### OS cron

Linux 또는 macOS에서는 프로젝트 가상환경 Python의 절대경로를 지정합니다.
다음 예시는 5분마다 실행합니다.

```cron
*/5 * * * * /absolute/path/to/project/.venv/bin/python /absolute/path/to/project/Total3/report.py >> /absolute/path/to/project/Total3/cron.log 2>&1
```

## 이메일 설정

SMTP 접속 정보는 코드에 저장하지 않고 환경변수로 전달합니다.

### STARTTLS

```powershell
$env:SMTP_HOST = "smtp.example.com"
$env:SMTP_PORT = "587"
$env:SMTP_USERNAME = "sender@example.com"
$env:SMTP_PASSWORD = "앱-비밀번호"
$env:SMTP_FROM = "sender@example.com"
$env:SMTP_USE_TLS = "true"
$env:SMTP_USE_SSL = "false"
```

### SSL

```powershell
$env:SMTP_PORT = "465"
$env:SMTP_USE_TLS = "false"
$env:SMTP_USE_SSL = "true"
```

`SMTP_HOST`가 없으면 리포트는 생성되고 이메일만 건너뜁니다. SMTP가 설정되면
생성된 HTML 파일을 `hideonbush@faker.com`으로 첨부 전송합니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s Total3 -p "test_*.py" -v
```

검증 범위:

- 이메일 수신자, TLS 로그인과 HTML 첨부
- Practice 3 재시도 상수 import
- 지수 백오프 대기시간
- 종합 2 Plotly 박스 그래프의 HTML 조각 생성

이메일 테스트는 SMTP 연결을 모의 처리하므로 실제 메일은 발송하지 않습니다.

## 결과

```text
Total3/output/sales_report_YYYYMMDD_HHMMSS_microseconds.html
```

리포트에는 생성 시각, KPI, 이탈 여부별 월 요금 Plotly 차트와 카테고리별 매출 표가 포함됩니다.

## 참고사항

- Plotly JavaScript는 CDN을 사용하므로 차트를 표시할 때 인터넷 연결이 필요합니다.
- 실제 이메일 발송에는 올바른 SMTP 계정과 앱 비밀번호가 필요합니다.
- `hideonbush@faker.com`이 실제 메일함이 아니면 수신 확인이 불가능할 수 있습니다.
