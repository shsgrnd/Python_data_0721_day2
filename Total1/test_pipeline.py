from pathlib import Path
from pipeline import Product, transform, load


def test_카테고리_소문자화():
    product = Product(
        id=1,
        name="A",
        category=" FOOD ",
        price=100,
    )

    assert product.category == "food"


def test_음수_가격_거부():
    valid, invalid = transform(
        [
            {
                "id": 1,
                "name": "A",
                "category": "food",
                "price": -5,
            }
        ]
    )

    assert (len(valid), len(invalid)) == (0, 1)


def test_유효_무효_건수_일치():
    rows = [
        {"id": 1, "name": "정상1", "category": "food", "price": 100},
        {"id": 2, "name": "정상2", "category": "book", "price": 200},
        {"id": 3, "name": "오염1", "category": "food", "price": -1},
    ]

    valid, invalid = transform(rows)

    assert len(valid) + len(invalid) == len(rows)


def sample_products() -> list[Product]:
    return [
        Product(
            id=1,
            name="A",
            category="food",
            price=100,
        )
    ]


def test_csv_파일_생성(tmp_path: Path):
    result = load(sample_products(), tmp_path)

    assert Path(result["csv"]).exists()


def test_parquet_파일_생성(tmp_path: Path):
    result = load(sample_products(), tmp_path)

    assert Path(result["parquet"]).exists()


def test_parquet_라운드트립(tmp_path: Path):
    result = load(sample_products(), tmp_path)

    assert result["saved_count"] == result["roundtrip_count"]
