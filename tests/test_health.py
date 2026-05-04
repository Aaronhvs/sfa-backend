import pytest
from httpx import ASGITransport, AsyncClient

from sfa.main import app


@pytest.fixture()
def mock_db_ok(mocker):
    mock_session = mocker.AsyncMock()
    mock_session.execute = mocker.AsyncMock()

    async def _override():
        yield mock_session

    return _override


@pytest.fixture()
def mock_redis_ok(mocker):
    mock_client = mocker.AsyncMock()
    mock_client.ping = mocker.AsyncMock(return_value=True)

    async def _override():
        yield mock_client

    return _override


@pytest.fixture()
def mock_db_error(mocker):
    mock_session = mocker.AsyncMock()
    mock_session.execute = mocker.AsyncMock(side_effect=Exception("DB down"))

    async def _override():
        yield mock_session

    return _override


@pytest.fixture()
def mock_redis_error(mocker):
    mock_client = mocker.AsyncMock()
    mock_client.ping = mocker.AsyncMock(side_effect=Exception("Redis down"))

    async def _override():
        yield mock_client

    return _override


@pytest.mark.asyncio
async def test_health_all_connected(mock_db_ok, mock_redis_ok):
    from sfa.core.dependencies import get_db, get_redis

    app.dependency_overrides[get_db] = mock_db_ok
    app.dependency_overrides[get_redis] = mock_redis_ok

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["redis"] == "connected"
    assert "version" in body
    assert "env" in body


@pytest.mark.asyncio
async def test_health_db_error(mock_db_error, mock_redis_ok):
    from sfa.core.dependencies import get_db, get_redis

    app.dependency_overrides[get_db] = mock_db_error
    app.dependency_overrides[get_redis] = mock_redis_ok

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "error"
    assert body["redis"] == "connected"


@pytest.mark.asyncio
async def test_health_redis_error(mock_db_ok, mock_redis_error):
    from sfa.core.dependencies import get_db, get_redis

    app.dependency_overrides[get_db] = mock_db_ok
    app.dependency_overrides[get_redis] = mock_redis_error

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["redis"] == "error"
