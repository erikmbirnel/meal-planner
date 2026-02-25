import logging

from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application

from app.config import settings
from app.sheets import SheetsClient
from app.todoist_client import TodoistClient
from app.claude_client import ClaudeClient
from app.meal_planner import MealPlanner
from app.bot import register_handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Build the Telegram application (shared singleton)
# ---------------------------------------------------------------------------

_tg_app: Application | None = None


def _build_app() -> Application:
    sheets = SheetsClient(
        spreadsheet_id=settings.google_spreadsheet_id,
        credentials_json=settings.google_credentials_json,
        credentials_path=settings.google_credentials_path,
    )
    todoist = TodoistClient(api_token=settings.todoist_api_token)
    claude = ClaudeClient(api_key=settings.anthropic_api_key)
    planner = MealPlanner(sheets=sheets, todoist=todoist, claude=claude)

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )
    app.bot_data["planner"] = planner
    register_handlers(app)
    return app


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

fastapi_app = FastAPI(title="Meal Planner Bot")
app = fastapi_app  # alias expected by ASGI servers


@fastapi_app.on_event("startup")
async def startup() -> None:
    global _tg_app
    _tg_app = _build_app()
    await _tg_app.initialize()
    await _tg_app.bot.set_webhook(url=settings.telegram_webhook_url)
    await _tg_app.start()
    log.info("Bot started. Webhook set to %s", settings.telegram_webhook_url)


@fastapi_app.on_event("shutdown")
async def shutdown() -> None:
    if _tg_app:
        await _tg_app.stop()
        await _tg_app.shutdown()


@fastapi_app.post("/webhook")
async def webhook(request: Request) -> Response:
    data = await request.json()
    update = Update.de_json(data, _tg_app.bot)
    await _tg_app.process_update(update)
    return Response(status_code=200)


@fastapi_app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
