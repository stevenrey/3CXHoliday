from datetime import date
import base64
import json
from pathlib import Path
import time

import requests


def _extract_token(data):
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return ""
    for key in ("access_token", "AccessToken", "accessToken", "token", "Token"):
        value = data.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested = _extract_token(value)
            if nested:
                return nested
    return ""


def _decode_jwt_payload(token: str):
    if not token:
        return {}
    clean_token = token[7:] if token.lower().startswith("bearer ") else token
    parts = clean_token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}


def _roles_allow_holiday_write(roles, max_role=""):
    role_set = {str(role).lower() for role in roles or []}
    max_role_text = str(max_role or "").lower()
    admin_markers = {
        "admin",
        "globaladmin",
        "systemadmin",
        "phonesystemadmin",
        "machineadmin",
        "apps.readwrite",
        "groups.create",
    }
    if any(marker in role_set for marker in admin_markers):
        return True
    return max_role_text in {"system_owners", "system_owner", "admins", "admin"}


def _normalize_date(value):
    if not value:
        return ""
    text = str(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def _date_from_parts(value):
    if not isinstance(value, dict):
        return ""
    day = value.get("Day")
    month = value.get("Month")
    year = value.get("Year")
    if not (day and month and year):
        return ""
    try:
        if int(year) == 0:
            return f"0000-{int(month):02d}-{int(day):02d}"
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return ""


def _collect_holidays(data):
    holidays = []

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return

        keys = {str(key).lower(): key for key in value}
        date_value = _date_from_parts(value)
        date_key = next(
            (keys[key] for key in ("date", "day", "holidaydate", "start", "starttime", "startdate", "from") if key in keys),
            None,
        )
        name_key = next((keys[key] for key in ("name", "displayname", "reason", "description") if key in keys), None)
        if (date_value or date_key) and name_key:
            holidays.append(
                {
                    "date": date_value or _normalize_date(value.get(date_key)),
                    "name": str(value.get(name_key) or ""),
                    "raw": value,
                }
            )

        for key, nested in value.items():
            if "holiday" in str(key).lower() or key in ("value", "Items", "items"):
                walk(nested)

    walk(data)
    unique = {}
    for holiday in holidays:
        if holiday["date"]:
            unique[(holiday["date"], holiday["name"].lower())] = holiday
    return list(unique.values())


class CXApi:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
        xapi_token: str = "",
        auth_mode: str = "userpass",
        client_id: str = "",
        client_secret: str = "",
    ):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.xapi_token = xapi_token.strip() if isinstance(xapi_token, str) else ""
        self.auth_mode = auth_mode or "userpass"
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self._session_logged_in = False

    def _auth_headers(self):
        if self.auth_mode == "clientcreds" or (self.username and self.password):
            token = _extract_token(self.get_access_token())
        else:
            token = _extract_token(self.xapi_token)
        return self._headers_for_token(token)

    def _login_auth_headers(self):
        token = _extract_token(self.get_access_token())
        return self._headers_for_token(token)

    @staticmethod
    def _headers_for_token(token: str):
        if not token:
            raise ConnectionError("Kein 3CX Access Token erhalten")
        authorization = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        return {"Accept": "application/json", "Authorization": authorization}

    def get_token_info(self):
        token = _extract_token(self.get_access_token())
        payload = _decode_jwt_payload(token)
        roles = payload.get("role", [])
        max_role = payload.get("MaxRole", "")
        return {
            "audience": payload.get("aud", ""),
            "issuer": payload.get("iss", ""),
            "user": payload.get("unique_name", payload.get("name", "")),
            "max_role": max_role,
            "roles": roles,
            "can_write_holidays": _roles_allow_holiday_write(roles, max_role),
            "expires_at": payload.get("exp", ""),
        }

    def assert_holiday_write_access(self):
        info = self.get_token_info()
        if not info.get("can_write_holidays"):
            if self.auth_mode == "userpass" and self.username and self.password:
                info["session_fallback"] = True
                return info
            roles = ", ".join(info.get("roles", [])) or "keine"
            raise PermissionError(
                "Der aktuelle 3CX Token darf keine Feiertage erstellen. "
                f"User={info.get('user') or 'unbekannt'}, MaxRole={info.get('max_role') or 'leer'}, Rollen={roles}. "
                "Bitte einen 3CX Benutzer mit Admin-/Systemrollen oder Client Credentials mit Schreibrechten verwenden."
            )
        return info

    def _request_with_auth_retry(self, method: str, url: str, **kwargs):
        headers = kwargs.pop("headers", {})
        auth_headers = self._auth_headers()
        auth_headers.update(headers)
        response = requests.request(method, url, headers=auth_headers, **kwargs)
        if response.status_code in (401, 403) and self.xapi_token and self.username and self.password:
            retry_headers = self._login_auth_headers()
            retry_headers.update(headers)
            response = requests.request(method, url, headers=retry_headers, **kwargs)
        return response

    def _xapi_get(self, path: str, params: dict | None = None, allow_missing: bool = False):
        url = f"{self.host}/xapi/v1/{path.lstrip('/')}"
        try:
            response = self._request_with_auth_retry("GET", url, params=params, timeout=15, verify=self.verify_ssl)
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung bei der 3CX XAPI") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX XAPI nicht erreichbar") from e
        if allow_missing and response.status_code in (400, 404, 405):
            return None
        if response.status_code in (401, 403):
            raise ValueError(
                "3CX XAPI Anmeldung fehlgeschlagen. Bitte pruefen: 3CX Host muss die FQDN-URL sein "
                "(z.B. https://tiagdemo.3cx.ch) und der Benutzer/Token braucht XAPI/Admin-Rechte."
            )
        if response.status_code != 200:
            raise ConnectionError(f"3CX XAPI Antwort: HTTP {response.status_code}")
        return response.json()

    def _xapi_post(self, path: str, payload: dict):
        url = f"{self.host}/xapi/v1/{path.lstrip('/')}"
        post_headers = {
            "Content-Type": "application/json",
            "Origin": self.host,
            "Referer": f"{self.host}/",
            "ngsw-bypass": "bypass",
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        }
        try:
            response = self._request_with_auth_retry(
                "POST",
                url,
                json=payload,
                headers=post_headers,
                timeout=15,
                verify=self.verify_ssl,
            )
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung bei der 3CX XAPI") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX XAPI nicht erreichbar") from e
        if response.status_code in (401, 403):
            token_hint = (
                "Client Credentials wurden abgelehnt; bitte App-Rechte in 3CX pruefen."
                if self.auth_mode == "clientcreds"
                else "Der konfigurierte XAPI Bearer Token wurde abgelehnt."
                if self.xapi_token
                else "Fuer Schreibzugriff ist wahrscheinlich ein aktueller XAPI Bearer Token aus der 3CX Admin-Session noetig."
            )
            raise ValueError(f"3CX XAPI Schreibzugriff fehlgeschlagen: HTTP {response.status_code}. {token_hint} {response.text[:300]}")
        if response.status_code not in (200, 201, 204):
            raise ConnectionError(f"3CX XAPI Antwort: HTTP {response.status_code} {response.text[:300]}")
        if response.content and response.text.strip():
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}
        return {}

    def _session_login(self):
        if self._session_logged_in:
            return
        if not self.host or not self.username or not self.password:
            raise ValueError("3CX Zugangsdaten fuer Session-Login unvollstaendig")
        url = f"{self.host}/api/v1/security/credentials"
        payload = {"SecurityCode": "", "Username": self.username, "Password": self.password}
        try:
            response = self.session.post(
                url,
                json=payload,
                headers={"Accept": "application/json"},
                timeout=15,
            )
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung beim 3CX Session-Login") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX Session-Login nicht erreichbar") from e
        if response.status_code not in (200, 204):
            raise ValueError(f"3CX Session-Login fehlgeschlagen: HTTP {response.status_code} {response.text[:300]}")
        if response.content and response.text.strip():
            try:
                data = response.json()
            except ValueError:
                data = {}
            status = str(data.get("Status", "")).lower()
            if status and status not in {"authsuccess", "authenticated"}:
                raise ValueError(f"3CX Session-Login fehlgeschlagen: {data.get('Status')}")
        self._session_logged_in = True

    def _session_json_request(self, method: str, path: str, payload: dict | None = None):
        self._session_login()
        url = f"{self.host}{path}"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": self.host,
            "Referer": f"{self.host}/",
            "ngsw-bypass": "bypass",
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        }
        try:
            response = self.session.request(
                method,
                url,
                json=payload,
                headers=headers,
                timeout=15,
            )
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung bei der 3CX Session API") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX Session API nicht erreichbar") from e
        if response.status_code == 401:
            self._session_logged_in = False
            self._session_login()
            response = self.session.request(method, url, json=payload, headers=headers, timeout=15)
        if response.status_code in (401, 403):
            raise ValueError(f"3CX Session API Schreibzugriff fehlgeschlagen: HTTP {response.status_code} {response.text[:300]}")
        if response.status_code not in (200, 201, 204):
            raise ConnectionError(f"3CX Session API Antwort: HTTP {response.status_code} {response.text[:300]}")
        if response.content and response.text.strip():
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}
        return {}

    def _xapi_delete(self, path: str, allow_missing: bool = False):
        url = f"{self.host}/xapi/v1/{path.lstrip('/')}"
        delete_headers = {
            "ngsw-bypass": "bypass",
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        }
        try:
            response = self._request_with_auth_retry(
                "DELETE",
                url,
                headers=delete_headers,
                timeout=15,
                verify=self.verify_ssl,
            )
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung bei der 3CX XAPI") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX XAPI nicht erreichbar") from e
        if allow_missing and response.status_code == 404:
            return {"status": "not_found"}
        if response.status_code in (401, 403):
            raise ValueError(f"3CX XAPI Schreibzugriff fehlgeschlagen: HTTP {response.status_code} {response.text[:300]}")
        if response.status_code not in (200, 204):
            raise ConnectionError(f"3CX XAPI Antwort: HTTP {response.status_code} {response.text[:300]}")
        return {"status": "deleted"}

    def upload_prompt(self, filepath: str, prompt_name: str):
        prompt_name = Path(prompt_name).name
        file_path = Path(filepath)
        if not file_path.exists():
            raise FileNotFoundError(f"Ansage-Datei nicht gefunden: {file_path}")
        wav_data = file_path.read_bytes()
        if not wav_data:
            raise ValueError(f"Ansage-Datei ist leer: {file_path}")

        self._xapi_delete(f"CustomPrompts('{prompt_name}')", allow_missing=True)

        url = f"{self.host}/xapi/v1/customPrompts"
        boundary = f"----3CXSyncBoundary{int(time.time() * 1000)}"
        preamble = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{prompt_name}"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("utf-8")
        closing = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = b"".join([preamble, wav_data, closing])
        headers = self._auth_headers()
        headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
                "ngsw-bypass": "bypass",
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
            }
        )
        try:
            response = requests.post(
                url,
                headers=headers,
                data=body,
                timeout=60,
                verify=self.verify_ssl,
            )
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung beim 3CX Prompt-Upload") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX Prompt-Upload nicht erreichbar") from e

        if response.status_code in (401, 403):
            raise ValueError(f"3CX Prompt-Upload fehlgeschlagen: HTTP {response.status_code} {response.text[:300]}")
        if response.status_code not in (200, 201, 204):
            raise ConnectionError(f"3CX Prompt-Upload Antwort: HTTP {response.status_code} {response.text[:300]}")
        if response.content and response.text.strip():
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}
        return {}

    def test_connection(self):
        token = self.get_access_token()
        return {"message": "Verbindung erfolgreich", "version": "", "token_type": "bearer" if token else ""}

    def get_access_token(self):
        if self.auth_mode == "clientcreds":
            return self.get_client_credentials_token()
        if not self.host or not self.username or not self.password:
            raise ValueError("3CX Zugangsdaten unvollstaendig")
        url = f"{self.host}/webclient/api/Login/GetAccessToken"
        payload = {"Username": self.username, "Password": self.password, "SecurityCode": ""}
        try:
            response = requests.post(url, json=payload, headers={"Accept": "application/json"}, timeout=15, verify=self.verify_ssl)
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung bei der Verbindung zu 3CX") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX Server nicht erreichbar") from e
        if response.status_code in (200, 204):
            if not response.content:
                return ""
            data = response.json()
            token = _extract_token(data)
            if not token:
                raise ConnectionError("3CX Login erfolgreich, aber kein Access Token erhalten")
            return token
        if response.status_code in (401, 403):
            raise ValueError("3CX Anmeldung fehlgeschlagen")
        raise ConnectionError(f"3CX Antwort: HTTP {response.status_code}")

    def get_client_credentials_token(self):
        if not self.host or not self.client_id or not self.client_secret:
            raise ValueError("3CX Client Credentials unvollstaendig")
        url = f"{self.host}/connect/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        try:
            response = requests.post(
                url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
                verify=self.verify_ssl,
            )
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung bei 3CX Client Credentials") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX Server nicht erreichbar") from e
        if response.status_code != 200:
            raise ValueError(f"3CX Client Credentials fehlgeschlagen: HTTP {response.status_code} {response.text[:300]}")
        data = response.json()
        token = _extract_token(data)
        if not token:
            raise ConnectionError("3CX Client Credentials erfolgreich, aber kein Access Token erhalten")
        return token

    def get_departments(self):
        params = {
            "$filter": "not startsWith(Name, '___FAVORITES___')",
            "$orderby": "Name",
            "$select": "Id,Name,Number,IsDefault",
        }
        data = self._xapi_get("Groups", params=params)
        groups = data.get("value", data if isinstance(data, list) else [])
        return [
            {
                "id": str(group.get("Id", "")),
                "name": group.get("Name", ""),
                "number": group.get("Number", ""),
                "is_default": bool(group.get("IsDefault", False)),
            }
            for group in groups
            if group.get("Id") and group.get("Name")
        ]

    def get_department_holidays(self, department_id: str):
        if not department_id:
            return {"holidays": [], "source": "no_department"}

        attempts = [
            (f"Groups({department_id})", {"$select": "OfficeHolidays", "$expand": "OfficeHolidays"}),
            (f"Groups({department_id})", {"$expand": "OfficeHolidays"}),
            (f"Groups({department_id})", {"$expand": "Holidays"}),
            (f"Groups({department_id})", None),
            (f"Groups({department_id})/OfficeHolidays", None),
            (f"Groups({department_id})/Holidays", None),
            ("Holidays", None),
            ("Holidays", {"$filter": f"GroupId eq {department_id}"}),
            ("OfficeHolidays", {"$filter": f"GroupId eq {department_id}"}),
        ]
        errors = []
        for path, params in attempts:
            try:
                data = self._xapi_get(path, params=params, allow_missing=True)
            except ValueError as exc:
                errors.append(f"{path}: {exc}")
                continue
            if data is None:
                errors.append(path)
                continue
            holidays = _collect_holidays(data)
            if path == "Holidays":
                group = self._group_identifier(department_id)
                holidays = [
                    holiday for holiday in holidays
                    if not group or str(holiday.get("raw", {}).get("Group", "")) == group
                ]
            if holidays:
                return {"holidays": holidays, "source": path}
        return {"holidays": [], "source": "not_found", "attempted": errors}

    def _group_identifier(self, department_id: str):
        departments = self.get_departments()
        for department in departments:
            if str(department.get("id", "")) == str(department_id):
                return department.get("number") or department.get("name") or ""
        return ""

    def set_holiday(self, name: str, date_str: str, filename: str, department_id: str = ""):
        if not department_id:
            raise ValueError("Kein Department fuer den Feiertag ausgewaehlt")
        try:
            day = date.fromisoformat(date_str)
        except ValueError as exc:
            raise ValueError(f"Ungueltiges Feiertagsdatum: {date_str}") from exc
        group = self._group_identifier(department_id)
        if not group:
            raise ValueError(f"Department {department_id} konnte nicht aufgeloest werden")
        payload = {
            "Group": group,
            "Name": name,
            "IsRecurrent": True,
            "HolidayPrompt": filename,
            "Day": day.day,
            "Month": day.month,
            "Year": 0,
            "TimeOfStartDate": "P0D",
            "DayEnd": day.day,
            "MonthEnd": day.month,
            "YearEnd": 0,
            "TimeOfEndDate": "P1D",
        }
        try:
            result = self._xapi_post("Holidays", payload)
            return {"status": "created", "payload": payload, "response": result, "api": "xapi_bearer"}
        except ValueError as exc:
            if self.auth_mode != "userpass" or "HTTP 403" not in str(exc):
                raise

        try:
            result = self._session_json_request("POST", "/xapi/v1/Holidays", payload)
            return {"status": "created", "payload": payload, "response": result, "api": "xapi_session"}
        except (ValueError, ConnectionError):
            legacy_payload = {
                "Name": name,
                "Date": date_str,
                "Repeat": True,
                "PromptFile": filename,
                "Group": group,
            }
            result = self._session_json_request("POST", "/api/v1/holiday", legacy_payload)
            return {"status": "created", "payload": legacy_payload, "response": result, "api": "legacy_session"}

    def get_holidays(self):
        return []
