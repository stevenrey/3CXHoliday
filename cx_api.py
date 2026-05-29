from datetime import date

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


def _date_from_parts(value):
    if not isinstance(value, dict):
        return ""
    day = value.get("Day")
    month = value.get("Month")
    year = value.get("Year")
    if not (day and month and year):
        return ""
    try:
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
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool = False, xapi_token: str = ""):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.xapi_token = xapi_token.strip() if isinstance(xapi_token, str) else ""

    def _auth_headers(self):
        token = _extract_token(self.xapi_token or self.get_access_token())
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
                "Der konfigurierte XAPI Bearer Token wurde abgelehnt."
                if self.xapi_token
                else "Fuer Schreibzugriff ist wahrscheinlich ein aktueller XAPI Bearer Token aus der 3CX Admin-Session noetig."
            )
            raise ValueError(f"3CX XAPI Schreibzugriff fehlgeschlagen: HTTP {response.status_code}. {token_hint} {response.text[:300]}")
        if response.status_code not in (200, 201, 204):
            raise ConnectionError(f"3CX XAPI Antwort: HTTP {response.status_code} {response.text[:300]}")
        if response.content:
            return response.json()
        return {}

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
            "IsRecurrent": False,
            "HolidayPrompt": filename,
            "Day": day.day,
            "Month": day.month,
            "Year": day.year,
            "TimeOfStartDate": "P0D",
            "DayEnd": day.day,
            "MonthEnd": day.month,
            "YearEnd": day.year,
            "TimeOfEndDate": "P1D",
        }
        result = self._xapi_post("Holidays", payload)
        return {"status": "created", "payload": payload, "response": result}

    def get_holidays(self):
        return []
