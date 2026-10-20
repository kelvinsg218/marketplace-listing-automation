import pytest

from mla.core.enums import ConnectionStatus, ItemStatus, Marketplace
from mla.core.models import MarketplaceAccount
from mla.core.sites import AccountUrlError, safe_url, site_for, validate_account_url
from mla.services.accounts import AccountError
from mla.services.context import AppContext

ML = Marketplace.MERCADO_LIVRE


# ------------------------------------------------------------------ URL validation
@pytest.mark.parametrize("raw, expected", [
    ("https://www.mercadolivre.com.br/", "https://www.mercadolivre.com.br/"),
    ("https://WWW.MercadoLivre.com.br/vendas#x", "https://www.mercadolivre.com.br/vendas"),
    ("www.mercadolivre.com.br/perfil/LOJA", "https://www.mercadolivre.com.br/perfil/LOJA"),
    ("https://mercadolivre.com.br", "https://mercadolivre.com.br/"),
    ("https://myaccount.mercadolivre.com.br/summary?x=1", "https://myaccount.mercadolivre.com.br/summary?x=1"),
])
def test_valid_mercado_livre_urls(raw, expected):
    assert validate_account_url(ML, raw) == expected


@pytest.mark.parametrize("raw, fragment", [
    ("", "Informe"),
    ("http://www.mercadolivre.com.br/", "HTTPS"),
    ("https://www.mercadolivre.com.br.golpe.com/", "precisa ser do Mercado Livre"),
    ("https://mercadolivre.com.br@golpe.com/", "usuário ou senha"),
    ("https://user:pw@www.mercadolivre.com.br/", "usuário ou senha"),
    ("https://fakemercadolivre.com.br/", "precisa ser do Mercado Livre"),
    ("https://shopee.com.br/", "precisa ser do Mercado Livre"),
    ("https://192.168.0.10/", "endereço IP"),
    ("https://www.mercadolivre.com.br:8443/", "porta"),
    ("https://www.mercadolívre.com.br/", "caracteres especiais"),
    ("javascript:alert(1)", "HTTPS"),
    ("file:///C:/Windows/", "HTTPS"),
    ("https://www.mercado livre.com.br", "espaços"),
])
def test_invalid_urls_are_rejected(raw, fragment):
    with pytest.raises(AccountUrlError, match=fragment):
        validate_account_url(ML, raw)


def test_simulated_only_accepts_bundled_pages():
    home = site_for(Marketplace.SIMULATED).home_url
    assert validate_account_url(Marketplace.SIMULATED, home) == home
    with pytest.raises(AccountUrlError):
        validate_account_url(Marketplace.SIMULATED, "file:///C:/Users/garci/Documents/x.html")
    with pytest.raises(AccountUrlError):
        validate_account_url(Marketplace.SIMULATED, "https://www.mercadolivre.com.br/")


# ------------------------------------------------------------------ account service
def _ml(**kw) -> MarketplaceAccount:
    data = {"marketplace": ML, "label": "Loja Norte", "seller_url": "https://www.mercadolivre.com.br/"}
    data.update(kw)
    return MarketplaceAccount(**data)


def test_create_edit_and_persist(paths):
    ctx = AppContext.open(paths)
    account = ctx.account_service.save(_ml(internal_id="Loja-Norte"))
    assert account.internal_id == "loja-norte"
    assert account.connection_status is ConnectionStatus.UNKNOWN
    account.label = "Loja Norte (principal)"
    account.seller_url = "https://www.mercadolivre.com.br/perfil/LOJANORTE"
    ctx.account_service.save(account)
    ctx.close()
    reopened = AppContext.open(paths)  # persisted in SQLite
    loaded = reopened.account_service.get(account.id)
    assert loaded.label == "Loja Norte (principal)"
    assert loaded.seller_url == "https://www.mercadolivre.com.br/perfil/LOJANORTE"
    assert loaded.connection_status is ConnectionStatus.UNKNOWN
    reopened.close()


def test_validation_errors(ctx):
    service = ctx.account_service
    with pytest.raises(AccountError, match="nome"):
        service.save(_ml(label=" "))
    with pytest.raises(AccountError, match="HTTPS"):
        service.save(_ml(seller_url="http://www.mercadolivre.com.br"))
    with pytest.raises(AccountError, match="identificador"):
        service.save(_ml(internal_id="Com Espaço"))
    service.save(_ml(internal_id="loja-a"))
    with pytest.raises(AccountError, match="identificador"):
        service.save(_ml(label="Outra", internal_id="LOJA-A"))
    with pytest.raises(AccountError, match="Já existe uma conta"):
        service.save(_ml())  # same label in the same marketplace


def test_marketplace_cannot_change_on_edit(ctx):
    account = ctx.account_service.save(_ml())
    account.marketplace = Marketplace.SHOPEE
    account.seller_url = "https://seller.shopee.com.br/"
    with pytest.raises(AccountError, match="não pode ser alterado"):
        ctx.account_service.save(account)


def test_changing_url_resets_connection_status(ctx):
    account = ctx.account_service.save(_ml())
    ctx.accounts.record_connection(account.id, ConnectionStatus.CONNECTED, "ok", "LOJANORTE")
    account = ctx.account_service.get(account.id)
    assert account.detected_identity == "LOJANORTE" and account.last_connected_at
    account.seller_url = "https://www.mercadolivre.com.br/outra"
    ctx.account_service.save(account)
    assert ctx.account_service.get(account.id).connection_status is ConnectionStatus.UNKNOWN


def test_default_account_and_run_selection(ctx):
    seeded = ctx.accounts.default_for(ML)  # migration seeds one default per marketplace
    assert seeded.is_default
    second = ctx.account_service.save(_ml(label="Loja Sul"))
    assert ctx.accounts.default_for(ML).id == seeded.id
    ctx.account_service.set_default(second.id)
    assert ctx.accounts.default_for(ML).id == second.id
    assert sum(a.is_default for a in ctx.account_service.list(ML)) == 1
    second.is_active = False
    ctx.account_service.save(second)
    assert ctx.accounts.default_for(ML).id == seeded.id  # inactive default is skipped


def test_delete_account_and_profile(ctx):
    account = ctx.account_service.save(_ml(label="Temporária", is_default=True))
    folder = ctx.account_service.profile_dir(account)
    folder.mkdir(parents=True)
    (folder / "Cookies").write_text("x")
    ctx.account_service.delete(account.id, remove_profile=True)
    assert ctx.account_service.get(account.id) is None
    assert not folder.exists()
    assert ctx.accounts.default_for(ML) is not None and ctx.accounts.default_for(ML).is_default


def test_account_with_history_cannot_be_deleted(ctx, complete_product):
    from mla.automation.queue import QueueManager
    product = complete_product()
    ctx.catalog.save(product)
    account = ctx.accounts.default_for(Marketplace.SIMULATED)
    queue = QueueManager(ctx.automation_repo, ctx.products, ctx.accounts)
    queue.enqueue([product.id])
    queue.finish_item(ctx.automation_repo.next_queued_item(), ItemStatus.FAILED, "x")
    with pytest.raises(AccountError, match="desative"):
        ctx.account_service.delete(account.id)


def test_profile_dir_is_always_managed_by_mla(ctx):
    account = ctx.account_service.save(_ml())
    expected = ctx.paths.browser_profiles / f"mercadolivre-{account.id}"
    assert ctx.account_service.profile_dir(account) == expected
    account.profile_dir = r"C:\Users\garci\AppData\Local\Google\Chrome\User Data"  # never the personal profile
    assert ctx.account_service.profile_dir(account) == expected
    ctx.account_service.save(account)
    assert ctx.account_service.get(account.id).profile_dir == ""


def test_safe_url_drops_query_and_fragment_from_messages():
    assert safe_url("https://www.mercadolivre.com.br/vendas?code=TG-123&state=x#top") == \
        "https://www.mercadolivre.com.br/vendas"
    assert safe_url("https://user:senha@exemplo.com.br/a?b=1") == "https://exemplo.com.br/a"
    assert safe_url("file:///C:/mock/sell.html?id=9") == "file:///C:/mock/sell.html"
    assert safe_url("") == ""
