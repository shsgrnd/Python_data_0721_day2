from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    """리포트 생성에 사용하는 변경 불가능한 설정입니다."""

    data_path: Path = BASE_DIR.parent / "data" / "0721" / "sales_raw.csv"
    output_path: Path = BASE_DIR / "output"
    template_path: Path = BASE_DIR / "templates" / "report.html"
    title: str = "일일 매출 리포트"
    top_n: int = 10
    email_recipient: str = "hideonbush@faker.com"


CONFIG = Config()
