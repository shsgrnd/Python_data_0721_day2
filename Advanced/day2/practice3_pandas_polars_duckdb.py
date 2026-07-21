"""
------------------------------
파일명 : 광주_3반_신형섭.py
작성일 : 2026-07-21
작성자 : 광주 3반 신형섭
실습 목적 : Pandas, Polars Lazy API, DuckDB SQL의 집계 결과와 성능 비교
변경 내역 : EDA, IQR 이상치 제거, named aggregation, 반복 성능 측정 추가
------------------------------
"""


import duckdb
import pandas as pd
import polars as pl
from timeit import repeat as timeit_repeat


def main():
    data_path = "data/lecture/sales_100k.csv"
    df = pd.read_csv(data_path, encoding="utf-8-sig")

    print("\n[데이터 기본 정보]")
    df.info()

    print("\n[열별 결측치]")
    print(df.isnull().sum())

    cleaned_df = remove_outliers(df, "amount", k=1.5)

    print("\n[IQR 이상치 처리]")
    print(f"처리 전 행 개수: {len(df):,}")
    print(f"처리 후 행 개수: {len(cleaned_df):,}")

    res_pandas, pandas_time = benchmark_query(pandas_pipeline, data_path)
    res_polars, polars_time = benchmark_query(polars_pipeline, data_path)
    res_duckdb, duckdb_time = benchmark_query(duckdb_pipeline, data_path)

    print("\n[Pandas 결과]")
    print(res_pandas.head())

    print("\n[Polars 결과]")
    print(res_polars.head())

    print("\n[DuckDB 결과]")
    print(res_duckdb.head())

    print("\n[실행시간 비교: repeat=3, number=1]")
    print(f"Pandas  : {pandas_time:.3f} ms")
    print(f"Polars  : {polars_time:.3f} ms")
    print(f"DuckDB  : {duckdb_time:.3f} ms")

def calculate_iqr_bounds(series: pd.Series, k: float = 1.5) -> tuple[float, float]:
    """IQR 방식으로 원저라이징의 하한과 상한을 계산한다."""

    q1, q3 = series.quantile([0.25, 0.75])
    iqr = q3 - q1
    return float(q1 - k * iqr), float(q3 + k * iqr)


def remove_outliers(df: pd.DataFrame, column: str, k: float = 1.5) -> pd.DataFrame:
    """IQR 방식으로 이상치를 제거한다."""

    lower_bound, upper_bound = calculate_iqr_bounds(df[column], k)
    normal_range = df[column].between(
        lower_bound,
        upper_bound,
        inclusive="both",
    )
    return df.loc[normal_range].copy()


def named_aggregation(df: pd.DataFrame) -> pd.DataFrame:
    """region·category별 총매출, 평균매출, 건수를 계산한다."""

    result = (
        df.groupby(
            ["region", "category"],
            as_index=False,
            dropna=False,
        )
        .agg(
            total_sales=("amount", "sum"),
            average_sales=("amount", "mean"),
            sales_count=("amount", "count"),
        )
        .sort_values("total_sales", ascending=False)
    )

    return result


def pandas_pipeline(csv_path: str) -> pd.DataFrame:
    """Pandas로 CSV 로딩부터 IQR 필터링과 집계까지 수행한다."""

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    cleaned_df = remove_outliers(df, "amount", k=1.5)
    return named_aggregation(cleaned_df)


def polars_pipeline(csv_path: str) -> pl.DataFrame:
    """Polars Lazy API로 CSV 로딩부터 IQR 필터링과 집계까지 수행한다."""

    sales = pl.scan_csv(csv_path)
    bounds = sales.select(
        pl.col("amount").quantile(0.25).alias("q1"),
        pl.col("amount").quantile(0.75).alias("q3"),
    )

    result = (
        sales.join(bounds, how="cross")
        .with_columns(
            (pl.col("q3") - pl.col("q1")).alias("iqr"),
        )
        .filter(
            pl.col("amount").is_between(
                pl.col("q1") - 1.5 * pl.col("iqr"),
                pl.col("q3") + 1.5 * pl.col("iqr"),
                closed="both",
            )
        )
        .group_by(["region", "category"])
        .agg(
            pl.col("amount").sum().alias("total_sales"),
            pl.col("amount").mean().alias("average_sales"),
            pl.col("amount").count().alias("sales_count"),
        )
        .sort("total_sales", descending=True)
        .collect()
    )

    return result


def duckdb_pipeline(csv_path: str) -> pd.DataFrame:
    """DuckDB SQL로 IQR 필터링과 동일 집계를 수행한다."""

    query = """
        WITH sales AS (
            SELECT *
            FROM read_csv_auto(?)
        ),
        bounds AS (
            SELECT
                QUANTILE_CONT(amount, 0.25) AS q1,
                QUANTILE_CONT(amount, 0.75) AS q3
            FROM sales
        ),
        cleaned_sales AS (
            SELECT sales.*
            FROM sales
            CROSS JOIN bounds
            WHERE amount BETWEEN
                q1 - 1.5 * (q3 - q1)
                AND q3 + 1.5 * (q3 - q1)
        )
        SELECT
            region,
            category,
            SUM(amount) AS total_sales,
            AVG(amount) AS average_sales,
            COUNT(amount) AS sales_count
        FROM cleaned_sales
        GROUP BY region, category
        ORDER BY total_sales DESC
    """

    return duckdb.execute(query, [csv_path]).fetchdf()


def benchmark_query(query_func, *args, repeat=5, number=3):
    """동일한 repeat와 number로 측정하고 1회 평균 ms를 반환한다."""

    query_func(*args)  # 워밍업: 최초 실행의 초기화 비용 제외
    times = timeit_repeat(
        lambda: query_func(*args),
        repeat=repeat,
        number=number,
    )
    average_ms = sum(times) / (repeat * number) * 1_000
    result = query_func(*args)
    return result, average_ms

if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as error:
        print(f"CSV 파일을 찾을 수 없습니다: {error}")
    except UnicodeDecodeError as error:
        print(f"CSV 인코딩 또는 파일 손상 오류: {error}")
    except (duckdb.Error, pl.exceptions.PolarsError) as error:
        print(f"데이터 처리 중 오류가 발생했습니다: {error}")
