from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from src.db.repositories import RepositoryBundle, build_repository_bundle
from src.db.session import (
    create_session_factory,
    get_engine,
    ping_database,
    session_scope,
)
from src.contracts.protocols import TicketStoreProtocol


class SqlAlchemyTicketStore(TicketStoreProtocol):
    def __init__(
        self,
        *,
        engine=None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = create_session_factory(self.engine)
        return self._session_factory

    def ping(self) -> bool:
        return ping_database(self.engine)

    def session_scope(self):
        return session_scope(self.session_factory)

    def repositories(self, session: Session) -> RepositoryBundle:
        return build_repository_bundle(session)
