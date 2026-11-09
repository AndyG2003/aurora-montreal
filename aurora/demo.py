from datetime import datetime, timedelta

from .decision import LABELS, forecast_alerts, urgent_alert
from .feeds import HOUR, KpBin, Weather
from .sites import LOCAL, SITES


def scenario():
    start = datetime(2026, 11, 12, 19, tzinfo=LOCAL)
    bins = [KpBin(start, 7)]
    weather = {
        site.name: {
            start + delta * HOUR: Weather(cloud, 8, 20_000, 0, -5, 20, 1, 0)
            for delta in range(-1, 4)
        }
        for site, cloud in zip(SITES, (15, 55), strict=True)
    }
    return start, bins, weather


def preview():
    print("SIMULACIÓN CON DATOS FICTICIOS · noviembre de 2026\n")
    start, bins, weather = scenario()
    for hours in (60, 24, 9):
        for alert in forecast_alerts(start - hours * HOUR, bins, weather, {}):
            print(f"{LABELS[alert.stage]}\n{alert.body}\n")
    now = start + timedelta(minutes=5)
    alert = urgent_alert(now, (now, 7.33), weather, {})
    if alert:
        print(f"{LABELS[alert.stage]}\n{alert.body}")
