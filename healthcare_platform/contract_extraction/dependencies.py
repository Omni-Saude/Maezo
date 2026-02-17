"""FastAPI dependency injection helpers for the Contract Rule Extraction API."""
import os
from typing import Generator, Optional

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from healthcare_platform.contract_extraction.services.contract_service import ContractService

_engine = None
_SessionLocal: Optional[sessionmaker] = None


def _get_engine():
    """Lazily initialise the SQLAlchemy engine from DATABASE_URL env var."""
    global _engine, _SessionLocal
    if _engine is None:
        database_url = os.environ.get(
            "DATABASE_URL", "sqlite:///./contract_rules.db"
        )
        connect_args = (
            {"check_same_thread": False}
            if database_url.startswith("sqlite")
            else {}
        )
        _engine = create_engine(database_url, connect_args=connect_args)
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=_engine
        )
    return _engine


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session and ensure it is closed after the request."""
    _get_engine()
    assert _SessionLocal is not None
    session: Session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_contract_service(
    session: Session = Depends(get_db),
) -> ContractService:
    """Return a ContractService bound to the current request's database session."""
    return ContractService(session)
