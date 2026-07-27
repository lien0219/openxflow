"""Service dependency functions for lfx package."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, cast

from fastapi import HTTPException

from lfx.log.logger import logger
from lfx.services.config_discovery import resolve_config_dir
from lfx.services.schema import ServiceType
from lfx.services.sqlite_runtime import ensure_sqlite_process_safety, install_sqlite_session_guard, is_sqlite_url

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from lfx.services.adapters.registry import AdapterRegistry
    from lfx.services.interfaces import (
        AuthServiceProtocol,
        CacheServiceProtocol,
        ChatServiceProtocol,
        DatabaseServiceProtocol,
        DeploymentServiceProtocol,
        SettingsServiceProtocol,
        StorageServiceProtocol,
        TracingServiceProtocol,
        TransactionServiceProtocol,
        VariableServiceProtocol,
    )


def get_service(service_type: ServiceType, default=None):
    """Retrieves the service instance for the given service type.

    Args:
        service_type: The type of service to retrieve.
        default: The default ServiceFactory to use if the service is not found.

    Returns:
        The service instance or None if not available.
    """
    from lfx.services.manager import get_service_manager

    service_manager = get_service_manager()

    if not service_manager.are_factories_registered():
        # ! This is a workaround to ensure that the service manager is initialized
        # ! Not optimal, but it works for now

        service_manager.register_factories(service_manager.get_factories())
    if ServiceType.SETTINGS_SERVICE not in service_manager.factories:
        from lfx.services.settings.factory import SettingsServiceFactory

        service_manager.register_factory(service_factory=SettingsServiceFactory())
    try:
        return service_manager.get(service_type, default)
    except Exception:  # noqa: BLE001
        return None


def get_db_service() -> DatabaseServiceProtocol:
    """Retrieves the database service instance.

    Returns a NoopDatabaseService if no real database service is available,
    ensuring that session_scope() always has a valid database service to work with.
    """
    from lfx.services.database.service import NoopDatabaseService
    from lfx.services.schema import ServiceType

    db_service = get_service(ServiceType.DATABASE_SERVICE)
    if db_service is None:
        # Return noop database service when no real database service is available
        # This allows lfx to work in standalone mode without requiring database setup
        return NoopDatabaseService()
    return db_service


def get_storage_service() -> StorageServiceProtocol | None:
    """Retrieves the storage service instance."""
    from lfx.services.schema import ServiceType

    return get_service(ServiceType.STORAGE_SERVICE)


def get_settings_service() -> SettingsServiceProtocol | None:
    """Retrieves the settings service instance."""
    from lfx.services.schema import ServiceType

    return get_service(ServiceType.SETTINGS_SERVICE)


def get_variable_service() -> VariableServiceProtocol | None:
    """Retrieves the variable service instance."""
    from lfx.services.schema import ServiceType

    return get_service(ServiceType.VARIABLE_SERVICE)


def get_shared_component_cache_service() -> CacheServiceProtocol | None:
    from lfx.services.shared_component_cache.factory import SharedComponentCacheServiceFactory

    return get_service(ServiceType.SHARED_COMPONENT_CACHE_SERVICE, SharedComponentCacheServiceFactory())


def get_extension_events_service():
    """Retrieves the ExtensionEventsService instance.

    Returns None if the service manager is not initialised (e.g. in unit-test
    environments that don't boot the full service stack). Callers must guard
    against None and fall back to structured logging.
    """
    from lfx.services.extension_events.factory import ExtensionEventsServiceFactory

    return get_service(ServiceType.EXTENSION_EVENTS_SERVICE, ExtensionEventsServiceFactory())


def get_chat_service() -> ChatServiceProtocol | None:
    """Retrieves the ChatService instance."""
    from lfx.services.schema import ServiceType

    return get_service(ServiceType.CHAT_SERVICE)


def get_tracing_service() -> TracingServiceProtocol | None:
    """Retrieves the TracingService instance."""
    from lfx.services.schema import ServiceType

    return get_service(ServiceType.TRACING_SERVICE)


def get_transaction_service() -> TransactionServiceProtocol | None:
    """Retrieves the transaction service for component execution logs."""
    from lfx.services.schema import ServiceType

    return get_service(ServiceType.TRANSACTION_SERVICE)


def get_auth_service() -> AuthServiceProtocol | None:
    """Retrieves the pluggable authentication service."""
    from lfx.services.schema import ServiceType

    return get_service(ServiceType.AUTH_SERVICE)


def _get_deployment_registry() -> AdapterRegistry[DeploymentServiceProtocol]:
    """Retrieve the deployment adapter registry singleton."""
    from lfx.services.adapters.registry import get_adapter_registry
    from lfx.services.adapters.schema import AdapterType

    return cast(
        "AdapterRegistry[DeploymentServiceProtocol]",
        get_adapter_registry(adapter_type=AdapterType.DEPLOYMENT),
    )


_deployment_discovery_lock = threading.Lock()


def get_deployment_adapter(
    adapter_key: str,
) -> DeploymentServiceProtocol | None:
    """Resolve a singleton deployment adapter instance by key."""
    registry = _get_deployment_registry()
    if not registry.is_discovered:
        with _deployment_discovery_lock:
            if not registry.is_discovered:
                registry.discover(config_dir=_resolve_adapter_config_dir())
    instance = registry.get_instance(adapter_key, factory=lambda adapter_class: adapter_class())
    if instance is None:
        logger.warning(
            f"No deployment adapter found for key='{adapter_key}'. "
            f"Available keys: {registry.list_keys()}. "
            f"Check your lfx.toml or adapter registration."
        )
    return instance


def _resolve_adapter_config_dir() -> Path:
    """Resolve config directory for adapter discovery."""
    return resolve_config_dir(None, settings_service=get_settings_service())


async def get_session():
    msg = "get_session is deprecated, use session_scope instead"
    logger.warning(msg)
    raise NotImplementedError(msg)


async def injectable_session_scope():
    async with session_scope() as session:
        yield session


async def _rollback_session(session: AsyncSession) -> None:
    """Reset a failed transaction without masking the original application error."""
    from sqlalchemy.exc import InvalidRequestError

    with suppress(InvalidRequestError):
        await session.rollback()


def _database_runtime_values(db_service: DatabaseServiceProtocol) -> tuple[str, int, float]:
    database_url = str(getattr(db_service, "database_url", "") or "")
    settings_service = getattr(db_service, "settings_service", None)
    settings = getattr(settings_service, "settings", None)
    workers = int(getattr(settings, "workers", 1) or 1)
    connect_timeout = float(getattr(settings, "db_connect_timeout", 30) or 30)
    return database_url, workers, min(10.0, max(1.0, connect_timeout))


def _configure_sqlite_session(
    db_service: DatabaseServiceProtocol,
    session: AsyncSession,
    *,
    writable: bool,
) -> None:
    database_url, workers, write_wait_seconds = _database_runtime_values(db_service)
    if not is_sqlite_url(database_url):
        return
    ensure_sqlite_process_safety(database_url, workers)
    if writable:
        install_sqlite_session_guard(
            session,
            database_url=database_url,
            workers=workers,
            write_wait_seconds=write_wait_seconds,
        )


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Manage an async write session with commit, rollback, and SQLite coordination."""
    db_service = get_db_service()
    async with db_service._with_session() as session:  # noqa: SLF001
        _configure_sqlite_session(db_service, session, writable=True)
        try:
            yield session
            await session.commit()
        except HTTPException:
            await _rollback_session(session)
            raise
        except Exception as e:
            await logger.aexception("An error occurred during the session scope.", exception=e)
            await _rollback_session(session)
            raise


async def injectable_session_scope_readonly():
    async with session_scope_readonly() as session:
        yield session


@asynccontextmanager
async def session_scope_readonly() -> AsyncGenerator[AsyncSession, None]:
    """Manage a read-only session without commit while preserving concurrent SQLite reads."""
    db_service = get_db_service()
    async with db_service._with_session() as session:  # noqa: SLF001
        _configure_sqlite_session(db_service, session, writable=False)
        yield session
