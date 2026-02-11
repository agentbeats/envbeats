import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore


from my_agent import MyAgentExecutor, my_agent_card, my_agent_port


def main():
    request_handler = DefaultRequestHandler(
        agent_executor=MyAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(
        agent_card=my_agent_card,
        http_handler=request_handler,
    )

    uvicorn.run(server.build(), host="0.0.0.0", port=my_agent_port)


main()
