#!/bin/bash
set -e
echo "=== 3CX Holiday Importer – Installation ==="

APP_PORT=5000
APP_DIR=/opt/3cx-holiday-importer
CONFIG_DIR=/etc/3cx-holiday-importer
NGINX_SNIPPETS=/var/lib/3cxpbx/Bin/nginx/conf/snippets

# Verzeichnisse
mkdir -p $APP_DIR
mkdir -p $CONFIG_DIR
mkdir -p $NGINX_SNIPPETS

# Dateien kopieren
cp -r . $APP_DIR/
cd $APP_DIR

# Python venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Piper TTS installieren
echo "Piper TTS herunterladen..."
mkdir -p /opt/piper
cd /opt/piper
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
  wget -q https://github.com/rhasspy/piper/releases/latest/download/piper_linux_x86_64.tar.gz -O piper.tar.gz
elif [ "$ARCH" = "aarch64" ]; then
  wget -q https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz -O piper.tar.gz
fi
tar -xzf piper.tar.gz --strip-components=1
chmod +x piper

# Deutsche Stimme (Thorsten)
echo "Deutsche Stimme (Thorsten) herunterladen..."
wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx" -O de_DE-thorsten-high.onnx
wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx.json" -O de_DE-thorsten-high.onnx.json
echo "Piper TTS bereit."

# systemd Service
cd $APP_DIR
cat > /etc/systemd/system/3cx-holiday-importer.service << EOF
[Unit]
Description=3CX Holiday Importer
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port $APP_PORT
Restart=on-failure
RestartSec=5
Environment=HOLIDAY_CONFIG=$CONFIG_DIR/config.json

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable 3cx-holiday-importer
systemctl start 3cx-holiday-importer

# Nginx Snippet (update-sicher)
cp $APP_DIR/nginx/holiday-importer.conf $NGINX_SNIPPETS/holiday-importer.conf
echo "Nginx Snippet installiert."
nginx -t && systemctl reload nginx

# Cronjob (jedes Jahr am 2. Januar um 06:00)
(crontab -l 2>/dev/null | grep -v "3cx-holiday-importer"; echo "0 6 2 1 * curl -s -X POST http://localhost:$APP_PORT/api/sync -H 'Content-Type: application/json' -d '{"year": null, "dry_run": false}' >> /var/log/3cx-holiday-importer-cron.log 2>&1") | crontab -

echo ""
echo "=== Installation abgeschlossen ==="
echo "Web-UI: https://tiagdemo.3cx.ch/holiday-importer/"
echo "Logs:   journalctl -u 3cx-holiday-importer -f"