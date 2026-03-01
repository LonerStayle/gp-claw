import uvicorn

from gp_claw.config import Settings
from gp_claw.llm import create_llm
from gp_claw.server import create_app
from gp_claw.tools import create_tool_registry


def main():
    settings = Settings()

    llm = None
    if settings.runpod_api_key and settings.runpod_endpoint_id:
        llm = create_llm(settings)
        print(f"LLM connected: {settings.vllm_model_name}")
    else:
        print("No LLM configured — running in echo mode")

    workspace = settings.workspace_root.expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    registry = create_tool_registry(str(workspace))
    app = create_app(llm=llm, registry=registry, workspace_root=str(workspace))
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
