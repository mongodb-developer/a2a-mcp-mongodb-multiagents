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
from langchain_core.tools import tool
from typing import Any, Dict

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

def create_sync_mcp_tools(mcp_tools):
    """Convert async MCP tools to synchronous tools for LangGraph compatibility."""
    sync_tools = []
    
    for mcp_tool in mcp_tools:
        # Get tool metadata
        tool_name = mcp_tool.name
        tool_description = mcp_tool.description
        
        print(f"Processing MCP tool: {tool_name}")
        
        # Create a simple synchronous wrapper that calls the tool directly
        def create_sync_wrapper(async_tool):
            def sync_wrapper(*args, **kwargs):
                """Synchronous wrapper for async MCP tool."""
                try:
                    # Try to call the tool directly first (some tools might be sync)
                    if hasattr(async_tool, 'invoke'):
                        return async_tool.invoke(*args, **kwargs)
                    elif hasattr(async_tool, '_run'):
                        return async_tool._run(*args, **kwargs)
                    elif hasattr(async_tool, 'run'):
                        return async_tool.run(*args, **kwargs)
                    else:
                        # Fallback to async invocation
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                if hasattr(async_tool, 'ainvoke'):
                                    result = loop.run_until_complete(async_tool.ainvoke(kwargs))
                                elif hasattr(async_tool, 'arun'):
                                    result = loop.run_until_complete(async_tool.arun(*args, **kwargs))
                                else:
                                    result = f"No suitable method found for {async_tool.name}"
                                return result
                            finally:
                                loop.close()
                        except Exception as async_e:
                            return f"Error in async execution for {async_tool.name}: {str(async_e)}"
                except Exception as e:
                    return f"Error calling {async_tool.name}: {str(e)}"
            
            return sync_wrapper
        
        # Create the synchronous wrapper
        sync_func = create_sync_wrapper(mcp_tool)
        sync_func.__name__ = tool_name
        sync_func.__doc__ = tool_description
        
        # Use the @tool decorator without schema to avoid Gemini validation issues
        try:
            sync_tool = tool(sync_func)
            sync_tool.name = tool_name
            sync_tool.description = tool_description
            
            # Remove any problematic schema attributes that might cause Gemini issues
            if hasattr(sync_tool, 'args_schema'):
                sync_tool.args_schema = None
                
            sync_tools.append(sync_tool)
            print(f"✓ Successfully created sync wrapper for: {tool_name}")
        except Exception as e:
            print(f"✗ Failed to create sync wrapper for {tool_name}: {e}")
            print(f"   Tool attributes: {[attr for attr in dir(sync_tool) if not attr.startswith('_')]}")
            # Continue with other tools even if one fails
            continue
    
    return sync_tools

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

    # Get async MCP tools
    async_mcp_tools = asyncio.run(client.get_tools())
    print(f"Retrieved {len(async_mcp_tools)} MCP tools")
    
    # # Convert to synchronous tools
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
    
    # Use synchronous tools with the agent
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
