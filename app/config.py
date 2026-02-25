from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_url: str = Field(..., alias="TELEGRAM_WEBHOOK_URL")

    google_credentials_path: str = Field(
        "./credentials/google_service_account.json",
        alias="GOOGLE_CREDENTIALS_PATH",
    )
    google_credentials_json: Optional[str] = Field(
        None, alias="GOOGLE_CREDENTIALS_JSON"
    )
    google_spreadsheet_id: str = Field(..., alias="GOOGLE_SPREADSHEET_ID")

    todoist_api_token: str = Field(..., alias="TODOIST_API_TOKEN")

    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")

    host: str = Field("0.0.0.0", alias="HOST")
    port: int = Field(8000, alias="PORT")

    model_config = {"env_file": ".env", "populate_by_name": True}


settings = Settings()
