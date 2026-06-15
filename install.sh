#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/3cx-holiday-importer}"
REPO_URL="${REPO_URL:-https://github.com/stevenrey/3CXHoliday.git}"
BRANCH="${BRANCH:-main}"
SERVICE_FILE="/etc/systemd/system/3cx-holiday-importer.service"
NGINX_SNIPPET="/etc/nginx/snippets/3cx-holiday-importer-location.conf"
NGINX_INCLUDE="include ${NGINX_SNIPPET};"
NGINX_BACKUP_DIR="/root/3cx-holiday-importer-nginx-backups"
PIPER_DIR="${PIPER_DIR:-/opt/piper}"
PIPER_RELEASE_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
PIPER_MODEL_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx"
PIPER_MODEL_CONFIG_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx.json"

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte als root ausfuehren, z.B. mit sudo." >&2
  exit 1
fi

if [ -z "${APP_DIR}" ] || [ "${APP_DIR}" = "/" ]; then
  echo "Ungueltiges APP_DIR: ${APP_DIR}" >&2
  exit 1
fi

echo "==> Pakete installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git python3 python3-venv python3-pip nginx tar

echo "==> App nach ${APP_DIR} installieren"
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" fetch origin "${BRANCH}"
  git -C "${APP_DIR}" checkout "${BRANCH}"
  git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
else
  rm -rf "${APP_DIR}"
  git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

echo "==> Python venv vorbereiten"
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "==> Piper TTS installieren"
mkdir -p "${PIPER_DIR}"
if [ ! -x "${PIPER_DIR}/piper" ]; then
  tmp_piper="$(mktemp -d)"
  curl -fsSL "${PIPER_RELEASE_URL}" -o "${tmp_piper}/piper.tar.gz"
  tar -xzf "${tmp_piper}/piper.tar.gz" -C "${tmp_piper}"
  cp -a "${tmp_piper}/piper/." "${PIPER_DIR}/"
  rm -rf "${tmp_piper}"
  chmod +x "${PIPER_DIR}/piper"
fi
if [ ! -s "${PIPER_DIR}/de_DE-thorsten-high.onnx" ]; then
  curl -fL "${PIPER_MODEL_URL}" -o "${PIPER_DIR}/de_DE-thorsten-high.onnx"
fi
if [ ! -s "${PIPER_DIR}/de_DE-thorsten-high.onnx.json" ]; then
  curl -fL "${PIPER_MODEL_CONFIG_URL}" -o "${PIPER_DIR}/de_DE-thorsten-high.onnx.json"
fi

echo "==> systemd Service installieren"
cp "${APP_DIR}/3cx-holiday-importer.service.example" "${SERVICE_FILE}"
touch /var/log/3cx-holiday-importer.log
systemctl daemon-reload
systemctl enable --now 3cx-holiday-importer
systemctl restart 3cx-holiday-importer

echo "==> Nginx Location /holiday-import einrichten"
mkdir -p /etc/nginx/snippets
mkdir -p "${NGINX_BACKUP_DIR}"
cat > "${NGINX_SNIPPET}" <<'NGINX'
location = /holiday-import {
    return 301 /holiday-import/;
}

location /holiday-import/ {
    proxy_pass http://127.0.0.1:5000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /holiday-import;
}
NGINX

python3 - "$NGINX_SNIPPET" "$NGINX_INCLUDE" "$NGINX_BACKUP_DIR" <<'PY'
import pathlib
import re
import subprocess
import sys

snippet = pathlib.Path(sys.argv[1])
include_line = sys.argv[2]
backup_dir = pathlib.Path(sys.argv[3])

def add_path(paths, path):
    try:
        path = path.resolve()
    except OSError:
        return
    if path.is_file() and path != snippet.resolve() and path not in paths:
        if ".bak" not in path.name and "holiday-importer" not in path.name:
            paths.append(path)

active_paths = []
try:
    dump = subprocess.run(["nginx", "-T"], text=True, capture_output=True, check=False)
    nginx_dump = f"{dump.stdout}\n{dump.stderr}"
    for match in re.finditer(r"^# configuration file ([^:]+):", nginx_dump, re.MULTILINE):
        add_path(active_paths, pathlib.Path(match.group(1)))
except Exception:
    pass

fallback_paths = []
for base in (
    pathlib.Path("/etc/nginx/sites-enabled"),
    pathlib.Path("/etc/nginx/conf.d"),
    pathlib.Path("/var/lib/3cxpbx/Bin/nginx/conf"),
):
    if base.exists():
        for path in base.rglob("*"):
            add_path(fallback_paths, path)

paths = active_paths + [path for path in fallback_paths if path not in active_paths]

def find_ssl_server_end(text):
    for match in re.finditer(r"server\s*\{", text):
        start = match.end()
        depth = 1
        pos = start
        while pos < len(text) and depth:
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
            pos += 1
        block = text[match.start():pos]
        has_ssl_listen = re.search(r"listen\s+[^;]*ssl[^;]*;", block)
        has_https_port = re.search(r"listen\s+[^;]*(443|5001)[^;]*;", block)
        has_ssl_certificate = "ssl_certificate" in block
        if has_ssl_listen and (has_https_port or has_ssl_certificate):
            return pos - 1
    return None

for path in paths:
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    if include_line in text:
        if path in active_paths:
            print(f"Nginx Include ist bereits in aktiver Konfiguration {path}")
            sys.exit(0)
        print(f"Nginx Include steht nur in inaktiver Konfiguration {path}; suche weiter.")
        continue
    end = find_ssl_server_end(text)
    if end is not None:
        backup = backup_dir / f"{path.name}.bak-holiday-import"
        backup.write_text(text, encoding="utf-8")
        new_text = text[:end] + f"\n    {include_line}\n" + text[end:]
        path.write_text(new_text, encoding="utf-8")
        print(f"Nginx Include in {path} eingefuegt. Backup: {backup}")
        sys.exit(0)

print("Kein aktiver HTTPS server{} Block in der geladenen Nginx-Konfiguration gefunden.", file=sys.stderr)
print(f"Bitte manuell in den bestehenden HTTPS server{{}} Block einfuegen: {include_line}", file=sys.stderr)
sys.exit(1)
PY

nginx -t
systemctl reload nginx

echo
echo "Fertig. Die GUI ist unter https://<3cx-host>/holiday-import/ erreichbar."
echo "Healthcheck: https://<3cx-host>/holiday-import/api/health"
