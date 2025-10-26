# alembic/env.py
import sys
import os

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context


# Add project root to Python path so `database` package can be found
sys.path.append(os.path.dirname(os.path.dirname(__file__)))


# Import your Base and database URL
from database.db_session import Base, SQLALCHEMY_DATABASE_URL

# Import all models so Alembic can detect tables
import database.models  # noqa: F401

# Alembic Config object
config = context.config
config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)

# Set up logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for 'autogenerate'
target_metadata = Base.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
