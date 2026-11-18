from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


class Database:
    def __init__(self, url: str):
        self.engine = create_engine(
            url, pool_pre_ping=True, pool_timeout=3, hide_parameters=True,
            connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        )
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def dispose(self) -> None:
        self.engine.dispose()


class DatabaseNotConfigured(Exception):
    pass


def get_db(request: Request) -> Iterator[Session]:
    database = request.app.state.database
    if database is None:
        raise DatabaseNotConfigured
    # close() returns the connection and rolls back any uncommitted transaction.
    # A feature's service must explicitly commit its own successful transaction.
    with database.sessions() as session:
        yield session
