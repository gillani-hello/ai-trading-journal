"""Runtime configuration, read from TJ_* environment variables, plus MT5 discovery.

MT5 is found in three kinds of places:
- Windows: %APPDATA%\\MetaQuotes\\Terminal\\...
- macOS: MetaQuotes' MT5 app, which runs inside its own Wine prefix
- Linux: a Wine prefix (~/.wine or ~/.mt5)
"""

import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# MetaQuotes' macOS app keeps MT5 inside its own Wine prefix.
MT5_WINE_PREFIX = Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5"
MT5_APP_WINE = Path("/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine")
EXPORT_SUBDIR = "TradeJournal"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TJ_", env_file=PROJECT_ROOT / ".env", extra="ignore")

    data_dir: Path = PROJECT_ROOT / "data"
    # Folder the EA writes into (…/Common/Files/TradeJournal). Auto-discovered when unset.
    mt5_dir: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8000
    web_dist: Path = PROJECT_ROOT / "web" / "dist"
    # Minimum seconds between on-demand syncs triggered by MCP tool calls.
    sync_throttle_seconds: float = 30.0

    @property
    def db_path(self) -> Path:
        return self.data_dir / "journal.db"

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    return settings


def _appdata() -> Path | None:
    value = os.environ.get("APPDATA")
    return Path(value) if IS_WINDOWS and value else None


def wine_prefixes() -> list[Path]:
    home = Path.home()
    return [p for p in (MT5_WINE_PREFIX, home / ".wine", home / ".mt5") if (p / "drive_c").is_dir()]


def wine_executable() -> str | None:
    if MT5_APP_WINE.exists():
        return str(MT5_APP_WINE)
    return shutil.which("wine64") or shutil.which("wine")


def _common_files_dirs() -> list[Path]:
    out: list[Path] = []
    if appdata := _appdata():
        out.append(appdata / "MetaQuotes" / "Terminal" / "Common" / "Files")
    for prefix in wine_prefixes():
        out += sorted((prefix / "drive_c" / "users").glob("*/AppData/Roaming/MetaQuotes/Terminal/Common/Files"))
    return out


def discover_mt5_dir() -> Path | None:
    """Return the folder the EA exports to, or None if MT5 isn't found."""
    settings = get_settings()
    if settings.mt5_dir:
        return settings.mt5_dir
    candidates = [c / EXPORT_SUBDIR for c in _common_files_dirs()]
    # Prefer a folder the EA has already written to.
    return next((c for c in candidates if c.is_dir()), candidates[0] if candidates else None)


def discover_mt5_terminal_dirs() -> list[Path]:
    """MT5 data folders (each contains MQL5/), where Expert Advisors are installed."""
    found: list[Path] = []
    if appdata := _appdata():
        found += sorted(d for d in (appdata / "MetaQuotes" / "Terminal").glob("*") if (d / "MQL5").is_dir())
    for prefix in wine_prefixes():
        drive = prefix / "drive_c"
        for program_files in ("Program Files", "Program Files (x86)"):
            # Portable installs keep MQL5/ next to terminal64.exe.
            found += sorted(d for d in (drive / program_files).glob("*") if (d / "MQL5").is_dir() and (d / "terminal64.exe").exists())
        found += sorted(d for d in (drive / "users").glob("*/AppData/Roaming/MetaQuotes/Terminal/*") if (d / "MQL5").is_dir())
    return list(dict.fromkeys(found))


def claude_desktop_config_path() -> Path:
    if appdata := _appdata():
        return appdata / "Claude" / "claude_desktop_config.json"
    if IS_MAC:
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"
