import re
from datetime import date

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


def get_holidays(region: str, year: int):
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
                items.append({
                    "date": day.isoformat(),
                    "date_iso": day.isoformat(),
                    "date_display": day.strftime("%d.%m.%Y"),
                    "name": str(name),
                    "weekday": WEEKDAYS[day.weekday()],
                    "filename": _filename(day, str(name)),
                })
        except Exception:
            pass
    if not items:
        today = date(year, 1, 1)
        items = [{
            "date": today.isoformat(),
            "date_iso": today.isoformat(),
            "date_display": today.strftime("%d.%m.%Y"),
            "name": "Neujahr",
            "weekday": WEEKDAYS[today.weekday()],
            "filename": _filename(today, "Neujahr"),
        }]
    return items
