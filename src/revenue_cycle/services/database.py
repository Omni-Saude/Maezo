"""
Database service for asynchronous database operations.

Provides a clean interface for database operations with:
- Connection pooling via SQLAlchemy
- Transaction management
- Query execution with parameter binding
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterator, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

from revenue_cycle.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class DatabaseService:
    """
    Asynchronous database service using SQLAlchemy.

    Provides methods for:
    - Query execution (fetch_one, fetch_all, execute)
    - Transaction management
    - Connection pooling

    Example:
        db = DatabaseService()
        await db.initialize()

        # Simple query
        result = await db.fetch_one(
            "SELECT * FROM glosas WHERE glosa_id = :id",
            {"id": "GL-001"}
        )

        # Transaction
        async with db.transaction():
            await db.execute("INSERT INTO ...", {...})
            await db.execute("UPDATE ...", {...})
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize database service.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self._settings = settings or get_settings()
        self._engine = None
        self._session_factory = None
        self._logger = logger.bind(service="database")

    async def initialize(self) -> None:
        """Initialize the database connection pool."""
        if self._engine is not None:
            return

        db_settings = self._settings.database

        self._engine = create_async_engine(
            db_settings.url,
            pool_size=db_settings.pool_size,
            max_overflow=db_settings.max_overflow,
            pool_timeout=db_settings.pool_timeout,
            pool_pre_ping=True,
            echo=self._settings.debug,
        )

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        self._logger.info(
            "Database connection pool initialized",
            host=db_settings.host,
            port=db_settings.port,
            database=db_settings.name,
            pool_size=db_settings.pool_size,
        )

    async def close(self) -> None:
        """Close the database connection pool."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._logger.info("Database connection pool closed")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """
        Get a database session.

        Yields:
            AsyncSession: Database session

        Raises:
            RuntimeError: If service not initialized
        """
        if self._session_factory is None:
            await self.initialize()

        async with self._session_factory() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """
        Execute operations in a transaction with automatic rollback on error.

        Yields:
            AsyncSession: Database session with active transaction

        Example:
            async with db.transaction() as session:
                await session.execute(text("INSERT INTO ..."))
                await session.execute(text("UPDATE ..."))
            # Auto-committed on success, rolled back on error
        """
        async with self.session() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                self._logger.error("Transaction rolled back", error=str(e))
                raise

    async def fetch_one(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Fetch a single row from the database.

        Args:
            query: SQL query with named parameters
            params: Query parameters

        Returns:
            Dictionary with column values, or None if not found
        """
        async with self.session() as session:
            result = await session.execute(text(query), params or {})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None

    async def fetch_all(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch all rows from a query.

        Args:
            query: SQL query with named parameters
            params: Query parameters

        Returns:
            List of dictionaries with column values
        """
        async with self.session() as session:
            result = await session.execute(text(query), params or {})
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]

    async def execute(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Execute a query (INSERT, UPDATE, DELETE).

        Args:
            query: SQL query with named parameters
            params: Query parameters

        Returns:
            Number of affected rows
        """
        async with self.session() as session:
            result = await session.execute(text(query), params or {})
            await session.commit()
            return result.rowcount

    async def execute_in_transaction(
        self,
        session: AsyncSession,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Execute a query within an existing transaction.

        Args:
            session: Active database session
            query: SQL query with named parameters
            params: Query parameters

        Returns:
            Number of affected rows
        """
        result = await session.execute(text(query), params or {})
        return result.rowcount


# Global database service instance
_db_service: Optional[DatabaseService] = None


def get_database_service(settings: Optional[Settings] = None) -> DatabaseService:
    """
    Get the global database service instance.

    Args:
        settings: Optional settings override

    Returns:
        DatabaseService instance
    """
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService(settings)
    return _db_service
