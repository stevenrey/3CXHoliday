#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/3cx-holiday-importer"
SERVICE_NAME="3cx-holiday-importer"
CONFIG_DIR="/etc/3cx-holiday-importer"
DEFAULT_APP_PORT="3001"
DEFAULT_PUBLIC_PORT="8088"
USER_NAME="${SUDO_USER:-$(whoami)}"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

port_in_use() {
  local port="$1"
  if command_exists ss; then
    ss -ltn | awk '{print $4}' | grep -Eq "[:.]${port}$"
  elif command_exists netstat; then
    netstat -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${port}$"
  else
    return 1
  fi
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Bitte mit sudo oder als root ausführen."
    exit 1
  fi
}

ask_port() {
  local prompt="$1"
  local default_port="$2"
  local result

  while true; do
    read -r -p "$prompt [$default_port]: " result || true
    result="${result:-$default_port}"

    if ! [[ "$result" =~ ^[0-9]+$ ]]; then
      echo "Ungültiger Port: $result"
      continue
    fi

    if [ "$result" -lt 1 ] || [ "$result" -gt 65535 ]; then
      echo "Port muss zwischen 1 und 65535 liegen."
      continue
    fi

    echo "$result"
    return 0
  done
}

write_systemd_service() {
  local app_port="$1"
  cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<SYSTEMD
[Unit]
Description=3CX Holiday Importer
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
Environment=CONFIG_PATH=${CONFIG_DIR}/config.json
Environment=LOG_FILE=/var/log/3cx-holiday-importer.log
Environment=APP_PORT=${app_port}
ExecStart=${APP_DIR}/venv/bin/uvicorn main:app --host 0.0.0.0 --port ${app_port}
Restart=always
RestartSec=3
User=${USER_NAME}
Group=${USER_NAME}

[Install]
WantedBy=multi-user.target
SYSTEMD
}

write_nginx_config() {
  local app_port="$1"
  local public_port="$2"
  cat > /etc/nginx/conf.d/holiday-importer.conf <<EOF_NGINX
server {
    listen ${public_port};
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:${app_port};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF_NGINX
}

main() {
  require_root

  echo "3CX Holiday Importer Installation"
  echo

  local app_port
  local public_port

  app_port="$(ask_port 'Interner Uvicorn-Port' "$DEFAULT_APP_PORT")"
  public_port="$(ask_port 'Öffentlicher Nginx-Port' "$DEFAULT_PUBLIC_PORT")"

  if [ "$app_port" = "$public_port" ]; then
    echo "Hinweis: interner und externer Port sind identisch. Das ist möglich, aber normalerweise nicht nötig."
  fi

  if port_in_use "$app_port"; then
    echo "Warnung: Interner Port $app_port scheint bereits belegt zu sein."
  fi

  if port_in_use "$public_port"; then
    echo "Warnung: Öffentlicher Port $public_port scheint bereits belegt zu sein."
  fi

  echo "[1/6] Installiere Systempakete"
  apt-get update
  apt-get install -y python3 python3-venv python3-pip curl nginx

  echo "[2/6] Kopiere Dateien nach ${APP_DIR}"
  mkdir -p "$APP_DIR"
  cp -r ./* "$APP_DIR/"
  mkdir -p "$CONFIG_DIR"

  echo "[3/6] Python venv erstellen"
  python3 -m venv "$APP_DIR/venv"
  # shellcheck disable=SC1091
  source "$APP_DIR/venv/bin/activate"
  pip install --upgrade pip
  pip install -r "$APP_DIR/requirements.txt"

  echo "[4/6] Rechte setzen"
  chown -R "$USER_NAME":"$USER_NAME" "$APP_DIR"
  mkdir -p /var/log
  touch /var/log/3cx-holiday-importer.log
  chown "$USER_NAME":"$USER_NAME" /var/log/3cx-holiday-importer.log
  mkdir -p /var/lib/3cxpbx/Instance1/Data/Ivr/Prompts || true

  echo "[5/6] systemd Service erstellen"
  write_systemd_service "$app_port"

  echo "[6/6] Nginx Site erstellen"
  write_nginx_config "$app_port" "$public_port"

  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}"

  nginx -t
  systemctl reload nginx

  echo
  echo "Installation abgeschlossen."
  echo "Interner App-Port: ${app_port}"
  echo "Öffentlicher Nginx-Port: ${public_port}"
  echo "Web-UI: http://<server-ip>:${public_port}"
  echo "Direkt:  http://<server-ip>:${app_port}"
  echo
  echo "Status prüfen: systemctl status ${SERVICE_NAME}"
  echo "Logs prüfen:   journalctl -u ${SERVICE_NAME} -f"
}

main "$@"
