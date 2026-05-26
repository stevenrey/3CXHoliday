#!/bin/bash
set -e
echo "=== 3CX Holiday Importer – Update ==="

APP_DIR=/opt/3cx-holiday-importer
NGINX_SNIPPETS=/var/lib/3cxpbx/Bin/nginx/conf/snippets

# Service stoppen
systemctl stop 3cx-holiday-importer

# Dateien aktualisieren (Config bleibt erhalten)
cp -r . $APP_DIR/
cd $APP_DIR

# Dependencies aktualisieren
source venv/bin/activate
pip install -r requirements.txt

# Nginx Snippet aktualisieren
cp $APP_DIR/nginx/holiday-importer.conf $NGINX_SNIPPETS/holiday-importer.conf
nginx -t && systemctl reload nginx

# Service neu starten
systemctl start 3cx-holiday-importer
systemctl status 3cx-holiday-importer

echo "=== Update abgeschlossen ==="
echo "Web-UI: https://tiagdemo.3cx.ch/holiday-importer/"