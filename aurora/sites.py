from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

# This pilot is entirely within Eastern Standard Time, after the Nov 1 switch.
LOCAL = timezone(timedelta(hours=-5), "EST")
FIRST_NIGHT = date(2026, 11, 9)
LAST_NIGHT = date(2026, 12, 27)
STM_PLANNER = "https://www.stm.info/en/schedules-and-routes/plan-a-route"


@dataclass(frozen=True)
class Site:
    name: str
    latitude: float
    longitude: float
    city_page: str
    access: str
    opens: time = time(7)
    closes: time = time(22)
    exit_buffer: timedelta = timedelta(minutes=30)

    def hours(self, night):
        return (
            datetime.combine(night, self.opens, LOCAL),
            datetime.combine(night, self.closes, LOCAL) - self.exit_buffer,
        )


# Coordinates are approximate forecast sampling points for each sector.
SITES = (
    Site(
        "Anse-à-l’Orme", 45.435, -73.947,
        "https://montreal.ca/en/places/grand-parc-de-louest-anse-lorme",
        "STM 68, parada Parc-nature de l’Anse-à-l’Orme. Verificar el acceso peatonal a la orilla.",
    ),
    Site(
        "Cap-Saint-Jacques", 45.463, -73.937,
        "https://montreal.ca/en/places/grand-parc-de-louest-cap-saint-jacques",
        "STM 68, parada Gouin / du Cap-Saint-Jacques. La playa está cerrada esta temporada.",
    ),
)
