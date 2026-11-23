import os
import tempfile

import pytest

# Base de datos SQLite temporal y sin LLM: se configura antes de importar la app
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmpdir, 'test.db')}"
os.environ["GROQ_API_KEY"] = ""
os.environ["LIDER_LIVE_REFRESH"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """Registra un usuario nuevo y devuelve el header Authorization."""
    import uuid
    email = f"qa_{uuid.uuid4().hex[:8]}@nutricart.cl"
    client.post("/api/auth/register", json={"full_name": "QA", "email": email, "password": "clave1234"})
    token = client.post("/api/auth/login", json={"email": email, "password": "clave1234"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
