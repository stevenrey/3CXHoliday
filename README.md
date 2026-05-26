# 3CX Holiday Importer

Automatische Feiertagsansagen für 3CX – Python/FastAPI Web-App.

## Installation (Erstinstallation)
```bash
chmod +x install.sh update.sh
sudo ./install.sh
```

## Update (bestehende Installation)
```bash
sudo ./update.sh
```

## Web-UI
```
https://tiagdemo.3cx.ch/holiday-importer/
```

## Ports
- App läuft intern auf Port **5000**
- Erreichbar via Nginx Reverse Proxy unter `/holiday-importer/`
- Nginx Snippet: `/var/lib/3cxpbx/Bin/nginx/conf/snippets/holiday-importer.conf`

## Konfiguration
- Config-Datei: `/etc/3cx-holiday-importer/config.json`
- Oder direkt über die Web-UI

## Logs
```bash
journalctl -u 3cx-holiday-importer -f
cat /var/log/3cx-holiday-importer.log
```

## Cronjob
Läuft automatisch am 2. Januar 06:00 Uhr.
Manuell triggern:
```bash
curl -X POST http://localhost:5000/api/sync -H "Content-Type: application/json" -d "{}"
```

## Prompt-Pfad auf 3CX-Server
```
/var/lib/3cxpbx/Instance1/Data/Ivr/Prompts/
```

## Ansage-Template Platzhalter
| Platzhalter | Beispiel        |
|-------------|-----------------|
| {company}   | Tiag AG         |
| {weekday}   | Donnerstag      |
| {date}      | 01.01.2026      |
| {holiday}   | Neujahrstag     |
| {phone}     | +41 44 315 55 99|