import pandas as pd
import time
import polars as pl
import duckdb

CSV_PATH = "data/0721/events_large.csv"

def main():

    res_pandas, t_pandas = benchmark(pandas_query)
    res_polars, t_polars = benchmark(polars_query)
    res_duckdb, t_duckdb = benchmark(duckdb_query)

    a = res_pandas.sort_values("event_type").reset_index(drop=True)
    b = res_polars.to_pandas().sort_values("event_type").reset_index(drop=True)
    c = res_duckdb.sort_values("event_type").reset_index(drop=True)

    pd.testing.assert_frame_equal(a, b, check_dtype=False, atol=1e-6)
    pd.testing.assert_frame_equal(a, c, check_dtype=False, atol=1e-6)
    print('세 가지 방법 모두 동일한 결과를 반환합니다.')

    results = [
        ("Pandas", t_pandas),
        ("Polars", t_polars),
        ("DuckDB", t_duckdb),
    ]
    base = t_pandas
    print(f"{'엔진':<10}{'시간(ms)':>10}{'배속':>10}")
    for name, t in sorted(results, key=lambda x: x[1]):
        print(f'{name:<10}{t:>10.0f}{base / t:>9.1f}x')



def pandas_query():
    start = time.perf_counter()

    df = pd.read_csv(CSV_PATH)
    result = (
        df[df["event_type"].isin(["purchase", "refund"])]
        .groupby("event_type")
        .agg(
            cnt=("event_id", "count"),
            avg=("amount", "mean"),
        )
        .sort_values("cnt", ascending=False)
        .reset_index()
    )

    elapsed = (time.perf_counter() - start) * 1000
    return result, elapsed


def polars_query():
    start = time.perf_counter()

    result = (
        pl.scan_csv(CSV_PATH)
        .filter(pl.col("event_type").is_in(["purchase", "refund"]))
        .group_by("event_type")
        .agg(
            pl.col("event_id").count().alias("cnt"),
            pl.col("amount").mean().alias("avg"),
        )
        .sort("cnt", descending=True)
        .collect()
    )

    elapsed = (time.perf_counter() - start) * 1000
    return result, elapsed


def duckdb_query():
    start = time.perf_counter()
    res_duckdb = duckdb.sql("""
        SELECT event_type, COUNT(event_id) AS cnt, AVG(amount) AS avg
        FROM '""" + CSV_PATH + """'
        WHERE event_type IN ('purchase', 'refund')
        GROUP BY event_type
        ORDER BY cnt DESC
    """).df()
    t_duckdb = (time.perf_counter() - start) * 1000
    return res_duckdb, t_duckdb


def benchmark(query, repeat=3):
    query()  # 워밍업

    times = []
    result = None

    for _ in range(repeat):
        result, elapsed = query()
        times.append(elapsed)

    return result, sum(times) / len(times)


if __name__ == "__main__":
    main()