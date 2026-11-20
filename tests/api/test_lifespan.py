import asyncio

import pytest
from aiogram.types import Update
from httpx import ASGITransport, AsyncClient

from payback.api import create_app
from payback.config import Settings


class _FakeBotSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeBot:
    def __init__(self) -> None:
        self.session = _FakeBotSession()
        self.drop_pending_updates: list[bool] = []
        self.webhook_urls: list[str] = []
        self.webhook_secrets: list[str] = []
        self.me_requested = False

    async def get_me(self) -> object:
        self.me_requested = True
        return object()

    async def delete_webhook(self, *, drop_pending_updates: bool) -> None:
        self.drop_pending_updates.append(drop_pending_updates)

    async def set_webhook(
        self,
        *,
        url: str,
        secret_token: str | None = None,
        drop_pending_updates: bool = False,
        **_kwargs: object,
    ) -> None:
        self.webhook_urls.append(url)
        if secret_token is not None:
            self.webhook_secrets.append(secret_token)
        self.drop_pending_updates.append(drop_pending_updates)


class _FakeDispatcher:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.handle_signals: bool | None = None
        self.close_bot_session: bool | None = None
        self.fed_updates: list[Update] = []
        self._stop = asyncio.Event()
        self._stopped = asyncio.Event()

    async def start_polling(
        self,
        _bot: _FakeBot,
        *,
        handle_signals: bool = True,
        close_bot_session: bool = True,
        **_kwargs: object,
    ) -> None:
        self.started = True
        self.handle_signals = handle_signals
        self.close_bot_session = close_bot_session
        self._stopped.clear()
        try:
            await self._stop.wait()
            self.stopped = True
        finally:
            self._stopped.set()

    async def stop_polling(self) -> None:
        if not self.started:
            raise RuntimeError("Polling is not started")
        self._stop.set()
        await self._stopped.wait()

    async def feed_update(self, _bot: object, update: Update) -> None:
        self.fed_updates.append(update)


class _FakeLivePlanfixClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


async def test_lifespan_starts_polling_and_closes_resources(env: dict[str, str]) -> None:
    settings = Settings()
    bot = _FakeBot()
    dispatcher = _FakeDispatcher()
    live_client = _FakeLivePlanfixClient()
    engine = _FakeEngine()
    app = create_app(
        settings,
        bot=bot,
        dispatcher=dispatcher,
        live_planfix_client=live_client,
        engine=engine,  # type: ignore[arg-type]
    )

    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)
        assert dispatcher.started is True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert bot.me_requested is True
    assert dispatcher.handle_signals is False
    assert dispatcher.close_bot_session is False
    assert dispatcher.stopped is True
    assert bot.drop_pending_updates == [True]
    assert bot.webhook_urls == []
    assert bot.session.closed is True
    assert live_client.closed is True
    assert engine.disposed is True
    assert app.state.engine is None


async def test_lifespan_registers_telegram_webhook_without_polling(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_UPDATE_MODE", "webhook")
    monkeypatch.setenv("DOMAIN", "payback.example")
    settings = Settings()
    bot = _FakeBot()
    dispatcher = _FakeDispatcher()
    app = create_app(settings, bot=bot, dispatcher=dispatcher)

    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)
        assert dispatcher.started is False
        assert bot.webhook_urls == ["https://payback.example/webhooks/telegram"]
        assert bot.webhook_secrets == [settings.webhook_secret.get_secret_value()]
        assert bot.drop_pending_updates == [True]


async def test_telegram_webhook_feeds_dispatcher(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_UPDATE_MODE", "webhook")
    monkeypatch.setenv("DOMAIN", "payback.example")
    settings = Settings()
    bot = _FakeBot()
    dispatcher = _FakeDispatcher()
    app = create_app(settings, bot=bot, dispatcher=dispatcher)
    secret = settings.webhook_secret.get_secret_value()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/webhooks/telegram", json={"update_id": 1})
        assert denied.status_code == 403

        ok = await client.post(
            "/webhooks/telegram",
            json={"update_id": 42},
            headers={"X-Telegram-Bot-Api-Secret-Token": secret},
        )
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}
    assert len(dispatcher.fed_updates) == 1
    assert dispatcher.fed_updates[0].update_id == 42


def test_webhook_mode_requires_domain(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_UPDATE_MODE", "webhook")
    monkeypatch.delenv("DOMAIN", raising=False)
    with pytest.raises(Exception, match="DOMAIN"):
        Settings()
