from gp_claw.config import Settings
from gp_claw.llm import create_llm


def test_create_llm_returns_chat_openai():
    settings = Settings(
        runpod_api_key="test-key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="test-model",
    )
    llm = create_llm(settings)

    assert llm.model_name == "test-model"
    assert llm.openai_api_key.get_secret_value() == "test-key"
    assert "ep-123" in str(llm.openai_api_base)


def test_create_llm_uses_settings_temperature():
    settings = Settings(
        runpod_api_key="test-key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="test-model",
        llm_temperature=0.3,
    )
    llm = create_llm(settings)
    assert llm.temperature == 0.3
