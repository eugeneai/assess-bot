from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    group_id: int
    admin_password: str
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    storage_path: str = "files"
    database_url: str = "sqlite+aiosqlite:///./assess.db"
    bot_proxy: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
