"""应用配置：通过环境变量注入，未配置时使用安全默认值。"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "Industrial Maintenance Copilot"
    APP_ENV: str = "development"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"

    # 数据库：留空默认 SQLite，保证本机可零配置启动
    DATABASE_URL: str = ""

    # 认证
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # AI
    AI_ENABLED: bool = False
    LLM_API_BASE: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    AI_REQUEST_TIMEOUT_SECONDS: int = 30

    # 存储
    STORAGE_TYPE: str = "local"
    STORAGE_LOCAL_DIR: str = "./uploads"
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = ""

    # 演示数据
    SEED_ON_STARTUP: bool = True

    @property
    def effective_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        # SQLite 默认文件数据库
        return "sqlite:///./maintenance.db"

    @property
    def cors_origins(self) -> List[str]:
        origins = [self.FRONTEND_URL]
        # 开发环境额外放行常见本地端口
        if self.APP_ENV == "development":
            origins.extend(
                [
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                    "http://localhost:3001",
                ]
            )
        # 去重
        return list(dict.fromkeys(origins))

    @property
    def ai_actually_enabled(self) -> bool:
        """真正可用的 AI：开关打开且配置了 API Key。"""
        return bool(self.AI_ENABLED and self.LLM_API_KEY and self.LLM_MODEL)


settings = Settings()
