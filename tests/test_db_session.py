from __future__ import annotations

from sqlalchemy import select

from src.db.base import Base
from src.db.models import AppMetadata
from src.db.session import build_engine, create_session_factory, ping_database, session_scope
from src.tools.ticket_store import SqlAlchemyTicketStore


def test_ticket_store_and_session_scope_work_with_sqlite():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    store = SqlAlchemyTicketStore(engine=engine)
    assert store.ping() is True

    with store.session_scope() as session:
        session.add(AppMetadata(key="schema_version", value="bootstrap"))

    with session_scope(create_session_factory(engine)) as session:
        rows = session.scalars(select(AppMetadata)).all()

    assert len(rows) == 1
    assert rows[0].key == "schema_version"


def test_ping_database_succeeds_for_sqlite():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    assert ping_database(engine) is True
