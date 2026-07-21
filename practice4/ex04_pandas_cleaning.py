from dataclasses import dataclass

import pandas as pd


# pandas 3.0부터 Copy-on-Write는 항상 활성화되어 별도 설정이 필요 없다.
if int(pd.__version__.split(".", maxsplit=1)[0]) < 3:
    pd.options.mode.copy_on_write = True


@dataclass(frozen=True)
class CleaningRules:
    """원본 데이터에서 학습하여 새 데이터에도 재사용할 정제 규칙."""

    price_medians: dict[str, float]
    price_fallback: float
    outlier_bounds: dict[str, tuple[float, float]]
    region_fill_value: str = "Unknown"


def clean_price(df: pd.DataFrame) -> pd.DataFrame:
    """단가를 숫자로 변환하고, 유효하지 않은 음수 단가를 결측치로 바꾼다."""

    cleaned = df.copy()
    cleaned["unit_price"] = pd.to_numeric(
        cleaned["unit_price"], errors="coerce"
    ).mask(lambda price: price < 0)
    return cleaned


def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    """분석에 필요한 숫자·날짜·범주 타입을 정규화한다."""

    cleaned = clean_price(df)
    cleaned["quantity"] = pd.to_numeric(cleaned["quantity"], errors="coerce")
    cleaned["discount"] = pd.to_numeric(cleaned["discount"], errors="coerce")
    cleaned["order_date"] = pd.to_datetime(cleaned["order_date"], errors="coerce")
    return cleaned


def fill_missing(
    df: pd.DataFrame,
    price_medians: dict[str, float] | None = None,
    price_fallback: float | None = None,
    region_fill_value: str = "Unknown",
) -> pd.DataFrame:
    """단가는 category별 중앙값, 지역은 지정 문자열로 대치한다."""

    cleaned = df.copy()

    if price_medians is None:
        price_medians = (
            cleaned.groupby("category", observed=True)["unit_price"]
            .median()
            .to_dict()
        )
    if price_fallback is None:
        price_fallback = float(cleaned["unit_price"].median())

    category_medians = (
        cleaned["category"].astype("string").map(price_medians).astype("float64")
    )
    cleaned["unit_price"] = (
        cleaned["unit_price"].fillna(category_medians).fillna(price_fallback)
    )
    cleaned["region"] = cleaned["region"].fillna(region_fill_value)
    return cleaned


def calculate_iqr_bounds(series: pd.Series, k: float = 1.5) -> tuple[float, float]:
    """IQR 방식으로 원저라이징의 하한과 상한을 계산한다."""

    q1, q3 = series.quantile([0.25, 0.75])
    iqr = q3 - q1
    return float(q1 - k * iqr), float(q3 + k * iqr)


def remove_outliers(
    df: pd.DataFrame,
    bounds: dict[str, tuple[float, float]] | None = None,
    columns: tuple[str, ...] = ("unit_price", "quantity"),
) -> pd.DataFrame:
    """이상치를 삭제하지 않고 IQR 경계값으로 원저라이징한다."""

    cleaned = df.copy()
    if bounds is None:
        bounds = {column: calculate_iqr_bounds(cleaned[column]) for column in columns}

    for column in columns:
        low, high = bounds[column]
        cleaned[column] = cleaned[column].clip(lower=low, upper=high)
    return cleaned


def fit_cleaning_rules(df: pd.DataFrame) -> CleaningRules:
    """원본 데이터에서 대치값과 이상치 경계를 학습한다."""

    typed = normalize_types(df)
    price_medians = (
        typed.groupby("category", observed=True)["unit_price"].median().to_dict()
    )
    price_fallback = float(typed["unit_price"].median())
    filled = fill_missing(typed, price_medians, price_fallback)
    bounds = {
        column: calculate_iqr_bounds(filled[column])
        for column in ("unit_price", "quantity")
    }
    return CleaningRules(price_medians, price_fallback, bounds)


def apply_cleaning_rules(df: pd.DataFrame, rules: CleaningRules) -> pd.DataFrame:
    """학습된 동일 규칙을 기존 또는 새 판매 데이터에 적용한다."""

    cleaned = normalize_types(df)
    cleaned = fill_missing(
        cleaned,
        rules.price_medians,
        rules.price_fallback,
        rules.region_fill_value,
    )
    cleaned = remove_outliers(cleaned, rules.outlier_bounds)

    cleaned["category"] = cleaned["category"].astype("category")
    cleaned["region"] = cleaned["region"].astype("category")
    cleaned["sales"] = (
        cleaned["unit_price"]
        * cleaned["quantity"]
        * (1 - cleaned["discount"])
    )
    cleaned["flag"] = 0
    cleaned.loc[cleaned["unit_price"] > 100_000, "flag"] = 1
    return cleaned


def make_reports(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """그룹 요약표와 category-region 교차표를 만든다."""

    summary = (
        df.groupby("category", observed=True)
        .agg(
            건수=("order_id", "count"),
            평균단가=("unit_price", "mean"),
            중앙값=("unit_price", "median"),
            총매출=("sales", "sum"),
        )
        .round(1)
    )
    pivot = df.pivot_table(
        index="category",
        columns="region",
        values="sales",
        aggfunc="sum",
        fill_value=0,
        observed=True,
    ).round(1)
    return summary, pivot


def main() -> None:
    raw = pd.read_csv("data/0721/sales_raw.csv")
    before_missing = int(raw.isna().sum().sum())
    quantity_max_before = pd.to_numeric(raw["quantity"], errors="coerce").max()

    rules = fit_cleaning_rules(raw)
    df = apply_cleaning_rules(raw, rules)
    summary, pivot = make_reports(df)

    # key 기준의 의미 있는 many-to-one 병합 예시
    category_info = pd.DataFrame(
        {
            "category": ["Beauty", "Electronics", "Fashion", "Food", "Home"],
            "category_name": ["뷰티", "전자제품", "패션", "식품", "생활용품"],
        }
    )
    merged_df = df.merge(
        category_info,
        on="category",
        how="left",
        validate="many_to_one",
    )

    print("결측치:", before_missing, "->", int(df.isna().sum().sum()))
    print("수량 max:", quantity_max_before, "->", df["quantity"].max())
    print("병합 행 수:", len(df), "->", len(merged_df))
    print("\n정제 후 타입\n", df.dtypes)
    print("\n그룹 요약\n", summary)
    print("\n교차표\n", pivot)


if __name__ == "__main__":
    main()
