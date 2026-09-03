import importlib.util
from pathlib import Path


def test_board_is_valid_marimo_app():
    path = Path(__file__).resolve().parents[1] / "book" / "modules" / "board.py"
    spec = importlib.util.spec_from_file_location("board", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.app is not None
