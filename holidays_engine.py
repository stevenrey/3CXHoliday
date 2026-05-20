"""
Holidays engine – wraps the `holidays` library and returns structured dicts.
Supports CH (kantonsweise), AT (bundesländer), DE (bundesländer), FR, IT.
"""
import holidays as hol
from datetime import date, timedelta

REGION_MAP = {
    # Schweiz
    "CH":    ("CH", None),
    "CH-ZH": ("CH", "ZH"),
    "CH-BE": ("CH", "BE"),
    "CH-AG": ("CH", "AG"),
    "CH-BS": ("CH", "BS"),
    "CH-BL": ("CH", "BL"),
    "CH-SG": ("CH", "SG"),
    "CH-TI": ("CH", "TI"),
    "CH-VD": ("CH", "VD"),
    "CH-GE": ("CH", "GE"),
    "CH-LU": ("CH", "LU"),
    "CH-SO": ("CH", "SO"),
    "CH-TG": ("CH", "TG"),
    "CH-GR": ("CH", "GR"),
    "CH-FR": ("CH", "FR"),
    # Österreich
    "AT":    ("AT", None),
    "AT-W":  ("AT", "W"),
    "AT-NO": ("AT", "NO"),
    "AT-OO": ("AT", "OO"),
    "AT-K":  ("AT", "K"),
    "AT-ST": ("AT", "ST"),
    "AT-T":  ("AT", "T"),
    # Deutschland
    "DE":    ("DE", None),
    "DE-BY": ("DE", "BY"),
    "DE-BW": ("DE", "BW"),
    "DE-NW": ("DE", "NW"),
    "DE-HE": ("DE", "HE"),
    "DE-SN": ("DE", "SN"),
}

WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def get_holidays(region: str, year: int) -> list[dict]:
    region = region.upper()
    entry = REGION_MAP.get(region, ("CH", "ZH"))
    country, subdiv = entry

    try:
        if subdiv:
            h = hol.country_holidays(country, subdiv=subdiv, years=year, language="de")
        else:
            h = hol.country_holidays(country, years=year, language="de")
    except Exception:
        # Fallback without language
        try:
            if subdiv:
                h = hol.country_holidays(country, subdiv=subdiv, years=year)
            else:
                h = hol.country_holidays(country, years=year)
        except Exception:
            return []

    result = []
    for d, name in sorted(h.items()):
        filename = f"holiday_{d.isoformat()}_{name.lower().replace(' ', '_').replace('/', '_')[:40]}.wav"
        result.append({
            "date": d.strftime("%d.%m.%Y"),
            "date_iso": d.isoformat(),
            "weekday": WEEKDAYS_DE[d.weekday()],
            "name": name,
            "filename": filename,
            "year": d.year,
            "month": d.month,
            "day": d.day,
        })
    return result


def get_all_regions() -> list[dict]:
    """Return list of region choices grouped."""
    return [
        {"group": "Schweiz", "options": [
            {"value": "CH-ZH", "label": "Zürich (ZH)"},
            {"value": "CH-BE", "label": "Bern (BE)"},
            {"value": "CH-AG", "label": "Aargau (AG)"},
            {"value": "CH-BS", "label": "Basel-Stadt (BS)"},
            {"value": "CH-BL", "label": "Basel-Landschaft (BL)"},
            {"value": "CH-SG", "label": "St. Gallen (SG)"},
            {"value": "CH-TI", "label": "Tessin (TI)"},
            {"value": "CH-VD", "label": "Waadt (VD)"},
            {"value": "CH-GE", "label": "Genf (GE)"},
            {"value": "CH-LU", "label": "Luzern (LU)"},
            {"value": "CH-SO", "label": "Solothurn (SO)"},
            {"value": "CH-TG", "label": "Thurgau (TG)"},
            {"value": "CH-GR", "label": "Graubünden (GR)"},
            {"value": "CH-FR", "label": "Freiburg (FR)"},
        ]},
        {"group": "Österreich", "options": [
            {"value": "AT",    "label": "Österreich (alle)"},
            {"value": "AT-W",  "label": "Wien"},
            {"value": "AT-NO", "label": "Niederösterreich"},
            {"value": "AT-OO", "label": "Oberösterreich"},
            {"value": "AT-K",  "label": "Kärnten"},
            {"value": "AT-ST", "label": "Steiermark"},
            {"value": "AT-T",  "label": "Tirol"},
        ]},
        {"group": "Deutschland", "options": [
            {"value": "DE",    "label": "Deutschland (alle)"},
            {"value": "DE-BY", "label": "Bayern"},
            {"value": "DE-BW", "label": "Baden-Württemberg"},
            {"value": "DE-NW", "label": "Nordrhein-Westfalen"},
            {"value": "DE-HE", "label": "Hessen"},
            {"value": "DE-SN", "label": "Sachsen"},
        ]},
    ]
