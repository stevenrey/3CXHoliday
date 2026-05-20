#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/opt/3cx-holiday-importer
SERVICE_NAME=3cx-holiday-importer
CONFIG_DIR=/etc/3cx-holiday-importer
USER_NAME=${SUDO_USER:-$(whoami)}

echo "[1/6] Installiere Systempakete"
apt-get update
apt-get install -y python3 python3-venv python3-pip curl nginx

echo "[2/6] Kopiere Dateien nach $APP_DIR"
mkdir -p "$APP_DIR"
cp -r ./* "$APP_DIR/"
mkdir -p "$CONFIG_DIR"

echo "[3/6] Python venv erstellen"
python3 -m venv "$APP_DIR/venv"
source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"

echo "[4/6] Rechte setzen"
chown -R "$USER_NAME":"$USER_NAME" "$APP_DIR"
mkdir -p /var/log
mkdir -p /var/lib/3cxpbx/Instance1/Data/Ivr/Prompts || true

echo "[5/6] systemd Service erstellen"
cat > /etc/systemd/system/${SERVICE_NAME}.service << SYSTEMD
[Unit]
Description=3CX Holiday Importer
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
Environment=CONFIG_PATH=$CONFIG_DIR/config.json
Environment=LOG_FILE=/var/log/3cx-holiday-importer.log
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 3001
Restart=always
User=$USER_NAME
Group=$USER_NAME

[Install]
WantedBy=multi-user.target
SYSTEMD

echo "[6/6] Nginx Site erstellen"
cat > /etc/nginx/conf.d/holiday-importer.conf << NGINX
server {
    listen 8088;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}
nginx -t && systemctl reload nginx

echo
echo "Installation abgeschlossen."
echo "Web-UI: http://<server-ip>:8088"
echo "Direkt:  http://<server-ip>:3001"
