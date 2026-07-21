import asyncio
import pandas as pd
from pathlib import Path
from typing import Any
from collections.abc import Awaitable, Callable
from pydantic import ValidationError


# 1. Product 모델
from models import Product


# 2. Extract
Fetcher = Callable[[int], Awaitable[dict]]


async def fetch_one(
    item_id: int,
    fetcher: Fetcher,
    semaphore: asyncio.Semaphore,
    max_attempts: int = 3,
) -> dict:
    for attempt in range(max_attempts):
        try:
            async with semaphore:
                return await fetcher(item_id)
        except Exception:
            if attempt == max_attempts - 1:
                raise

            await asyncio.sleep(0.05 * (2**attempt))

    raise RuntimeError("도달할 수 없는 코드")


async def extract(
    item_ids: list[int],
    fetcher: Fetcher,
    concurrency: int = 5,
) -> tuple[list[dict], list[dict]]:
    semaphore = asyncio.Semaphore(concurrency)

    tasks = [fetch_one(item_id, fetcher, semaphore) for item_id in item_ids]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    collected = []
    failed = []

    for item_id, result in zip(item_ids, results):
        if isinstance(result, BaseException):
            failed.append(
                {
                    "id": item_id,
                    "error": str(result),
                }
            )
        else:
            collected.append(result)

    return collected, failed


# 3. Transform
def transform(raw: list[dict[str, Any]]) -> tuple[list, list]:
    valid, invalid = [], []
    for row in raw:
        try:
            valid.append(Product.model_validate(row))
        except ValidationError as error:
            invalid.append({"data": row, "errors": error.errors()})
    return valid, invalid


# 4. Load
def load(
    products: list[Product],
    output_dir: Path,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    dataframe = pd.DataFrame([product.model_dump() for product in products])

    csv_path = output_dir / "products.csv"
    parquet_path = output_dir / "products.parquet"

    dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")
    dataframe.to_parquet(parquet_path, index=False)

    restored = pd.read_parquet(parquet_path)

    if len(restored) != len(dataframe):
        raise ValueError("Parquet 라운드트립 건수가 일치하지 않습니다.")

    return {
        "csv": str(csv_path),
        "parquet": str(parquet_path),
        "saved_count": len(dataframe),
        "roundtrip_count": len(restored),
    }


# 5. Orchestrate
async def mock_fetch(item_id: int) -> dict:
    await asyncio.sleep(0.01)

    return {
        "id": item_id,
        "name": f"상품-{item_id}",
        "category": " FOOD " if item_id % 2 else "BOOK",
        "price": -100 if item_id == 3 else item_id * 1000,
    }


async def run() -> dict:
    raw, extract_failed = await extract(
        item_ids=[1, 2, 3, 4, 5],
        fetcher=mock_fetch,
        concurrency=3,
    )

    valid, invalid = transform(raw)

    load_result = load(
        valid,
        Path(__file__).parent / "output",
    )

    return {
        "collected": len(raw),
        "extract_failed": len(extract_failed),
        "valid": len(valid),
        "invalid": len(invalid),
        **load_result,
    }


if __name__ == "__main__":
    print(asyncio.run(run()))
