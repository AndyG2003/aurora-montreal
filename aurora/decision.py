from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .feeds import HOUR
from .sites import FIRST_NIGHT, LAST_NIGHT, LOCAL, SITES, STM_PLANNER

STAGES = ("early", "action", "final")
LABELS = {
    "early": "Aviso preliminar (48–72 h)", "action": "Preparación (~24 h)",
    "final": "Evaluación final", "urgent": "Actividad intensa en curso",
    "downgrade": "Condiciones deterioradas", "upgrade": "Condiciones mejoradas",
}


@dataclass(frozen=True)
class Alert:
    night: str
    stage: str
    status: str
    body: str
    start: datetime
    end: datetime


def local_window(start, end):
    return f"{start.astimezone(LOCAL):%d/%m %H:%M}–{end.astimezone(LOCAL):%H:%M} EST"


def evening_hours(site, night):
    opens, cutoff = site.hours(night)
    start = max(opens, datetime.combine(night, time(17), LOCAL))
    if start.minute:
        start = start.replace(minute=0) + HOUR
    while start + HOUR <= cutoff:
        yield start
        start += HOUR


def forecast_night(now, night, bins, weather):
    strong_hours = {}
    coverage = set()
    candidates = []
    assessments = {}
    for site in SITES:
        conditions = weather.get(site.name, {})
        usable = {}
        incomplete = False
        for hour in evening_hours(site, night):
            if hour <= now:
                continue
            scores = [row.kp for row in bins if row.start <= hour and hour + HOUR <= row.end]
            if not scores:
                continue
            coverage.add(hour)
            if max(scores) < 6:
                continue
            before, current, after = (conditions.get(hour + delta) for delta in (-HOUR, timedelta(), HOUR))
            if (current and current.daylight) or (after and after.daylight):
                continue
            strong_hours[hour] = max(scores)
            if not all((before, current, after)):
                incomplete = True
                continue
            # Require a dark prior hourly sample to screen out twilight near sunset.
            if before.daylight == 0 and current.suitable and after.suitable:
                usable[hour] = max(current.cloud, after.cloud)
        site_candidates = [
            (max(cloud, usable[hour + HOUR]), hour, site.name, site)
            for hour, cloud in usable.items() if hour + HOUR in usable
        ]
        best = min(site_candidates, default=None)
        if best:
            candidates.append(best)
            assessments[site.name] = f"ventana candidata, hasta {best[0]:g}% de nubes"
        else:
            assessments[site.name] = "datos incompletos" if incomplete else "sin ventana apta"
    return strong_hours, coverage, min(candidates, default=None), assessments


def site_details(site):
    return (
        f"{site.name}. {site.access}\n"
        "Tarifa de referencia: 14 CAD ida y vuelta para dos, con dos boletos de 2 viajes y trayecto íntegro en zona A.\n"
        "Confirmen ida y regreso con STM, el último enlace y una alternativa. Verifiquen cierres y carteles, "
        "la salida antes del cierre y un recorrido peatonal habilitado y seguro de hasta una hora desde la parada. "
        "Eviten arcenes, senderos aislados y hielo. Si falla alguna verificación, descarten la salida.\n"
        f"{STM_PLANNER}\n{site.city_page}"
    )


def forecast_alerts(now, bins, weather, history):
    today = now.astimezone(LOCAL).date()
    for offset in range(4):
        night = today + timedelta(days=offset)
        if not FIRST_NIGHT <= night <= LAST_NIGHT:
            continue
        key = night.isoformat()
        sent = history.get(key, {})
        hours, coverage, best, assessments = forecast_night(now, night, bins, weather)
        if hours:
            start, end = min(hours), min(hours) + HOUR
            lead = (start - now) / HOUR
            if lead > 72:
                continue
            stage = "early" if lead >= 48 else "action" if lead > 12 else "final"
            # Skip gaps between the early outlook and the ~24 h reassessment.
            if 30 < lead < 48:
                continue
            status = "VIGILANCIA"
            detail = "La nubosidad y la hora de llegada pueden cambiar. Revisen el pronóstico en la próxima actualización."
            if best:
                cloud, start, _, site = best
                end = start + 2 * HOUR
                status = "CONDICIONAL" if stage != "early" else status
                detail = f"Ventana con hasta {cloud:g}% de nubosidad total pronosticada. {site_details(site)}"
            elif stage != "early":
                incomplete = "datos incompletos" in assessments.values()
                status = "DATOS INSUFICIENTES" if incomplete else "NO-GO"
                detail = "Faltan datos para completar la evaluación de los parques." if incomplete else (
                    "Sin dos horas consecutivas de actividad prevista y cielo apto dentro del horario con margen de salida."
                )
            if stage == "action":
                detail += "\n" + " · ".join(f"{name}: {result}" for name, result in assessments.items())
            if stage == "final" and "final" in sent:
                previous = sent.get("upgrade", sent["final"])
                previous_start = datetime.fromisoformat(previous["start"])
                previous_window_ruled_out = (
                    status == "NO-GO" and now < previous_start
                    and {previous_start, previous_start + HOUR} <= coverage
                )
                if previous["status"] == "CONDICIONAL" and previous_window_ruled_out:
                    stage = "downgrade"
                    start, end = previous_start, datetime.fromisoformat(previous["end"])
                    detail += " Descarten el plan anterior."
                elif previous["status"] != "CONDICIONAL" and status == "CONDICIONAL" and "downgrade" not in sent:
                    stage = "upgrade"
            if stage in sent or (stage in STAGES and any(s in sent for s in STAGES[STAGES.index(stage) + 1:])):
                continue
            timing = "Actualización tardía (<6 h). " if stage == "final" and lead < 6 else ""
            body = (
                f"{status} · {local_window(start, end)}. {timing}Kp NOAA de hasta {max(hours.values()):g} "
                f"en la tarde/noche. Es un índice global y el horario puede cambiar.\n{detail}\n"
                "Meteorología de Open-Meteo (evaluada con filtros del piloto)."
            )
            yield Alert(key, stage, status, body, start, end)
        elif "downgrade" not in sent and ("final" in sent or "action" in sent):
            previous = sent.get("upgrade") or sent.get("final") or sent["action"]
            start = datetime.fromisoformat(previous["start"])
            end = datetime.fromisoformat(previous["end"])
            if previous["status"] == "CONDICIONAL" and now < start and {start, start + HOUR} <= coverage:
                yield Alert(key, "downgrade", "NO-GO", (
                    f"NO-GO · {local_window(start, end)}. La evaluación actual ya no identifica "
                    "una ventana candidata para esa noche. Descarten el plan anterior."
                ), start, end)


def urgent_alert(now, active, weather, history):
    night = now.astimezone(LOCAL).date()
    if not active or not FIRST_NIGHT <= night <= LAST_NIGHT or "urgent" in history.get(night.isoformat(), {}):
        return None
    stamp, kp = active
    end_limit = stamp + HOUR  # Expiry for reassessment, independent of predicted storm duration.
    choices = []
    for site in SITES:
        conditions = weather.get(site.name, {})
        for hour in evening_hours(site, night):
            start, end = max(now, hour), min(end_limit, hour + HOUR)
            if end - start < timedelta(minutes=25):
                continue
            before, current, after = (conditions.get(hour + delta) for delta in (-HOUR, timedelta(), HOUR))
            if before and before.daylight == 0 and current and current.suitable and after and after.suitable:
                choices.append((start, current.cloud, site.name, end, site))
    if choices:
        start, _, _, end, site = min(choices)
        body = (
            f"CONDICIONAL · {local_window(start, end)}. NOAA estima Kp {kp:g} reciente. "
            "Revisen el óvalo NOAA ahora. Consideren la ventana solo si ya están cerca y han confirmado el regreso y el acceso.\n"
            f"{site_details(site)}\nMeteorología de Open-Meteo (evaluada con filtros del piloto).\n"
            "https://www.swpc.noaa.gov/products/aurora-30-minute-forecast"
        )
        return Alert(night.isoformat(), "urgent", "CONDICIONAL", body, start, end)
    return None
