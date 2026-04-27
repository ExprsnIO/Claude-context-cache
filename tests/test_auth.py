"""Tests for the API-key detection cascade.

The cascade is `env > .env > platform config > keyring` and earlier hits
shadow later ones. These tests pin that order down. We never put a real
key in tests; the placeholder `sk-ant-` shape is enough to satisfy the
shape check.

`monkeypatch.delenv` is used to scrub `ANTHROPIC_API_KEY` and
`CLAUDE_API_KEY` so the host environment doesn't leak into the tests
(developer machines often have one of these set).
"""

from __future__ import annotations

import sys

import pytest

from ccc.auth import (
    ApiKeyHit,
    _looks_like_key,
    _parse_dotenv,
    detect_api_key,
    search_summary,
)


VALID = "sk-ant-" + "a" * 32
ALT = "sk-ant-" + "b" * 32


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch, tmp_path):
    """Hide host env vars, redirect $HOME and $XDG_CONFIG_HOME under tmp_path."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    yield home


def test_looks_like_key_accepts_sk_ant_prefix() -> None:
    assert _looks_like_key(VALID)
    assert _looks_like_key("  " + VALID + "  ")


def test_looks_like_key_rejects_obvious_garbage() -> None:
    assert not _looks_like_key("")
    assert not _looks_like_key("placeholder")
    assert not _looks_like_key("sk-ant-")  # too short
    assert not _looks_like_key("xxx-" + "a" * 60)


def test_env_var_wins_when_set(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", VALID)
    hit = detect_api_key()
    assert hit is not None
    assert hit.key == VALID
    assert hit.source == "$ANTHROPIC_API_KEY"


def test_claude_alias_used_when_anthropic_absent(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_API_KEY", VALID)
    hit = detect_api_key()
    assert hit is not None
    assert hit.source == "$CLAUDE_API_KEY"


def test_anthropic_shadows_claude_alias(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", VALID)
    monkeypatch.setenv("CLAUDE_API_KEY", ALT)
    hit = detect_api_key()
    assert hit is not None
    assert hit.key == VALID
    assert hit.source == "$ANTHROPIC_API_KEY"


def test_project_dotenv_used_when_no_env_var(tmp_path) -> None:
    (tmp_path / ".env").write_text(f'ANTHROPIC_API_KEY="{VALID}"\n', encoding="utf-8")
    hit = detect_api_key(project_root=tmp_path)
    assert hit is not None
    assert hit.key == VALID
    assert hit.source.endswith(".env")


def test_env_var_shadows_dotenv(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", VALID)
    (tmp_path / ".env").write_text(f"ANTHROPIC_API_KEY={ALT}\n", encoding="utf-8")
    hit = detect_api_key(project_root=tmp_path)
    assert hit is not None
    assert hit.key == VALID  # env, not the .env file


def test_xdg_config_path_used_on_linux(_scrub_env, monkeypatch) -> None:
    if sys.platform == "win32":
        pytest.skip("Linux/Unix path test")
    cfg = _scrub_env.parent / "xdg" / "anthropic" / "api_key"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(VALID + "\n", encoding="utf-8")
    hit = detect_api_key()
    assert hit is not None
    assert hit.key == VALID
    assert "anthropic/api_key" in hit.source.replace("\\", "/")


def test_legacy_dot_anthropic_path(_scrub_env) -> None:
    cfg = _scrub_env / ".anthropic" / "api_key"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(VALID, encoding="utf-8")
    hit = detect_api_key()
    assert hit is not None
    assert hit.key == VALID


def test_invalid_key_in_dotenv_is_ignored(monkeypatch, tmp_path, _scrub_env) -> None:
    """A placeholder in .env must NOT fool the detector."""
    (tmp_path / ".env").write_text(
        "ANTHROPIC_API_KEY=put-your-real-key-here\n", encoding="utf-8"
    )
    hit = detect_api_key(project_root=tmp_path)
    assert hit is None


def test_redacted_form_hides_most_of_the_key() -> None:
    hit = ApiKeyHit(key=VALID, source="$ANTHROPIC_API_KEY")
    redacted = hit.redacted()
    # No more than the documented prefix/suffix appears.
    assert VALID not in redacted
    assert redacted.startswith(VALID[:8])
    assert redacted.endswith(VALID[-4:])


def test_search_summary_lists_every_candidate(monkeypatch, _scrub_env) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", VALID)
    rows = search_summary()
    labels = [label for label, _ in rows]
    assert "$ANTHROPIC_API_KEY" in labels
    assert "$CLAUDE_API_KEY" in labels
    assert any("anthropic" in label and "api_key" in label for label in labels)
    # The env-var row reports a hit.
    by_label = dict(rows)
    assert by_label["$ANTHROPIC_API_KEY"] is True
    assert by_label["$CLAUDE_API_KEY"] is False


def test_dotenv_parser_handles_quotes_comments_and_export(tmp_path) -> None:
    p = tmp_path / ".env"
    p.write_text(
        "\n".join(
            [
                "# leading comment",
                "",
                "export ANTHROPIC_API_KEY='single-quoted'",
                'CLAUDE_API_KEY="double-quoted"',
                "BARE=value-no-quotes",
                "EMPTY=",
                "BAD_LINE_NO_EQUALS",
            ]
        ),
        encoding="utf-8",
    )
    parsed = dict(_parse_dotenv(p))
    assert parsed["ANTHROPIC_API_KEY"] == "single-quoted"
    assert parsed["CLAUDE_API_KEY"] == "double-quoted"
    assert parsed["BARE"] == "value-no-quotes"
    assert parsed["EMPTY"] == ""
    assert "BAD_LINE_NO_EQUALS" not in parsed


def test_no_key_anywhere_returns_none() -> None:
    # Fixture already scrubs env / sets HOME under tmp_path with no files.
    assert detect_api_key() is None
