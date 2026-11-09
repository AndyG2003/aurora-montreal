import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FORECAST = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
MINUTE_KP = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
WEATHER = "https://api.open-meteo.com/v1/forecast"
HOUR = timedelta(hours=1)
FIELDS = (
    "cloud_cover", "cloud_cover_low", "visibility", "precipitation",
    "temperature_2m", "wind_gusts_10m", "weather_code", "is_day",
)


def fetch_json(url):
    request = Request(url, headers={"User-Agent": "Montreal-Aurora-Pilot/1.0"})
    with urlopen(request, timeout=8) as response:
        return json.load(response)


def utc_time(value):
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def kp_value(value):
    number = float(value)
    if not isfinite(number) or not 0 <= number <= 9:
        raise ValueError("Invalid Kp")
    return number


@dataclass(frozen=True)
class KpBin:
    start: datetime
    kp: float
    kind: str = "predicted"

    @property
    def end(self):
        return self.start + 3 * HOUR


def parse_forecast(payload, now):
    if payload and isinstance(payload[0], list):
        header, *rows = payload
        payload = [dict(zip(header, row)) for row in rows]
    bins = [
        KpBin(utc_time(row["time_tag"]), kp_value(row["kp"]), row["observed"])
        for row in payload
    ]
    recent = [
        row for row in bins
        if now - 9 * HOUR <= row.start <= now and row.kind in {"observed", "estimated"}
    ]
    forecast = [
        row for row in bins if row.kind in {"predicted", "estimated"}
        and row.end > now and row.start <= now + 72 * HOUR
    ]
    if not recent or not forecast:
        raise ValueError("Stale or incomplete NOAA forecast")
    return forecast


def parse_active(payload, now):
    samples = {}
    for row in payload:
        stamp = utc_time(row["time_tag"])
        if now - timedelta(minutes=20) <= stamp <= now and row["estimated_kp"] is not None:
            samples[stamp] = kp_value(row["estimated_kp"])
    if not samples or now - max(samples) > timedelta(minutes=10):
        raise ValueError("Stale NOAA minute estimate")
    timestamps = sorted(samples)
    latest = timestamps[-1]
    # A single spike (or duplicated timestamp) cannot trigger an urgent push.
    for index, start in enumerate(timestamps):
        if latest - start >= timedelta(minutes=5):
            sustained = timestamps[index:]
            continuous = all(b - a <= timedelta(minutes=2) for a, b in zip(sustained, sustained[1:]))
            if continuous and all(samples[stamp] >= 7 for stamp in sustained):
                return latest, samples[latest]
    return None


@dataclass(frozen=True)
class Weather:
    cloud: float
    low_cloud: float
    visibility: float
    precip: float
    temperature: float
    gusts: float
    code: float
    daylight: float

    @property
    def suitable(self):
        return (
            self.daylight == 0 and self.cloud <= 30 and self.low_cloud <= 20
            and self.visibility >= 10_000 and self.precip == 0
            and self.temperature >= -15 and self.gusts <= 40 and self.code in {0, 1, 2, 3}
        )


def parse_weather(payload):
    if payload["utc_offset_seconds"] != 0:
        raise ValueError("Expected UTC weather hours")
    hourly = payload["hourly"]
    rows = {}
    for stamp, *values in zip(hourly["time"], *(hourly[field] for field in FIELDS), strict=True):
        if all(type(value) in {int, float} and isfinite(value) for value in values):
            rows[utc_time(stamp)] = Weather(*values)
    if not rows:
        raise ValueError("No usable Open-Meteo hours")
    return rows


def get_weather(site):
    query = urlencode({
        "latitude": site.latitude, "longitude": site.longitude,
        "hourly": ",".join(FIELDS), "forecast_days": 5, "timezone": "GMT",
        "temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm",
    })
    return parse_weather(fetch_json(f"{WEATHER}?{query}"))
