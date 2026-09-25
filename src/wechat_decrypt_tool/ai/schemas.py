from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator
from .compaction_policy import CompactionPolicy


class ModelOverrides(BaseModel):
    context_window: int | None = Field(default=None, ge=4096, le=10000000)
    max_output_tokens: int | None = Field(default=None, ge=1, le=10000000)
    vision: bool | None = None
    tool_call: bool | None = None
    structured_output: bool | None = None
    reasoning: bool | None = None
    reasoning_efforts: list[str] | None = Field(None, max_length=20)
    temperature: bool | None = None
    attachment: bool | None = None


class ProviderInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    provider: Literal[
        "deepseek", "xiaomi", "claude", "kimi", "openai", "gemini", "qwen", "zhipu",
        "doubao", "siliconflow", "openrouter", "requesty", "groq", "ollama", "lmstudio", "custom",
    ] = "deepseek"
    protocol: Literal["openai", "anthropic"] = "openai"
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    model: str = Field(min_length=1, max_length=200)
    vision: bool = False
    context_window: int | None = Field(default=None, ge=4096, le=10000000)
    model_overrides: ModelOverrides = Field(default_factory=ModelOverrides)
    compaction_policy: CompactionPolicy = Field(default_factory=CompactionPolicy)


class Defaults(BaseModel):
    text: str = ""
    vision: str = ""


class ModelListInput(BaseModel):
    # 拉取模型不要求先填写配置名称和模型名称。
    provider: str = ''
    base_url: str = Field(min_length=1, max_length=2048)
    protocol: Literal["openai", "anthropic"] = "openai"
    api_key: str | None = Field(default=None, max_length=4096)
    profile_id: str = ""


class MessageRange(BaseModel):
    mode: Literal["count", "hours", "dates", "since"] = "count"
    count: int = Field(default=100, ge=1, le=100000)
    hours: float = Field(default=24, gt=0, le=87600)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_dates(self):
        if self.mode == "dates" and (self.start is None or self.end is None or self.end <= self.start):
            raise ValueError("起止时间必须完整，结束时间必须晚于开始时间")
        return self


class TaskInput(BaseModel):
    account: str = Field(min_length=1)
    conversations: list[str] = Field(min_length=1, max_length=200)
    range: MessageRange = Field(default_factory=MessageRange)
    profile_id: str = ""
    vision_profile_id: str = ""
    media: bool = True
    max_attachment_mb: int = Field(default=20, ge=1, le=200)
    notify: bool = True
    hide_content: bool = False

    @model_validator(mode="after")
    def unique_conversations(self):
        self.conversations = list(dict.fromkeys(x.strip() for x in self.conversations if x.strip()))
        if not self.conversations:
            raise ValueError("请选择会话")
        return self


class RuleInput(TaskInput):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["summary", "alert"] = "summary"
    trigger: Literal["interval", "daily", "count"] = "interval"
    interval_seconds: int = Field(default=60, ge=10, le=31536000)
    daily_time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    threshold: int = Field(default=100, ge=1, le=100000)
    condition: str = Field(default="", max_length=4000)
    enabled: bool = False

    @model_validator(mode="after")
    def validate_condition(self):
        if self.kind == "alert":
            if not self.condition.strip():
                raise ValueError("请填写关注条件")
            self.trigger = "interval"
        return self


class Point(BaseModel):
    text: str
    sources: list[str] = Field(min_length=1)


class Summary(BaseModel):
    overview: str
    topics: list[Point] = Field(default_factory=list)
    conclusions: list[Point] = Field(default_factory=list)
    todos: list[Point] = Field(default_factory=list)


class Match(BaseModel):
    reason: str
    sources: list[str] = Field(min_length=1)


class Matches(BaseModel):
    matches: list[Match] = Field(default_factory=list)
