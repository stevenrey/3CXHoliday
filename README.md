# 3CX Holiday Importer

Dieses Paket enthält eine bereinigte Version, bei der die Web-GUI die Konfiguration direkt über `/api/config` lädt und speichert.

## Enthaltene Fixes

- `config.py` nutzt standardmäßig `/opt/3cx-holiday-importer/config.json`
- Einheitliche Feldnamen mit Unterstrichen, z. B. `cx_host`, `company_name`, `auto_set_holidays`
- Web-GUI lädt die Config beim Öffnen per `GET /api/config`
- Web-GUI speichert per `POST /api/config`
- Debug-Block zeigt die aktuell vom Backend geladene Config an
- `/health` zeigt den aktiven `CONFIG_PATH`

## Deployment

1. Dateien nach `/opt/3cx-holiday-importer/` kopieren.
2. In der systemd-Datei setzen:

```ini
Environment=CONFIG_PATH=/opt/3cx-holiday-importer/config.json
WorkingDirectory=/opt/3cx-holiday-importer
```

3. Danach:

```bash
sudo systemctl daemon-reload
sudo systemctl restart 3cx-holiday-importer
```

## Test

```bash
curl -i -X POST http://127.0.0.1:5000/api/config \
  -H "Content-Type: application/json" \
  --data-binary @/opt/3cx-holiday-importer/config.json
```
