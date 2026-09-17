import asyncio
import json
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiError(Exception):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.status = code, status


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class Choice(Model):
    role: Literal["radio", "button", "combobox"]
    name: str = Field(min_length=1, max_length=300)
    value: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_choice(self):
        if self.role == "combobox" and self.value is None:
            raise ValueError("下拉选项需要 value")
        if self.role == "button" and self.name not in ("继续", "选择", "选取"):
            raise ValueError("button 仅允许 继续 / 选择 / 选取")
        return self


class Product(Model):
    url: str
    expected_bag_name: str = Field(alias="expectedBagName", min_length=1, max_length=300)
    choices: list[Choice] = Field(default_factory=list, max_length=30)

    @field_validator("url")
    @classmethod
    def apple_url(cls, value):
        url = urlsplit(value)
        host = url.hostname or ""
        if (url.scheme != "https" or url.username or url.password or url.port
                or not (host == "apple.com.cn" or host.endswith(".apple.com.cn"))
                or not re.match(r"^/(cn/)?shop/", url.path)):
            raise ValueError("必须提供 apple.com.cn 商店 HTTPS 商品链接")
        return value


class SessionInput(Model):
    headless: bool = False


class Quantity(Model):
    quantity: int = Field(ge=1, le=99)


class Idempotency:
    """Cache both successes and failures; cancellation must not repeat an add."""

    def __init__(self):
        self.entries = {}

    async def run(self, key, payload, action):
        if not key or len(key) > 128:
            raise ApiError("IDEMPOTENCY_KEY_REQUIRED", "写操作需要 Idempotency-Key 请求头", 400)
        fingerprint = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if key in self.entries:
            previous, task = self.entries[key]
            if previous != fingerprint:
                raise ApiError("KEY_CONFLICT", "同一幂等键不能用于不同请求")
        else:
            if len(self.entries) >= 1000:
                raise ApiError("SESSION_LIMIT", "会话请求数量已达上限")
            task = asyncio.create_task(action())
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            self.entries[key] = (fingerprint, task)
        return await asyncio.shield(task)
