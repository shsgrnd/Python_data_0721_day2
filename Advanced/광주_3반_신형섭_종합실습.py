"""
------------------------------
파일명 : 광주_3반_신형섭_종합실습.py
작성일 : 2026-07-21
작성자 : 광주 3반 신형섭
실습 목적 : 3개 공개 API를 비동기로 수집하고 검증·저장·성능 비교
변경 내역 : asyncio/httpx 수집, Pydantic v2 검증, CSV/Parquet 저장 구현
------------------------------
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import httpx
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


# 과제에서 지정한 세 공개 API
API_URLS = {
    "weather": "https://api.open-meteo.com/v1/forecast",
    "country": "https://countries.dev/alpha/KOR",
    "ip": "http://ip-api.com/json/8.8.8.8",
}
WEATHER_PARAMS = {
    "latitude": 37.5665,
    "longitude": 126.9780,
    "hourly": "temperature_2m,precipitation_probability",
    "forecast_days": 3,
    "timezone": "Asia/Seoul",
}
IP_PARAMS = {
    "fields": "status,message,query,country,countryCode,regionName,city,lat,lon,timezone"
}


class PipelineError(RuntimeError):
    """수집 또는 검증 단계의 오류를 사용자에게 설명하기 위한 예외."""


# ------------------------------
# Pydantic v2 스키마
# ------------------------------
class HourlyWeather(BaseModel):
    time: datetime
    temperature_c: float = Field(ge=-100, le=70)
    precipitation_probability: int = Field(ge=0, le=100)


class WeatherHourlyPayload(BaseModel):
    time: list[datetime]
    temperature_2m: list[float]
    precipitation_probability: list[int]

    @model_validator(mode="after")
    def validate_array_lengths(self) -> "WeatherHourlyPayload":
        lengths = {
            len(self.time),
            len(self.temperature_2m),
            len(self.precipitation_probability),
        }
        if len(lengths) != 1:
            raise ValueError("시간·기온·강수확률 배열 길이가 서로 다릅니다")
        return self


class WeatherResponse(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = Field(min_length=1)
    hourly: WeatherHourlyPayload

    def to_hourly_forecasts(self) -> list[HourlyWeather]:
        return [
            HourlyWeather(
                time=time,
                temperature_c=temperature,
                precipitation_probability=probability,
            )
            for time, temperature, probability in zip(
                self.hourly.time,
                self.hourly.temperature_2m,
                self.hourly.precipitation_probability,
            )
        ]


class Currency(BaseModel):
    code: str = Field(min_length=3, max_length=3)
    name: str = Field(min_length=1)
    symbol: str | None = None


class CountryInfo(BaseModel):
    name: str = Field(min_length=1)
    alpha2_code: str = Field(alias="alpha2Code", pattern=r"^[A-Z]{2}$")
    alpha3_code: str = Field(alias="alpha3Code", pattern=r"^[A-Z]{3}$")
    capital: str = Field(min_length=1)
    region: str = Field(min_length=1)
    subregion: str = Field(min_length=1)
    population: int = Field(gt=0)
    area: float = Field(gt=0)
    latlng: tuple[float, float]
    currencies: list[Currency] = Field(min_length=1)

    @field_validator("latlng")
    @classmethod
    def validate_coordinates(cls, value: tuple[float, float]) -> tuple[float, float]:
        latitude, longitude = value
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("국가 좌표 범위를 벗어났습니다")
        return value


class IpLocation(BaseModel):
    status: Literal["success"]
    query: IPv4Address | IPv6Address
    country: str = Field(min_length=1)
    country_code: str = Field(alias="countryCode", pattern=r"^[A-Z]{2}$")
    region_name: str = Field(alias="regionName", min_length=1)
    city: str = Field(min_length=1)
    latitude: float = Field(alias="lat", ge=-90, le=90)
    longitude: float = Field(alias="lon", ge=-180, le=180)
    timezone: str = Field(min_length=1)


# ------------------------------
# Extract: 세 API 동시 수집
# ------------------------------
async def fetch_json(
    client: httpx.AsyncClient,
    name: str,
    url: str,
    params: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    response = await client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise PipelineError(f"{name} API 응답이 JSON 객체가 아닙니다")
    return name, payload


async def collect_all(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    """asyncio.gather를 사용해 세 API를 동시에 호출한다."""
    requests = (
        fetch_json(client, "weather", API_URLS["weather"], WEATHER_PARAMS),
        fetch_json(client, "country", API_URLS["country"]),
        fetch_json(client, "ip", API_URLS["ip"], IP_PARAMS),
    )
    results = await asyncio.gather(*requests, return_exceptions=True)

    payloads: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for name, result in zip(API_URLS, results):
        if isinstance(result, BaseException):
            failures.append(f"{name}: {result}")
        else:
            result_name, payload = result
            payloads[result_name] = payload

    if failures:
        raise PipelineError("API 수집 실패 - " + "; ".join(failures))
    return payloads


# ------------------------------
# Transform: 스키마 검증 및 표 정규화
# ------------------------------
def validate_payloads(
    payloads: dict[str, dict[str, Any]],
) -> tuple[WeatherResponse, CountryInfo, IpLocation]:
    try:
        return (
            WeatherResponse.model_validate(payloads["weather"]),
            CountryInfo.model_validate(payloads["country"]),
            IpLocation.model_validate(payloads["ip"]),
        )
    except (KeyError, ValidationError) as error:
        raise PipelineError(f"스키마 검증 실패: {error}") from error


def to_dataframe(
    weather: WeatherResponse,
    country: CountryInfo,
    ip_location: IpLocation,
) -> pd.DataFrame:
    """3일 예보 72개 행에 국가 및 IP 지역 정보를 결합한다."""
    common_fields = {
        "country_name": country.name,
        "country_code": country.alpha3_code,
        "capital": country.capital,
        "population": country.population,
        "area_km2": country.area,
        "ip": str(ip_location.query),
        "ip_country": ip_location.country,
        "ip_city": ip_location.city,
        "ip_timezone": ip_location.timezone,
    }
    rows = [
        {
            **common_fields,
            "forecast_time": forecast.time,
            "temperature_c": forecast.temperature_c,
            "precipitation_probability": forecast.precipitation_probability,
        }
        for forecast in weather.to_hourly_forecasts()
    ]
    return pd.DataFrame(rows)


# ------------------------------
# Load: CSV/Parquet 저장 및 성능 측정
# ------------------------------
def save_and_benchmark(dataframe: pd.DataFrame, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "csv": output_dir / "collected_data.csv",
        "parquet": output_dir / "collected_data.parquet",
    }
    metrics: dict[str, Any] = {}

    for file_format, path in paths.items():
        write_start = perf_counter()
        if file_format == "csv":
            dataframe.to_csv(path, index=False, encoding="utf-8-sig")
        else:
            dataframe.to_parquet(path, index=False)
        write_ms = (perf_counter() - write_start) * 1_000

        read_start = perf_counter()
        restored = pd.read_csv(path) if file_format == "csv" else pd.read_parquet(path)
        read_ms = (perf_counter() - read_start) * 1_000

        if len(restored) != len(dataframe):
            raise PipelineError(f"{file_format} 라운드트립 건수가 일치하지 않습니다")
        metrics[file_format] = {
            "path": str(path),
            "rows": len(restored),
            "size_bytes": path.stat().st_size,
            "write_ms": round(write_ms, 3),
            "read_ms": round(read_ms, 3),
        }
    return metrics


async def run(output_dir: Path | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0), follow_redirects=True
    ) as client:
        payloads = await collect_all(client)

    dataframe = to_dataframe(*validate_payloads(payloads))
    output_dir = output_dir or Path(__file__).parent / "output"
    return {
        "validated_rows": len(dataframe),
        "formats": save_and_benchmark(dataframe, output_dir),
    }


def main() -> None:
    result = asyncio.run(run())
    print(f"검증 완료: {result['validated_rows']}개 시간대")
    for file_format, metrics in result["formats"].items():
        print(
            f"{file_format.upper():7} | 쓰기 {metrics['write_ms']:8.3f} ms | "
            f"읽기 {metrics['read_ms']:8.3f} ms | {metrics['size_bytes']:6} bytes"
        )


if __name__ == "__main__":
    main()
