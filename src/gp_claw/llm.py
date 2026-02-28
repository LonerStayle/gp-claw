from langchain_openai import ChatOpenAI

from gp_claw.config import Settings


def create_llm(settings: Settings) -> ChatOpenAI:
    """RunPod vLLM 엔드포인트에 연결하는 ChatOpenAI 인스턴스 생성."""
    return ChatOpenAI(
        model=settings.vllm_model_name,
        api_key=settings.runpod_api_key,
        base_url=settings.vllm_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
