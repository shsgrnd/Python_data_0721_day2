"""
------------------------------
파일명 : 광주_3반_신형섭.py
작성일 : 2026-07-21
작성자 : 광주 3반 신형섭
실습 목적 : 이상치가 제거된 판매 데이터를 4가지 그래프로 시각화
변경 내역 : 실습 3 함수 재사용, 통계 검정과 sklearn Pipeline 추가
------------------------------
"""

import os
from pathlib import Path

# macOS에서 joblib이 물리 CPU 수를 조회할 때 발생하는 경고를 방지한다.
logical_cpu_count = os.cpu_count() or 2
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(max(logical_cpu_count - 1, 1)))

import joblib
import matplotlib

# macOS GUI 백엔드의 GIL 충돌을 피하고 차트를 파일로 저장한다.
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import seaborn as sns
from scipy.stats import chi2_contingency, ttest_ind
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

from practice3_pandas_polars_duckdb import named_aggregation, remove_outliers

# macOS의 한글 지원 글꼴을 사용하고 음수 기호 깨짐을 방지한다.
plt.rcParams["font.family"] = "Apple SD Gothic Neo"
plt.rcParams["axes.unicode_minus"] = False


def main() -> None:
    project_dir = Path(__file__).resolve().parents[2]
    csv_path = project_dir / "data" / "lecture" / "sales_100k.csv"

    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    # 실습 3에서 import한 함수로 amount 이상치를 제거한다.
    cleaned_df = remove_outliers(df, "amount", k=1.5)

    
    print(f"이상치 제거 전: {len(df):,}행")
    print(f"이상치 제거 후: {len(cleaned_df):,}행")

    # 1) EDA 시각화 4종
    output_path = project_dir / "Advanced" / "day2" / "practice4_eda.png"
    draw_eda_charts(cleaned_df, output_path)


    # 2) 통계 검정 - t-test와 카이제곱 검정
    compare_seoul_busan_sales(cleaned_df)
    test_region_category_independence(cleaned_df)


    # 3) sklearn Pipeline 구성 및 학습·평가·저장
    model_path = project_dir / "Advanced" / "day2" / "sales_amount_pipeline.joblib"
    train_evaluate_save_pipeline(cleaned_df, model_path)


    # 4) Plotly로 지역·카테고리별 총매출 막대 차트를 독립형 HTML로 저장
    html_path = project_dir / "Advanced" / "day2" / "region_category_sales.html"
    save_interactive_sales_chart(cleaned_df, html_path)


def draw_eda_charts(df: pd.DataFrame, output_path: Path) -> None:
    """히스토그램, 박스플롯, 월별 라인 차트, 상관 히트맵을 그린다."""

    chart_df = df.copy()
    chart_df["order_date"] = pd.to_datetime(
        chart_df["order_date"],
        errors="coerce",
    )

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    sns.histplot(
        data=chart_df,
        x="amount",
        bins=30,
        kde=True,
        ax=axes[0, 0],
    )
    axes[0, 0].set_title("매출액 분포")
    axes[0, 0].set_xlabel("매출액")
    axes[0, 0].set_ylabel("빈도")

    sns.boxplot(
        data=chart_df,
        x="category",
        y="amount",
        ax=axes[0, 1],
    )
    axes[0, 1].set_title("카테고리별 매출액 분포")
    axes[0, 1].set_xlabel("카테고리")
    axes[0, 1].set_ylabel("매출액")
    axes[0, 1].tick_params(axis="x", rotation=30)

    monthly_sales = (
        chart_df.dropna(subset=["order_date"])
        .set_index("order_date")
        .resample("MS")["amount"]
        .sum()
    )
    sns.lineplot(
        x=monthly_sales.index,
        y=monthly_sales.values,
        marker="o",
        ax=axes[1, 0],
    )
    axes[1, 0].set_title("월별 총매출 추이")
    axes[1, 0].set_xlabel("월")
    axes[1, 0].set_ylabel("총매출")
    axes[1, 0].tick_params(axis="x", rotation=45)

    numeric_columns = ["quantity", "unit_price", "customer_age", "amount"]
    correlation = chart_df[numeric_columns].corr()
    sns.heatmap(
        correlation,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        vmin=-1,
        vmax=1,
        ax=axes[1, 1],
    )
    axes[1, 1].set_title("숫자형 변수 상관관계")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nEDA 차트 저장 완료: {output_path}")


def compare_seoul_busan_sales(
    df: pd.DataFrame,
    alpha: float = 0.05,
) -> None:
    """서울과 부산의 평균 매출액 차이를 Welch t-test로 검정한다."""

    seoul_sales = df.loc[df["region"].eq("서울"), "amount"].dropna()
    busan_sales = df.loc[df["region"].eq("부산"), "amount"].dropna()

    if len(seoul_sales) < 2 or len(busan_sales) < 2:
        raise ValueError("t-test를 위한 서울 또는 부산 데이터가 부족합니다.")

    statistic, p_value = ttest_ind(
        seoul_sales,
        busan_sales,
        equal_var=False,
    )

    print("\n[서울 vs 부산 평균 매출 t-test]")
    print("귀무가설(H0): 서울과 부산의 평균 매출액은 같다.")
    print(f"서울: {len(seoul_sales):,}건, 평균 {seoul_sales.mean():,.2f}원")
    print(f"부산: {len(busan_sales):,}건, 평균 {busan_sales.mean():,.2f}원")
    print(f"t 통계량: {statistic:.4f}")
    print(f"p-value: {p_value:.6g}")

    if p_value < alpha:
        print(f"해석: p < {alpha}이므로 평균 매출액에 유의한 차이가 있습니다.")
    else:
        print(f"해석: p >= {alpha}이므로 유의한 차이가 있다고 보기 어렵습니다.")


def test_region_category_independence(
    df: pd.DataFrame,
    alpha: float = 0.05,
) -> None:
    """region과 category가 서로 독립인지 카이제곱 검정을 수행한다."""

    contingency_table = pd.crosstab(df["region"], df["category"])
    if contingency_table.shape[0] < 2 or contingency_table.shape[1] < 2:
        raise ValueError("카이제곱 검정을 위한 분류 데이터가 부족합니다.")

    statistic, p_value, degrees_of_freedom, _ = chi2_contingency(
        contingency_table,
    )

    print("\n[지역과 카테고리 카이제곱 독립성 검정]")
    print("귀무가설(H0): 지역과 카테고리는 서로 독립이다.")
    print("\n[관찰 도수표]")
    print(contingency_table)
    print(f"\n카이제곱 통계량: {statistic:.4f}")
    print(f"자유도: {degrees_of_freedom}")
    print(f"p-value: {p_value:.6g}")

    if p_value < alpha:
        print(f"해석: p < {alpha}이므로 지역과 카테고리는 서로 관련이 있습니다.")
    else:
        print(f"해석: p >= {alpha}이므로 두 변수가 관련 있다고 보기 어렵습니다.")


def train_evaluate_save_pipeline(
    df: pd.DataFrame,
    model_path: Path,
) -> None:
    """매출액 예측 Pipeline을 학습·평가하고 joblib 파일로 저장한다."""

    numeric_features = ["quantity", "unit_price", "customer_age"]
    categorical_features = [
        "region",
        "category",
        "payment_method",
        "customer_gender",
    ]
    feature_columns = numeric_features + categorical_features

    x = df[feature_columns]
    y = df["amount"]
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
    )

    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "encoder",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                ),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric_transformer, numeric_features),
            ("categorical", categorical_transformer, categorical_features),
        ]
    )
    model_pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "regressor",
                HistGradientBoostingRegressor(
                    max_iter=150,
                    learning_rate=0.1,
                    random_state=42,
                ),
            ),
        ]
    )

    model_pipeline.fit(x_train, y_train)
    predictions = model_pipeline.predict(x_test)
    r2_score = model_pipeline.score(x_test, y_test)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    mae = mean_absolute_error(y_test, predictions)

    print("\n[sklearn Pipeline 학습 및 평가]")
    print(f"학습 데이터: {len(x_train):,}건")
    print(f"평가 데이터: {len(x_test):,}건")
    print(f"R² score: {r2_score:.4f}")
    print(f"RMSE: {rmse:,.2f}원")
    print(f"MAE: {mae:,.2f}원")

    joblib.dump(model_pipeline, model_path)
    loaded_pipeline = joblib.load(model_path)
    loaded_predictions = loaded_pipeline.predict(x_test.iloc[:10])
    predictions_match = np.allclose(
        predictions[:10],
        loaded_predictions,
    )

    print(f"모델 저장 완료: {model_path}")
    print(f"재로딩 예측 일치 여부: {predictions_match}")


def save_interactive_sales_chart(
    df: pd.DataFrame,
    output_path: Path,
) -> None:
    """지역·카테고리별 총매출 막대 차트를 독립형 HTML로 저장한다."""

    chart_df = df.copy()
    chart_df[["region", "category"]] = chart_df[
        ["region", "category"]
    ].fillna("미상")

    # 실습 3의 region·category groupby 함수를 재사용한다.
    grouped_sales = named_aggregation(chart_df)

    figure = px.bar(
        grouped_sales,
        x="region",
        y="total_sales",
        color="category",
        barmode="group",
        title="지역·카테고리별 총매출",
        labels={
            "region": "지역",
            "category": "카테고리",
            "total_sales": "총매출",
            "average_sales": "평균매출",
            "sales_count": "판매 건수",
        },
        hover_data={
            "total_sales": ":,.0f",
            "average_sales": ":,.0f",
            "sales_count": ":,",
        },
    )
    figure.update_layout(
        template="plotly_white",
        xaxis_title="지역",
        yaxis_title="총매출(원)",
        legend_title_text="카테고리",
    )
    figure.write_html(
        output_path,
        include_plotlyjs=True,
        full_html=True,
    )
    print(f"\nPlotly 차트 저장 완료: {output_path}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as error:
        print(f"CSV 파일을 찾을 수 없습니다: {error}")
    except KeyError as error:
        print(f"필요한 열이 없습니다: {error}")
    except (ValueError, TypeError) as error:
        print(f"데이터 처리 중 오류가 발생했습니다: {error}")
