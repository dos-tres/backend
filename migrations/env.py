from alembic import context
from sqlalchemy import create_engine, pool

from app.config import Settings
from app.database import Base

# Import model modules here so autogenerate sees their metadata.
import app.catalog.models  # noqa: E402,F401
target_metadata = Base.metadata
url = Settings().database_url.get_secret_value()
if not url:
    raise RuntimeError("DATABASE_URL must be configured for migrations")

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
