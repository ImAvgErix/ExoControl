"""paths + document value plumbing unit tests."""
from __future__ import annotations

from aether.paths import exo_root, file_roots, state_dir
from aether.uia_cache import CachedElement, read_element_value_meta


def test_exo_root_under_home(tmp_path, monkeypatch):
    monkeypatch.setenv("EXO_HOME", str(tmp_path / ".exo"))
    # clear AETHER_HOME so it does not win
    monkeypatch.delenv("AETHER_HOME", raising=False)
    root = exo_root()
    assert root.name == ".exo" or str(root).endswith(".exo")
    assert state_dir().exists()
    assert any("workspace" in str(r) for r in file_roots())


def test_cached_element_value_via_in_dict():
    el = CachedElement(0, "", "edit", None, value="hello", value_via="win32")
    d = el.as_dict()
    assert d["value"] == "hello"
    assert d["value_via"] == "win32"


def test_read_element_value_meta_empty_raw():
    text, via = read_element_value_meta(None)
    assert text == ""
    assert via == ""
