"""
Alternative async-first approach for the Gradio app
Use this if you continue to have event loop issues
"""

import gradio as gr
from typing import List, AsyncIterator
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from adk_agent.agent import root_agent as routing_agent
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()
from google.adk.events import Event
from google.genai import types
from pprint import pformat
import asyncio
import traceback
import uuid
import threading
import concurrent.futures

APP_NAME = "routing_app"
USER_ID = "default_user"
SESSION_SERVICE = InMemorySessionService()

ROUTING_AGENT_RUNNER = Runner(
    agent=routing_agent,
    app_name=APP_NAME,
    session_service=SESSION_SERVICE,
    memory_service=InMemoryMemoryService(),
)

# Global executor for handling async operations
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

def get_or_create_session_id(session_state):
    """Get existing session ID or create new one"""
    if 'session_id' not in session_state:
        session_state['session_id'] = str(uuid.uuid4())
        session_state['initialized'] = False
    return session_state['session_id']

async def get_response_from_agent_async(
    message: str,
    history: List[gr.ChatMessage],
    session_state: dict 
) -> str:
    """Get response from host agent - pure async version."""
    try:
        session_id = get_or_create_session_id(session_state)
        
        # Initialize session if not done already
        if not session_state.get('initialized', False):
            await SESSION_SERVICE.create_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=session_id
            )
            session_state['initialized'] = True

        events_iterator: AsyncIterator[Event] = ROUTING_AGENT_RUNNER.run_async(
            user_id=USER_ID,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        )

        response_parts = []
        
        try:
            async for event in events_iterator:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.function_call:
                            formatted_call = f"```python\n{pformat(part.function_call.model_dump(exclude_none=True), indent=2, width=80)}\n```"
                            response_parts.append(f"🛠️ **Tool Call: {part.function_call.name}**\n{formatted_call}")
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
                            response_parts.append(f"⚡ **Tool Response from {part.function_response.name}**\n{formatted_response}")
                
                if event.is_final_response():
                    final_response_text = ""
                    if event.content and event.content.parts:
                        final_response_text = "".join(
                            [p.text for p in event.content.parts if p.text]
                        )
                    elif event.actions and event.actions.escalate:
                        final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
                    if final_response_text:
                        response_parts.append(final_response_text)
                    break
                    
        except Exception as iter_error:
            print(f"Error during event iteration: {iter_error}")
            traceback.print_exc()
            return f"Error during agent processing: {str(iter_error)}"
        
        return "\n\n".join(response_parts) if response_parts else "No response received."
        
    except Exception as e:
        print(f"Error in get_response_from_agent_async (Type: {type(e)}): {e}")
        print(f"Session ID being used: {session_state.get('session_id', 'Not set')}")
        traceback.print_exc()
        return f"An error occurred while processing your request: {str(e)}"

def run_in_thread(coro):
    """Run coroutine in a new thread with its own event loop"""
    def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    # Run in thread pool to avoid blocking
    future = executor.submit(thread_target)
    return future.result(timeout=60)  # 60 second timeout

def chat_handler_threaded(message: str, history: List[gr.ChatMessage], session_state: dict) -> str:
    """Thread-safe wrapper for async chat function"""
    try:
        return run_in_thread(
            get_response_from_agent_async(message, history, session_state)
        )
    except concurrent.futures.TimeoutError:
        return "Request timed out. Please try again."
    except Exception as e:
        print(f"Error in chat_handler_threaded: {e}")
        traceback.print_exc()
        return f"Error processing request: {str(e)}"

def main():
    """Main gradio app."""
    print("ADK session will be created on first request.")

    with gr.Blocks(theme=gr.themes.Ocean(), title="A2A Host Agent with Logo") as demo:
        session_state = gr.State({})
        
        gr.Image(
            "static/a2a.png",
            width=100,
            height=100,
            scale=0,
            show_label=False,
            show_download_button=False,
            container=False,
            show_fullscreen_button=False,
        )
        
        gr.ChatInterface(
            lambda msg, hist: chat_handler_threaded(msg, hist, session_state.value),
            title="A2A Host Agent",
            description="This assistant can help you to check support issues and find schedule slots for Biggly Bobsy Watches",
        )

    print("Launching Gradio interface...")
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=8083,
    )
    print("Gradio application has been shut down.")

if __name__ == "__main__":
    main()
