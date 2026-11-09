import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time
from pathlib import Path
from urllib.request import Request, urlopen

from .decision import LABELS, forecast_alerts, urgent_alert
from .feeds import FORECAST, MINUTE_KP, fetch_json, get_weather, parse_active, parse_forecast
from .sites import FIRST_NIGHT, LAST_NIGHT, LOCAL, SITES


def load_state(path):
    if not path.exists():
        return {}
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("version") != 1 or not isinstance(state.get("events"), dict):
        raise ValueError("Invalid alert history")
    return state["events"]


def checkpoint(path, history, git_state, message):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"version": 1, "events": history}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    if git_state:
        for args in (["add", "--", str(path)], ["commit", "-m", message, "--", str(path)], ["push", "origin", "HEAD"]):
            subprocess.run(["git", *args], check=True)


def publish(topic, title, message, priority=3):
    payload = json.dumps({"topic": topic, "title": title, "message": message, "priority": priority}).encode()
    request = Request("https://ntfy.sh", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=8) as response:
            confirmation = json.load(response)
        if confirmation.get("event") != "message" or not isinstance(confirmation.get("id"), str):
            raise ValueError("Unexpected confirmation")
        return confirmation["id"]
    except (OSError, ValueError, AttributeError) as error:
        code = getattr(error, "code", None)
        # Keep the topic, request, and any upstream response body out of logs.
        raise RuntimeError(f"ntfy publish unconfirmed{f' (HTTP {code})' if code else ''}") from None


def deliver(alert, topic, history, save):
    event = history.setdefault(alert.night, {})
    if alert.stage in event:
        return
    record = {
        "delivery": "pending", "attempted_at": datetime.now(UTC).isoformat(),
        "status": alert.status, "start": alert.start.isoformat(), "end": alert.end.isoformat(), "body": alert.body,
    }
    event[alert.stage] = record
    save(f"Reserve aurora alert {alert.night} {alert.stage}")
    try:
        message_id = publish(topic, f"Aurora Montréal · {LABELS[alert.stage]}", alert.body, 4 if alert.stage == "urgent" else 3)
    except RuntimeError:
        record["delivery"] = "unconfirmed"
        save(f"Record unconfirmed aurora alert {alert.night} {alert.stage}")
        raise
    record.update(delivery="accepted", message_id=message_id, accepted_at=datetime.now(UTC).isoformat())
    save(f"Record accepted aurora alert {alert.night} {alert.stage}")


def checked(future, service, failures, fallback):
    try:
        return future.result()
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        print(f"{service}: datos no disponibles ({type(error).__name__}).", file=sys.stderr)
        failures.append(service)
        return fallback


def collect(now):
    failures = []
    weather = {}
    local_time = now.astimezone(LOCAL).time()
    with ThreadPoolExecutor(max_workers=3) as pool:
        forecast = pool.submit(lambda: parse_forecast(fetch_json(FORECAST), now))
        minute = None
        if time(16, 30) <= local_time < time(21):
            minute = pool.submit(lambda: parse_active(fetch_json(MINUTE_KP), now))
        bins = checked(forecast, "NOAA forecast", failures, [])
        active = checked(minute, "NOAA minute estimate", failures, None) if minute else None
        if active or any(row.kp >= 6 for row in bins):
            weather_jobs = {site.name: pool.submit(get_weather, site) for site in SITES}
            for name, future in weather_jobs.items():
                weather[name] = checked(future, f"Open-Meteo {name}", failures, {})
    return bins, active, weather, failures


def main():
    parser = argparse.ArgumentParser(description="Montréal aurora pilot. Live feeds in dry-run mode by default.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--send", action="store_true")
    modes.add_argument("--test-push", action="store_true")
    modes.add_argument("--demo", action="store_true")
    parser.add_argument("--state", type=Path, default=Path(".aurora-state.json"))
    parser.add_argument("--git-state", action="store_true", help="Commit and push every delivery checkpoint")
    args = parser.parse_args()

    if args.demo:
        from .demo import preview
        preview()
        return 0

    topic = os.environ.get("NTFY_TOPIC", "")
    if args.send or args.test_push:
        if not re.fullmatch(r"aurora-[a-f0-9]{48}", topic):
            parser.error("Set NTFY_TOPIC to aurora- followed by 48 random hexadecimal characters.")
    try:
        if args.test_push:
            publish(topic, "Prueba de avisos de aurora", "Prueba de entrega en ambos Android. Mensaje de configuración.")
            print("ntfy aceptó la prueba. Comprueben la notificación en los dos teléfonos.")
            return 0
        now = datetime.now(UTC)
        if not FIRST_NIGHT <= now.astimezone(LOCAL).date() <= LAST_NIGHT:
            print("Fuera del periodo de seguimiento.")
            return 0
        history = load_state(args.state)
        bins, active, weather, failures = collect(now)
        urgent = urgent_alert(now, active, weather, history)
        alerts = list(forecast_alerts(now, bins, weather, history))
        if urgent:
            alerts = [urgent] + [alert for alert in alerts if alert.night != urgent.night]
        if not alerts:
            print("Sin avisos nuevos para esta evaluación.")
        for alert in alerts:
            print(f"{LABELS[alert.stage]} · {alert.body}")
            if args.send:
                deliver(alert, topic, history, lambda msg: checkpoint(args.state, history, args.git_state, msg))
        return int(bool(failures))
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Ejecución incompleta. {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
