import requests


class CXApi:
    def __init__(self, host: str, username: str, password: str, verify_ssl: bool = False):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl

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
            token = (
                data.get("Token")
                or data.get("token")
                or data.get("access_token")
                or data.get("AccessToken")
                or data.get("accessToken")
            )
            if not token:
                raise ConnectionError("3CX Login erfolgreich, aber kein Access Token erhalten")
            return token
        if response.status_code in (401, 403):
            raise ValueError("3CX Anmeldung fehlgeschlagen")
        raise ConnectionError(f"3CX Antwort: HTTP {response.status_code}")

    def get_departments(self):
        token = self.get_access_token()
        if not token:
            raise ConnectionError("Kein 3CX Access Token erhalten")
        url = f"{self.host}/xapi/v1/Groups"
        params = {
            "$filter": "not startsWith(Name, '___FAVORITES___')",
            "$orderby": "Name",
            "$select": "Id,Name,Number,IsDefault",
        }
        headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15, verify=self.verify_ssl)
        except requests.exceptions.Timeout as e:
            raise TimeoutError("Zeitueberschreitung beim Abrufen der Departments") from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError("3CX XAPI nicht erreichbar") from e
        if response.status_code in (401, 403):
            raise ValueError("3CX XAPI Anmeldung fehlgeschlagen")
        if response.status_code != 200:
            raise ConnectionError(f"3CX XAPI Antwort: HTTP {response.status_code}")
        data = response.json()
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
