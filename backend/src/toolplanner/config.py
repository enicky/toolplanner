from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://toolplanner:toolplanner@localhost:5432/toolplanner"
    public_base_url: str = "http://localhost:5173"
    cookie_secure: bool = False
    session_ttl_hours: int = 12
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_prefix="TOOLPLANNER_", extra="ignore")


settings = Settings()
