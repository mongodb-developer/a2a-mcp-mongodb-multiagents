"""
Copyright 2025 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import gradio as gr
from typing import List, AsyncIterator, Dict, Any
from adk_agent.agent import (
    root_agent as routing_agent,
)  
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from dotenv import load_dotenv
import os
from pathlib import Path
import aiohttp
import json

# Assuming memory module is in ../memory relative to host_agent directory
# Adjust the path as necessary if memory is located elsewhere in a2a-adk-app
# try:
# except ImportError:
#     # Fallback if running script directly from host_agent and memory is a sibling directory
#     import sys
#     sys.path.append(str(Path(__file__).resolve().parent.parent))
#     from memory.mongodb_memory import get_memory_instance

# Load environment variables from .env file in the current directory (host_agent)
load_dotenv()
from google.adk.events import Event
from google.genai import types
from pprint import pformat
import asyncio
import traceback  # Import the traceback module

APP_NAME = "routing_app"
USER_ID = "default_user"
SESSION_ID = "default_session"

# Initialize MongoDB Memory
# The MONGODB_URI should be in host_agent/.env
try:
    print("MongoDBMemory initialized for Host Agent.")
except ValueError as e:
    print(f"Failed to initialize MongoDBMemory for Host Agent: {e}")
    mongo_memory = None

SESSION_SERVICE = InMemorySessionService() # ADK's session service
ROUTING_AGENT_RUNNER = Runner(
    agent=routing_agent, # This agent's internal logic will need to use mongo_memory
    app_name=APP_NAME,
    session_service=SESSION_SERVICE,
)

# Agent URLs for health checking
AGENT_URLS = [
    "http://localhost:8001",
    "http://localhost:8002"
]

async def fetch_agent_health(url: str) -> Dict[str, Any]:
    """Fetch agent health status from .well-known/agent.json endpoint."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/.well-known/agent.json", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "status": "healthy",
                        "url": url,
                        "name": data.get("name", "Unknown Agent"),
                        "description": data.get("description", "No description available"),
                        "version": data.get("version", "Unknown"),
                        "capabilities": data.get("capabilities", {}),
                        "skills": data.get("skills", [])
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "url": url,
                        "name": "Unknown Agent",
                        "description": f"HTTP {response.status}",
                        "version": "Unknown",
                        "capabilities": {},
                        "skills": []
                    }
    except Exception as e:
        return {
            "status": "offline",
            "url": url,
            "name": "Unknown Agent",
            "description": f"Connection failed: {str(e)}",
            "version": "Unknown",
            "capabilities": {},
            "skills": []
        }

async def get_all_agent_health() -> List[Dict[str, Any]]:
    """Get health status for all agents."""
    tasks = [fetch_agent_health(url) for url in AGENT_URLS]
    return await asyncio.gather(*tasks)


async def get_response_from_agent(
    message: str,
    history: List[gr.ChatMessage],
) -> AsyncIterator[gr.ChatMessage]:
    """Get response from host agent."""
    try:
        events_iterator: AsyncIterator[Event] = ROUTING_AGENT_RUNNER.run_async(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        )

        async for event in events_iterator:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call:
                        formatted_call = f"```python\n{pformat(part.function_call.model_dump(exclude_none=True), indent=2, width=80)}\n```"
                        yield gr.ChatMessage(
                            role="assistant",
                            content=f"🛠️ **Tool Call: {part.function_call.name}**\n{formatted_call}",
                        )
                    elif part.function_response:
                        response_content = part.function_response.response
                        if (
                            isinstance(response_content, dict)
                            and "response" in response_content
                        ):
                            formatted_response_data = response_content["response"]
                        else:
                            formatted_response_data = response_content
                        formatted_response = f"```json\n{pformat(formatted_response_data, indent=2, width=80)}\n```"
                        yield gr.ChatMessage(
                            role="assistant",
                            content=f"⚡ **Tool Response from {part.function_response.name}**\n{formatted_response}",
                        )
            if event.is_final_response():
                final_response_text = ""
                if event.content and event.content.parts:
                    final_response_text = "".join(
                        [p.text for p in event.content.parts if p.text]
                    )
                elif event.actions and event.actions.escalate:
                    final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
                if final_response_text:
                    yield gr.ChatMessage(role="assistant", content=final_response_text)
                break
    except Exception as e:
        print(f"Error in get_response_from_agent (Type: {type(e)}): {e}")
        traceback.print_exc()  # This will print the full traceback
        yield gr.ChatMessage(
            role="assistant",
            content="An error occurred while processing your request. Please check the server logs for details.",
        )


def format_agent_status(agent_data: Dict[str, Any]) -> str:
    """Format agent data for display in a tile."""
    status_emoji = {
        "healthy": "🟢",
        "unhealthy": "🟡", 
        "offline": "🔴"
    }
    
    emoji = status_emoji.get(agent_data["status"], "⚪")
    
    # Format skills section
    skills_section = ""
    if agent_data.get("skills"):
        skills_list = []
        for skill in agent_data['skills'][:2]:  # Show max 2 skills
            skill_name = skill.get('name', 'Unnamed')
            skills_list.append(f"• {skill_name}")
        
        skills_section = f"\n\n**🛠️ Skills:**\n" + "\n".join(skills_list)
        
        if len(agent_data['skills']) > 2:
            skills_section += f"\n• *+{len(agent_data['skills']) - 2} more skills*"
    
    # Format capabilities section
    capabilities_section = ""
    if agent_data.get("capabilities"):
        caps = agent_data["capabilities"]
        streaming_icon = "✅" if caps.get("streaming", False) else "❌"
        
        input_modes = caps.get("defaultInputModes", [])
        output_modes = caps.get("defaultOutputModes", [])
        
        capabilities_section = f"""
**⚙️ Capabilities:**
• Streaming: {streaming_icon}
• Input: {', '.join(input_modes) if input_modes else 'N/A'}
• Output: {', '.join(output_modes) if output_modes else 'N/A'}"""
    
    # Status styling
    status_text = agent_data['status'].title()
    if agent_data['status'] == 'healthy':
        status_display = f"🟢 **{status_text}**"
    elif agent_data['status'] == 'unhealthy':
        status_display = f"🟡 **{status_text}**"
    else:
        status_display = f"🔴 **{status_text}**"
    
    return f"""### {emoji} {agent_data['name']}
**Version:** `{agent_data['version']}`  
**Endpoint:** `{agent_data['url']}`  
**Status:** {status_display}

**📝 Description:**  
*{agent_data['description']}*{skills_section}{capabilities_section}

---"""

async def refresh_agent_status():
    """Refresh and return agent status for all agents."""
    agent_healths = await get_all_agent_health()
    return [format_agent_status(agent) for agent in agent_healths]

async def main():
    """Main gradio app."""
    print("Creating ADK session...")
    await SESSION_SERVICE.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    print("ADK session created successfully.")

    with gr.Blocks(theme=gr.themes.Ocean(), title="A2A Host Agent with Logo") as demo:
        gr.Image(
            str(Path(__file__).parent / "static" / "a2a.png"),
            width=100,
            height=100,
            scale=0,
            show_label=False,
            show_download_button=False,
            container=False,
            show_fullscreen_button=False,
        )
        
        chat_interface = gr.ChatInterface(
            get_response_from_agent,
            title="A2A Host Agent",  # Title can be handled by Markdown above
            description="This assistant can help you to check support issues and find schedule slots for Aura Watches",
        )
        
        gr.Markdown("## 🖥️ Agent Status Dashboard")
        
        with gr.Row(equal_height=True):
            with gr.Column(scale=1):
                agent1_status = gr.Markdown("🔄 Loading Agent 1...", container=True)
            with gr.Column(scale=1):
                agent2_status = gr.Markdown("🔄 Loading Agent 2...", container=True)
        
        refresh_btn = gr.Button("🔄 Refresh Agent Status", variant="secondary", size="sm")
        
        async def update_status():
            statuses = await refresh_agent_status()
            return statuses[0], statuses[1]
        
        refresh_btn.click(
            update_status,
            outputs=[agent1_status, agent2_status]
        )
        
        # Load initial status
        demo.load(
            update_status,
            outputs=[agent1_status, agent2_status]
        )

    print("Launching Gradio interface...")
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=8083,
    )
    print("Gradio application has been shut down.")

if __name__ == "__main__":
    asyncio.run(main())