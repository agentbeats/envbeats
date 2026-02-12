import json
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard
from a2a.utils import new_agent_text_message
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult
from openenv.core.env_client import StepResult
from openenv.core.env_server.types import State
from echo_env import EchoAction, EchoObservation

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


async def call_mcp_tool(
    url: str,
    tool_name: str,
    arguments: dict | None = None,
    bearer_token: str | None = None,
) -> CallToolResult:
    """Call an MCP tool and return the result."""
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None
    async with streamablehttp_client(url=url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"Calling tool {tool_name} with arguments {arguments}")
            result = await session.call_tool(tool_name, arguments=arguments)
            print(f"Got tool result: {result}")
            return result


def think(
    step_count: int, step_results: list[StepResult[EchoObservation]]
) -> EchoAction | None:
    """Mock thinking: decide the next action based on past observations.

    Returns an EchoAction for the next step, or None to stop.
    """
    if step_count == 0:
        return EchoAction(message="This is a gym agent calling step.")
    elif step_count == 1:
        return EchoAction(
            message="Why did the agent cross the road? To optimize the reward!"
        )
    return None


class MCPEchoEnv:
    """Minimal MCP-backed env client, mimicking the EchoEnv interface."""

    def __init__(self, mcp_url: str, bearer_token: str | None = None):
        self.mcp_url = mcp_url
        self.bearer_token = bearer_token

    async def step(self, action: EchoAction) -> StepResult[EchoObservation]:
        result = await call_mcp_tool(
            self.mcp_url,
            "step",
            {"action": action.model_dump()},
            bearer_token=self.bearer_token,
        )
        result_dict = json.loads(result.content[0].text)
        return StepResult(
            observation=EchoObservation(**result_dict["observation"]),
            reward=result_dict["reward"],
            done=result_dict["done"],
        )

    async def done(self) -> None:
        await call_mcp_tool(self.mcp_url, "done", {}, bearer_token=self.bearer_token)

    async def state(self) -> State:
        result = await call_mcp_tool(
            self.mcp_url, "state", {}, bearer_token=self.bearer_token
        )
        return State.model_validate_json(result.content[0].text)


class MyAgent:
    def __init__(
        self,
        mcp_url: str = "http://localhost:9000/mcp/",
        mcp_bearer_token: str | None = "456",
    ):
        self._inspector_proc = None
        self.env = MCPEchoEnv(mcp_url, bearer_token=mcp_bearer_token)

    async def invoke(self, context: RequestContext) -> str:
        user_input = context.get_user_input()
        tags = parse_tags(user_input)
        reset_step_result_str = tags["StepResult"]
        print("Received task:\n", user_input)
        print("Reset StepResult:\n", reset_step_result_str)

        # GYM-style loop, mimicking:
        #   result = env.step(EchoAction(message="Hello, World!"))
        #   print(result.echoed_message)
        step_results = []
        for step_count in range(10):
            action = think(step_count, step_results)
            if action is None:
                break
            step_result = await self.env.step(action)
            step_results.append(step_result)
            print(f"Step {step_count}: {step_result.observation.echoed_message}")

        await self.env.done()
        return f"Completed GYM loop with {len(step_results)} steps."


class MyAgentExecutor(AgentExecutor):
    def __init__(self):
        self.agent = MyAgent(
            mcp_url="http://localhost:9000/mcp/",
            mcp_bearer_token="456",
        )

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        result = await self.agent.invoke(context)
        await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported")


def main():
    agent_executor = MyAgentExecutor()

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(
        agent_card=my_agent_card,
        http_handler=request_handler,
    )

    uvicorn.run(server.build(), host="0.0.0.0", port=my_agent_port)


main()
