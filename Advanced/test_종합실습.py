import asyncio
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from Python_data_0721_day2.Advanced.광주_3반_신형섭_종합실습 import (
    HourlyWeather,
    IpLocation,
    WeatherResponse,
    collect_all,
    save_and_benchmark,
    to_dataframe,
    validate_payloads,
)


@pytest.fixture
def payloads() -> dict:
    return {
        "weather": {
            "latitude": 37.5,
            "longitude": 127.0,
            "timezone": "Asia/Seoul",
            "hourly": {
                "time": ["2026-07-21T00:00", "2026-07-21T01:00"],
                "temperature_2m": [25.1, 24.8],
                "precipitation_probability": [10, 20],
            },
        },
        "country": {
            "name": "South Korea",
            "alpha2Code": "KR",
            "alpha3Code": "KOR",
            "capital": "Seoul",
            "region": "Asia",
            "subregion": "Eastern Asia",
            "population": 51_000_000,
            "area": 100_210,
            "latlng": [37, 127.5],
            "currencies": [{"code": "KRW", "name": "Won", "symbol": "₩"}],
        },
        "ip": {
            "status": "success",
            "query": "8.8.8.8",
            "country": "United States",
            "countryCode": "US",
            "regionName": "Virginia",
            "city": "Ashburn",
            "lat": 39.03,
            "lon": -77.5,
            "timezone": "America/New_York",
        },
    }


def test_three_apis_are_collected(payloads: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "open-meteo" in request.url.host:
            data = payloads["weather"]
        elif "countries.dev" in request.url.host:
            data = payloads["country"]
        else:
            data = payloads["ip"]
        return httpx.Response(200, json=data)

    async def scenario() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await collect_all(client)

    assert set(asyncio.run(scenario())) == {"weather", "country", "ip"}


def test_weather_array_lengths_must_match(payloads: dict) -> None:
    payloads["weather"]["hourly"]["temperature_2m"].pop()
    with pytest.raises(ValidationError, match="배열 길이"):
        WeatherResponse.model_validate(payloads["weather"])


@pytest.mark.parametrize("probability", [-1, 101])
def test_precipitation_probability_range(probability: int) -> None:
    with pytest.raises(ValidationError):
        HourlyWeather(
            time="2026-07-21T00:00",
            temperature_c=20,
            precipitation_probability=probability,
        )


def test_invalid_ip_status_is_rejected(payloads: dict) -> None:
    payloads["ip"]["status"] = "fail"
    with pytest.raises(ValidationError):
        IpLocation.model_validate(payloads["ip"])


def test_validated_payloads_become_hourly_rows(payloads: dict) -> None:
    dataframe = to_dataframe(*validate_payloads(payloads))
    assert len(dataframe) == 2
    assert dataframe.loc[0, "country_code"] == "KOR"
    assert dataframe.loc[1, "precipitation_probability"] == 20


def test_csv_and_parquet_roundtrip(payloads: dict, tmp_path: Path) -> None:
    dataframe = to_dataframe(*validate_payloads(payloads))
    result = save_and_benchmark(dataframe, tmp_path)

    assert result["csv"]["rows"] == len(dataframe)
    assert result["parquet"]["rows"] == len(dataframe)
    assert Path(result["csv"]["path"]).exists()
    assert Path(result["parquet"]["path"]).exists()
