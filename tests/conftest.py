import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class FakeHttp:
    """Подменённый httpx: маршрут → ответ, журнал вызовов."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def get(self, url, headers=None):
        self.calls.append(("GET", url, None))
        return self.routes.get(("GET", url), FakeResp(404))

    def post(self, url, json=None, headers=None):
        self.calls.append(("POST", url, json))
        return self.routes.get(("POST", url), FakeResp(404))
