import importlib
import os
from collections.abc import Generator
from contextlib import contextmanager
from types import ModuleType

import pytest

import harbor.constants as constants


@contextmanager
def patched_harbor_registry_website_url(
    value: str | None,
) -> Generator[ModuleType, None, None]:
    original = os.environ.get("HARBOR_REGISTRY_WEBSITE_URL")
    try:
        if value is None:
            os.environ.pop("HARBOR_REGISTRY_WEBSITE_URL", None)
        else:
            os.environ["HARBOR_REGISTRY_WEBSITE_URL"] = value
        yield importlib.reload(constants)
    finally:
        if original is None:
            os.environ.pop("HARBOR_REGISTRY_WEBSITE_URL", None)
        else:
            os.environ["HARBOR_REGISTRY_WEBSITE_URL"] = original
        importlib.reload(constants)


def test_harbor_registry_website_url_defaults_to_hub() -> None:
    with patched_harbor_registry_website_url(None) as reloaded:
        assert (
            reloaded.HARBOR_REGISTRY_WEBSITE_URL
            == reloaded.DEFAULT_HARBOR_REGISTRY_WEBSITE_URL
        )
        assert (
            reloaded.HARBOR_VIEWER_WEBSITE_URL
            == reloaded.DEFAULT_HARBOR_REGISTRY_WEBSITE_URL
        )


def test_harbor_registry_website_url_prefers_env() -> None:
    with patched_harbor_registry_website_url("https://branch.harbor.test") as reloaded:
        assert reloaded.HARBOR_REGISTRY_WEBSITE_URL == "https://branch.harbor.test"
        assert reloaded.HARBOR_REGISTRY_TASKS_URL == "https://branch.harbor.test/tasks"
        assert (
            reloaded.HARBOR_REGISTRY_DATASETS_URL
            == "https://branch.harbor.test/datasets"
        )
        assert reloaded.HARBOR_VIEWER_WEBSITE_URL == "https://branch.harbor.test"
        assert reloaded.HARBOR_VIEWER_JOBS_URL == "https://branch.harbor.test/jobs"


def _reload_with_construct_env(value: str | None) -> ModuleType:
    original = os.environ.get("HARBOR_CONSTRUCT_ENV")
    try:
        if value is None:
            os.environ.pop("HARBOR_CONSTRUCT_ENV", None)
        else:
            os.environ["HARBOR_CONSTRUCT_ENV"] = value
        return importlib.reload(constants)
    finally:
        if original is None:
            os.environ.pop("HARBOR_CONSTRUCT_ENV", None)
        else:
            os.environ["HARBOR_CONSTRUCT_ENV"] = original


def test_hub_url_defaults_to_construct_production() -> None:
    try:
        with patched_harbor_registry_website_url(None) as reloaded:
            assert reloaded.CONSTRUCT_HUB_URL == "https://api.research.inv.tech/hub"
            assert reloaded.HARBOR_REGISTRY_WEBSITE_URL == reloaded.CONSTRUCT_HUB_URL
    finally:
        importlib.reload(constants)


def test_construct_env_staging_selects_staging_hub() -> None:
    try:
        reloaded = _reload_with_construct_env("staging")
        assert reloaded.CONSTRUCT_HUB_URL == "https://api.research.invsta.systems/hub"
        assert reloaded.HARBOR_REGISTRY_WEBSITE_URL == reloaded.CONSTRUCT_HUB_URL
    finally:
        _reload_with_construct_env(None)


def test_construct_env_rejects_unknown_value() -> None:
    try:
        with pytest.raises(ValueError, match="HARBOR_CONSTRUCT_ENV"):
            _reload_with_construct_env("qa")
    finally:
        _reload_with_construct_env(None)


def test_construct_env_is_case_insensitive() -> None:
    try:
        assert _reload_with_construct_env("Staging").CONSTRUCT_ENV == "staging"
    finally:
        _reload_with_construct_env(None)
