import json
import logging
import os
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
CONFIG_PATH = os.environ.get("CONFIG_PATH", str(BASE_DIR / "config.json"))

STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("holiday-importer")

app = FastAPI(title="3CX Holiday Importer", version="2.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.exception("Failed to load config: %s", e)

    return {
        "country": "CH",
        "region": "ZH",
        "language": "de",
        "tts_enabled": False,
        "api_base_url": "",
        "client_id": "",
        "client_secret": "",
    }


def get_last_log_lines(limit=50):
    return []


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "config_path": CONFIG_PATH
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    config = load_config()
    holidays = []
    year = datetime.now().year

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "config": config,
            "holidays": holidays,
            "year": year,
            "log_lines": get_last_log_lines(50),
            "config_path": CONFIG_PATH,
        },
    )


@app.get("/api/config")
async def get_config():
    return JSONResponse(load_config())