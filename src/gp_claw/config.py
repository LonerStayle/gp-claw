from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # RunPod vLLM
    runpod_api_key: str = ""
    runpod_endpoint_id: str = ""
    vllm_model_name: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workspace_root: Path = Path.home() / ".gp_claw" / "workspace"

    # LLM
    llm_temperature: float = 0.6
    llm_max_tokens: int = 4096

    @property
    def vllm_base_url(self) -> str:
        return f"https://api.runpod.ai/v2/{self.runpod_endpoint_id}/openai/v1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
