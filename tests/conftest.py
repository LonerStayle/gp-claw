import pytest

from gp_claw.config import Settings


@pytest.fixture
def settings():
    return Settings(
        runpod_api_key="test-key",
        runpod_endpoint_id="test-endpoint",
        vllm_model_name="test-model",
        workspace_root="/tmp/gp_claw_test",
    )
