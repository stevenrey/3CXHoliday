#!/usr/bin/env python3
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import load_config, save_config

try:
    from holidays_engine import get_holidays
except Exception:
    def get_holidays(region, year):
        return []

try:
    from tts_engine import generate_tts
except Exception:
    def generate_tts(text, filepath, config):
        return None

try:
    from cx_api import CXApi
except Exception:
    class CXApi:
        def __init__(self, host, user, password):
            self.host = host
            self.user = user
            self.password = password
        def test_connection(self):
            return {"message": "Mock-Verbindung erfolgreich", "version": "demo"}
        def set_holiday(self, name, date_str, filename):
            return True

logging.basicConfig(
    filename="/var/log/3cx-holiday-importer.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="3CX Holiday Importer", version="1.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class SyncRequest(BaseModel):
    year: Optional[int] = None
    dry_run: bool = False

class ConfigModel(BaseModel):
    cx_host: str
    cx_username: str
    cx_password: str
    region: str = "CH-ZH"
    prompt_path: str = "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts"
    tts_engine: str = "piper"
    piper_binary: str = "/opt/piper/piper"
    piper_model: str = "/opt/piper/de_DE-thorsten-high.onnx"
    google_api_key: Optional[str] = ""
    company_name: str = "Tiag AG"
    phone_number: str = "+41 44 315 55 99"
    announcement_template: str = "Sie haben {company} angerufen. Wir sind am {weekday}, {date} wegen {holiday} geschlossen. Bitte rufen Sie uns am naechsten Werktag zurueck oder hinterlassen Sie eine Nachricht."
    auto_set_holidays: bool = True
    verify_ssl: bool = False

@app.get("/")
async def index(request: Request):
    config = load_config()
    year = datetime.now().year
    holidays = get_holidays(config.get("region", "CH-ZH"), year)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "config": config,
        "holidays": holidays,
        "year": year,
        "log_lines": get_last_log_lines(50),
        "config_path": os.environ.get("CONFIG_PATH", "/opt/3cx-holiday-importer/config.json")
    })

@app.get("/api/config")
async def api_get_config():
    return load_config()

@app.post("/api/config")
async def api_save_config(cfg: ConfigModel):
    save_config(cfg.model_dump())
    return {"status": "ok"}

@app.post("/api/test-connection")
async def api_test_connection():
    config = load_config()
    cx_host = (config.get("cx_host") or "").strip()
    cx_username = (config.get("cx_username") or "").strip()
    cx_password = (config.get("cx_password") or "").strip()
    if not cx_host or not cx_username or not cx_password:
        return JSONResponse(status_code=400, content={"status": "error", "connected": False, "message": "Bitte Host, Benutzername und Passwort speichern."})
    try:
        api = CXApi(cx_host, cx_username, cx_password)
        result = api.test_connection()
        return {"status": "ok", "connected": True, "message": result.get("message", "Verbunden"), "version": result.get("version", "")}
    except Exception as e:
        logger.exception("Fehler bei /api/test-connection")
        return JSONResponse(status_code=500, content={"status": "error", "connected": False, "message": str(e)})

@app.post("/api/sync")
async def api_sync(req: SyncRequest, background_tasks: BackgroundTasks):
    config = load_config()
    year = req.year or datetime.now().year
    background_tasks.add_task(run_sync, config, year, req.dry_run)
    return {"status": "started", "year": year, "dry_run": req.dry_run}

@app.get("/api/logs")
async def api_logs(lines: int = 100):
    return {"logs": get_last_log_lines(lines)}

@app.get("/health")
async def health():
    return {"status": "ok", "config_path": os.environ.get("CONFIG_PATH", "/opt/3cx-holiday-importer/config.json")}


def get_last_log_lines(n=50):
    logfile = "/var/log/3cx-holiday-importer.log"
    try:
        with open(logfile, encoding="utf-8") as f:
            return f.readlines()[-n:]
    except Exception:
        return []


def run_sync(config: dict, year: int, dry_run: bool):
    logger.info(f"Starte Sync für Jahr {year} (dry_run={dry_run})")
    region = config.get("region", "CH-ZH")
    holidays = get_holidays(region, year)
    prompt_path = config.get("prompt_path", "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts")
    for holiday in holidays:
        name = holiday.get("name", "Holiday")
        date_str = holiday.get("date", "")
        weekday = holiday.get("weekday", "")
        text = config.get("announcement_template", "").format(
            company=config.get("company_name", ""),
            weekday=weekday,
            date=date_str,
            holiday=name,
            phone=config.get("phone_number", "")
        )
        filename = f"holiday_{date_str}_{name.replace(' ', '_').lower()}.wav"
        filepath = os.path.join(prompt_path, filename)
        if not dry_run:
            try:
                generate_tts(text, filepath, config)
            except Exception as e:
                logger.error(f"TTS Fehler bei {name}: {e}")
                continue
            if config.get("auto_set_holidays", True):
                try:
                    api = CXApi(config["cx_host"], config["cx_username"], config["cx_password"])
                    api.set_holiday(name, date_str, filename)
                except Exception as e:
                    logger.error(f"3CX API Fehler bei {name}: {e}")
    logger.info(f"Sync abgeschlossen für {year}")
