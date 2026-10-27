import plistlib

from tj.cli import SERVICE_LABEL, service_plist
from tj.config import PROJECT_ROOT


def test_service_plist_runs_serve_from_the_project():
    p = service_plist()
    assert p["Label"] == SERVICE_LABEL
    assert p["ProgramArguments"][1:] == ["--directory", str(PROJECT_ROOT), "run", "tj", "serve"]
    assert p["RunAtLoad"] is True and p["KeepAlive"] == {"SuccessfulExit": False}
    assert p["StandardOutPath"].endswith("data/logs/serve.log")
    plistlib.dumps(p)  # serialisable as a launchd plist


def test_non_portable_mt5_layout_is_discovered(tmp_path, monkeypatch):
    """AppData-style data folder whose origin.txt points at the install folder (Linux/Wine layout)."""
    from tj import config
    from tj.cli import _metaeditor, _to_windows_path

    prefix = tmp_path / "wine"
    install = prefix / "drive_c" / "Program Files" / "MetaTrader 5"
    install.mkdir(parents=True)
    (install / "MetaEditor64.exe").write_bytes(b"")
    (install / "terminal64.exe").write_bytes(b"")  # no MQL5/ here: not portable
    data = prefix / "drive_c/users/me/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37"
    (data / "MQL5").mkdir(parents=True)
    (data / "origin.txt").write_bytes("C:\\Program Files\\MetaTrader 5".encode("utf-16"))
    common = prefix / "drive_c/users/me/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
    common.mkdir(parents=True)
    monkeypatch.setattr(config, "wine_prefixes", lambda: [prefix])
    monkeypatch.setattr(config, "_appdata", lambda: None)

    assert config.discover_mt5_terminal_dirs() == [data]
    assert _metaeditor(data) == (install / "MetaEditor64.exe", False)
    assert _to_windows_path(data / "MQL5" / "x.mq5", prefix) == (
        "C:\\users\\me\\AppData\\Roaming\\MetaQuotes\\Terminal\\D0E8209F77C8CF37\\MQL5\\x.mq5"
    )
    monkeypatch.setattr(config, "get_settings", lambda: type("S", (), {"mt5_dir": None})())
    assert config.discover_mt5_dir() == common / "TradeJournal"
