# scheduling_agent/main.py

import logging
import click
import uvicorn
import asyncio
import sys
import os
from dotenv import load_dotenv
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
# Import StructuredTool instead of Tool
from langchain.tools import StructuredTool
from pydantic import create_model, BaseModel, Field
from typing import Any, Dict, Type, Optional
from datetime import datetime
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

load_dotenv()
logging.basicConfig()

# Helper to map JSON schema types to Python types for Pydantic model creation
JSON_TYPE_TO_PYTHON_TYPE = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}

def create_sync_mcp_tools(mcp_tools):
    """
    Convert async MCP tools to synchronous, structured tools for LangGraph and
    Google Gemini API compatibility.
    """
    sync_tools = []

    for mcp_tool in mcp_tools:
        tool_name = mcp_tool.name
        tool_description = mcp_tool.description
        args_schema_dict = mcp_tool.args_schema

        print(f"Processing MCP tool: {tool_name}")

        arg_fields = {}
        required_fields = args_schema_dict.get('required', [])

        if 'properties' in args_schema_dict:
            for field_name, field_schema in args_schema_dict['properties'].items():
                json_type = field_schema.get("type")
                
                if json_type == "string" and field_schema.get("format") == "date-time":
                    python_type = datetime
                else:
                    python_type = JSON_TYPE_TO_PYTHON_TYPE.get(json_type, Any)

                is_required = field_name in required_fields

                if "default" in field_schema:
                    arg_fields[field_name] = (Optional[python_type], Field(default=field_schema["default"]))
                elif is_required:
                    arg_fields[field_name] = (python_type, ...)
                else:
                    arg_fields[field_name] = (Optional[python_type], Field(default=None))
        
        # This Pydantic model defines the arguments for the StructuredTool
        sync_args_model = create_model(f"{tool_name}Args", **arg_fields)

        # UPDATED WRAPPER: Accepts **kwargs as provided by StructuredTool
        def create_sync_wrapper(async_tool):
            def sync_wrapper(**kwargs):
                """
                Synchronous wrapper that executes the async MCP tool.
                StructuredTool handles validation and passes arguments as kwargs.
                """
                try:
                    # The kwargs are already validated by StructuredTool against the args_schema
                    invoke_args = kwargs
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                         future = asyncio.run_coroutine_threadsafe(
                             async_tool.ainvoke(invoke_args), loop
                         )
                         return future.result()
                    else:
                         return asyncio.run(async_tool.ainvoke(invoke_args))
                except RuntimeError:
                    # Fallback for environments where there's no running event loop
                    return asyncio.run(async_tool.ainvoke(kwargs))
                except Exception as e:
                    print(f"Error invoking async tool {async_tool.name}: {e}")
                    return f"Error: {e}"
            return sync_wrapper

        sync_func = create_sync_wrapper(mcp_tool)
        
        # UPDATED: Use StructuredTool instead of Tool
        decorated_tool = StructuredTool(
            name=tool_name,
            description=tool_description,
            args_schema=sync_args_model,
            func=sync_func,
        )
        
        sync_tools.append(decorated_tool)
        print(f"✓ Successfully created sync wrapper for: {tool_name}")

    return sync_tools


@click.command()
@click.option("--host", "host", default="localhost")
@click.option("--port", "port", default=11002) # Default port for this agent
def main(host, port):

    client = MultiServerMCPClient(
        { "scheduling" : {
            "url": os.environ.get("MEETING_SCHEDULE_MCP", "http://localhost:8000/sse"),
            "transport": "sse"
        }
        }
    )

    async_mcp_tools = asyncio.run(client.get_tools())
    print(f"Retrieved {len(async_mcp_tools)} MCP tools")
    
    sync_tools = create_sync_mcp_tools(async_mcp_tools)
    print(f"Created {len(sync_tools)} synchronous tool wrappers")
    
    skill = AgentSkill(
        id='scheduling_management',
        name='Schedule meetings and manage calendars',
        description='The agent will help users schedule meetings, manage calendar appointments, and interact with scheduling systems.',
        tags=['scheduling', 'calendar', 'meetings'],
        examples=['Schedule a meeting for next Tuesday', 'What meetings do I have today?', 'Cancel my 3pm appointment'],
    )
    
    agent_card = AgentCard(
        name="Scheduling Agent",
        description="Schedules meetings and manages calendars.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
    )
    
    agent = create_agent(
        system_prompt="You are a calendar agent to support users in scheduling appointments, managing time slots, and interacting with the scheduling system.", 
        tools=sync_tools
    )
    
    agent_executor = LangGraphAgentExecutor(agent, agent_card)
    handler = DefaultRequestHandler(agent_executor=agent_executor, task_store=InMemoryTaskStore())
    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
    uvicorn.run(app.build(), host=host, port=port)

if __name__ == "__main__":
    main()