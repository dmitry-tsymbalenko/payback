"""Telegram Bot API webhook intake (when TELEGRAM_UPDATE_MODE=webhook)."""

from __future__ import annotations

import hmac

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/telegram")
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        expected = getattr(request.app.state, "telegram_webhook_secret", None)
        if not isinstance(expected, str) or not expected:
            raise HTTPException(status_code=503, detail="Telegram webhook is not configured")
        provided = x_telegram_bot_api_secret_token or ""
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=403, detail="Forbidden")

        bot = getattr(request.app.state, "bot", None)
        dispatcher = getattr(request.app.state, "dispatcher", None)
        if bot is None or dispatcher is None:
            raise HTTPException(status_code=503, detail="Bot is not configured")

        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": bot})
        await dispatcher.feed_update(bot, update)
        return {"ok": True}

    return router


__all__ = ["create_router"]
