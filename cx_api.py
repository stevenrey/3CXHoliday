"""3CX xAPI Client für Holiday-Profile"""
import requests, logging
from datetime import datetime

logger = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings()

class CXApi:
    def __init__(self, host: str, username: str, password: str):
        self.base = host.rstrip("/")
        self.token = None
        self._login(username, password)

    def _login(self, username: str, password: str):
        url = f"{self.base}/webclient/api/Login/GetAccessToken"
        try:
            resp = requests.post(
                url,
                json={"SecurityCode": "", "Username": username, "Password": password},
                verify=False, timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            self.token = data.get("Token", data.get("access_token"))
            if not self.token:
                raise ValueError("Kein Token in Login-Antwort erhalten")
            logger.info("3CX Login erfolgreich")
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Verbindung zu {self.base} fehlgeschlagen – Host nicht erreichbar")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Verbindung zu {self.base} Timeout – Server antwortet nicht")
        except requests.exceptions.HTTPError as e:
            raise ValueError(f"Login fehlgeschlagen: HTTP {resp.status_code} – Benutzername/Passwort prüfen")
        except Exception as e:
            raise RuntimeError(f"Login Fehler: {str(e)}")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def test_connection(self) -> dict:
        url = f"{self.base}/xapi/v1/SystemStatus"
        try:
            resp = requests.get(url, headers=self._headers(), verify=False, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return {
                "connected": True,
                "version": data.get("Version", "unbekannt"),
                "message": f"Verbunden mit 3CX {data.get('Version', 'unbekannt')}"
            }
        except Exception as e:
            raise RuntimeError(f"Statusabfrage fehlgeschlagen: {str(e)}")

    def get_holidays(self):
        url = f"{self.base}/xapi/v1/HolidayList"
        resp = requests.get(url, headers=self._headers(), verify=False, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def set_holiday(self, name: str, date_str: str, prompt_filename: str):
        d = datetime.strptime(date_str, "%d.%m.%Y")
        url = f"{self.base}/xapi/v1/HolidayList"
        payload = {
            "Name": name,
            "StartDate": d.strftime("%Y-%m-%dT00:00:00"),
            "EndDate": d.strftime("%Y-%m-%dT23:59:59"),
            "Prompt": prompt_filename,
            "Recurring": True
        }
        resp = requests.post(url, headers=self._headers(), json=payload, verify=False, timeout=10)
        resp.raise_for_status()
        logger.info(f"Holiday gesetzt: {name} am {date_str}")
        return resp.json()