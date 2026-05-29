# 3CX Holiday Importer

FastAPI-GUI zum Erzeugen von Feiertagsansagen fuer 3CX. Die App wird lokal auf dem 3CX-Server unter `127.0.0.1:5000` betrieben und ueber den bestehenden Nginx unter `/holiday-import/` veroeffentlicht.

## Installation auf der 3CX

Auf dem 3CX-Server als Benutzer mit sudo-Rechten ausfuehren:

```bash
curl -fsSL https://raw.githubusercontent.com/stevenrey/3CXHoliday/main/install.sh | sudo bash
```

Danach ist die GUI erreichbar unter:

```text
https://<3cx-host>/holiday-import/
```

Healthcheck:

```text
https://<3cx-host>/holiday-import/api/health
```

## Was der Installer macht

- installiert `git`, `python3`, `python3-venv`, `python3-pip`, `nginx` und Hilfstools
- clont oder aktualisiert das Repo nach `/opt/3cx-holiday-importer`
- erstellt ein Python-Venv und installiert `requirements.txt`
- installiert Piper TTS nach `/opt/piper`
- laedt das deutsche Modell `de_DE-thorsten-high.onnx`
- installiert den systemd-Service `3cx-holiday-importer`
- startet Uvicorn lokal auf `127.0.0.1:5000`
- erstellt ein Nginx-Snippet fuer `/holiday-import/`
- bindet dieses Snippet in den bestehenden HTTPS-Serverblock ein
- verwendet dadurch das vorhandene SSL-Zertifikat des bestehenden Nginx weiter

Der Installer erstellt kein neues Zertifikat und keinen separaten HTTPS-VHost.

## Wichtige Pfade

- App: `/opt/3cx-holiday-importer`
- Config: `/opt/3cx-holiday-importer/config.json`
- Service: `/etc/systemd/system/3cx-holiday-importer.service`
- Nginx Location: `/etc/nginx/snippets/3cx-holiday-importer-location.conf`
- Log: `/var/log/3cx-holiday-importer.log`
- Piper Binary: `/opt/piper/piper`
- Piper Modell: `/opt/piper/de_DE-thorsten-high.onnx`

## Betrieb

```bash
sudo systemctl status 3cx-holiday-importer
sudo journalctl -u 3cx-holiday-importer -f
sudo tail -f /var/log/3cx-holiday-importer.log
sudo nginx -t
```

## Update

Der gleiche Installationsbefehl kann erneut ausgefuehrt werden. Wenn `/opt/3cx-holiday-importer` bereits ein Git-Checkout ist, wird `main` per `git pull --ff-only` aktualisiert.

## Hinweis zur 3CX API

Die App meldet sich per Benutzer/Passwort oder Client Credentials bei der 3CX an. Ein manueller XAPI Bearer Token ist nur als Test-Fallback vorgesehen. Beim Sync wird die WAV-Ansage als 3CX Custom Prompt hochgeladen und der Feiertag danach mit diesem Prompt im ausgewaehlten Department erstellt.
