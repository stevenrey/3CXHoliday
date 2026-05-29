#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/3cx-holiday-importer}"
REPO_URL="${REPO_URL:-https://github.com/stevenrey/3CXHoliday.git}"
BRANCH="${BRANCH:-main}"
SERVICE_FILE="/etc/systemd/system/3cx-holiday-importer.service"
NGINX_SNIPPET="/etc/nginx/snippets/3cx-holiday-importer-location.conf"
NGINX_INCLUDE="include ${NGINX_SNIPPET};"

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
apt-get install -y git python3 python3-venv python3-pip nginx

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

echo "==> systemd Service installieren"
cp "${APP_DIR}/3cx-holiday-importer.service.example" "${SERVICE_FILE}"
touch /var/log/3cx-holiday-importer.log
systemctl daemon-reload
systemctl enable --now 3cx-holiday-importer
systemctl restart 3cx-holiday-importer

echo "==> Nginx Location /holiday-import einrichten"
mkdir -p /etc/nginx/snippets
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

python3 - "$NGINX_SNIPPET" "$NGINX_INCLUDE" <<'PY'
import pathlib
import re
import sys

snippet = pathlib.Path(sys.argv[1])
include_line = sys.argv[2]
paths = []
for base in (pathlib.Path("/etc/nginx/sites-enabled"), pathlib.Path("/etc/nginx/conf.d"), pathlib.Path("/etc/nginx")):
    if base.exists():
        paths.extend(path for path in base.rglob("*.conf") if path != snippet)
paths.extend(path for path in pathlib.Path("/etc/nginx/sites-enabled").glob("*") if path.is_file())

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
        if re.search(r"listen\s+[^;]*443[^;]*ssl", block) and "ssl_certificate" in block:
            return pos - 1
    return None

for path in paths:
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    if include_line in text:
        print(f"Nginx Include ist bereits in {path}")
        sys.exit(0)
    end = find_ssl_server_end(text)
    if end is not None:
        backup = path.with_suffix(path.suffix + ".bak-holiday-import")
        backup.write_text(text, encoding="utf-8")
        new_text = text[:end] + f"\n    {include_line}\n" + text[end:]
        path.write_text(new_text, encoding="utf-8")
        print(f"Nginx Include in {path} eingefuegt. Backup: {backup}")
        sys.exit(0)

print("Kein bestehender SSL server{} Block in /etc/nginx/sites-enabled oder /etc/nginx/conf.d gefunden.", file=sys.stderr)
print(f"Bitte manuell in den bestehenden HTTPS server{} Block einfuegen: {include_line}", file=sys.stderr)
sys.exit(1)
PY

nginx -t
systemctl reload nginx

echo
echo "Fertig. Die GUI ist unter https://<3cx-host>/holiday-import/ erreichbar."
echo "Healthcheck: https://<3cx-host>/holiday-import/api/health"
