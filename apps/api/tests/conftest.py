from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from mla_api.db import Base
from mla_api.mailer import MemoryMailer
from mla_api.main import create_app
from mla_api.settings import Settings

PASSWORD = "senha-forte-123"


def make_settings(tmp_path, **overrides) -> Settings:
    values = dict(environment="test", database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
                  storage_dir=tmp_path / "storage", cookie_secure=False, public_url="http://web.test")
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def app(tmp_path):
    app = create_app(make_settings(tmp_path), mailer=MemoryMailer())
    Base.metadata.create_all(app.state.engine)
    yield app
    app.state.engine.dispose()


class Api:
    """One browser: own cookie jar, CSRF header always sent."""

    def __init__(self, app):
        self.client = TestClient(app, headers={"X-MLA-Client": "web"})

    def __getattr__(self, name):
        return getattr(self.client, name)

    def register(self, email: str, org: str = "Empresa", name: str = "Pessoa") -> dict:
        r = self.client.post("/api/auth/register", json={"name": name, "email": email, "password": PASSWORD,
                                                         "organization_name": org})
        assert r.status_code == 201, r.text
        return r.json()

    def org_id(self) -> str:
        return self.client.get("/api/auth/me").json()["memberships"][0]["organization"]["id"]

    def add_product(self, org_id: str, sku: str, **fields) -> dict:
        body = {"sku": sku, "name": f"Produto {sku}", **fields}
        r = self.client.post(f"/api/orgs/{org_id}/products", json=body)
        assert r.status_code == 201, r.text
        return r.json()


@pytest.fixture
def new_api(app):
    def factory() -> Api:
        return Api(app)
    return factory


@pytest.fixture
def api(new_api) -> Api:
    return new_api()


@pytest.fixture
def pg_url():
    url = os.environ.get("MLA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("MLA_TEST_DATABASE_URL não definido (PostgreSQL necessário para testar RLS)")
    return url


def random_uuid() -> str:
    return str(uuid.uuid4())
