"""
Multi-tenant database management.

Provides schema-based multi-tenancy for PostgreSQL databases,
supporting both synchronous and asynchronous operations.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from revenue_cycle.config import Settings, get_settings
from revenue_cycle.multi_tenant.context import (
    TenantContext,
    TenantInfo,
    get_current_tenant,
    require_tenant_context,
)

logger = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""

    pass


class MultiTenantDatabase:
    """
    Multi-tenant database manager.

    Provides schema-based multi-tenancy where each tenant has
    their own PostgreSQL schema within a shared database.

    Features:
    - Automatic schema switching based on tenant context
    - Connection pooling per database
    - Session management with proper cleanup
    - Schema creation and migration support

    Example:
        db = MultiTenantDatabase(settings)
        await db.initialize()

        async with TenantContext(tenant_info):
            async with db.session() as session:
                result = await session.execute(select(Claim))
                claims = result.scalars().all()
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize multi-tenant database manager.

        Args:
            settings: Application settings (uses get_settings() if not provided)
        """
        self._settings = settings or get_settings()
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the database engine and session factory.

        Should be called once at application startup.
        """
        if self._initialized:
            logger.warning("Database already initialized")
            return

        db_settings = self._settings.database

        self._engine = create_async_engine(
            db_settings.url,
            pool_size=db_settings.pool_size,
            max_overflow=db_settings.max_overflow,
            pool_timeout=db_settings.pool_timeout,
            pool_pre_ping=True,  # Verify connections before use
            echo=self._settings.debug,
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        # Register event listener for schema switching
        @event.listens_for(self._engine.sync_engine, "connect")
        def set_search_path(dbapi_connection: Any, connection_record: Any) -> None:
            """Set search_path on new connections."""
            ctx = get_current_tenant()
            if ctx:
                cursor = dbapi_connection.cursor()
                cursor.execute(f"SET search_path TO {ctx.tenant.database_schema}, public")
                cursor.close()

        self._initialized = True
        logger.info(
            "Database initialized",
            host=db_settings.host,
            port=db_settings.port,
            database=db_settings.name,
            pool_size=db_settings.pool_size,
        )

    async def close(self) -> None:
        """
        Close the database engine and all connections.

        Should be called during application shutdown.
        """
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._initialized = False
            logger.info("Database connections closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session with tenant-aware schema.

        The session automatically uses the current tenant's schema
        if running within a TenantContext.

        Yields:
            AsyncSession: SQLAlchemy async session

        Raises:
            RuntimeError: If database not initialized
        """
        if not self._session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        session = self._session_factory()
        try:
            # Set search_path for current tenant
            ctx = get_current_tenant()
            if ctx:
                await session.execute(
                    text(f"SET search_path TO {ctx.tenant.database_schema}, public")
                )
                logger.debug(
                    "Session created with tenant schema",
                    schema=ctx.tenant.database_schema,
                )

            yield session

        except Exception as e:
            await session.rollback()
            logger.error("Session error, rolled back", error=str(e))
            raise
        finally:
            await session.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session with automatic transaction management.

        Commits on successful exit, rolls back on exception.

        Yields:
            AsyncSession: SQLAlchemy async session with transaction
        """
        async with self.session() as session:
            async with session.begin():
                yield session

    async def create_tenant_schema(self, tenant: TenantInfo) -> None:
        """
        Create a schema for a new tenant.

        Args:
            tenant: Tenant information with schema name

        Note:
            This creates an empty schema. Migrations should be
            run separately to create tables.
        """
        if not self._engine:
            raise RuntimeError("Database not initialized")

        async with self._engine.begin() as conn:
            await conn.execute(
                text(f"CREATE SCHEMA IF NOT EXISTS {tenant.database_schema}")
            )
            logger.info(
                "Created tenant schema",
                tenant_id=tenant.tenant_id,
                schema=tenant.database_schema,
            )

    async def drop_tenant_schema(self, tenant: TenantInfo, cascade: bool = False) -> None:
        """
        Drop a tenant's schema.

        Args:
            tenant: Tenant information
            cascade: If True, drop all objects in the schema

        Warning:
            This is a destructive operation. Use with caution.
        """
        if not self._engine:
            raise RuntimeError("Database not initialized")

        cascade_clause = "CASCADE" if cascade else "RESTRICT"

        async with self._engine.begin() as conn:
            await conn.execute(
                text(f"DROP SCHEMA IF EXISTS {tenant.database_schema} {cascade_clause}")
            )
            logger.warning(
                "Dropped tenant schema",
                tenant_id=tenant.tenant_id,
                schema=tenant.database_schema,
                cascade=cascade,
            )

    async def schema_exists(self, schema_name: str) -> bool:
        """
        Check if a schema exists.

        Args:
            schema_name: Name of the schema to check

        Returns:
            True if schema exists, False otherwise
        """
        if not self._engine:
            raise RuntimeError("Database not initialized")

        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name = :schema"
                ),
                {"schema": schema_name},
            )
            return result.scalar() is not None

    async def list_tenant_schemas(self, prefix: str = "tenant_") -> list[str]:
        """
        List all tenant schemas.

        Args:
            prefix: Schema name prefix to filter by

        Returns:
            List of schema names
        """
        if not self._engine:
            raise RuntimeError("Database not initialized")

        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE :prefix"
                ),
                {"prefix": f"{prefix}%"},
            )
            return [row[0] for row in result.fetchall()]

    async def execute_for_all_tenants(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
        schema_prefix: str = "tenant_",
    ) -> dict[str, Any]:
        """
        Execute a query across all tenant schemas.

        Args:
            query: SQL query to execute
            params: Query parameters
            schema_prefix: Schema name prefix

        Returns:
            Dictionary mapping schema name to results
        """
        schemas = await self.list_tenant_schemas(prefix=schema_prefix)
        results: dict[str, Any] = {}

        for schema in schemas:
            async with self._engine.connect() as conn:  # type: ignore
                await conn.execute(text(f"SET search_path TO {schema}, public"))
                result = await conn.execute(text(query), params or {})
                results[schema] = result.fetchall()

        return results

    @property
    def engine(self) -> AsyncEngine:
        """Get the SQLAlchemy async engine."""
        if not self._engine:
            raise RuntimeError("Database not initialized")
        return self._engine

    @property
    def is_initialized(self) -> bool:
        """Check if database is initialized."""
        return self._initialized
