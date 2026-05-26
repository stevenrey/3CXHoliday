#!/usr/bin/env bash
set -e
APP_DIR=/opt/3cx-holiday-importer
SERVICE_FILE=/etc/systemd/system/3cx-holiday-importer.service
mkdir -p "$APP_DIR"
cp -r ./* "$APP_DIR"/
cd "$APP_DIR"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
cp 3cx-holiday-importer.service.example "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable 3cx-holiday-importer
systemctl restart 3cx-holiday-importer
