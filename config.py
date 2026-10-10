from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./cosmic_tickets.db"
    ticket_secret: str = "local-demo-secret-change-me"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
