import requests
from django.conf import settings

AUTH_URL = "https://cos2.cityopensource.com/api/v1/auth/signin"
REFRESH_URL = "https://cos2.cityopensource.com/api/signin"


class COS2Client:
    _access_token = None
    _refresh_token = None

    def __init__(self):
        self.username = settings.COS2_USERNAME
        self.password = settings.COS2_PASSWORD

    def _signin(self):
        r = requests.post(AUTH_URL, json={
            "username": self.username,
            "password": self.password
        })
        r.raise_for_status()
        data = r.json()
        # salva in memoria
        self.__class__._access_token = data.get("accessToken")
        self.__class__._refresh_token = data.get("refreshToken")
        return self._access_token

    def _refresh(self):
        refresh_token = self.__class__._refresh_token
        if not refresh_token:
            return self._signin()

        r = requests.post(REFRESH_URL, json={
            "username": self.username,
            "refreshtoken": refresh_token
        })
        if r.status_code != 200:
            return self._signin()

        data = r.json()
        self.__class__._access_token = data.get("accessToken")
        self.__class__._refresh_token = data.get("refreshToken", refresh_token)
        return self._access_token

    def get_token(self):
        if self.__class__._access_token:
            return self._access_token
        return self._signin()

    def request(self, method, url, **kwargs):
        token = self.get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers

        r = requests.request(method, url, **kwargs)
        if r.status_code == 401:
            token = self._refresh()
            headers["Authorization"] = f"Bearer {token}"
            r = requests.request(method, url, **kwargs)
        r.raise_for_status()
        return r
