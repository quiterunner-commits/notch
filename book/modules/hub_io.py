"""Разговор книги с хабом — вынесен из ячеек marimo, чтобы его можно было проверить.

Логика жила внутри `@app.cell`, куда не дотянуться ни импортом, ни pytest:
проверка размера и суффикса, разбор ответа хаба, чтение сессии. Здесь она
обычным модулем, который импортируют и книга, и тесты. Функции ничего не
печатают и не знают про marimo — они возвращают структуру, а показ остаётся
за ячейкой.

Границы продублированы из relay_vision.py сознательно: книга живёт в своём
контейнере и импортировать модуль хаба не может. Дублирование проверяется
тестом на совпадение с исходником, а не надеждой.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

# Те же значения, что в relay_vision.py (IMAGE_SUFFIXES, MAX_BYTES).
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic"})
MAX_BYTES = 24 * 1024 * 1024

# Отказ хаба в личности выглядит одинаково для истёкшей, чужой и
# отсутствующей сессии — fail closed на его стороне, один текст на нашей.
NO_IDENTITY = "хаб не принял личность — войдите собой на /book/passkey"


def read_session(session_path: str) -> str:
    """Токен веб-сессии из файла, который пишет /book/passkey.

    Любая поломка файла — отсутствие, битый JSON, чужая структура — это
    одно и то же: сессии нет. Исключение наружу не выпускается, иначе
    страница падала бы вместо того, чтобы честно предложить войти.
    """
    if not session_path or not os.path.exists(session_path):
        return ""
    try:
        with open(session_path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return ""
    if not isinstance(loaded, dict):
        return ""
    session = loaded.get("session", "")
    return session if isinstance(session, str) else ""


def credential(session_path: str, env_token: str = "") -> Tuple[str, str]:
    """Чем представляемся хабу и откуда это взялось.

    Порядок не случаен: личность предъявляет человек сессией, а не
    контейнер токеном (см. _desk_session_email в event_hub.py). Токен из
    окружения остаётся запасным путём для отладки.

    Возвращает (значение, источник), где источник — "session", "token"
    или "" — чтобы страница могла сказать правду о том, кто она.
    """
    session = read_session(session_path)
    if session:
        return session, "session"
    if env_token:
        return env_token, "token"
    return "", ""


def auth_headers(token: str) -> Dict[str, str]:
    """Пустой словарь вместо `Bearer ` без значения: заголовок с пустым
    токеном хаб читает как попытку авторизации и отвечает иначе, чем на
    запрос вовсе без заголовка."""
    return {"Authorization": f"Bearer {token}"} if token else {}


def check_material(name: str, data: bytes) -> Optional[str]:
    """Причина, по которой хаб этот файл не примет, — или None.

    Проверяется здесь, до отправки, не ради вежливости: 24 МБ, посланные
    ради ответа 400, это 32 МБ base64 в теле запроса.
    Порядок проверок повторяет relay_vision.save_material().
    """
    name = os.path.basename(name or "")
    if not name or name.startswith("."):
        return "имя файла пустое или скрытое"
    suffix = os.path.splitext(name)[1].lower()
    if suffix not in IMAGE_SUFFIXES:
        return "не изображение (хаб примет только его)"
    if not data:
        return "файл пуст"
    if len(data) > MAX_BYTES:
        return f"{len(data) // 1024 // 1024} МБ — больше {MAX_BYTES // 1024 // 1024}"
    return None


def _refusal(response: Any) -> str:
    """Слова отказа — хаба, а не наши. Свой текст только там, где хаб
    молчит по существу (401 одинаков для всех причин)."""
    if response.status_code == 401:
        return NO_IDENTITY
    text = (response.text or "").strip()
    try:
        detail = response.json().get("error") or text
    except (ValueError, AttributeError):
        detail = text
    return f"хаб отказал ({response.status_code}): {str(detail)[:200]}"


def attach(http: Any, relay_url: str, headers: Dict[str, str], name: str, data: bytes) -> Dict[str, Any]:
    """Положить файл в материал хаба. Байты не касаются диска книги."""
    reason = check_material(name, data)
    if reason:
        return {"ok": False, "name": name, "reason": reason}
    response = http.post(
        f"{relay_url}/v1/vision/material",
        headers=headers,
        json={
            "name": os.path.basename(name),
            "data_base64": base64.b64encode(data).decode("ascii"),
        },
    )
    if not response.is_success:
        return {"ok": False, "name": name, "reason": _refusal(response)}
    stored = response.json()
    return {"ok": True, "name": stored.get("name", name), "bytes": stored.get("bytes", len(data))}


def look(http: Any, relay_url: str, headers: Dict[str, str], name: str, question: str) -> Dict[str, Any]:
    """Спросить модель про уже лежащий в материале файл."""
    if not question.strip():
        return {"ok": False, "reason": "вопрос пустой"}
    response = http.post(
        f"{relay_url}/v1/vision/look",
        headers=headers,
        json={"name": name, "question": question},
    )
    if not response.is_success:
        return {"ok": False, "reason": _refusal(response)}
    answer = response.json()
    return {
        "ok": True,
        "model": answer.get("model", "?"),
        "seconds": answer.get("seconds", 0),
        "answer": answer.get("answer", ""),
    }


def material_listing(http: Any, relay_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Что лежит в материале ПО ВЕРСИИ ХАБА — доказательство вместо кода 201."""
    response = http.get(f"{relay_url}/v1/vision", headers=headers)
    if not response.is_success:
        return {"ok": False, "reason": _refusal(response), "items": []}
    body = response.json()
    items = body.get("material") or []
    return {"ok": True, "items": [i for i in items if isinstance(i, dict)]}


def material_href(relay_browser_url: str, name: str) -> str:
    """Ссылка на байты. Имя обязано быть закодировано: хаб на своей
    стороне делает unquote(), и без quote() файл с пробелом или кириллицей
    даёт битую ссылку — а такие имена как раз обычны для скриншотов."""
    return f"{relay_browser_url}/v1/vision/material/{quote(name, safe='')}"


def human_size(size: int) -> str:
    """КБ округлением вниз превращали 900-байтный файл в «0 КБ» — для
    иконки или подписи это обычный размер, и ноль там читается как сбой."""
    if size < 1024:
        return f"{size} Б"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} КБ"
    return f"{size / 1024 / 1024:.1f} МБ"


def format_attached(result: Dict[str, Any], seen: Optional[Dict[str, Any]] = None) -> str:
    """Одна строка отчёта. Формат отдельно от отправки — чтобы проверять
    текст, не поднимая ни хаба, ни marimo."""
    if not result.get("ok"):
        return f"- 🔴 `{result.get('name', '?')}` — {result.get('reason', 'причина неизвестна')}"
    line = f"- 🟢 `{result['name']}` — {human_size(result['bytes'])} в материале"
    if seen is None:
        return line
    if not seen.get("ok"):
        return line + f"\n  - 🟡 разбор не вышел: {seen.get('reason', '')}"
    return line + f"\n  - _{seen['model']}, {seen['seconds']} с_: {seen['answer']}"
