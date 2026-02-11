import multiprocessing as mp
import json
import asyncio
import uvicorn

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard
from a2a.utils import new_agent_text_message
from mcp.server.fastmcp import FastMCP

from openenv.core.env_client import StepResult
from echo_env import EchoAction, EchoEnv, EchoObservation
from openenv.core.env_server.types import State


from my_util import send_message, parse_tags

# OpenEnv

DEFAULT_TASK_TIMEOUT = 60  # seconds
shutdown_event = asyncio.Event()


def _step_result_to_dict(step_result: StepResult[EchoObservation]) -> dict:
    return {
        "observation": step_result.observation.model_dump(),
        "reward": step_result.reward,
        "done": step_result.done,
    }


def run_mcp(assessee_url: str, q: mp.Queue):
    with EchoEnv(base_url="https://openenv-echo-env.hf.space") as client:
        # Step 1. start env and reset
        reset_result = client.reset()  # Initialize the environment
        print(reset_result.observation.echoed_message)  # "Echo environment ready!"

        # Step 2. prepare (timed) MCP server
        mcp = FastMCP("openenv", host="0.0.0.0", port=9500, stateless_http=True)

        @mcp.tool()
        def step(action: EchoAction) -> StepResult[EchoObservation]:
            r = client.step(action)
            q.put(("step", _step_result_to_dict(r)))
            if r.done:
                q.put(("done", "from env"))
                asyncio.get_event_loop().call_later(0.5, shutdown_event.set)
            return r

        @mcp.tool()
        def state() -> State:
            r: State = client.state()
            q.put(("state", r.model_dump()))
            return r

        @mcp.tool()
        def done():
            q.put(("done", "from assessee"))
            asyncio.get_event_loop().call_later(0.5, shutdown_event.set)
            return {"message": "Task marked as done."}

        # Future TODO: register via MCP-X

        # result = client.step(EchoAction(message="Hello, World!"))
        # print(result.observation.echoed_message)  # "Hello, World!"
        # print(result.reward)  # 1.3 (based on message length)

        # Step 3. send task instruction
        task_instruction = f"""
Please finish the task `EchoEnv` from OpenEnv. 
You can use the `step` and `state` functions to explore the environment and complete the task.
You should now have access to these functions from your MCP tool calls.

The environment is reset with following step result:
<StepResult>
{json.dumps(_step_result_to_dict(reset_result))}
</StepResult>
"""

        async def _run():
            starlette_app = mcp.streamable_http_app()
            config = uvicorn.Config(
                starlette_app,
                host=mcp.settings.host,
                port=mcp.settings.port,
                log_level=mcp.settings.log_level.lower(),
            )
            server = uvicorn.Server(config)
            run_mcp_async = server.serve()
            run_mcp_task = asyncio.create_task(run_mcp_async)
            send_msg_async = send_message(assessee_url, task_instruction)
            send_msg_task = asyncio.create_task(send_msg_async)
            await shutdown_event.wait()
            await server.shutdown()
            run_mcp_task.cancel()
            send_msg_task.cancel()
            for task in (run_mcp_task, send_msg_task):
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        asyncio.run(_run())


# Agent definition

my_agent_host = "localhost"
my_agent_port = 9999
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
    async def invoke(self, context: RequestContext) -> str:
        user_input = context.get_user_input()
        tags = parse_tags(user_input)
        assessee_url = tags["assessee_url"]
        q = mp.Queue()
        p = mp.Process(
            target=run_mcp,
            args=(
                assessee_url,
                q,
            ),
        )
        p.daemon = True
        p.start()
        p.join(timeout=DEFAULT_TASK_TIMEOUT)
        alive = False
        if p.is_alive():
            alive = True
            p.terminate()
            p.join(timeout=3)
            if p.is_alive():
                p.kill()
                p.join(timeout=3)
        p.close()
        # get all messages from the queue
        messages = []
        while not q.empty():
            messages.append(q.get())
        if not messages or messages[-1][0] != "done":
            if alive:
                messages.append(("timeout", "Timeout but process still alive."))
            else:
                messages.append(
                    ("runtime_error", "Process finished but no done message received.")
                )
        return f"Task completed. Messages from environment:\n<messages>\n{json.dumps(messages)}\n</messages>"


class MyAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = MyAgent()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        result = await self.agent.invoke(context)
        await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported")
