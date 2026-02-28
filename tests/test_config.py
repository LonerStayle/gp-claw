from pathlib import Path

from gp_claw.config import Settings


def test_settings_defaults():
    s = Settings(
        runpod_api_key="key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="model-name",
    )
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.llm_temperature == 0.6


def test_vllm_base_url():
    s = Settings(
        runpod_api_key="key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="model-name",
    )
    assert s.vllm_base_url == "https://api.runpod.ai/v2/ep-123/openai/v1"


def test_workspace_root_default():
    s = Settings(
        runpod_api_key="key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="model-name",
    )
    assert s.workspace_root == Path.home() / ".gp_claw" / "workspace"
