from datetime import date

try:
    import holidays as holidays_lib
except Exception:
    holidays_lib = None

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


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
                    "name": str(name),
                    "weekday": WEEKDAYS[day.weekday()]
                })
        except Exception:
            pass
    if not items:
        today = date(year, 1, 1)
        items = [{"date": today.isoformat(), "name": "Neujahr", "weekday": WEEKDAYS[today.weekday()]}]
    return items
