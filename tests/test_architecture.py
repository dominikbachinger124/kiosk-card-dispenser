"""Architecture guards: fakes stay in tests, domain stays free of hardware and Qt."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "kiosk"
FORBIDDEN_IN_DOMAIN = ("PySide6", "serial", "sqlite3", "kiosk.hardware", "kiosk.gui")
FAKE_NAMES = ("FakeDispenser", "FakeIdReader", "FakeState", "ScriptedLink")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _python_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


@pytest.mark.parametrize("path", _python_files(SRC / "domain"), ids=lambda p: p.name)
def test_domain_imports_no_hardware_gui_or_storage(path: Path) -> None:
    for module in _imports(path):
        assert not module.startswith(FORBIDDEN_IN_DOMAIN), (
            f"{path.name} imports {module}"
        )


def test_production_code_never_imports_test_package() -> None:
    for path in _python_files(SRC):
        for module in _imports(path):
            assert not module.startswith("tests"), f"{path} imports {module}"


def test_no_fake_class_is_defined_in_production_code() -> None:
    for path in _python_files(SRC):
        source = path.read_text(encoding="utf-8")
        for name in FAKE_NAMES:
            assert f"class {name}" not in source, f"{name} defined in {path}"


def test_fakes_live_only_under_tests() -> None:
    tests_dir = Path(__file__).resolve().parent
    found = [
        path.name
        for path in _python_files(tests_dir)
        if any(
            f"class {name}" in path.read_text(encoding="utf-8") for name in FAKE_NAMES
        )
    ]

    assert found, "expected the fakes to exist in the test package"
