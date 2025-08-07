import logging
import click
import uvicorn
import asyncio
import sys
import os
from dotenv import load_dotenv
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from langchain_mcp_adapters.client import MultiServerMCPClient

from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from common.langgraph_agent import create_agent
from common.langgraph_agent_executor import LangGraphAgentExecutor

## mcp langchain


load_dotenv()
logging.basicConfig()

@click.command()
@click.option("--host", "host", default="localhost")
@click.option("--port", "port", default=11002)
def main(host, port):

    client = MultiServerMCPClient(
        { "scheduling" : {
            "url": os.environ.get("MEETING_SCHEDULE_MCP", "http://localhost:8000/sse"),
            "transport": "sse"
        }
        }
    )

    tools = asyncio.run(client.get_tools())
    agent_card = AgentCard(
        name="Scheduling Agent",
        description="Schedules meetings and manages calendars.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[],
    )
    agent = create_agent(system_prompt="You are a calendar agent to support users in scheduling appointments, managing time slots, and interacting with the scheduling system.", tools=tools)
    agent_executor = LangGraphAgentExecutor(agent, agent_card)
    handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=InMemoryTaskStore())
    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
    uvicorn.run(app.build(), host=host, port=port)

if __name__ == "__main__":
    main()
