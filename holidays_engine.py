import re
from datetime import date, timedelta

try:
    import holidays as holidays_lib
except Exception:
    holidays_lib = None

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

REGIONS = [
    {
        "group": "Schweiz",
        "options": [
            {"value": "CH-ZH", "label": "Zuerich (ZH)"},
            {"value": "CH-BE", "label": "Bern (BE)"},
            {"value": "CH-AG", "label": "Aargau (AG)"},
            {"value": "CH-BS", "label": "Basel-Stadt (BS)"},
            {"value": "CH-SG", "label": "St. Gallen (SG)"},
            {"value": "CH-TI", "label": "Tessin (TI)"},
        ],
    },
    {
        "group": "Deutschland",
        "options": [
            {"value": "DE", "label": "Deutschland"},
            {"value": "DE-BW", "label": "Baden-Wuerttemberg"},
            {"value": "DE-BY", "label": "Bayern"},
            {"value": "DE-NW", "label": "Nordrhein-Westfalen"},
        ],
    },
    {"group": "Oesterreich", "options": [{"value": "AT", "label": "Oesterreich"}]},
]


def get_all_regions():
    return REGIONS


def _filename(day: date, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"holiday_{day.isoformat()}_{slug}.wav"


def _holiday_item(day: date, name: str):
    return {
        "date": day.isoformat(),
        "date_iso": day.isoformat(),
        "date_display": day.strftime("%d.%m.%Y"),
        "name": str(name),
        "weekday": WEEKDAYS[day.weekday()],
        "filename": _filename(day, str(name)),
    }


def _with_bridge_days(items: list[dict], year: int):
    result = list(items)
    existing_dates = {item["date"] for item in result}
    for item in items:
        day = date.fromisoformat(item["date"])
        if day.weekday() != 3:
            continue
        bridge_day = day + timedelta(days=1)
        if bridge_day.year != year or bridge_day.isoformat() in existing_dates:
            continue
        result.append(_holiday_item(bridge_day, f"Brueckentag nach {item['name']}"))
        existing_dates.add(bridge_day.isoformat())
    return sorted(result, key=lambda item: item["date"])


def get_holidays(region: str, year: int, include_bridge_days: bool = False):
    region = (region or "CH-ZH").upper()
    country, _, subdiv = region.partition("-")
    items = []
    if holidays_lib:
        kwargs = {"years": [year]}
        if country == "CH" and subdiv:
            kwargs["subdiv"] = subdiv
        try:
            h = holidays_lib.country_holidays(country, **kwargs)
            for day, name in sorted(h.items()):
                items.append(_holiday_item(day, str(name)))
        except Exception:
            pass
    if not items:
        today = date(year, 1, 1)
        items = [_holiday_item(today, "Neujahr")]
    if include_bridge_days:
        items = _with_bridge_days(items, year)
    return items
