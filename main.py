#!/usr/bin/env python3
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import load_config, save_config
from cx_api import CXApi
from holidays_engine import get_all_regions, get_holidays
from tts_engine import check_piper_available, generate_tts

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/3cx-holiday-importer.log")
ROOT_PATH = os.environ.get("ROOT_PATH", "/holiday-import")

Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger("3cx-holiday-importer")

app = FastAPI(title="3CX Holiday Importer", version="2.0.0", root_path=ROOT_PATH)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class SyncRequest(BaseModel):
    year: Optional[int] = None
    dry_run: bool = False
    selected_dates: Optional[list[str]] = None


class ConfigModel(BaseModel):
    cx_host: str = "https://localhost:5001"
    cx_auth_mode: str = "userpass"
    cx_username: str = "admin"
    cx_password: str = ""
    cx_client_id: str = ""
    cx_client_secret: str = ""
    cx_department_id: str = ""
    cx_department_name: str = ""
    cx_xapi_token: str = ""
    region: str = "CH-ZH"
    prompt_path: str = "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts"
    tts_engine: str = "piper"
    piper_binary: str = "/opt/piper/piper"
    piper_model: str = "/opt/piper/de_DE-thorsten-high.onnx"
    google_api_key: str = ""
    company_name: str = "Tiag AG"
    phone_number: str = "+41 44 315 55 99"
    announcement_template: str = (
        "Sie haben {company} angerufen. Wir sind am {weekday}, den {date} wegen {holiday} geschlossen. "
        "Bitte rufen Sie uns am naechsten Werktag zurueck oder hinterlassen Sie eine Nachricht."
    )
    auto_set_holidays: bool = True
    verify_ssl: bool = False


class TtsPreviewRequest(BaseModel):
    text: str


def get_last_log_lines(limit: int = 100) -> list[str]:
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as handle:
            return handle.readlines()[-limit:]
    except Exception:
        return []


def safe_config(config: dict) -> dict:
    masked = config.copy()
    for key in ("cx_password", "cx_client_secret", "google_api_key"):
        if masked.get(key):
            masked[key] = "***"
    if masked.get("cx_xapi_token"):
        masked["cx_xapi_token"] = "***"
    return masked


def make_cx_api(config: dict) -> CXApi:
    return CXApi(
        config.get("cx_host", ""),
        config.get("cx_username", ""),
        config.get("cx_password", ""),
        config.get("verify_ssl", False),
        config.get("cx_xapi_token", ""),
        config.get("cx_auth_mode", "userpass"),
        config.get("cx_client_id", ""),
        config.get("cx_client_secret", ""),
    )


def build_announcement(holiday: dict, config: dict) -> str:
    template = config.get("announcement_template") or ConfigModel().announcement_template
    return template.format(
        company=config.get("company_name", ""),
        weekday=holiday["weekday"],
        date=holiday["date_display"],
        holiday=holiday["name"],
        phone=config.get("phone_number", ""),
    )


def run_sync(config: dict, year: int, dry_run: bool, selected_dates: list[str] | None = None) -> None:
    logger.info("Starte Sync fuer Jahr %s (dry_run=%s)", year, dry_run)
    holidays = get_holidays(config.get("region", "CH-ZH"), year)
    selected = set(selected_dates or [])
    if selected_dates is not None:
        holidays = [holiday for holiday in holidays if holiday["date"] in selected]
    prompt_path = config.get("prompt_path", "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts")

    api = None
    should_write_3cx = bool(config.get("auto_set_holidays", True))
    if not dry_run and not should_write_3cx:
        logger.error("3CX Holiday-Erstellung ist deaktiviert. Checkbox 'Feiertage automatisch in 3CX setzen' aktivieren.")
        return
    if not dry_run and not config.get("cx_department_id"):
        logger.error("Kein Department ausgewaehlt. Bitte Department laden und auswaehlen.")
        return
    if not dry_run:
        api = make_cx_api(config)

    ok_count = 0
    for holiday in holidays:
        text = build_announcement(holiday, config)
        filepath = os.path.join(prompt_path, holiday["filename"])
        logger.info("Verarbeite %s am %s -> %s", holiday["name"], holiday["date"], holiday["filename"])

        if dry_run:
            ok_count += 1
            continue

        try:
            generate_tts(text, filepath, config)
            api.upload_prompt(filepath, holiday["filename"])
            logger.info("3CX Ansage hochgeladen: %s", holiday["filename"])
            result = api.set_holiday(
                holiday["name"],
                holiday["date"],
                holiday["filename"],
                config.get("cx_department_id", ""),
            )
            logger.info("3CX Holiday erstellt: %s", result.get("payload", {}))
            ok_count += 1
        except Exception as exc:
            logger.exception("Fehler bei %s: %s", holiday["name"], exc)

    logger.info("Sync abgeschlossen: %s/%s Feiertage erfolgreich", ok_count, len(holidays))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    config = load_config()
    year = datetime.now().year
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "base_path": ROOT_PATH.rstrip("/"),
            "config": safe_config(config),
            "holidays": get_holidays(config.get("region", "CH-ZH"), year),
            "regions": get_all_regions(),
            "year": year,
            "piper_status": check_piper_available(config),
            "log_lines": get_last_log_lines(50),
        },
    )


@app.get("/health")
@app.get("/api/health")
async def api_health():
    config = load_config()
    return {
        "status": "ok",
        "version": app.version,
        "root_path": ROOT_PATH,
        "piper": check_piper_available(config),
        "auto_set_holidays": bool(config.get("auto_set_holidays", True)),
        "department_id": config.get("cx_department_id", ""),
        "department_name": config.get("cx_department_name", ""),
        "xapi_token_configured": bool(config.get("cx_xapi_token")),
        "auth_mode": config.get("cx_auth_mode", "userpass"),
        "client_credentials_configured": bool(config.get("cx_client_id") and config.get("cx_client_secret")),
    }


@app.get("/api/regions")
async def api_regions():
    return {"regions": get_all_regions()}


@app.get("/api/holidays")
async def api_holidays(year: Optional[int] = None, region: Optional[str] = None):
    config = load_config()
    selected_year = year or datetime.now().year
    selected_region = region or config.get("region", "CH-ZH")
    holidays = get_holidays(selected_region, selected_year)
    return {"holidays": holidays, "year": selected_year, "region": selected_region, "count": len(holidays)}


@app.get("/api/config")
async def api_get_config():
    return safe_config(load_config())


@app.post("/api/config")
async def api_save_config(payload: ConfigModel):
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    existing = load_config()
    if data.get("cx_password") == "***":
        data["cx_password"] = existing.get("cx_password", "")
    if data.get("cx_client_secret") == "***":
        data["cx_client_secret"] = existing.get("cx_client_secret", "")
    if data.get("google_api_key") == "***":
        data["google_api_key"] = existing.get("google_api_key", "")
    if data.get("cx_xapi_token") == "***":
        data["cx_xapi_token"] = existing.get("cx_xapi_token", "")
    return safe_config(save_config(data))


@app.post("/api/test-connection")
async def api_test_connection():
    config = load_config()
    try:
        api = make_cx_api(config)
        result = api.test_connection()
        return {"status": "ok", "connected": True, **result}
    except ValueError as exc:
        return JSONResponse(status_code=401, content={"status": "error", "connected": False, "message": str(exc)})
    except TimeoutError as exc:
        return JSONResponse(status_code=504, content={"status": "error", "connected": False, "message": str(exc)})
    except ConnectionError as exc:
        return JSONResponse(status_code=503, content={"status": "error", "connected": False, "message": str(exc)})
    except Exception as exc:
        logger.exception("Verbindungstest fehlgeschlagen")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/auth-info")
async def api_auth_info():
    config = load_config()
    try:
        api = make_cx_api(config)
        info = api.get_token_info()
        return {"status": "ok", **info}
    except ValueError as exc:
        return JSONResponse(status_code=401, content={"status": "error", "message": str(exc)})
    except TimeoutError as exc:
        return JSONResponse(status_code=504, content={"status": "error", "message": str(exc)})
    except ConnectionError as exc:
        return JSONResponse(status_code=503, content={"status": "error", "message": str(exc)})
    except Exception as exc:
        logger.exception("Auth-Info konnte nicht geladen werden")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/departments")
async def api_departments():
    config = load_config()
    try:
        api = make_cx_api(config)
        departments = api.get_departments()
        return {"departments": departments, "count": len(departments)}
    except ValueError as exc:
        return JSONResponse(status_code=401, content={"status": "error", "message": str(exc), "departments": []})
    except TimeoutError as exc:
        return JSONResponse(status_code=504, content={"status": "error", "message": str(exc), "departments": []})
    except ConnectionError as exc:
        return JSONResponse(status_code=503, content={"status": "error", "message": str(exc), "departments": []})
    except Exception as exc:
        logger.exception("Departments konnten nicht geladen werden")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/diff")
async def api_diff(request: SyncRequest):
    config = load_config()
    year = request.year or datetime.now().year
    holidays = get_holidays(config.get("region", "CH-ZH"), year)
    prompt_path = config.get("prompt_path", "/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts")
    department_id = config.get("cx_department_id", "")
    cx_holidays = []
    cx_source = "not_loaded"
    if department_id:
        try:
            api = make_cx_api(config)
            existing = api.get_department_holidays(department_id)
            cx_holidays = existing.get("holidays", [])
            cx_source = existing.get("source", "unknown")
        except Exception as exc:
            logger.warning("Bestehende 3CX Feiertage konnten nicht geladen werden: %s", exc)
            cx_source = f"error: {exc}"

    existing_dates = {holiday.get("date", "") for holiday in cx_holidays}
    existing_month_days = {holiday.get("date", "")[5:] for holiday in cx_holidays if holiday.get("date", "").startswith("0000-")}

    diff = []
    for holiday in holidays:
        filepath = os.path.join(prompt_path, holiday["filename"])
        cx_exists = holiday["date"] in existing_dates or holiday["date"][5:] in existing_month_days
        diff.append(
            {
                **holiday,
                "text": build_announcement(holiday, config),
                "audio_exists": os.path.exists(filepath),
                "cx_exists": cx_exists,
                "selected": not cx_exists,
                "action": "skip" if cx_exists else ("update_audio" if os.path.exists(filepath) else "create"),
            }
        )
    return {
        "diff": diff,
        "existing_holidays": cx_holidays,
        "cx_source": cx_source,
        "department_id": department_id,
        "department_name": config.get("cx_department_name", ""),
        "year": year,
        "region": config.get("region", "CH-ZH"),
        "total": len(diff),
    }


@app.post("/api/sync")
async def api_sync(request: SyncRequest, background_tasks: BackgroundTasks):
    config = load_config()
    year = request.year or datetime.now().year
    background_tasks.add_task(run_sync, config, year, request.dry_run, request.selected_dates)
    return {
        "status": "started",
        "year": year,
        "dry_run": request.dry_run,
        "selected_count": None if request.selected_dates is None else len(request.selected_dates),
    }


@app.post("/api/tts-preview")
async def api_tts_preview(request: TtsPreviewRequest):
    config = load_config()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        temp_path = temp_file.name
    try:
        generate_tts(request.text, temp_path, config)
        with open(temp_path, "rb") as handle:
            content = handle.read()
        return Response(content=content, media_type="audio/wav")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@app.get("/api/piper-status")
async def api_piper_status():
    return check_piper_available(load_config())


@app.get("/api/logs")
async def api_logs(lines: int = 100):
    return {"logs": get_last_log_lines(lines)}
