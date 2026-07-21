from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any


# 기본은 네트워크가 없어도 재현 가능한 모의 실행입니다.
USE_REAL_HTTP = False

TOTAL_REQUESTS = 60
MAX_CONCURRENCY = 10
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT = 2.0
BACKOFF_SECONDS = 0.05
MOCK_DELAY_SECONDS = 0.20
REAL_API_URL = "https://jsonplaceholder.typicode.com/todos/{item_id}"
DEAD_LETTER_PATH = Path(__file__).with_name("dead_letter.json")


async def mock_request(item_id: int, attempt: int) -> dict[str, Any]:
    """지연, 일시 오류, 영구 오류를 재현하는 모의 요청입니다."""
    await asyncio.sleep(MOCK_DELAY_SECONDS)

    # 첫 시도만 실패하므로 재시도 후 복구됩니다.
    if item_id % 17 == 0 and attempt == 1:
        raise ConnectionError("모의 일시 오류")

    # 모든 시도에서 실패하므로 최종적으로 dead-letter가 됩니다.
    if item_id in {23, 47}:
        raise TimeoutError("모의 영구 오류")

    return {"id": item_id, "ok": True, "source": "mock"}


async def request_once(
    item_id: int,
    attempt: int,
    client: Any | None,
) -> dict[str, Any]:
    if client is None:
        return await mock_request(item_id, attempt)

    response = await client.get(REAL_API_URL.format(item_id=item_id + 1))
    response.raise_for_status()
    return {
        "id": item_id,
        "ok": True,
        "source": "http",
        "data": response.json(),
    }


async def fetch(
    item_id: int,
    semaphore: asyncio.Semaphore,
    client: Any | None,
) -> dict[str, Any]:
    """동시성 제한 안에서 요청하고 지수 백오프로 재시도합니다."""
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with semaphore:
                result = await asyncio.wait_for(
                    request_once(item_id, attempt, client),
                    timeout=REQUEST_TIMEOUT,
                )

            result["attempts"] = attempt
            return result

        except Exception as error:
            last_error = error

            if attempt < MAX_ATTEMPTS:
                delay = BACKOFF_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

    raise RuntimeError(
        f"item_id={item_id}, {MAX_ATTEMPTS}회 시도 실패: {last_error}"
    ) from last_error


async def collect(
    client: Any | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    item_ids = list(range(TOTAL_REQUESTS))
    tasks = [fetch(item_id, semaphore, client) for item_id in item_ids]

    # 한 요청의 최종 실패가 다른 요청까지 취소하지 않게 격리합니다.
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    successes: list[dict[str, Any]] = []
    dead_letters: list[dict[str, Any]] = []

    for item_id, result in zip(item_ids, gathered):
        if isinstance(result, BaseException):
            dead_letters.append({"id": item_id, "error": str(result)})
        else:
            successes.append(result)

    return successes, dead_letters


async def run_collection() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not USE_REAL_HTTP:
        return await collect()

    try:
        import httpx
    except ImportError as error:
        raise RuntimeError(
            "실 HTTP 실행에는 httpx가 필요합니다. "
            "`python3 -m pip install -r requirements.txt`로 설치하세요."
        ) from error

    timeout = httpx.Timeout(REQUEST_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await collect(client)


def save_dead_letters(dead_letters: list[dict[str, Any]]) -> None:
    """최종 실패 요청을 스크립트와 같은 폴더의 JSON 파일에 저장합니다."""
    with DEAD_LETTER_PATH.open("w", encoding="utf-8") as file:
        json.dump(dead_letters, file, ensure_ascii=False, indent=2)


async def main() -> None:
    started_at = time.perf_counter()
    successes, dead_letters = await run_collection()
    await asyncio.to_thread(save_dead_letters, dead_letters)
    elapsed = time.perf_counter() - started_at

    print("=" * 40)
    print(f"전체 요청 : {TOTAL_REQUESTS}건")
    print(f"성공      : {len(successes)}건")
    print(f"실패 격리 : {len(dead_letters)}건")
    print(f"실패 저장 : {DEAD_LETTER_PATH}")
    print(f"처리 시간 : {elapsed:.2f}초")

    if dead_letters:
        print("-- dead-letter --")
        for failure in dead_letters:
            print(f"  ID {failure['id']:>2}: {failure['error']}")


if __name__ == "__main__":
    asyncio.run(main())
