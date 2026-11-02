"""OpenAI image provider, setup switches and budget. Every call goes to a FAKE transport: no network, no cost."""
from __future__ import annotations

import base64
import json

import pytest
from conftest import make_settings
from helpers import make_png

from mla_api.services import openai_images
from mla_api.services.image_ai import PRESERVE_PRODUCT, ImageEditError, provider_from_settings
from mla_api.services.openai_images import OpenAIImageProvider, cost_usd

KEY = "sk-test-not-a-real-key-000"
USAGE = {"input_tokens": 1500, "output_tokens": 1000,
         "input_tokens_details": {"text_tokens": 500, "image_tokens": 1000}}


class FakeTransport:
    def __init__(self, png: bytes, status: int = 200, usage: dict | None = USAGE, error: dict | None = None):
        self.png, self.status, self.usage, self.error, self.calls = png, status, usage, error, []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, body))
        if self.status != 200:
            return self.status, json.dumps({"error": self.error or {"message": "falhou"}}).encode()
        payload = {"data": [{"b64_json": base64.b64encode(self.png).decode()}]}
        if self.usage is not None:
            payload["usage"] = self.usage
        return 200, json.dumps(payload).encode()


@pytest.fixture
def pngs(tmp_path):
    return (make_png(tmp_path / "o.png", 30, 30).read_bytes(),
            make_png(tmp_path / "e.png", 20, 20, (255, 255, 255)).read_bytes())


def test_setup_needs_key_and_explicit_enable(tmp_path):
    assert provider_from_settings(make_settings(tmp_path)).provider is None
    no_key = provider_from_settings(make_settings(tmp_path, image_ai_provider="openai"))
    assert no_key.provider is None and "MLA_OPENAI_API_KEY" in no_key.message
    disabled = provider_from_settings(make_settings(tmp_path, image_ai_provider="openai", openai_api_key=KEY))
    assert disabled.provider is None and "MLA_IMAGE_AI_ENABLED" in disabled.message
    ready = provider_from_settings(make_settings(tmp_path, image_ai_provider="openai", openai_api_key=KEY,
                                                 image_ai_enabled=True))
    assert ready.message is None and ready.provider.model == "gpt-image-2" and ready.provider.paid
    with pytest.raises(ImageEditError, match="desconhecido"):
        provider_from_settings(make_settings(tmp_path, image_ai_provider="outro"))
    with pytest.raises(ImageEditError, match="sem preço"):
        OpenAIImageProvider(KEY, model="modelo-inventado")


def test_cost_from_usage():
    # 500 text x $5 + 1000 image x $8 + 1000 output x $30, per 1M tokens (developers.openai.com/api/docs/pricing)
    assert cost_usd("gpt-image-2", USAGE) == pytest.approx(0.0405)
    assert cost_usd("gpt-image-2", {"input_tokens": 1000, "output_tokens": 0}) == pytest.approx(0.008)  # no breakdown
    assert cost_usd("gpt-image-2", {}) is None


def test_request_shape(pngs):
    original, edited = pngs
    t = FakeTransport(edited)
    r = OpenAIImageProvider(KEY, transport=t).edit(original, "image/png", "Fundo branco", safety_id="abc")
    assert r.data == edited and r.cost_usd == pytest.approx(0.0405) and r.model == "gpt-image-2"
    url, headers, body = t.calls[0]
    assert url == "https://api.openai.com/v1/images/edits" and headers["Authorization"] == f"Bearer {KEY}"
    for field in (b'name="model"\r\n\r\ngpt-image-2', b'name="quality"\r\n\r\nmedium',
                  b'name="output_format"\r\n\r\npng', b'name="safety_identifier"\r\n\r\nabc',
                  (PRESERVE_PRODUCT + "Fundo branco").encode()):
        assert field in body
    assert b"input_fidelity" not in body and b'name="n"' not in body  # gpt-image-2: omit; one image per call
    assert original in body


@pytest.mark.parametrize("status_,charged", [(401, 0.0), (429, 0.0), (400, None), (500, None)])
def test_errors_report_what_may_have_been_charged(pngs, status_, charged):
    t = FakeTransport(pngs[1], status=status_, error={"message": "recusado", "code": "x"})
    with pytest.raises(ImageEditError) as exc:
        OpenAIImageProvider(KEY, transport=t).edit(pngs[0], "image/png", "Fundo branco")
    assert exc.value.charged_usd == charged and "recusado" in str(exc.value)


@pytest.fixture
def studio(api, app, pngs):
    """The app with the real OpenAI provider class wired to a fake transport and a small budget."""
    original, edited = pngs
    t = FakeTransport(edited)
    app.state.image_ai = OpenAIImageProvider(KEY, transport=t)
    app.state.image_ai_message = None
    app.state.settings = app.state.settings.model_copy(update={"image_ai_provider": "openai",
                                                               "image_ai_budget_usd": 0.55, "image_ai_reserve_usd": 0.25})
    api.register("estudio@example.com", org="Estudio")
    o = f"/api/orgs/{api.org_id()}"
    p = api.post(f"{o}/products", json={"sku": "EST-1", "name": "Vaso"}).json()
    up = api.post(f"{o}/products/{p['id']}/images/upload", files={"file": ("o.png", original, "image/png")}).json()
    return api, app, t, o, p, up, original


def test_edit_records_cost_and_budget_blocks(studio):
    api, app, t, o, p, up, original = studio
    url = f"{o}/products/{p['id']}/images/{up['id']}/ai-edit"
    st = api.get(f"{o}/images/ai/status").json()
    assert st["configured"] and st["model"] == "gpt-image-2" and st["budget"]["remaining_usd"] == 0.55
    assert KEY not in json.dumps(st)  # the key never leaves the server
    v = api.post(url, json={"prompt": "Fundo branco", "consent": True}).json()
    assert v["status"] == "pending" and v["cost_usd"] == pytest.approx(0.0405)
    # A second edit of the AI version is made from the ORIGINAL photo.
    api.post(f"{o}/products/{p['id']}/images/{v['id']}/ai-edit", json={"prompt": "Mais luz", "consent": True})
    assert original in t.calls[1][2]
    st = api.get(f"{o}/images/ai/status").json()["budget"]
    assert st["spent_usd"] == pytest.approx(0.081) and st["reserved_usd"] == 0 and st["calls"] == 2
    # Unknown cost keeps the whole reservation: 0.081 + 0.25 = 0.331 spent ...
    t.usage = None
    api.post(url, json={"prompt": "Fundo cinza", "consent": True})
    # ... and the next one (0.331 + 0.25 > 0.55) is refused before any call.
    calls = len(t.calls)
    r = api.post(url, json={"prompt": "Fundo azul", "consent": True})
    assert r.status_code == 409 and "Limite interno" in r.json()["detail"] and len(t.calls) == calls
    assert api.get(f"{o}/images/ai/status").json()["blocked"] is True
    assert api.get(f"{o}/products/{p['id']}/images/{up['id']}/file").content == original


def test_failed_call_is_audited_and_settled(studio):
    api, app, t, o, p, up, _ = studio
    t.status = 401
    r = api.post(f"{o}/products/{p['id']}/images/{up['id']}/ai-edit", json={"prompt": "Fundo branco", "consent": True})
    assert r.status_code == 502
    st = api.get(f"{o}/images/ai/status").json()["budget"]
    assert st["spent_usd"] == 0 and st["reserved_usd"] == 0
    assert "image.ai_failed" in [e["action"] for e in api.get(f"{o}/audit").json()]


def test_disabled_installation_makes_no_call(api, app, pngs, monkeypatch):
    called = []
    monkeypatch.setattr(openai_images, "_urllib_transport", lambda *a: called.append(a))
    api.register("off@example.com", org="Off")
    o = f"/api/orgs/{api.org_id()}"
    p = api.post(f"{o}/products", json={"sku": "OFF-1", "name": "Vaso"}).json()
    up = api.post(f"{o}/products/{p['id']}/images/upload", files={"file": ("o.png", pngs[0], "image/png")}).json()
    r = api.post(f"{o}/products/{p['id']}/images/{up['id']}/ai-edit", json={"prompt": "Fundo", "consent": True})
    assert r.status_code == 409 and called == []
