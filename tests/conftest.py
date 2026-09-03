"""Общая оснастка тестов книги.

Модули книги — это marimo-приложения: обычные Python-модули, у которых
`app.run()` исполняет все ячейки и возвращает (outputs, defs). Сеть в
ячейках ходит через httpx.Client, поэтому здесь его подменяют на клиент
с MockTransport — тесты не зависят от живого хаба и MLX.
"""

import importlib
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def fake_relay(monkeypatch):
    """Подменяет httpx.Client на клиент с программируемыми ответами.

    Возвращает словарь routes: {"/v1/status": (200, json)}. Тест наполняет
    его ДО импорта модуля книги. Незнакомый путь -> ConnectError, как при
    выключенном хабе.
    """
    routes = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path
        if key not in routes:
            raise httpx.ConnectError("нет маршрута " + key, request=request)
        status, payload = routes[key]
        return httpx.Response(status, json=payload)

    real_client = httpx.Client

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", patched_client)
    return routes


def run_book_module(name: str):
    """Импортирует модуль книги заново и исполняет его marimo-приложение."""
    sys.modules.pop(name, None)
    module = importlib.import_module(name)
    outputs, defs = module.app.run()
    return outputs, defs
