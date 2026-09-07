from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_VERSIONS = _BACKEND_ROOT / "migrations" / "versions"


def _revision_id_from_node(node: ast.stmt) -> str | None:
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "revision":
        value = node.value
    elif isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "revision" for target in node.targets
    ):
        value = node.value
    else:
        return None
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _revision_ids_from_files() -> list[str]:
    ids: list[str] = []
    for path in _VERSIONS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            rev = _revision_id_from_node(node)
            if rev is not None:
                ids.append(rev)
    return ids


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    return ScriptDirectory.from_config(cfg)


def test_alembic_revision_ids_are_unique() -> None:
    dupes = [rev for rev, count in Counter(_revision_ids_from_files()).items() if count > 1]
    assert dupes == [], f"duplicate Alembic revision ids: {dupes}"


def test_alembic_has_single_head() -> None:
    heads = _script_directory().get_heads()
    assert len(heads) == 1, f"multiple Alembic heads (Render upgrade head fails): {heads}"
