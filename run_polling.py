"""
Run the bot locally using polling (no webhook or HTTPS needed).
Use this for testing before deploying to a server.

Usage:
    python run_polling.py
"""

from app.config import settings
from app.sheets import SheetsClient
from app.todoist_client import TodoistClient
from app.claude_client import ClaudeClient
from app.meal_planner import MealPlanner
from app.bot import register_handlers
from telegram.ext import Application

app = Application.builder().token(settings.telegram_bot_token).build()
sheets = SheetsClient(settings.google_credentials_path, settings.google_spreadsheet_id)
todoist = TodoistClient(settings.todoist_api_token)
claude = ClaudeClient(settings.anthropic_api_key)
app.bot_data["planner"] = MealPlanner(sheets, todoist, claude)
register_handlers(app)
app.run_polling()
