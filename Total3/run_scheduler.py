import argparse
import time

from report import run_once


def run_loop(interval: int) -> None:
    """외부 의존성 없는 경량 루프로 리포트를 반복 생성합니다."""
    print(f"경량 루프 시작: {interval}초 간격 (종료: Ctrl+C)")
    while True:
        run_once()
        time.sleep(interval)


def run_with_schedule(interval: int) -> None:
    """schedule 라이브러리로 리포트 작업을 주기적으로 실행합니다."""
    import schedule

    print(f"schedule 실행 시작: {interval}초 간격 (종료: Ctrl+C)")
    run_once()
    schedule.every(interval).seconds.do(run_once)
    while True:
        schedule.run_pending()
        time.sleep(1)


def positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("실행 간격은 1 이상의 정수여야 합니다.")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="매출 HTML 리포트 실행 스케줄러")
    parser.add_argument(
        "--mode",
        choices=("once", "loop", "schedule"),
        default="loop",
        help="once: 1회 실행, loop: 경량 루프, schedule: schedule 라이브러리",
    )
    parser.add_argument(
        "--interval",
        type=positive_integer,
        default=60,
        help="loop/schedule 모드의 실행 간격(초, 기본값: 60)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.mode == "once":
            run_once()
        elif args.mode == "schedule":
            run_with_schedule(args.interval)
        else:
            run_loop(args.interval)
    except KeyboardInterrupt:
        print("\n스케줄러를 종료합니다.")


if __name__ == "__main__":
    main()
