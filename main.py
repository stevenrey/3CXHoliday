#!/usr/bin/env python3
"""3CX Holiday Importer – FastAPI Server"""
import os
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, BackgroundTasks, HTTPException, Response
import os, logging
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from holidays_engine import get_holidays, get_all_regions
from tts_engine import generate_tts, check_piper_available
from holidays_engine import get_holidays
from tts_engine import generate_tts
from cx_api import CXApi
from config import load_config, save_config

LOG_FILE = os.environ.get("LOG_FILE", "/var/log/3cx-holiday-importer.log")

logging.basicConfig(
    filename=LOG_FILE,
    filename="/var/log/3cx-holiday-importer.log",
level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    format="%(asctime)s [%(levelname)s] %(message)s"
)
# Also log to stdout
logging.getLogger().addHandler(logging.StreamHandler())
logger = logging.getLogger(__name__)

app = FastAPI(title="3CX Holiday Importer", version="2.0.0")
app = FastAPI(title="3CX Holiday Importer", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── Models ───────────────────────────────────────────────────────────────────

class SyncRequest(BaseModel):
year: Optional[int] = None
dry_run: bool = False

class ConfigModel(BaseModel):
    cxhost: str
    cxusername: str
    cxpassword: str
    cx_host: str
    cx_username: str
    cx_password: str
region: str = "CH-ZH"
    promptpath: str = "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts"
    ttsengine: str = "piper"
    piperbinary: str = "/opt/piper/piper"
    pipermodel: str = "/opt/piper/de_DE-thorsten-high.onnx"
    googleapikey: Optional[str] = None
    companyname: str = ""
    phonenumber: str = ""
    announcementtemplate: str = (
        "Sie haben {company} angerufen. Wir sind am {weekday}, den {date} "
        "wegen {holiday} geschlossen. Bitte hinterlassen Sie eine Nachricht. "
        "Unsere Nummer ist {phone}. Vielen Dank."
    )
    autosetholidays: bool = True
    verify_ssl: bool = False

class TtsPreviewRequest(BaseModel):
    text: str

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_last_log_lines(n: int = 100) -> list[str]:
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()
            return lines[-n:]
    except Exception:
        return []

def build_announcement(holiday: dict, config: dict) -> str:
    template = config.get(
        "announcementtemplate",
        "Sie haben {company} angerufen. Wir sind am {weekday}, den {date} wegen {holiday} geschlossen."
    )
    return template.format(
        company=config.get("companyname", ""),
        weekday=holiday["weekday"],
        date=holiday["date"],
        holiday=holiday["name"],
        phone=config.get("phonenumber", ""),
    )

def run_sync(config: dict, year: int, dry_run: bool):
    logger.info(f"Starte Sync für Jahr {year} (dry_run={dry_run})")
    region = config.get("region", "CH-ZH")
    holidays = get_holidays(region, year)
    prompt_path = config.get("promptpath", "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts")
    results = []

    api = None
    if not dry_run and config.get("autosetholidays", True):
        try:
            api = CXApi(
                config["cxhost"],
                config["cxusername"],
                config["cxpassword"],
                config.get("verify_ssl", False),
            )
        except Exception as e:
            logger.error(f"3CX API Init fehlgeschlagen: {e}")

    for holiday in holidays:
        name = holiday["name"]
        date_str = holiday["date"]
        date_iso = holiday["date_iso"]
        filename = holiday["filename"]
        filepath = os.path.join(prompt_path, filename)
        text = build_announcement(holiday, config)

        logger.info(f"Verarbeite: {name} am {date_str} → {filename}")

        tts_ok = False
        tts_error = None
        if not dry_run:
            try:
                generate_tts(text, filepath, config)
                tts_ok = True
                logger.info(f"TTS generiert: {filepath}")
            except Exception as e:
                tts_error = str(e)
                logger.error(f"TTS Fehler bei {name}: {e}")

        cx_ok = False
        cx_error = None
        if not dry_run and api and tts_ok:
            try:
                api.set_holiday(name, date_iso, filename)
                cx_ok = True
                logger.info(f"3CX Holiday gesetzt: {name}")
            except Exception as e:
                cx_error = str(e)
                logger.error(f"3CX API Fehler bei {name}: {e}")

        results.append({
            "name": name,
            "date": date_str,
            "filename": filename,
            "text": text,
            "tts_ok": tts_ok,
            "tts_error": tts_error,
            "cx_ok": cx_ok,
            "cx_error": cx_error,
            "dry_run": dry_run,
            "status": "dry_run" if dry_run else ("ok" if (tts_ok and (cx_ok or not config.get("autosetholidays"))) else "error"),
        })

    ok_count = sum(1 for r in results if r["status"] in ("ok", "dry_run"))
    logger.info(f"Sync abgeschlossen: {ok_count}/{len(results)} Feiertage erfolgreich")

# ─── Routes ───────────────────────────────────────────────────────────────────
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
    regions = get_all_regions()
    piper_status = check_piper_available(config)
return templates.TemplateResponse("index.html", {
"request": request,
"config": config,
"holidays": holidays,
"year": year,
        "regions": regions,
        "loglines": get_last_log_lines(50),
        "piper_status": piper_status,
        "log_lines": get_last_log_lines(50)
})

@app.get("/api/holidays")
async def api_holidays(year: int = None, region: str = None):
config = load_config()
y = year or datetime.now().year
r = region or config.get("region", "CH-ZH")
    holidays = get_holidays(r, y)
    return {"holidays": holidays, "year": y, "region": r, "count": len(holidays)}

@app.get("/api/regions")
async def api_regions():
    return {"regions": get_all_regions()}
    return {"holidays": get_holidays(r, y), "year": y, "region": r}

@app.get("/api/config")
async def api_get_config():
    cfg = load_config()
    # Never expose password via API
    safe = {k: ("***" if k in ("cxpassword", "googleapikey") and v else v) for k, v in cfg.items()}
    return safe
    return load_config()

@app.post("/api/config")
async def api_save_config(cfg: ConfigModel):
    data = cfg.dict()
    # If password is masked, keep old one
    existing = load_config()
    if data.get("cxpassword") == "***":
        data["cxpassword"] = existing.get("cxpassword", "")
    if data.get("googleapikey") == "***":
        data["googleapikey"] = existing.get("googleapikey", "")
    save_config(data)
    save_config(cfg.dict())
return {"status": "ok"}

@app.post("/api/test-connection")
async def api_test_connection():
config = load_config()
try:
        api = CXApi(config["cxhost"], config["cxusername"], config["cxpassword"], config.get("verify_ssl", False))
        api = CXApi(config["cx_host"], config["cx_username"], config["cx_password"])
result = api.test_connection()
        return {"status": "ok", "message": result}
        return JSONResponse(content={"status": "ok", "connected": True, "message": result["message"], "version": result.get("version","")})
    except ConnectionError as e:
        return JSONResponse(status_code=503, content={"status": "error", "connected": False, "message": str(e)})
    except TimeoutError as e:
        return JSONResponse(status_code=504, content={"status": "error", "connected": False, "message": str(e)})
    except ValueError as e:
        return JSONResponse(status_code=401, content={"status": "error", "connected": False, "message": str(e)})
except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/diff")
async def api_diff(request: SyncRequest):
    """Return what would be synced – compare with existing 3CX holidays."""
    config = load_config()
    year = request.year or datetime.now().year
    region = config.get("region", "CH-ZH")
    holidays = get_holidays(region, year)
    prompt_path = config.get("promptpath", "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts")

    existing_cx = []
    try:
        api = CXApi(config["cxhost"], config["cxusername"], config["cxpassword"], config.get("verify_ssl", False))
        existing_cx = api.get_holidays()
        existing_names = {h.get("Name", "").lower() for h in existing_cx}
        existing_dates = {h.get("Date", "")[:10] for h in existing_cx}
    except Exception:
        existing_names = set()
        existing_dates = set()

    diff = []
    for h in holidays:
        filepath = os.path.join(prompt_path, h["filename"])
        audio_exists = os.path.exists(filepath)
        cx_exists = (h["name"].lower() in existing_names) or (h["date_iso"] in existing_dates)
        text = build_announcement(h, config)
        diff.append({
            **h,
            "text": text,
            "audio_exists": audio_exists,
            "cx_exists": cx_exists,
            "action": "skip" if cx_exists else ("update_audio" if audio_exists else "create"),
        })

    return {"diff": diff, "year": year, "region": region, "total": len(diff)}
        return JSONResponse(status_code=500, content={"status": "error", "connected": False, "message": str(e)})

@app.post("/api/sync")
async def api_sync(req: SyncRequest, background_tasks: BackgroundTasks):
@@ -255,37 +97,47 @@ async def api_sync(req: SyncRequest, background_tasks: BackgroundTasks):
background_tasks.add_task(run_sync, config, year, req.dry_run)
return {"status": "started", "year": year, "dry_run": req.dry_run}

@app.post("/api/tts-preview")
async def api_tts_preview(req: TtsPreviewRequest):
    """Generate TTS to temp file and return audio stream."""
    config = load_config()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        generate_tts(req.text, tmp_path, config)
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
        os.unlink(tmp_path)
        return Response(content=audio_bytes, media_type="audio/wav")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/piper-status")
async def api_piper_status():
    config = load_config()
    return check_piper_available(config)

@app.get("/api/logs")
async def api_logs(lines: int = 100):
return {"logs": get_last_log_lines(lines)}

@app.get("/api/health")
async def api_health():
    config = load_config()
    return {
        "status": "ok",
        "version": "2.0.0",
        "piper": check_piper_available(config),
    }
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