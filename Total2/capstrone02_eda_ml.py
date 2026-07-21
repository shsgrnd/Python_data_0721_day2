from pathlib import Path

import joblib
import pandas as pd
import plotly.express as px
import polars as pl
from scipy.stats import chi2_contingency, ttest_ind
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


# 스크립트를 어느 위치에서 실행해도 동일한 파일을 찾도록 기준 경로를 고정합니다.
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR.parent / "data" / "0721" / "telco_churn.csv"
OUTPUT_DIR = BASE_DIR / "output"

TARGET_COLUMN = "churn"
CHARGE_COLUMN = "monthly_charges"
CONTRACT_COLUMN = "contract"


def load_data(file_path: Path) -> pl.DataFrame:
    """CSV 파일을 Polars 데이터프레임으로 불러옵니다."""
    if not file_path.exists():
        raise FileNotFoundError(
            f"데이터 파일을 찾을 수 없습니다: {file_path}\n"
            "telco_churn.csv 파일이 data/0721 폴더에 있는지 확인해 주세요."
        )

    # 공백이나 일반적인 결측값 표기를 null로 읽습니다.
    return pl.read_csv(
        file_path,
        null_values=["", " ", "NA", "N/A", "null"],
        infer_schema_length=None,
    )


def validate_columns(df: pl.DataFrame) -> None:
    """분석에 필요한 열이 모두 있는지 확인합니다."""
    required_columns = {TARGET_COLUMN, CHARGE_COLUMN, CONTRACT_COLUMN}
    missing_columns = required_columns.difference(df.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(f"필수 열이 없습니다: {missing_text}")


def prepare_analysis_data(df: pl.DataFrame) -> pl.DataFrame:
    """통계 분석에 사용할 열의 형식과 결측값을 정리합니다."""
    return df.with_columns(
        pl.col(TARGET_COLUMN).cast(pl.String).str.strip_chars(),
        pl.col(CONTRACT_COLUMN).cast(pl.String).str.strip_chars(),
        pl.col(CHARGE_COLUMN).cast(pl.Float64, strict=False),
    )


def create_visualization(df: pl.DataFrame, output_path: Path) -> None:
    """이탈 여부별 월 요금 분포를 Plotly HTML 파일로 저장합니다."""
    chart_data = df.select(TARGET_COLUMN, CHARGE_COLUMN).drop_nulls().to_pandas()
    figure = px.box(
        chart_data,
        x=TARGET_COLUMN,
        y=CHARGE_COLUMN,
        color=TARGET_COLUMN,
        title="이탈 여부별 월 요금 분포",
        labels={TARGET_COLUMN: "이탈 여부", CHARGE_COLUMN: "월 요금"},
    )
    figure.write_html(output_path, include_plotlyjs="cdn")


def run_t_test(df: pl.DataFrame) -> tuple[float, float]:
    """이탈 집단과 비이탈 집단의 월 요금 평균 차이를 검정합니다."""
    normalized_target = pl.col(TARGET_COLUMN).str.to_lowercase()
    churned = (
        df.filter(normalized_target.is_in(["yes", "1", "true"]))
        .get_column(CHARGE_COLUMN)
        .drop_nulls()
        .to_numpy()
    )
    retained = (
        df.filter(normalized_target.is_in(["no", "0", "false"]))
        .get_column(CHARGE_COLUMN)
        .drop_nulls()
        .to_numpy()
    )

    if len(churned) < 2 or len(retained) < 2:
        raise ValueError("t-검정에는 이탈/비이탈 집단별로 2개 이상의 월 요금 값이 필요합니다.")

    # 두 집단의 분산이 같다고 가정하지 않는 Welch의 t-검정을 사용합니다.
    statistic, p_value = ttest_ind(churned, retained, equal_var=False)
    return float(statistic), float(p_value)


def run_chi_square_test(df: pl.DataFrame) -> tuple[float, float]:
    """계약 유형과 고객 이탈 여부가 서로 연관되는지 검정합니다."""
    chi_square_data = (
        df.select(CONTRACT_COLUMN, TARGET_COLUMN).drop_nulls().to_pandas()
    )
    contingency_table = pd.crosstab(
        chi_square_data[CONTRACT_COLUMN],
        chi_square_data[TARGET_COLUMN],
    )

    if contingency_table.shape[0] < 2 or contingency_table.shape[1] < 2:
        raise ValueError("카이제곱 검정에는 각 변수에 2개 이상의 범주가 필요합니다.")

    statistic, p_value, _, _ = chi2_contingency(contingency_table)
    return float(statistic), float(p_value)


def encode_target(target: pd.Series) -> pd.Series:
    """이탈 여부를 모델이 학습할 수 있는 0과 1로 변환합니다."""
    normalized = target.astype("string").str.strip().str.lower()
    encoded = normalized.map(
        {"yes": 1, "true": 1, "1": 1, "no": 0, "false": 0, "0": 0}
    )

    if encoded.isna().any():
        invalid_values = sorted(normalized[encoded.isna()].dropna().unique().tolist())
        raise ValueError(f"churn 열에 변환할 수 없는 값이 있습니다: {invalid_values}")

    return encoded.astype("int8")


def prepare_model_data(df: pl.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """모델 입력값과 정답을 분리하고 고객 식별 열을 제거합니다."""
    model_data = df.to_pandas()
    y = encode_target(model_data.pop(TARGET_COLUMN))

    # 고객 ID는 개인을 식별할 뿐 일반적인 이탈 패턴을 설명하지 않으므로 제외합니다.
    identifier_columns = [
        column for column in model_data.columns if column.lower() in {"customerid", "customer_id"}
    ]
    X = model_data.drop(columns=identifier_columns)
    return X, y


def build_model(X_train: pd.DataFrame, y_train: pd.Series) -> Pipeline:
    """전처리와 랜덤 포레스트를 연결한 파이프라인을 생성하고 학습합니다."""
    # 학습 데이터만 사용해 열 유형을 구분하므로 테스트 데이터 정보가 섞이지 않습니다.
    numeric_columns = X_train.select_dtypes(include="number").columns.tolist()
    categorical_columns = X_train.select_dtypes(exclude="number").columns.tolist()

    # 수치형 결측값은 중앙값으로 대체합니다.
    numeric_pipeline = Pipeline(
        steps=[("결측값_대체", SimpleImputer(strategy="median"))]
    )

    # 범주형 결측값을 최빈값으로 대체한 뒤 원핫 인코딩합니다.
    categorical_pipeline = Pipeline(
        steps=[
            ("결측값_대체", SimpleImputer(strategy="most_frequent")),
            (
                "원핫_인코딩",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("수치형", numeric_pipeline, numeric_columns),
            ("범주형", categorical_pipeline, categorical_columns),
        ]
    )

    pipeline = Pipeline(
        steps=[
            ("전처리", preprocessor),
            (
                "분류기",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=10,
                    min_samples_leaf=3,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    pipeline.fit(X_train, y_train)
    return pipeline


def evaluate_model(
    model: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> float:
    """학습된 모델을 테스트 데이터의 ROC-AUC로 평가합니다."""
    # ROC-AUC에는 0/1 예측값이 아니라 이탈 클래스(1)의 확률을 사용합니다.
    churn_probability = model.predict_proba(X_test)[:, 1]
    roc_auc = roc_auc_score(y_test, churn_probability)
    return float(roc_auc)


def main() -> None:
    """EDA, 통계 검정, 모델 학습과 결과 저장을 순서대로 실행합니다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_data = load_data(DATA_PATH)
    validate_columns(raw_data)
    analysis_data = prepare_analysis_data(raw_data)

    create_visualization(analysis_data, OUTPUT_DIR / "churn_charges.html")

    t_statistic, t_p_value = run_t_test(analysis_data)
    chi2_statistic, chi2_p_value = run_chi_square_test(analysis_data)

    X, y = prepare_model_data(analysis_data)

    # 정답 비율을 유지하며 학습용 80%, 테스트용 20%로 나눕니다.
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        stratify=y,
        random_state=42,
    )

    model = build_model(X_train, y_train)
    roc_auc = evaluate_model(model, X_test, y_test)
    joblib.dump(model, OUTPUT_DIR / "ml_pipeline.joblib")

    print(f"t-검정: 통계량={t_statistic:.4f}, p값={t_p_value:.4e}")
    print(f"카이제곱 검정: 통계량={chi2_statistic:.4f}, p값={chi2_p_value:.4e}")
    print(f"ROC-AUC: {roc_auc:.4f}")
    print(f"시각화 저장: {OUTPUT_DIR / 'churn_charges.html'}")
    print(f"모델 저장: {OUTPUT_DIR / 'ml_pipeline.joblib'}")


if __name__ == "__main__":
    main()
