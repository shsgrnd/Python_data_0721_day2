# SKALA Python 데이터 처리 실습

Python을 이용한 데이터 수집, 검증, 정제, 대용량 집계, 머신러닝 및 자동화 리포트 생성을 단계적으로 다루는 실습 프로젝트입니다.

기초 실습 5개와 종합 과제 3개를 중심으로 구성되어 있으며, `Advanced`에는 비동기 API 파이프라인과 데이터 분석 심화 예제가 들어 있습니다.

## 프로젝트 구조

```text
Python_data_0721_day2/
├─ Advanced/
│  ├─ day1/                     # 비동기 공개 API 수집·검증·저장
│  └─ day2/                     # 데이터 엔진 비교, EDA, 통계, ML
├─ data/
│  ├─ 0720/                     # Practice 1·2가 참조하는 경로
│  ├─ 0721/                     # 공용 합성 데이터와 생성 스크립트
│  └─ lecture/                  # Advanced day2 판매 데이터 경로
├─ practice1/                   # 제너레이터 기반 로그 스트리밍
├─ practice2/                   # Pydantic 중첩 JSON 검증
├─ practice3/                   # 비동기 수집과 지수 백오프
├─ practice4/                   # Pandas 데이터 정제
├─ practice5/                   # Pandas·Polars·DuckDB 성능 비교
├─ Total1/                      # 비동기 ETL 파이프라인
├─ Total2/                      # EDA·통계 검정·머신러닝
├─ Total3/                      # 자동화 HTML 리포트와 스케줄링
├─ requirements.txt
└─ README.md
```

실행 결과 이미지, HTML, CSV, Parquet 및 모델 파일은 각 과제 디렉터리 또는 그 아래 `output/`에 저장됩니다.

## 실습 구성

| 구분 | 주제 | 핵심 기술 | 주요 결과 |
|---|---|---|---|
| Practice 1 | 대용량 로그 스트리밍 | generator, `Counter`, `reduce`, `tracemalloc` | 요청 통계와 메모리 비교 |
| Practice 2 | JSON 스키마 검증 | Pydantic v2, 중첩 모델, validator | 유효·무효 사용자 분리 |
| Practice 3 | 비동기 수집 | `asyncio`, 동시성 제한, timeout, 지수 백오프 | 성공 데이터와 dead letter |
| Practice 4 | 판매 데이터 정제 | Pandas, 결측값 대치, IQR 원저라이징 | 정제 데이터와 그룹 집계 |
| Practice 5 | 대용량 집계 비교 | Pandas, Polars Lazy API, DuckDB SQL | 동일성 검증과 실행시간 비교 |
| Total 1 | 비동기 ETL | Extract·Transform·Load, Pydantic, CSV/Parquet | 상품 데이터 파이프라인 |
| Total 2 | 이탈 분석과 예측 | Plotly, 통계 검정, sklearn Pipeline | HTML 차트와 ML 모델 |
| Total 3 | 리포트 자동화 | Jinja2, Plotly, schedule, cron, SMTP | 자동 생성 HTML 리포트 |

## Practice 1 · 로그 스트리밍

파일: `practice1/ex01_streaming_egg.py`

웹 로그를 한 행씩 읽는 제너레이터를 사용하여 다음 항목을 집계합니다.

- 전체 요청 수와 5xx 오류율
- 인기 경로 상위 5개
- 시간대별 요청 수
- 접속 IP 상위 5개
- `readlines()`와 제너레이터 방식의 최대 메모리 비교

```powershell
python practice1\ex01_streaming_egg.py
```

## Practice 2 · Pydantic 검증

파일: `practice2/ex02_pydantic.py`

중첩된 사용자 JSON을 `UserRecord`와 `Profile` 모델로 검증합니다. 숫자 범위,
회원 등급, 이메일 형식을 확인하고 실패한 레코드의 위치와 원인을 출력합니다.

```powershell
python practice2\ex02_pydantic.py
```

## Practice 3 · 비동기 수집과 재시도

파일: `practice3/ex03_async_collector.py`

`asyncio.Semaphore`로 동시 요청 수를 제한하고, timeout과 지수 백오프를 적용합니다.
최종 실패 데이터는 `practice3/dead_letter.json`에 저장합니다. 기본값은 네트워크가
필요 없는 모의 요청이며, `USE_REAL_HTTP=True`로 변경하면 실제 HTTP 요청을 사용합니다.

```powershell
python practice3\ex03_async_collector.py
```

## Practice 4 · Pandas 데이터 정제

파일: `practice4/ex04_pandas_cleaning.py`

음수 단가를 결측값으로 변환하고 카테고리 중앙값으로 대치합니다. IQR로 계산한
경계에 맞춰 단가와 수량을 원저라이징하고, 정제 규칙을 새 데이터에도 동일하게
적용합니다. 카테고리 집계와 카테고리·지역 교차표도 생성합니다.

```powershell
python practice4\ex04_pandas_cleaning.py
```

## Practice 5 · 데이터 엔진 비교

파일: `practice5/ex05_polars_duckdb.py`

대용량 이벤트 CSV에서 구매와 환불 이벤트를 필터링하고 건수 및 평균 금액을 집계합니다.
Pandas, Polars Lazy API, DuckDB SQL 결과가 같은지 검증한 뒤 평균 실행시간을 비교합니다.

```powershell
python practice5\ex05_polars_duckdb.py
```

## Total 1 · 비동기 ETL 파이프라인

주요 파일:

- `Total1/models.py`: Pydantic 상품 모델
- `Total1/pipeline.py`: 비동기 Extract, 검증 Transform, CSV/Parquet Load
- `Total1/test_pipeline.py`: 데이터 변환과 저장 테스트

수집 실패와 검증 실패를 분리하며, 정상 상품은 CSV와 Parquet으로 저장한 뒤
Parquet 라운드트립 건수를 검증합니다.

```powershell
python Total1\pipeline.py
python -m pytest Total1\test_pipeline.py -v
```

## Total 2 · EDA, 통계 검정 및 머신러닝

파일: `Total2/capstrone02_eda_ml.py`

통신사 고객 이탈 데이터를 대상으로 다음 작업을 수행합니다.

- Polars 데이터 로딩 및 분석 열 정규화
- 이탈 여부별 월 요금 Plotly 박스 그래프
- 이탈·비이탈 집단의 Welch t-test
- 계약 유형과 이탈 여부의 카이제곱 검정
- 수치형·범주형 전처리를 포함한 sklearn Pipeline
- Random Forest 분류와 ROC-AUC 평가
- 학습 모델을 `joblib` 파일로 저장

```powershell
python Total2\capstrone02_eda_ml.py
```

결과는 `Total2/output/churn_charges.html`과 `Total2/output/ml_pipeline.joblib`에 저장됩니다.

## Total 3 · 자동화 HTML 리포트

`sales_raw.csv`를 정제·집계하여 Jinja2 HTML 리포트를 생성합니다. 직접 실행,
경량 루프, `schedule`, OS cron을 지원하며 Plotly 차트, SMTP 이메일 알림,
지수 백오프 재시도가 포함되어 있습니다.

```powershell
python Total3\report.py
python Total3\run_scheduler.py --mode loop --interval 60
python Total3\run_scheduler.py --mode schedule --interval 60
```

세부 구조, SMTP 설정, cron 예시는 [Total3 README](Total3/README.md)를 참고하세요.

## Advanced

### Day 1 · 공개 API 통합 파이프라인

`Advanced/day1/광주_3반_신형섭_종합실습.py`는 날씨, 국가, IP 위치 API를
`httpx`와 `asyncio.gather()`로 동시에 호출합니다. Pydantic으로 응답을 검증하고
정규화된 결과를 CSV와 Parquet으로 저장하며 형식별 저장 성능을 비교합니다.

실제 공개 API를 사용하므로 실행 시 인터넷 연결과 각 API의 정상 응답이 필요합니다.

```powershell
python "Advanced\day1\광주_3반_신형섭_종합실습.py"
```

### Day 2 · 분석 심화

- `practice3_pandas_polars_duckdb.py`: 세 데이터 엔진의 IQR 필터링·집계·성능 비교
- `practice4_.sklearn.py`: EDA 차트, t-test, 카이제곱 검정, 회귀 Pipeline, Plotly 시각화

두 번째 파일은 첫 번째 파일의 `remove_outliers()`와 `named_aggregation()`을 import하여 재사용합니다.

```powershell
python Advanced\day2\practice3_pandas_polars_duckdb.py
python Advanced\day2\practice4_.sklearn.py
```

## 데이터

`data/0721/generate_data.py`는 `seed=42`를 사용하여 다음 합성 데이터를 생성합니다.

| 파일 | 사용처 | 특징 |
|---|---|---|
| `web_logs.csv` | 로그 스트리밍 | 대용량 웹 접근 로그 |
| `api_response.json` | Pydantic 검증 | 중첩 스키마와 의도적인 오류 |
| `sales_raw.csv` | Pandas 정제, Total 3 | 결측값과 이상치 포함 |
| `events_large.csv` | 엔진 성능 비교 | 대용량 이벤트 데이터 |
| `telco_churn.csv` | Total 2 | 이탈 예측용 데이터 |

데이터를 다시 생성하려면 다음 명령을 사용합니다.

```powershell
python data\0721\generate_data.py
```

## 설치

Python 3.11 환경을 기준으로 작성되었습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

현재 일부 코드와 테스트에서 사용하는 다음 도구는 `requirements.txt`에 별도로
고정되어 있지 않으므로 필요한 경우 추가로 설치합니다.

```powershell
python -m pip install pydantic httpx pytest
```

주요 라이브러리는 Pandas, Polars, DuckDB, PyArrow, Pydantic, HTTPX, Plotly,
Matplotlib, Seaborn, SciPy, scikit-learn, Jinja2와 schedule입니다.

## 테스트

```powershell
python -m pytest Total1\test_pipeline.py -v
python -m unittest practice4\test_ex04_pandas_cleaning.py -v
python -m unittest discover -s Total3 -p "test_*.py" -v
```

## 실행 전 확인사항

- 명령은 프로젝트 루트에서 실행하는 것을 기준으로 합니다.
- Practice 1과 2는 코드상 `data/0720`을 참조하지만 현재 제공 데이터는
  `data/0721`에 있습니다. 실행 전 데이터 위치 또는 코드 경로를 맞춰야 합니다.
- Advanced day2는 `data/lecture/sales_100k.csv`를 요구하며 현재 해당 파일은
  저장소에 포함되어 있지 않습니다.
- Advanced day1의 실제 API 수집은 네트워크 상태와 외부 서비스에 영향을 받습니다.
- Total 3 이메일 알림은 별도의 SMTP 환경변수 설정이 필요합니다.
- 생성 결과와 모델 파일은 용량이 클 수 있으므로 버전 관리 포함 여부를 확인하세요.
