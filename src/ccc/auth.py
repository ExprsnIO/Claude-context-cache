"""API key detection across well-known locations.

The harness walks a fixed cascade and stops at the first hit. Order:

  1. Environment variables: $ANTHROPIC_API_KEY, then $CLAUDE_API_KEY.
  2. `.env` file in the project root (if `detect_api_key(project_root=...)`).
  3. `.env` file in $HOME.
  4. Platform-specific user-config file:
       - Windows: %APPDATA%\\anthropic\\api_key
       - macOS:   ~/Library/Application Support/anthropic/api_key
       - Linux/Unix: $XDG_CONFIG_HOME/anthropic/api_key (default ~/.config/...)
  5. ~/.anthropic/api_key (legacy convention).
  6. OS keyring entry (service=`anthropic`, username=`api_key`) — uses
     Keychain on macOS, Credential Manager on Windows, Secret Service /
     libsecret on Linux. Requires the optional `keyring` package
     (`pip install -e ".[keyring]"`); silently skipped if absent.

Each candidate value is shape-checked (`sk-ant-` prefix, ≥ 32 chars) before
being accepted, so an obvious typo or accidentally-saved placeholder won't
be used. The detector NEVER mutates `os.environ` — it just returns the
detected value, so the key doesn't leak into subprocesses.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_VARS: tuple[str, ...] = ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY")
KEYRING_SERVICE = "anthropic"
KEYRING_USERNAME = "api_key"


@dataclass(frozen=True)
class ApiKeyHit:
    """A successful key lookup. `source` is a human-readable label (never the key)."""

    key: str
    source: str

    def redacted(self) -> str:
        """Safe-to-print form: 8 leading chars + ellipsis + 4 trailing."""
        if len(self.key) <= 12:
            return "***"
        return f"{self.key[:8]}…{self.key[-4:]}"


def detect_api_key(*, project_root: Path | str | None = None) -> ApiKeyHit | None:
    """Run the full cascade. First valid hit wins; returns None if nothing found."""
    root = Path(project_root).resolve() if project_root is not None else None

    for env in ENV_VARS:
        val = os.environ.get(env)
        if val and _looks_like_key(val):
            return ApiKeyHit(val.strip(), source=f"${env}")

    for env_path in _dotenv_candidates(root):
        for key, val in _parse_dotenv(env_path):
            if key in ENV_VARS and _looks_like_key(val):
                return ApiKeyHit(val.strip(), source=str(env_path))

    for cfg_path in _config_candidates():
        val = _read_first_line(cfg_path)
        if val and _looks_like_key(val):
            return ApiKeyHit(val.strip(), source=str(cfg_path))

    val = _keyring_get()
    if val and _looks_like_key(val):
        return ApiKeyHit(
            val.strip(),
            source=f"keyring://{KEYRING_SERVICE}/{KEYRING_USERNAME}",
        )

    return None


def search_summary(*, project_root: Path | str | None = None) -> list[tuple[str, bool]]:
    """Return `(label, present)` for every candidate the detector inspects.

    Used by `ccc auth` to show the user *what was searched* without leaking
    the key. Order matches `detect_api_key`. `present=True` means the
    candidate yielded a syntactically valid key, not necessarily the one
    that won the cascade — `detect_api_key` returns the first hit.
    """
    root = Path(project_root).resolve() if project_root is not None else None
    rows: list[tuple[str, bool]] = []

    for env in ENV_VARS:
        val = os.environ.get(env)
        rows.append((f"${env}", bool(val and _looks_like_key(val))))

    for env_path in _dotenv_candidates(root):
        hit = any(
            k in ENV_VARS and _looks_like_key(v) for k, v in _parse_dotenv(env_path)
        )
        rows.append((str(env_path), hit))

    for cfg_path in _config_candidates():
        val = _read_first_line(cfg_path)
        rows.append((str(cfg_path), bool(val and _looks_like_key(val))))

    val = _keyring_get()
    rows.append(
        (
            f"keyring://{KEYRING_SERVICE}/{KEYRING_USERNAME}",
            bool(val and _looks_like_key(val)),
        )
    )
    return rows


def _looks_like_key(val: str) -> bool:
    val = val.strip()
    return val.startswith("sk-ant-") and len(val) >= 32


def _dotenv_candidates(project_root: Path | None) -> list[Path]:
    paths: list[Path] = []
    if project_root is not None:
        paths.append(project_root / ".env")
    paths.append(Path.home() / ".env")
    return paths


def _config_candidates() -> list[Path]:
    home = Path.home()
    paths: list[Path] = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths.append(Path(appdata) / "anthropic" / "api_key")
    elif sys.platform == "darwin":
        paths.append(
            home / "Library" / "Application Support" / "anthropic" / "api_key"
        )
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    paths.append(Path(xdg) / "anthropic" / "api_key")
    paths.append(home / ".anthropic" / "api_key")
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _parse_dotenv(path: Path) -> list[tuple[str, str]]:
    """Tiny `.env` parser. No interpolation, no multi-line values, no escapes.

    Handles: blank lines, `#` comments, optional `export ` prefix,
    optional `'…'` or `"…"` quoting around the value.
    """
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and (
            (v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")
        ):
            v = v[1:-1]
        if k:
            out.append((k, v))
    return out


def _read_first_line(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        if path.stat().st_size == 0:
            return None
        return path.read_text(encoding="utf-8").splitlines()[0].strip()
    except OSError:
        return None


def _keyring_get() -> str | None:
    """Look up the key in the OS keyring; return None if `keyring` is missing.

    `keyring` itself dispatches to Keychain (macOS), Credential Manager
    (Windows), or Secret Service / libsecret (Linux).
    """
    try:
        import keyring  # type: ignore
    except ImportError:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None
