import pytest

from tj import config, db


@pytest.fixture
def journal(tmp_path, monkeypatch):
    """A fresh journal database and MT5 export folder for one test."""
    data_dir = tmp_path / "data"
    export_dir = tmp_path / "TradeJournal"
    export_dir.mkdir()
    monkeypatch.setenv("TJ_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TJ_MT5_DIR", str(export_dir))
    config.get_settings.cache_clear()
    engine = db.make_engine(config.get_settings().db_path)
    db.set_engine(engine)
    db.init_db()
    yield export_dir
    engine.dispose()
    config.get_settings.cache_clear()
