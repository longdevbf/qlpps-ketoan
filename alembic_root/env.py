"""Alembic env cho schema `shared` — chỉ migrate tables thuộc schema 'shared'.

Mỗi app (baogia/marketing/muahang) sẽ có env.py riêng filter theo schema của app đó.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from shared.config import settings
from shared.db import Base
import shared.models  # noqa: F401  — đảm bảo Base.metadata thấy tất cả models


config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """Chỉ migrate objects thuộc schema 'shared'."""
    if type_ == "table":
        return obj.schema == "shared"
    if type_ in ("index", "unique_constraint", "foreign_key_constraint"):
        return obj.table.schema == "shared"
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
        version_table_schema="shared",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
            version_table_schema="shared",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
