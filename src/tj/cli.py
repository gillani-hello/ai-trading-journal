"""`tj` command line: serve, mcp, sync, install-ea, mcp-config, install-service, seed-demo."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from tj.config import (
    IS_MAC,
    IS_WINDOWS,
    PROJECT_ROOT,
    claude_desktop_config_path,
    discover_mt5_dir,
    discover_mt5_terminal_dirs,
    wine_executable,
)

DEMO_DIR = PROJECT_ROOT / "demo-data"
EA_SOURCE = PROJECT_ROOT / "mt5" / "TradeJournalSync.mq5"
CLAUDE_DESKTOP_CONFIG = claude_desktop_config_path()
SERVICE_LABEL = "com.tradingjournal.serve"
SERVICE_PLIST = Path.home() / "Library/LaunchAgents" / f"{SERVICE_LABEL}.plist"


def _use_demo() -> None:
    """Point everything at the separate demo data folder (must run before settings are read)."""
    os.environ["TJ_DATA_DIR"] = str(DEMO_DIR)
    os.environ["TJ_MT5_DIR"] = str(DEMO_DIR / "export")


def cmd_serve(args: argparse.Namespace) -> int:
    if args.demo:
        _use_demo()
    import uvicorn

    from tj.api.main import create_app
    from tj.config import get_settings

    settings = get_settings()
    host, port = args.host or settings.host, args.port or settings.port
    print(f"Trading journal on http://{host}:{port}" + ("  (demo data)" if args.demo else ""))
    uvicorn.run(create_app(watch=not args.no_watch), host=host, port=port, log_level="info")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    if args.demo:
        _use_demo()
    from tj.mcp_server.server import main

    main()
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    if args.demo:
        _use_demo()
    from tj.db import init_db
    from tj.ingest.watcher import run_sync

    init_db()
    print(json.dumps(run_sync(force=args.force).as_dict(), indent=2))
    return 0


def cmd_seed_demo(args: argparse.Namespace) -> int:
    _use_demo()
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    from tj.db import init_db, session_scope
    from tj.demo import annotate, generate
    from tj.ingest.mt5_files import sync_mt5

    init_db()
    stats = generate(DEMO_DIR / "export", days=args.days)
    with session_scope() as s:
        sync_mt5(s)
        annotate(s)
    print(f"Demo journal created in {DEMO_DIR} with {stats['trades']} trades.")
    print("Start it with:  uv run tj serve --demo")
    return 0


def _wine_prefix_of(path: Path) -> Path | None:
    return next((p for p in path.parents if (p / "drive_c").is_dir()), None)


def _to_windows_path(path: Path, prefix: Path) -> str:
    return "C:\\" + "\\".join(path.relative_to(prefix / "drive_c").parts)


def _metaeditor(data_dir: Path) -> tuple[Path, bool] | None:
    """MetaEditor64.exe for an MT5 data folder, and whether that install is portable."""
    if (data_dir / "MetaEditor64.exe").exists():
        return data_dir / "MetaEditor64.exe", True
    origin = data_dir / "origin.txt"  # AppData data folders record where MT5 is installed
    if not origin.is_file():
        return None
    install = origin.read_bytes().decode("utf-16", errors="ignore").strip().lstrip("\ufeff")
    if IS_WINDOWS:
        path = Path(install)
    else:
        prefix = _wine_prefix_of(data_dir)
        if prefix is None or not install[:2].upper() == "C:":
            return None
        path = prefix / "drive_c" / Path(*install[3:].split("\\"))
    editor = path / "MetaEditor64.exe"
    return (editor, False) if editor.exists() else None


def _compile_ea(data_dir: Path, source: Path) -> str | None:
    """Compile with the terminal's own MetaEditor; returns MetaEditor's result line."""
    found = _metaeditor(data_dir)
    if found is None:
        return None
    editor, portable = found
    log_file = source.with_suffix(".log")
    log_file.unlink(missing_ok=True)
    if portable:
        # Proven form for portable installs: a path relative to the data folder.
        target, cwd = r"MQL5\Experts\TradeJournal\TradeJournalSync.mq5", data_dir
    else:
        cwd = editor.parent
        target = str(source) if IS_WINDOWS else _to_windows_path(source, _wine_prefix_of(data_dir))  # type: ignore[arg-type]
    args = [f"/compile:{target}", "/log"] + (["/portable"] if portable else [])
    if IS_WINDOWS:
        cmd, env = [str(editor), *args], None
    else:
        wine, prefix = wine_executable(), _wine_prefix_of(data_dir)
        if wine is None or prefix is None:
            return None
        exe = editor.name if portable else _to_windows_path(editor, prefix)
        cmd, env = [wine, exe, *args], {**os.environ, "WINEPREFIX": str(prefix), "WINEDEBUG": "-all"}
    try:
        subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not log_file.is_file():
        return None
    text = log_file.read_bytes().decode("utf-16", errors="replace")
    return next((ln.strip() for ln in text.splitlines() if ln.strip().startswith("Result:")), None)


def cmd_install_ea(_args: argparse.Namespace) -> int:
    terminals = discover_mt5_terminal_dirs()
    if not terminals:
        print(
            "MetaTrader 5 wasn't found automatically. In MT5 choose File > Open Data Folder, copy\n"
            f"  {EA_SOURCE}\ninto MQL5/Experts/, then open it in MetaEditor and press F7 to compile."
        )
        return 1
    all_ok = True
    for data_dir in terminals:
        dest = data_dir / "MQL5" / "Experts" / "TradeJournal"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EA_SOURCE, dest / EA_SOURCE.name)
        print(f"Copied the EA to {dest}")
        result = _compile_ea(data_dir, dest / EA_SOURCE.name)
        if result:
            print(f"  Compile: {result}")
        ok = bool(result and result.startswith("Result: 0 errors"))
        all_ok &= ok
        if not ok:
            print("  Couldn't compile automatically: open TradeJournal/TradeJournalSync.mq5 in MetaEditor and press F7.")
    print(
        "\nNext, in MetaTrader 5:\n"
        "  1. Navigator > Expert Advisors > TradeJournal > TradeJournalSync (right-click > Refresh if missing).\n"
        "  2. Drag it onto any one chart and click OK. It only reads history; it never trades,\n"
        "     so Algo Trading can stay off.\n"
        "  3. Leave that chart open. New trades reach the journal within seconds.\n"
        "If the EA was already on a chart, restart MT5 (or remove it and drag it on again)\n"
        "so MT5 loads the newly compiled version.\n"
        f"\nThe EA writes to: {discover_mt5_dir()}"
    )
    return 0 if all_ok else 1


def _mcp_command() -> list[str]:
    return [shutil.which("uv") or "uv", "--directory", str(PROJECT_ROOT), "run", "tj", "mcp"]


def cmd_mcp_config(args: argparse.Namespace) -> int:
    cmd = _mcp_command()
    entry = {"command": cmd[0], "args": cmd[1:]}
    print("Claude Code:\n  claude mcp add --scope user trading-journal -- " + shlex.join(cmd))
    print(f"\nClaude Desktop ({CLAUDE_DESKTOP_CONFIG}):")
    print(json.dumps({"mcpServers": {"trading-journal": entry}}, indent=2))
    if args.write_desktop:
        config = json.loads(CLAUDE_DESKTOP_CONFIG.read_text()) if CLAUDE_DESKTOP_CONFIG.is_file() else {}
        if CLAUDE_DESKTOP_CONFIG.is_file():
            shutil.copy2(CLAUDE_DESKTOP_CONFIG, CLAUDE_DESKTOP_CONFIG.with_suffix(".json.bak"))
        config.setdefault("mcpServers", {})["trading-journal"] = entry
        CLAUDE_DESKTOP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CLAUDE_DESKTOP_CONFIG.write_text(json.dumps(config, indent=2))
        print("\nAdded to Claude Desktop (backup saved as .json.bak). Restart Claude Desktop to load it.")
    return 0


def service_plist() -> dict:
    """launchd agent that runs `tj serve` at login and restarts it if it crashes."""
    log_dir = PROJECT_ROOT / "data" / "logs"
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    return {
        "Label": SERVICE_LABEL,
        "ProgramArguments": [uv, "--directory", str(PROJECT_ROOT), "run", "tj", "serve"],
        "WorkingDirectory": str(PROJECT_ROOT),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": str(log_dir / "serve.log"),
        "StandardErrorPath": str(log_dir / "serve.log"),
        "EnvironmentVariables": {"PATH": f"{Path(uv).parent}:/usr/bin:/bin:/usr/sbin:/sbin"},
    }


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=False)


def cmd_install_service(_args: argparse.Namespace) -> int:
    if not IS_MAC:
        uv = shutil.which("uv") or "uv"
        serve = f'"{uv}" --directory "{PROJECT_ROOT}" run tj serve'
        if IS_WINDOWS:
            print("Automatic start uses launchd on macOS. On Windows, create a logon task instead:\n"
                  f'  schtasks /Create /SC ONLOGON /TN "AI Trading Journal" /TR "{serve}"')  # fmt: skip
        else:
            print("Automatic start uses launchd on macOS. On Linux, add a systemd user service whose\n"
                  f"ExecStart is: {serve}")  # fmt: skip
        return 1
    import plistlib
    import time
    import urllib.request

    from tj.config import get_settings

    (PROJECT_ROOT / "data" / "logs").mkdir(parents=True, exist_ok=True)
    SERVICE_PLIST.parent.mkdir(parents=True, exist_ok=True)
    with SERVICE_PLIST.open("wb") as fh:
        plistlib.dump(service_plist(), fh)
    domain = f"gui/{os.getuid()}"
    # Replace any older copy. bootout returns before the job has fully exited, and
    # bootstrapping too early fails with "5: Input/output error", so wait and retry.
    _launchctl("bootout", f"{domain}/{SERVICE_LABEL}")
    for _ in range(20):
        if _launchctl("print", f"{domain}/{SERVICE_LABEL}").returncode != 0:
            break
        time.sleep(0.5)
    for _ in range(5):
        result = _launchctl("bootstrap", domain, str(SERVICE_PLIST))
        if result.returncode == 0:
            break
        time.sleep(1)
    if result.returncode != 0:
        print(f"launchctl bootstrap failed: {result.stderr.strip()}")
        return 1

    settings = get_settings()
    url = f"http://{settings.host}:{settings.port}"
    for _ in range(30):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"{url}/api/status", timeout=2)
            print(f"The journal now starts when you log in: {url}")
            print(f"Logs: {PROJECT_ROOT / 'data' / 'logs' / 'serve.log'}   Remove with: uv run tj uninstall-service")
            return 0
        except OSError:
            continue
    print(f"Installed, but {url} isn't answering yet. Is something else using port {settings.port}? "
          f"See {PROJECT_ROOT / 'data' / 'logs' / 'serve.log'}")  # fmt: skip
    return 1


def cmd_uninstall_service(_args: argparse.Namespace) -> int:
    if not IS_MAC:
        print("Nothing to remove: install-service only manages a macOS launch agent.")
        return 0
    _launchctl("bootout", f"gui/{os.getuid()}/{SERVICE_LABEL}")
    SERVICE_PLIST.unlink(missing_ok=True)
    print("The journal no longer starts at login (and has been stopped).")
    return 0


def cmd_db_revision(args: argparse.Namespace) -> int:
    from alembic import command
    from alembic.config import Config

    from tj.db import MIGRATIONS_DIR

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    command.revision(cfg, message=args.message, autogenerate=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tj", description="AI trading journal")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="Run the web app (and MT5 watcher)")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--demo", action="store_true", help="Use the demo journal")
    p.add_argument("--no-watch", action="store_true", help="Don't watch the MT5 folder")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("mcp", help="Run the MCP server on stdio (for Claude)")
    p.add_argument("--demo", action="store_true")
    p.set_defaults(func=cmd_mcp)

    p = sub.add_parser("sync", help="Import new trades from MT5 now")
    p.add_argument("--force", action="store_true", help="Re-read everything and rebuild all trades")
    p.add_argument("--demo", action="store_true")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("install-ea", help="Copy and compile the MT5 Expert Advisor")
    p.set_defaults(func=cmd_install_ea)

    p = sub.add_parser("mcp-config", help="Show how to connect Claude to the journal")
    p.add_argument("--write-desktop", action="store_true", help="Add the server to Claude Desktop's config")
    p.set_defaults(func=cmd_mcp_config)

    p = sub.add_parser("install-service", help="Start the web app automatically at login (launchd)")
    p.set_defaults(func=cmd_install_service)

    p = sub.add_parser("uninstall-service", help="Stop starting the web app at login")
    p.set_defaults(func=cmd_uninstall_service)

    p = sub.add_parser("seed-demo", help="Create a demo journal with realistic sample trades")
    p.add_argument("--days", type=int, default=90)
    p.set_defaults(func=cmd_seed_demo)

    p = sub.add_parser("db-revision", help="Autogenerate a schema migration")
    p.add_argument("message")
    p.set_defaults(func=cmd_db_revision)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
