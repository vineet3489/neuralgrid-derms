import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "L&T Neural Grid DERMS"
    version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = int(os.environ.get("PORT", 8080))
    debug: bool = False

    # Database - SQLite for dev, PostgreSQL for prod
    database_url: str = os.environ.get(
        "DATABASE_URL", "sqlite+aiosqlite:///./neuralgrid.db"
    )

    # JWT Auth
    secret_key: str = os.environ.get(
        "SECRET_KEY", "change-me-in-production-neuralgrid-derms-2026"
    )
    algorithm: str = "HS256"
    access_token_expire_hours: int = 8

    # Claude LLM
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    llm_model: str = "claude-haiku-4-5-20251001"  # Cost-effective default
    llm_advisor_model: str = "claude-sonnet-4-6"  # For complex reasoning

    # Simulation
    adms_poll_interval: int = 30
    aggregator_poll_interval: int = 20
    dispatch_check_interval: int = 15
    forecast_update_interval: int = 300  # 5 minutes

    # Grid thresholds
    voltage_nominal: float = 230.0
    voltage_high_warn: float = 244.0
    voltage_low_warn: float = 216.0
    voltage_high_trip: float = 253.0
    voltage_low_trip: float = 207.0
    feeder_loading_warn: float = 80.0
    feeder_loading_max: float = 100.0
    hosting_capacity_warn: float = 85.0

    # Static files (React build output)
    static_dir: str = os.environ.get("STATIC_DIR", "../frontend/dist")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
