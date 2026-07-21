import csv
import tracemalloc
from pathlib import Path
from collections import Counter, defaultdict
from functools import reduce


def main():
    tracemalloc.start()

    data_dir = Path(__file__).resolve().parent.parent / "data" / "0720"
    file_path = data_dir / "web_logs.csv"

    gen = read_logs(file_path)
    total, by_status, by_path, by_hour, by_ip = count_logs(gen)

    ratio = ratio_err(total, by_status)

    init = {"total": 0, "status": Counter()}
    result = reduce(fold, read_logs(file_path), init)
    print(f"fold 패턴 : {result['total']}")

    report(total, ratio, by_path, by_hour, by_ip)

    measure_readlines(file_path)
    measure_generator(file_path)

    tracemalloc.stop()


def read_logs(path):
    with open(path, encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            yield row


def count_logs(raw_data):
    total = 0
    by_status = Counter()
    by_path = Counter()
    by_hour = defaultdict(int)
    by_ip = Counter()

    for row in raw_data:
        total += 1
        by_status[row["status"]] += 1
        by_path[row["path"]] += 1
        by_ip[row["ip"]] += 1
        hour = row["timestamp"][11:13]
        by_hour[hour] += 1
    return total, by_status, by_path, by_hour, by_ip


def ratio_err(data_total, data_status):
    err_5xx = sum(
        count for status, count in data_status.items() if str(status).startswith("5")
    )
    ratio = err_5xx / data_total * 100
    return ratio


def fold(acc, row):
    acc["total"] += 1
    acc["status"][row["status"]] += 1
    return acc


def report(data_total, data_ratio, data_path, data_hour, data_ip):
    print("=" * 40)
    print(f"총 요청 수 : {data_total:,}")
    print(f"5xx 오류율 : {data_ratio:.1f}%")
    print("-- 인기 경로 TOP 5 --")
    for path, cnt in data_path.most_common(5):
        print(f"  {path:<20} {cnt:>7,}")

    print("-- 시간대별 요청 수 --")
    for hour in sorted(data_hour):
        print(f"  {hour}:00{'':<15} {data_hour[hour]:>7,}")

    print("-- 접속 상위 IP TOP 5 --")
    for ip, cnt in data_ip.most_common(5):
        print(f"  {ip:<20} {cnt:>7,}")


def measure_readlines(path):
    tracemalloc.start()

    with open(path, encoding="utf-8") as file:
        lines = file.readlines()

        for line in lines:
            pass

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"readlines 최대 메모리: {peak / 1024 / 1024:.2f} MB")


def measure_generator(path):
    tracemalloc.start()

    with open(path, encoding="utf-8") as file:
        for line in file:
            pass

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"제너레이터 최대 메모리: {peak / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
