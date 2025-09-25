import requests, time
from django.conf import settings
from django.core.cache import cache

AUTH_URL = "https://cos2.cityopensource.com/api/v1/auth/signin"
REFRESH_URL = "https://cos2.cityopensource.com/api/signin"

class COS2Client:
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
        # salva in cache
        cache.set("cos2_access", data["accessToken"], timeout=23*3600)  # 23h
        cache.set("cos2_refresh", data["refreshToken"], timeout=350*24*3600)
        return data["accessToken"]

    def _refresh(self):
        refresh_token = cache.get("cos2_refresh")
        if not refresh_token:
            return self._signin()
        r = requests.post(REFRESH_URL, json={
            "username": self.username,
            "refreshtoken": refresh_token
        })
        if r.status_code != 200:
            return self._signin()
        data = r.json()
        cache.set("cos2_access", data["accessToken"], timeout=23*3600)
        return data["accessToken"]

    def get_token(self):
        token = cache.get("cos2_access")
        if token:
            return token
        return self._signin()

    def request(self, method, url, **kwargs):
        token = self.get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers

        r = requests.request(method, url, **kwargs)
        if r.status_code == 401:
            # accessToken scaduto → refresh
            token = self._refresh()
            headers["Authorization"] = f"Bearer {token}"
            r = requests.request(method, url, **kwargs)
        r.raise_for_status()
        return r
