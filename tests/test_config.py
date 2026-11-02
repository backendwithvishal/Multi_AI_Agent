import os
from pathlib import Path
import pytest
from tripmate.config.settings import Settings

BASE_DIR = Path(__file__).resolve().parent.parent


def test_missing_required_env_fails_startup_in_prod(monkeypatch):
    """Verifies that missing mandatory configuration fails fast in production mode."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)

    prod_settings = Settings(
        APP_ENV="production",
        ENV="prod",
        API_KEY="",
        GROQ_API_KEY="",
        OPENROUTER_API_KEY="",
        HUGGINGFACE_API_KEY="",
    )

    with pytest.raises(ValueError, match="Production startup failed! Mandatory configuration missing"):
        prod_settings.validate_production()


def test_valid_required_env_passes_startup_in_prod(monkeypatch):
    """Verifies that valid mandatory configuration passes startup in production mode."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENV", "prod")

    prod_settings = Settings(
        APP_ENV="production",
        ENV="prod",
        API_KEY="prod-master-key-xyz",
        GROQ_API_KEY="gsk_valid_key",
    )
    # Should not raise
    prod_settings.validate_production()


def test_env_example_keys_match_settings():
    """.env.example keys must exactly match keys recognized/read by the settings module."""
    env_example_path = BASE_DIR / ".env.example"
    assert env_example_path.exists(), ".env.example must exist"

    example_keys = set()
    with open(env_example_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key:
                    example_keys.add(key)

    settings_keys = set(Settings.model_fields.keys())

    missing_in_example = sorted(settings_keys - example_keys)
    extra_in_example = sorted(example_keys - settings_keys)

    assert not missing_in_example, (
        f".env.example is missing settings fields: {missing_in_example}"
    )
    assert not extra_in_example, (
        f".env.example has extra keys not read by settings: {extra_in_example}"
    )
    assert example_keys == settings_keys, ".env.example keys must equal Settings fields"

