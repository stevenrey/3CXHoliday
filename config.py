import json
import os
from pathlib import Path

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/opt/3cx-holiday-importer/config.json")

DEFAULTS = {
    "cx_host": "https://localhost:5001",
    "cx_username": "admin",
    "cx_password": "",
    "region": "CH-ZH",
    "prompt_path": "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts",
    "tts_engine": "piper",
    "piper_binary": "/opt/piper/piper",
    "piper_model": "/opt/piper/de_DE-thorsten-high.onnx",
    "google_api_key": "",
    "company_name": "Tiag AG",
    "phone_number": "+41 44 315 55 99",
    "announcement_template": (
        "Sie haben {company} angerufen. Wir sind am {weekday}, den {date} wegen {holiday} geschlossen. "
        "Bitte rufen Sie uns am naechsten Werktag zurueck oder hinterlassen Sie eine Nachricht."
    ),
    "auto_set_holidays": True,
    "verify_ssl": False,
}


def load_config():
    path = Path(CONFIG_PATH)
    if not path.exists():
        return DEFAULTS.copy()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return DEFAULTS.copy()
    cfg = DEFAULTS.copy()
    cfg.update(data or {})
    return cfg


def save_config(data):
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = DEFAULTS.copy()
    cfg.update(data or {})
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg
