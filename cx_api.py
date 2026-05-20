"""
3CX xAPI client for V20.
Docs: https://www.3cx.com/docs/manual/pbx-api-v2/
"""
import requests
import logging
import urllib3
from typing import Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


class CXApi:
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool = False):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self._token: Optional[str] = None

    def _login(self):
        url = f"{self.host}/api/v1/security/credentials"
        payload = {
            "SecurityCode": "",
            "Username": self.username,
            "Password": self.password,
        }
        resp = self.session.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # V20 returns Status=AuthSuccess and sets cookies
        if data.get("Status") not in ("AuthSuccess", "Authenticated"):
            raise RuntimeError(f"3CX Login fehlgeschlagen: {data.get('Status')}")
        logger.info("3CX Login erfolgreich")

    def _get(self, path: str, **kwargs) -> requests.Response:
        resp = self.session.get(f"{self.host}{path}", timeout=15, **kwargs)
        if resp.status_code == 401:
            self._login()
            resp = self.session.get(f"{self.host}{path}", timeout=15, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, path: str, **kwargs) -> requests.Response:
        resp = self.session.post(f"{self.host}{path}", timeout=15, **kwargs)
        if resp.status_code == 401:
            self._login()
            resp = self.session.post(f"{self.host}{path}", timeout=15, **kwargs)
        resp.raise_for_status()
        return resp

    def test_connection(self) -> str:
        """Test connection and return version string."""
        self._login()
        try:
            resp = self._get("/api/v1/pbx/status")
            data = resp.json()
            version = data.get("Version", "unbekannt")
            return f"Verbindung OK – 3CX Version {version}"
        except Exception:
            return "Verbindung OK (Version nicht abrufbar)"

    def get_holidays(self) -> list[dict]:
        """Return all holidays currently configured in 3CX."""
        try:
            resp = self._get("/api/v1/holiday")
            return resp.json().get("list", [])
        except Exception as e:
            logger.warning(f"Konnte 3CX-Feiertage nicht lesen: {e}")
            return []

    def set_holiday(self, name: str, date_iso: str, filename: str) -> dict:
        """
        Create or update a holiday in 3CX V20.
        date_iso: YYYY-MM-DD
        filename: just the .wav filename (no path)
        """
        self._login()
        payload = {
            "Name": name,
            "Date": date_iso,
            "Repeat": False,
            "PromptFile": filename,
        }
        resp = self._post("/api/v1/holiday", json=payload)
        return resp.json()

    def get_prompt_files(self) -> list[str]:
        """List existing IVR prompt files."""
        try:
            resp = self._get("/api/v1/promptfile")
            return [f["Filename"] for f in resp.json().get("list", [])]
        except Exception as e:
            logger.warning(f"Prompt-Dateien nicht abrufbar: {e}")
            return []

    def upload_prompt(self, filepath: str, filename: str) -> bool:
        """Upload a WAV file as IVR prompt."""
        try:
            with open(filepath, "rb") as f:
                files = {"file": (filename, f, "audio/wav")}
                resp = self.session.post(
                    f"{self.host}/api/v1/promptfile",
                    files=files,
                    timeout=30,
                )
                if resp.status_code == 401:
                    self._login()
                    f.seek(0)
                    resp = self.session.post(
                        f"{self.host}/api/v1/promptfile",
                        files=files,
                        timeout=30,
                    )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Upload fehlgeschlagen {filename}: {e}")
            return False
