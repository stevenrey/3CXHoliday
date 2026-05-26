#!/usr/bin/env python3
"""3CX Holiday Importer – FastAPI Server"""
import os, logging
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from holidays_engine import get_holidays
from tts_engine import generate_tts
from cx_api import CXApi
from config import load_config, save_config

logging.basicConfig(
    filename="/var/log/3cx-holiday-importer.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="3CX Holiday Importer", version="1.0.0")
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
    google_api_key: Optional[str] = None
    company_name: str = "Tiag AG"
    phone_number: str = "+41 44 315 55 99"
    announcement_template: str = "Sie haben {company} angerufen. Wir sind am {weekday}, {date} wegen {holiday} geschlossen. Bitte rufen Sie uns am naechsten Werktag zurueck oder hinterlassen Sie eine Nachricht."
    auto_set_holidays: bool = True

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
        "log_lines": get_last_log_lines(50)
    })

@app.get("/api/holidays")
async def api_holidays(year: int = None, region: str = None):
    config = load_config()
    y = year or datetime.now().year
    r = region or config.get("region", "CH-ZH")
    return {"holidays": get_holidays(r, y), "year": y, "region": r}

@app.get("/api/config")
async def api_get_config():
    return load_config()

@app.post("/api/config")
async def api_save_config(cfg: ConfigModel):
    save_config(cfg.dict())
    return {"status": "ok"}

@app.post("/api/test-connection")
async def api_test_connection():
    config = load_config()
    try:
        api = CXApi(config["cx_host"], config["cx_username"], config["cx_password"])
        result = api.test_connection()
        return JSONResponse(content={"status": "ok", "connected": True, "message": result["message"], "version": result.get("version","")})
    except ConnectionError as e:
        return JSONResponse(status_code=503, content={"status": "error", "connected": False, "message": str(e)})
    except TimeoutError as e:
        return JSONResponse(status_code=504, content={"status": "error", "connected": False, "message": str(e)})
    except ValueError as e:
        return JSONResponse(status_code=401, content={"status": "error", "connected": False, "message": str(e)})
    except Exception as e:
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

def get_last_log_lines(n=50):
    logfile = "/var/log/3cx-holiday-importer.log"
    try:
        with open(logfile) as f:
            return f.readlines()[-n:]
    except Exception:
        return []

def run_sync(config: dict, year: int, dry_run: bool):
    logger.info(f"Starte Sync für Jahr {year} (dry_run={dry_run})")
    region = config.get("region", "CH-ZH")
    holidays = get_holidays(region, year)
    prompt_path = config.get("prompt_path", "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts")
    for holiday in holidays:
        name = holiday["name"]
        date_str = holiday["date"]
        weekday = holiday["weekday"]
        text = config.get("announcement_template", "").format(
            company=config.get("company_name", ""),
            weekday=weekday, date=date_str, holiday=name,
            phone=config.get("phone_number", "")
        )
        filename = f"holiday_{date_str}_{name.replace(' ', '_').lower()}.wav"
        filepath = os.path.join(prompt_path, filename)
        logger.info(f"Feiertag: {name} am {date_str} → {filename}")
        if not dry_run:
            try:
                generate_tts(text, filepath, config)
                logger.info(f"TTS generiert: {filepath}")
            except Exception as e:
                logger.error(f"TTS Fehler bei {name}: {e}")
                continue
            if config.get("auto_set_holidays", True):
                try:
                    api = CXApi(config["cx_host"], config["cx_username"], config["cx_password"])
                    api.set_holiday(name, date_str, filename)
                    logger.info(f"3CX Holiday gesetzt: {name}")
                except Exception as e:
                    logger.error(f"3CX API Fehler bei {name}: {e}")
    logger.info(f"Sync abgeschlossen für {year}")