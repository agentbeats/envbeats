import asyncio
import atexit
import os
import signal

import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard
from a2a.utils import new_agent_text_message


from my_util import parse_tags

# Agent definition

my_agent_host = "localhost"
my_agent_port = 9990
my_agent_host = f"http://{my_agent_host}:{my_agent_port}/"
my_agent_card = AgentCard(
    name="My Agent",
    description="No description.",
    url=my_agent_host,
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[],
)


class MyAgent:
    def __init__(self):
        self._inspector_proc = None

    async def invoke(self, context: RequestContext) -> str:
        user_input = context.get_user_input()
        tags = parse_tags(user_input)
        reset_step_result_str = tags["StepResult"]
        print("Received task:\n", user_input)
        print("Reset StepResult:\n", reset_step_result_str)

        # Kill previous MCP Inspector if still running
        if self._inspector_proc is not None and self._inspector_proc.returncode is None:
            print(
                f"Killing previous MCP Inspector process group (pid={self._inspector_proc.pid})"
            )
            os.killpg(self._inspector_proc.pid, signal.SIGTERM)
            await self._inspector_proc.wait()

        # Start MCP Inspector web UI as a background process (in its own process group)
        env = {**os.environ, "SERVER_PORT": "9502", "CLIENT_PORT": "9501"}
        self._inspector_proc = await asyncio.create_subprocess_exec(
            "npx",
            "@modelcontextprotocol/inspector",
            "--config",
            "mcp.json",
            "--header",
            '"Authorization: Bearer 456"',
            env=env,
            preexec_fn=os.setsid,
        )
        print(f"MCP Inspector started (pid={self._inspector_proc.pid})")
        print("Set header: Authorization: Bearer 456")
        print("Then click 'List Tools'")

        return "Ok, will do."


class MyAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = MyAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        result = await self.agent.invoke(context)
        await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported")


def main():
    agent_executor = MyAgentExecutor()

    def cleanup_subprocesses():
        agent = agent_executor.agent
        if agent._inspector_proc is not None:
            try:
                os.killpg(agent._inspector_proc.pid, signal.SIGTERM)
                print(
                    f"Cleaned up MCP Inspector process group (pid={agent._inspector_proc.pid})"
                )
            except (ProcessLookupError, PermissionError, OSError):
                pass

    atexit.register(cleanup_subprocesses)

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(
        agent_card=my_agent_card,
        http_handler=request_handler,
    )

    try:
        uvicorn.run(server.build(), host="0.0.0.0", port=my_agent_port)
    finally:
        cleanup_subprocesses()


main()
