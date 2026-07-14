from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CollectionSettings(StrictModel):
    interval_hours: int = Field(ge=1, le=24)
    slot_minute_kst: int = Field(ge=0, le=59)
    request_min_delay_seconds: float = Field(ge=0.5, le=30)
    request_max_delay_seconds: float = Field(ge=0.5, le=60)
    concurrency: int = Field(ge=1, le=2)
    max_retries: int = Field(ge=0, le=10)

    @model_validator(mode="after")
    def interval_divides_day(self) -> "CollectionSettings":
        if 24 % self.interval_hours:
            raise ValueError("collection.interval_hours must divide 24")
        if self.request_max_delay_seconds < self.request_min_delay_seconds:
            raise ValueError("maximum request delay must not be below minimum request delay")
        return self


class RankingSettings(StrictModel):
    window_days: int = Field(ge=1, le=365)
    top_n: int = Field(ge=1, le=500)


class NormalizedWeights(StrictModel):
    recommendation: float
    comment: float
    view: float


class RisingSettings(StrictModel):
    windows_hours: tuple[int, ...] = Field(min_length=1)
    recommendation_weight: float = Field(ge=0, allow_inf_nan=False)
    comment_weight: float = Field(ge=0, allow_inf_nan=False)
    view_weight: float = Field(ge=0, allow_inf_nan=False)
    acceleration_weight: float = Field(ge=0, le=1)
    boundary_tolerance_hours: int = Field(ge=0, le=12)
    category_top_k: int = Field(ge=1, le=20)
    category_min_posts: int = Field(ge=1, le=20)
    category_top_mean_weight: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_rising_controls(self) -> "RisingSettings":
        if any(window <= 0 for window in self.windows_hours):
            raise ValueError("rising windows must be positive")
        if len(set(self.windows_hours)) != len(self.windows_hours):
            raise ValueError("rising windows must be unique")
        if max(self.recommendation_weight, self.comment_weight, self.view_weight) <= 0:
            raise ValueError("at least one rising weight must be positive")
        return self

    def normalized_weights(self) -> NormalizedWeights:
        scale = max(self.recommendation_weight, self.comment_weight, self.view_weight)
        if scale <= 0:
            raise ValueError("at least one rising weight must be positive")
        recommendation = self.recommendation_weight / scale
        comment = self.comment_weight / scale
        view = self.view_weight / scale
        total = recommendation + comment + view
        return NormalizedWeights(
            recommendation=recommendation / total,
            comment=comment / total,
            view=view / total,
        )


class AnalysisSettings(StrictModel):
    local_batch_size: int = Field(ge=1, le=500)
    codex_max_items_per_session: int = Field(ge=0, le=500)
    codex_estimated_input_token_budget: int = Field(ge=0, le=1_000_000)
    codex_prompt_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    codex_model_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")


class SecuritySettings(StrictModel):
    quarantine_threshold: int = Field(ge=50, le=70)


class RetentionSettings(StrictModel):
    raw_html_days: int = Field(ge=1, le=90)
    full_text_days: int = Field(ge=1, le=90)


class ResourceSettings(StrictModel):
    disk_warn_percent: int = Field(ge=1, le=99)
    disk_pause_percent: int = Field(ge=2, le=100)

    @model_validator(mode="after")
    def pause_exceeds_warning(self) -> "ResourceSettings":
        if self.disk_pause_percent <= self.disk_warn_percent:
            raise ValueError("disk pause threshold must exceed warning threshold")
        return self


class Settings(StrictModel):
    collection: CollectionSettings
    ranking: RankingSettings
    rising: RisingSettings
    analysis: AnalysisSettings
    security: SecuritySettings
    retention: RetentionSettings
    resources: ResourceSettings


class LoadedSettings(StrictModel):
    settings: Settings
    config_version: str


def load_settings(path: Path) -> LoadedSettings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    settings = Settings.model_validate(raw)
    normalized = json.dumps(
        settings.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return LoadedSettings(settings=settings, config_version=hashlib.sha256(normalized).hexdigest())


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.current = load_settings(path)
        self.last_error: str | None = None

    def reload(self) -> bool:
        try:
            candidate = load_settings(self.path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            self.last_error = str(exc)
            return False
        self.current = candidate
        self.last_error = None
        return True
