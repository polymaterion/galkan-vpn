"""
Shared test fixtures.
Uses SQLite in-memory for speed.
"""
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Override DB to SQLite before any imports that touch DATABASE_URL
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("BILLING_SECRET_KEY", "test-secret")
os.environ.setdefault("TELEGRAM_TOKEN", "0:test_token")
os.environ.setdefault("CRYPTOPAY_TOKEN", "")
os.environ.setdefault("ADMIN_IDS", "12345")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from models import Base
import models.models  # noqa: F401 - register all tables


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture(scope="function")
async def session(engine):
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        yield s


@pytest.fixture
def mock_amnezia_client():
    """Mock AmneziaClient so tests don't make real HTTP calls."""
    with patch("billing.services.billing_service.AmneziaClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value = instance

        # Default happy-path responses
        from integrations.amnezia.schemas import CreateClientResponse, CreatedClient
        instance.create_client.return_value = CreateClientResponse(
            message="Клиент создан",
            client=CreatedClient(
                id="test-uuid-1234",
                config="vpn://eyJ0ZXN0IjoiY29uZmlnIn0=",
                protocol="amneziawg",
            ),
        )
        instance.enable_client.return_value = None
        instance.disable_client.return_value = None
        instance.delete_client.return_value = None
        instance.healthcheck.return_value = True

        yield instance
