from __future__ import annotations

from pathlib import Path

import pytest

from paper_insights.config import Settings, SettingsError


def test_settings_reject_unknown_keys(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="unknown configuration key"):
        Settings.from_mapping(
            {
                "paper_insights": {
                    "data_root": str(tmp_path / "corpus"),
                    "surprise": True,
                }
            }
        )


def test_settings_load_known_sections_without_creating_data_root(tmp_path: Path) -> None:
    data_root = tmp_path / "corpus"

    settings = Settings.from_mapping(
        {
            "paper_insights": {
                "data_root": str(data_root),
                "request_timeout_seconds": 12,
                "user_agent": "paper-insights/test",
            },
            "sources": {
                "arxiv": {
                    "enabled": False,
                    "categories": ["cs.AI", "cs.SE"],
                    "page_size": 25,
                }
            },
            "search": {"default_limit": 5, "maximum_limit": 20},
            "analysis": {"enabled": False, "provider": "", "model": ""},
        }
    )

    assert settings.data_root == data_root.resolve()
    assert settings.request_timeout_seconds == 12
    assert settings.arxiv.categories == ("cs.AI", "cs.SE")
    assert settings.search.maximum_limit == 20
    assert not data_root.exists()


def test_settings_reject_invalid_limits(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="default search limit"):
        Settings.from_mapping(
            {
                "paper_insights": {"data_root": str(tmp_path)},
                "search": {"default_limit": 11, "maximum_limit": 10},
            }
        )


@pytest.mark.parametrize(
    "mapping",
    [
        {"sources": {"arxiv": {"page_size": 101}}},
        {"search": {"default_limit": 10, "maximum_limit": 51}},
    ],
)
def test_settings_reject_limits_outside_public_cli_contract(
    tmp_path: Path,
    mapping: dict[str, object],
) -> None:
    mapping["paper_insights"] = {"data_root": str(tmp_path)}

    with pytest.raises(SettingsError, match="at most"):
        Settings.from_mapping(mapping)


def test_relative_data_root_in_toml_is_resolved_from_config_directory(tmp_path: Path) -> None:
    config_directory = tmp_path / "configuration"
    config_directory.mkdir()
    config_path = config_directory / "paper-insights.toml"
    config_path.write_text('[paper_insights]\ndata_root = "./corpus"\n', encoding="utf-8")

    settings = Settings.load(config_path=config_path, environ={})

    assert settings.data_root == config_directory / "corpus"
    assert not settings.data_root.exists()
