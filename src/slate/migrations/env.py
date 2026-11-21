"""Alembic environment.

The app runs migrations itself at startup (``slate.db.run_migrations``), passing
its connection in ``config.attributes``. The ``alembic`` CLI also works for
authoring: it builds a sync engine from DATABASE_URL.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from slate.models import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:  # noqa: ANN001
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite cannot ALTER most things in place
        compare_type=True,
    )


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    from slate.config import Settings

    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    url = Settings().database_url.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")
    config.set_main_option("sqlalchemy.url", url)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as conn:
        _configure(conn)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
