from pathlib import Path

from app.core.config import BACKEND_ENV_FILE, Settings


def test_settings_default_ark_model_matches_current_endpoint():
    assert (
        Settings.model_fields["ark_model"].default
        == "ep-m-20260518145505-mt7gb"
    )


def test_settings_include_backend_env_file_when_started_from_project_root():
    env_files = Settings.model_config["env_file"]
    if isinstance(env_files, (str, Path)):
        env_files = (env_files,)
    normalized = {Path(path) for path in env_files}

    assert BACKEND_ENV_FILE in normalized


def test_settings_ignore_unknown_env_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "REMOVED_SETTING=legacy-value",
                "ARK_MODEL=doubao-test",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.ark_model == "doubao-test"


def test_settings_reads_ark_timeout_seconds(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ARK_TIMEOUT_SECONDS=17\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.ark_timeout_seconds == 17


def test_settings_reads_ark_max_retries(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ARK_MAX_RETRIES=1\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.ark_max_retries == 1


def test_settings_reads_agent_runtime_limits(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "AGENT_MODEL_TIMEOUT_SECONDS=21",
                "AGENT_TOOL_TIMEOUT_SECONDS=9",
                "AGENT_HISTORY_MAX_MESSAGES=6",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.agent_model_timeout_seconds == 21
    assert settings.agent_tool_timeout_seconds == 9
    assert settings.agent_history_max_messages == 6
