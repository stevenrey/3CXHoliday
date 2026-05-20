import json
import os
from pathlib import Path

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/etc/3cx-holiday-importer/config.json")

DEFAULTS = {
    "cxhost": "https://localhost:5001",
    "cxusername": "admin",
    "cxpassword": "",
    "region": "CH-ZH",
    "promptpath": "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts",
    "ttsengine": "piper",
    "piperbinary": "/opt/piper/piper",
    "pipermodel": "/opt/piper/de_DE-thorsten-high.onnx",
    "googleapikey": "",
    "companyname": "",
    "phonenumber": "",
    "announcementtemplate": (
        "Sie haben {company} angerufen. "
        "Wir sind am {weekday}, den {date} wegen {holiday} geschlossen. "
        "Bitte hinterlassen Sie eine Nachricht oder rufen Sie uns morgen wieder an. "
        "Unsere Telefonnummer ist {phone}. Vielen Dank."
    ),
    "autosetholidays": True,
    "verify_ssl": False,
}


def load_config() -> dict:
    path = Path(CONFIG_PATH)
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            # Merge with defaults so new keys are always present
            merged = {**DEFAULTS, **data}
            return merged
        except Exception:
            pass
    return dict(DEFAULTS)


def save_config(data: dict):
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never store password in plaintext warning – just write it as-is for now
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
