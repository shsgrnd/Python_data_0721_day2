from datetime import datetime
from email.message import EmailMessage
import os
from pathlib import Path
import smtplib
import sys
import time
from typing import Callable, TypeVar

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import CONFIG, Config


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from Total2 import capstrone02_eda_ml as total2  # noqa: E402
from practice3 import ex03_async_collector as practice3_retry  # noqa: E402


REQUIRED_COLUMNS = {
    "order_id",
    "category",
    "quantity",
    "unit_price",
    "discount",
}
T = TypeVar("T")


def load_data(data_path: Path) -> pd.DataFrame:
    """원본 매출 CSV를 읽고 주문별 실매출액을 계산합니다."""
    if not data_path.exists():
        raise FileNotFoundError(f"매출 데이터 파일을 찾을 수 없습니다: {data_path}")

    df = pd.read_csv(data_path)
    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"필수 열이 없습니다: {', '.join(sorted(missing))}")

    numeric_columns = ["quantity", "unit_price", "discount"]
    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors="coerce")
    df["unit_price"] = df["unit_price"].mask(df["unit_price"] < 0)

    # 원본 데이터의 결측 단가와 이상치를 그대로 매출에 반영하지 않습니다.
    category_medians = df.groupby("category", observed=True)["unit_price"].transform("median")
    df["unit_price"] = df["unit_price"].fillna(category_medians)
    df["unit_price"] = df["unit_price"].fillna(df["unit_price"].median())
    df["discount"] = df["discount"].fillna(0)

    if df[["quantity", "unit_price"]].isna().any().any():
        raise ValueError("quantity 또는 unit_price 열에 복구할 수 없는 결측값이 있습니다.")
    if not df["discount"].between(0, 1).all():
        raise ValueError("discount 값은 0 이상 1 이하여야 합니다.")

    # IQR 경계로 원저라이징하여 비정상적인 수량/단가가 KPI를 왜곡하지 않게 합니다.
    for column in ("quantity", "unit_price"):
        q1, q3 = df[column].quantile([0.25, 0.75])
        iqr = q3 - q1
        df[column] = df[column].clip(q1 - 1.5 * iqr, q3 + 1.5 * iqr)

    df["amount"] = df["quantity"] * df["unit_price"] * (1 - df["discount"])
    return df


def aggregate(df: pd.DataFrame, top_n: int = 10) -> dict:
    """리포트에 표시할 KPI와 카테고리별 매출을 집계합니다."""
    total_sales = float(df["amount"].sum())
    order_count = int(df["order_id"].nunique())
    average_order = total_sales / order_count if order_count else 0.0

    by_category = (
        df.groupby("category", observed=True)["amount"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .reset_index()
    )
    by_category["amount"] = by_category["amount"].round(0).astype(int)

    return {
        "kpi": {
            "총매출": round(total_sales),
            "주문수": order_count,
            "평균주문액": round(average_order),
        },
        "by_category": by_category.to_dict("records"),
    }


def create_total2_chart_html() -> str:
    """종합 2의 전처리와 그래프 구성을 재사용해 HTML 조각을 만듭니다."""
    raw_data = total2.load_data(total2.DATA_PATH)
    total2.validate_columns(raw_data)
    analysis_data = total2.prepare_analysis_data(raw_data)

    chart_data = (
        analysis_data.select(total2.TARGET_COLUMN, total2.CHARGE_COLUMN)
        .drop_nulls()
        .to_pandas()
    )
    figure = total2.px.box(
        chart_data,
        x=total2.TARGET_COLUMN,
        y=total2.CHARGE_COLUMN,
        color=total2.TARGET_COLUMN,
        title="이탈 여부별 월 요금 분포",
        labels={
            total2.TARGET_COLUMN: "이탈 여부",
            total2.CHARGE_COLUMN: "월 요금",
        },
    )
    return figure.to_html(full_html=False, include_plotlyjs="cdn")


def render_report(context: dict, template_path: Path) -> str:
    """별도 Jinja2 템플릿을 이용해 HTML을 렌더링합니다."""
    if not template_path.exists():
        raise FileNotFoundError(f"리포트 템플릿을 찾을 수 없습니다: {template_path}")

    environment = Environment(
        loader=FileSystemLoader(template_path.parent),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template(template_path.name)
    return template.render(**context)


def retry(action: Callable[[], T], attempts: int, delay_seconds: float, label: str) -> T:
    """작업 실패 시 지정 횟수만큼 대기 후 다시 시도합니다."""
    if attempts < 1:
        raise ValueError("재시도 횟수는 1 이상이어야 합니다.")

    for attempt in range(1, attempts + 1):
        try:
            return action()
        except Exception:
            if attempt == attempts:
                raise
            delay = delay_seconds * (2 ** (attempt - 1))
            print(f"{label} 실패 ({attempt}/{attempts}) - {delay}초 후 재시도")
            time.sleep(delay)
    raise RuntimeError("도달할 수 없는 재시도 상태입니다.")


def generate_report(config: Config = CONFIG) -> Path:
    """데이터를 집계해 타임스탬프가 붙은 HTML 리포트를 생성합니다."""
    generated_at = datetime.now()
    df = load_data(config.data_path)
    summary = aggregate(df, config.top_n)

    context = {
        "title": config.title,
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "chart_html": create_total2_chart_html(),
        **summary,
    }
    html = render_report(context, config.template_path)

    config.output_path.mkdir(parents=True, exist_ok=True)
    output_file = config.output_path / f"sales_report_{generated_at:%Y%m%d_%H%M%S_%f}.html"
    output_file.write_text(html, encoding="utf-8")
    print(f"리포트 생성 완료: {output_file}")
    return output_file


def send_email_notification(report_path: Path, config: Config = CONFIG) -> bool:
    """SMTP가 설정된 경우 생성된 HTML 리포트를 이메일로 첨부합니다."""
    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        print("이메일 알림 건너뜀: SMTP_HOST 환경변수가 설정되지 않았습니다.")
        return False

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM") or username
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes"}
    use_ssl = os.getenv("SMTP_USE_SSL", "false").strip().lower() in {"1", "true", "yes"}

    if not sender:
        raise ValueError("이메일 발신 주소가 없습니다. SMTP_FROM 또는 SMTP_USERNAME을 설정하세요.")

    message = EmailMessage()
    message["Subject"] = f"[{config.title}] 리포트 생성 완료"
    message["From"] = sender
    message["To"] = config.email_recipient
    message.set_content(
        f"{config.title}가 생성되었습니다.\n"
        f"생성 파일: {report_path.name}\n\n"
        "HTML 리포트는 이 메일에 첨부되어 있습니다."
    )
    message.add_attachment(
        report_path.read_bytes(),
        maintype="text",
        subtype="html",
        filename=report_path.name,
    )

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(smtp_host, smtp_port, timeout=30) as smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)

    print(f"이메일 알림 전송 완료: {config.email_recipient}")
    return True


def run_once(config: Config = CONFIG) -> Path:
    """리포트를 생성하고 이메일로 알리며 실패한 작업을 재시도합니다."""
    report_path = retry(
        lambda: generate_report(config),
        practice3_retry.MAX_ATTEMPTS,
        practice3_retry.BACKOFF_SECONDS,
        "리포트 생성",
    )

    if os.getenv("SMTP_HOST"):
        try:
            retry(
                lambda: send_email_notification(report_path, config),
                practice3_retry.MAX_ATTEMPTS,
                practice3_retry.BACKOFF_SECONDS,
                "이메일 알림",
            )
        except Exception as error:
            print(f"이메일 알림 최종 실패: {error}")
    else:
        send_email_notification(report_path, config)

    return report_path


def main() -> None:
    run_once()


if __name__ == "__main__":
    main()
