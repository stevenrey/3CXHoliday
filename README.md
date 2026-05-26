# 3CX Holiday Importer Clean Package

Sauberes Neuaufsetzen des Projekts mit konsistenten Config-Keys und funktionierender Web-GUI.

## Inhalte

- FastAPI App (`main.py`)
- GUI (`templates/index.html`)
- Konfiguration (`config.py`)
- Feiertagslogik (`holidays_engine.py`)
- TTS Wrapper (`tts_engine.py`)
- 3CX API Test (`cx_api.py`)
- `requirements.txt`
- systemd Beispielservice
- `install.sh`

## Empfohlene Neuinstallation

1. Repo nach Git hochladen.
2. Server sauber vorbereiten.
3. Neu clonen nach `/opt/3cx-holiday-importer`.
4. `python3 -m venv venv`
5. `pip install -r requirements.txt`
6. Service-Datei nach `/etc/systemd/system/3cx-holiday-importer.service` kopieren.
7. `systemctl daemon-reload && systemctl enable --now 3cx-holiday-importer`

## Test

```bash
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:5000/api/config
```

## Wichtige Pfade

- App: `/opt/3cx-holiday-importer`
- Config: `/opt/3cx-holiday-importer/config.json`
- Venv: `/opt/3cx-holiday-importer/venv`
- Service: `/etc/systemd/system/3cx-holiday-importer.service`
