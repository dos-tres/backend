from alembic import context

from app import models  # noqa: F401
from app.core.config import Settings
from app.core.database import Base, build_engine

target_metadata = Base.metadata
database_url = Settings().database_url.get_secret_value()

if context.is_offline_mode():
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = build_engine(database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
