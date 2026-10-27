"""Alembic environment. `tj.db.init_db()` passes the connection in; run
`uv run tj db-revision "message"` to autogenerate a new migration."""

from alembic import context

from tj.db import get_engine
from tj.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with get_engine().connect() as conn:
        _run(conn)


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
