# 3CX Holiday Importer for Linux

Linux-native Holiday Importer für 3CX v20 mit FastAPI-Weboberfläche, regionalen Feiertagen, TTS via Piper oder Google und direkter 3CX-Integration.

## Features
- Feiertage für CH, AT und DE nach Region/Kanton/Bundesland.
- Web-UI für Konfiguration, Vorschau, Diff und Sync.
- Dry Run vor produktivem Schreiben.
- Lokale TTS mit Piper oder optional Google Cloud TTS.
- Audio-Preview direkt im Browser.
- systemd-Service und Nginx-Reverse-Proxy.

## Ordnerstruktur
- `main.py` – FastAPI App
- `config.py` – Laden/Speichern der Konfiguration
- `holidays_engine.py` – Feiertage aus Python `holidays`
- `tts_engine.py` – Piper/Google TTS
- `cx_api.py` – 3CX API Wrapper
- `templates/index.html` – Weboberfläche
- `install.sh` – Linux Installer

## Installation
```bash
chmod +x install.sh
sudo ./install.sh
```

## Manuell starten
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
CONFIG_PATH=./config.json LOG_FILE=./holiday-importer.log uvicorn main:app --host 0.0.0.0 --port 3001
```

## Konfiguration
Standardpfad für die Konfiguration:
- `/etc/3cx-holiday-importer/config.json`

Wichtige Felder:
- `cxhost`
- `cxusername`
- `cxpassword`
- `region`
- `promptpath`
- `ttsengine`
- `piperbinary`
- `pipermodel`

## Hinweise
- Die 3CX-Endpunkte können je nach v20 Build abweichen; der Wrapper ist absichtlich kompakt gehalten.
- Piper wird bevorzugt, weil es lokal und offline auf Linux läuft.
- Für erste Tests `autosetholidays=false` setzen und mit Dry Run starten.
