"""应用配置：通过环境变量注入，未配置时使用安全默认值。"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-this-to-a-random-secret-key-in-production"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "AI-Powered Industrial Intelligent Maintenance Platform"
    APP_ENV: str = "development"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"

    # 数据库：留空默认 SQLite，保证本机可零配置启动
    DATABASE_URL: str = ""
    REDIS_URL: str = ""
    AUTO_MIGRATE_ON_STARTUP: bool | None = None

    # 认证
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # AI
    AI_ENABLED: bool = False
    LLM_API_BASE: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    AI_REQUEST_TIMEOUT_SECONDS: int = 30

    # 高风险命令超过此时间仍无结果时，转为人工核验。
    EQUIPMENT_COMMAND_TIMEOUT_SECONDS: int = Field(default=300, ge=30, le=3600)

    # 工业协议网关（OPC UA，只读遥测接入）。默认关闭，不影响既有 Mock 链路。
    GATEWAY_ENABLED: bool = False
    GATEWAY_MODE: str = "mock"  # mock：进程内模拟客户端；opcua：真实 OPC UA 连接
    GATEWAY_ENDPOINT: str = ""  # 留空使用各模式默认端点
    GATEWAY_POLL_INTERVAL_SECONDS: float = Field(default=5.0, ge=1.0)
    GATEWAY_AUTO_INGEST: bool = True
    GATEWAY_MAPPING_CONFIG: str = "configs/opcua-node-mapping.yaml"
    GATEWAY_TIMEOUT_SECONDS: float = Field(default=4.0, ge=1.0)

    # OPC UA DataChange 订阅（事件驱动，只读）。默认关闭，轮询能力保持不变。
    GATEWAY_SUBSCRIPTION_ENABLED: bool = False
    GATEWAY_SUBSCRIPTION_SAMPLING_MS: float = Field(default=1000.0, ge=100.0)
    GATEWAY_SUBSCRIPTION_DEBOUNCE_MS: float = Field(default=1000.0, ge=100.0)

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
    def is_development(self) -> bool:
        return self.APP_ENV.strip().lower() == "development"

    @model_validator(mode="after")
    def reject_unsafe_non_development_config(self) -> Settings:
        if self.is_development:
            return self

        secret_key = self.SECRET_KEY.strip()
        if secret_key == DEFAULT_SECRET_KEY or len(secret_key) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"非开发环境必须配置至少 {MIN_SECRET_KEY_LENGTH} 个字符的随机 SECRET_KEY"
            )
        if self.SEED_ON_STARTUP:
            raise ValueError("非开发环境禁止启用 SEED_ON_STARTUP")
        if self.AUTO_MIGRATE_ON_STARTUP:
            raise ValueError("非开发环境禁止在应用启动时自动执行数据库迁移")
        return self

    @property
    def effective_database_url(self) -> str:
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgres://"):
                return self.DATABASE_URL.replace(
                    "postgres://", "postgresql+psycopg://", 1
                )
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace(
                    "postgresql://", "postgresql+psycopg://", 1
                )
            return self.DATABASE_URL
        # SQLite 默认文件数据库
        return "sqlite:///./maintenance.db"

    @property
    def auto_migrate_on_startup(self) -> bool:
        if self.AUTO_MIGRATE_ON_STARTUP is not None:
            return self.AUTO_MIGRATE_ON_STARTUP
        return self.is_development

    @property
    def cors_origins(self) -> list[str]:
        origins = [self.FRONTEND_URL]
        # 开发环境额外放行常见本地端口
        if self.is_development:
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
