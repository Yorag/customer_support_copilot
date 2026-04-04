from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from src.config import get_settings


class CheckpointConfigurationError(RuntimeError):
    """Raised when the configured LangGraph checkpointer cannot be created."""


class CheckpointNamespaceAdapter:
    """Preserve checkpoint_ns across LangGraph saver operations."""

    def __init__(self, saver: Any) -> None:
        self._saver = saver

    def get(self, config: dict[str, Any]) -> Any:
        return self._saver.get(self._normalize_config(config))

    def get_tuple(self, config: dict[str, Any]) -> Any:
        checkpoint = self._saver.get_tuple(self._normalize_config(config))
        return self._restore_tuple_namespace(checkpoint, config)

    def list(self, config: dict[str, Any] | None, **kwargs: Any):
        normalized_config = self._normalize_config(config) if config is not None else None
        for item in self._saver.list(normalized_config, **kwargs):
            yield self._restore_tuple_namespace(item, normalized_config)

    def put(self, config: dict[str, Any], checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        normalized_config = self._normalize_config(config)
        stored = self._saver.put(normalized_config, checkpoint, metadata, new_versions)
        return self._restore_config_namespace(stored, config)

    def put_writes(
        self,
        config: dict[str, Any],
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._saver.put_writes(
            self._normalize_config(config),
            writes,
            task_id,
            task_path,
        )

    async def aget(self, config: dict[str, Any]) -> Any:
        return await self._saver.aget(self._normalize_config(config))

    async def aget_tuple(self, config: dict[str, Any]) -> Any:
        checkpoint = await self._saver.aget_tuple(self._normalize_config(config))
        return self._restore_tuple_namespace(checkpoint, config)

    async def alist(self, config: dict[str, Any] | None, **kwargs: Any):
        normalized_config = self._normalize_config(config) if config is not None else None
        async for item in self._saver.alist(normalized_config, **kwargs):
            yield self._restore_tuple_namespace(item, normalized_config)

    async def aput(self, config: dict[str, Any], checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        normalized_config = self._normalize_config(config)
        stored = await self._saver.aput(normalized_config, checkpoint, metadata, new_versions)
        return self._restore_config_namespace(stored, config)

    async def aput_writes(
        self,
        config: dict[str, Any],
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        await self._saver.aput_writes(
            self._normalize_config(config),
            writes,
            task_id,
            task_path,
        )

    def delete_thread(self, thread_id: str) -> None:
        self._saver.delete_thread(thread_id)

    async def adelete_thread(self, thread_id: str) -> None:
        await self._saver.adelete_thread(thread_id)

    def get_next_version(self, current: Any, channel: Any) -> Any:
        return self._saver.get_next_version(current, channel)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._saver, name)

    def _normalize_config(self, config: dict[str, Any] | None) -> dict[str, Any] | None:
        if config is None:
            return None
        normalized = dict(config)
        configurable = dict(normalized.get("configurable") or {})
        metadata = dict(normalized.get("metadata") or {})
        checkpoint_ns = configurable.get("checkpoint_ns") or metadata.get("checkpoint_ns") or ""
        configurable["checkpoint_ns"] = checkpoint_ns
        metadata.setdefault("checkpoint_ns", checkpoint_ns)
        normalized["configurable"] = configurable
        normalized["metadata"] = metadata
        return normalized

    def _restore_config_namespace(
        self,
        config: dict[str, Any] | None,
        source: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if config is None:
            return None
        restored = dict(config)
        configurable = dict(restored.get("configurable") or {})
        metadata = dict(restored.get("metadata") or {})
        source_configurable = dict((source or {}).get("configurable") or {})
        source_metadata = dict((source or {}).get("metadata") or {})
        checkpoint_ns = (
            source_configurable.get("checkpoint_ns")
            or source_metadata.get("checkpoint_ns")
            or configurable.get("checkpoint_ns")
            or metadata.get("checkpoint_ns")
            or ""
        )
        configurable["checkpoint_ns"] = checkpoint_ns
        metadata.setdefault("checkpoint_ns", checkpoint_ns)
        restored["configurable"] = configurable
        restored["metadata"] = metadata
        return restored

    def _restore_tuple_namespace(self, checkpoint_tuple: Any, source: dict[str, Any] | None) -> Any:
        if checkpoint_tuple is None:
            return None
        return checkpoint_tuple._replace(
            config=self._restore_config_namespace(checkpoint_tuple.config, source),
            parent_config=self._restore_config_namespace(
                checkpoint_tuple.parent_config,
                source,
            ),
        )


@dataclass(frozen=True)
class CheckpointIdentity:
    thread_id: str
    checkpoint_ns: str


class ManagedCheckpointer(AbstractContextManager):
    def __init__(self, factory_cm) -> None:
        self._factory_cm = factory_cm
        self._manager = None
        self._checkpointer = None

    def get(self) -> Any:
        if self._checkpointer is None:
            self._manager = self._factory_cm
            self._checkpointer = CheckpointNamespaceAdapter(self._manager.__enter__())
        return self._checkpointer

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._manager is not None:
            self._manager.__exit__(exc_type, exc, tb)
        self._manager = None
        self._checkpointer = None


def build_checkpoint_identity(*, ticket_id: str, run_id: str) -> CheckpointIdentity:
    normalized_ticket_id = ticket_id.strip()
    normalized_run_id = run_id.strip()
    if not normalized_ticket_id:
        raise ValueError("ticket_id must not be blank.")
    if not normalized_run_id:
        raise ValueError("run_id must not be blank.")
    return CheckpointIdentity(
        thread_id=normalized_ticket_id,
        checkpoint_ns=normalized_run_id,
    )


def build_checkpoint_config(*, ticket_id: str, run_id: str) -> dict[str, Any]:
    identity = build_checkpoint_identity(ticket_id=ticket_id, run_id=run_id)
    settings = get_settings()
    return {
        "recursion_limit": settings.app.graph_recursion_limit,
        "configurable": {
            "thread_id": identity.thread_id,
            "checkpoint_ns": identity.checkpoint_ns,
        },
    }


def build_default_checkpointer() -> ManagedCheckpointer:
    settings = get_settings()
    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
    except ModuleNotFoundError as exc:
        raise CheckpointConfigurationError(
            "Postgres checkpointing requires the `langgraph-checkpoint-postgres` package."
        ) from exc

    try:
        saver_cm = PostgresSaver.from_conn_string(settings.database.dsn)

        class _PostgresManagedCheckpointer(ManagedCheckpointer):
            def __init__(self, factory_cm) -> None:
                super().__init__(factory_cm)
                self._is_setup_complete = False

            def get(self) -> Any:
                checkpointer = super().get()
                setup = getattr(checkpointer, "setup", None)
                if not self._is_setup_complete and callable(setup):
                    setup()
                    self._is_setup_complete = True
                return checkpointer

        return _PostgresManagedCheckpointer(saver_cm)
    except Exception as exc:  # pragma: no cover
        raise CheckpointConfigurationError(
            "Failed to create the Postgres-backed LangGraph checkpointer."
        ) from exc


def build_test_checkpointer() -> Any:
    return CheckpointNamespaceAdapter(InMemorySaver())


__all__ = [
    "CheckpointConfigurationError",
    "CheckpointIdentity",
    "CheckpointNamespaceAdapter",
    "ManagedCheckpointer",
    "build_checkpoint_config",
    "build_checkpoint_identity",
    "build_default_checkpointer",
    "build_test_checkpointer",
]
