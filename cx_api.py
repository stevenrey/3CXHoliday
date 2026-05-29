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


def _normalize_date(value):
    if not value:
        return ""
    text = str(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


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
        date_key = next(
            (keys[key] for key in ("date", "day", "holidaydate", "start", "starttime", "startdate", "from") if key in keys),
            None,
        )
        name_key = next((keys[key] for key in ("name", "displayname", "reason", "description") if key in keys), None)
        if date_key and name_key:
            holidays.append(
                {
                    "date": _normalize_date(value.get(date_key)),
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
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool = False, xapi_token: str = ""):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.xapi_token = xapi_token.strip() if isinstance(xapi_token, str) else ""

    def _auth_headers(self):
        token = _extract_token(self.xapi_token or self.get_access_token())
        if not token:
            raise ConnectionError("Kein 3CX Access Token erhalten")
        authorization = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        return {"Accept": "application/json", "Authorization": authorization}

    def _xapi_get(self, path: str, params: dict | None = None, allow_missing: bool = False):
        url = f"{self.host}/xapi/v1/{path.lstrip('/')}"
        try:
            response = requests.get(url, params=params, headers=self._auth_headers(), timeout=15, verify=self.verify_ssl)
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung bei der 3CX XAPI") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX XAPI nicht erreichbar") from e
        if allow_missing and response.status_code in (400, 404):
            return None
        if response.status_code in (401, 403):
            raise ValueError(
                "3CX XAPI Anmeldung fehlgeschlagen. Bitte pruefen: 3CX Host muss die FQDN-URL sein "
                "(z.B. https://tiagdemo.3cx.ch) und der Benutzer/Token braucht XAPI/Admin-Rechte."
            )
        if response.status_code != 200:
            raise ConnectionError(f"3CX XAPI Antwort: HTTP {response.status_code}")
        return response.json()

    def test_connection(self):
        token = self.get_access_token()
        return {"message": "Verbindung erfolgreich", "version": "", "token_type": "bearer" if token else ""}

    def get_access_token(self):
        if not self.host or not self.username or not self.password:
            raise ValueError("3CX Zugangsdaten unvollstaendig")
        url = f"{self.host}/webclient/api/Login/GetAccessToken"
        payload = {"Username": self.username, "Password": self.password}
        try:
            response = requests.post(url, json=payload, timeout=15, verify=self.verify_ssl)
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
            (f"Groups({department_id})", {"$expand": "Holidays"}),
            (f"Groups({department_id})", {"$expand": "OfficeHolidays"}),
            (f"Groups({department_id})/Holidays", None),
            (f"Groups({department_id})/OfficeHolidays", None),
            ("Holidays", {"$filter": f"GroupId eq {department_id}"}),
            ("OfficeHolidays", {"$filter": f"GroupId eq {department_id}"}),
            (f"Groups({department_id})", None),
        ]
        errors = []
        for path, params in attempts:
            data = self._xapi_get(path, params=params, allow_missing=True)
            if data is None:
                errors.append(path)
                continue
            holidays = _collect_holidays(data)
            if holidays:
                return {"holidays": holidays, "source": path}
        return {"holidays": [], "source": "not_found", "attempted": errors}

    def set_holiday(self, name: str, date_str: str, filename: str, department_id: str = ""):
        return {
            "status": "not_implemented",
            "name": name,
            "date": date_str,
            "file": filename,
            "department_id": department_id,
        }

    def get_holidays(self):
        return []
