from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from paper_insights.paths import CorpusPaths


class SettingsError(ValueError):
    """The supplied configuration is invalid or contains unknown keys."""


def _mapping(value: object, section: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SettingsError(f"configuration section {section} must be a table")
    return cast(Mapping[str, object], value)


def _reject_unknown(values: Mapping[str, object], allowed: frozenset[str], section: str) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise SettingsError(f"unknown configuration key: {section}.{unknown[0]}")


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsError(f"{name} must be an integer")
    return value


def _positive_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise SettingsError(f"{name} must be positive")
    return float(value)


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise SettingsError(f"{name} must be a boolean")
    return value


@dataclass(frozen=True, slots=True)
class ArxivSettings:
    enabled: bool = True
    categories: tuple[str, ...] = ("cs.AI",)
    page_size: int = 100


@dataclass(frozen=True, slots=True)
class SearchSettings:
    default_limit: int = 10
    maximum_limit: int = 50


@dataclass(frozen=True, slots=True)
class AnalysisSettings:
    enabled: bool = False
    provider: str = ""
    model: str = ""


@dataclass(frozen=True, slots=True)
class Settings:
    data_root: Path = field(default_factory=lambda: Path("data").resolve())
    request_timeout_seconds: float = 30.0
    user_agent: str = "paper-insights/0.1"
    arxiv: ArxivSettings = field(default_factory=ArxivSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    analysis: AnalysisSettings = field(default_factory=AnalysisSettings)

    @property
    def paths(self) -> CorpusPaths:
        return CorpusPaths.from_data_root(self.data_root)

    @classmethod
    def load(
        cls,
        *,
        config_path: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> Settings:
        raw: dict[str, object] = {}
        if config_path is not None:
            try:
                with config_path.open("rb") as stream:
                    raw = tomllib.load(stream)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise SettingsError("configuration file could not be loaded") from exc

        environment = os.environ if environ is None else environ
        prefix = "PAPER_INSIGHTS_"
        allowed_environment = {
            "PAPER_INSIGHTS_DATA_ROOT",
            "PAPER_INSIGHTS_REQUEST_TIMEOUT_SECONDS",
            "PAPER_INSIGHTS_USER_AGENT",
        }
        unknown = sorted(
            key for key in environment if key.startswith(prefix) and key not in allowed_environment
        )
        if unknown:
            raise SettingsError("unknown configuration key in environment")

        platform = dict(_mapping(raw.get("paper_insights", {}), "paper_insights"))
        configured_data_root = platform.get("data_root")
        if config_path is not None and isinstance(configured_data_root, str):
            configured_path = Path(configured_data_root).expanduser()
            if not configured_path.is_absolute():
                platform["data_root"] = str(config_path.parent / configured_path)
        if "PAPER_INSIGHTS_DATA_ROOT" in environment:
            platform["data_root"] = environment["PAPER_INSIGHTS_DATA_ROOT"]
        if "PAPER_INSIGHTS_REQUEST_TIMEOUT_SECONDS" in environment:
            try:
                platform["request_timeout_seconds"] = float(
                    environment["PAPER_INSIGHTS_REQUEST_TIMEOUT_SECONDS"]
                )
            except ValueError as exc:
                raise SettingsError("request timeout environment value is invalid") from exc
        if "PAPER_INSIGHTS_USER_AGENT" in environment:
            platform["user_agent"] = environment["PAPER_INSIGHTS_USER_AGENT"]
        raw["paper_insights"] = platform
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> Settings:
        _reject_unknown(raw, frozenset({"paper_insights", "sources", "search", "analysis"}), "root")

        platform = _mapping(raw.get("paper_insights", {}), "paper_insights")
        _reject_unknown(
            platform,
            frozenset({"data_root", "request_timeout_seconds", "user_agent"}),
            "paper_insights",
        )
        sources = _mapping(raw.get("sources", {}), "sources")
        _reject_unknown(sources, frozenset({"arxiv"}), "sources")
        arxiv = _mapping(sources.get("arxiv", {}), "sources.arxiv")
        _reject_unknown(
            arxiv,
            frozenset({"enabled", "categories", "page_size"}),
            "sources.arxiv",
        )
        search = _mapping(raw.get("search", {}), "search")
        _reject_unknown(search, frozenset({"default_limit", "maximum_limit"}), "search")
        analysis = _mapping(raw.get("analysis", {}), "analysis")
        _reject_unknown(
            analysis,
            frozenset({"enabled", "provider", "model"}),
            "analysis",
        )

        data_root_value = platform.get("data_root", "data")
        if not isinstance(data_root_value, str) or not data_root_value.strip():
            raise SettingsError("paper_insights.data_root must be a non-empty path")
        timeout = _positive_number(
            platform.get("request_timeout_seconds", 30),
            "paper_insights.request_timeout_seconds",
        )
        user_agent = platform.get("user_agent", "paper-insights/0.1")
        if not isinstance(user_agent, str) or not user_agent.strip():
            raise SettingsError("paper_insights.user_agent must be a non-empty string")

        categories_value = arxiv.get("categories", ["cs.AI"])
        if not isinstance(categories_value, list) or not all(
            isinstance(category, str) and category.strip() for category in categories_value
        ):
            raise SettingsError("sources.arxiv.categories must be a list of strings")
        page_size = _integer(arxiv.get("page_size", 100), "sources.arxiv.page_size")
        if page_size <= 0:
            raise SettingsError("sources.arxiv.page_size must be positive")

        default_limit = _integer(search.get("default_limit", 10), "search.default_limit")
        maximum_limit = _integer(search.get("maximum_limit", 50), "search.maximum_limit")
        if default_limit <= 0 or maximum_limit <= 0 or default_limit > maximum_limit:
            raise SettingsError("default search limit must be positive and at most maximum")

        provider = analysis.get("provider", "")
        model = analysis.get("model", "")
        if not isinstance(provider, str) or not isinstance(model, str):
            raise SettingsError("analysis provider and model must be strings")

        return cls(
            data_root=Path(data_root_value).expanduser().resolve(strict=False),
            request_timeout_seconds=timeout,
            user_agent=user_agent.strip(),
            arxiv=ArxivSettings(
                enabled=_boolean(arxiv.get("enabled", True), "sources.arxiv.enabled"),
                categories=tuple(category.strip() for category in categories_value),
                page_size=page_size,
            ),
            search=SearchSettings(default_limit=default_limit, maximum_limit=maximum_limit),
            analysis=AnalysisSettings(
                enabled=_boolean(analysis.get("enabled", False), "analysis.enabled"),
                provider=provider,
                model=model,
            ),
        )
