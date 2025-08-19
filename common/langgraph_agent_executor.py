# common/langgraph_agent_executor.py

import logging
from a2a.types import TextPart, TaskState, Part
from a2a.server.agent_execution import AgentExecutor
from a2a.server.tasks import TaskUpdater
from .session_thread_mapper import get_session_mapper

logger = logging.getLogger(__name__)

class LangGraphAgentExecutor(AgentExecutor):
    def __init__(self, agent, card):
        self.agent = agent
        self._card = card

    async def execute(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if not context.current_task:
            updater.submit()
        updater.start_work()

        # Extract A2A session context for proper thread mapping
        session_mapper = get_session_mapper()
        
        # Extract user_id and session_id from A2A context
        # Use context_id as session identifier (A2A protocol standard)
        user_id = getattr(context, 'user_id', 'default_user')
        session_id = context.context_id or 'default_session'
        
        # Get consistent thread ID based on A2A session context
        thread_id = session_mapper.get_thread_id(user_id, session_id)
        
        print(f"DEBUG: A2A Context - user_id: {user_id}, session_id: {session_id}")
        print(f"DEBUG: Mapped to LangGraph thread_id: {thread_id}")
        print(f"DEBUG: A2A task_id: {context.task_id}")
        print(f"DEBUG: A2A context_id: {context.context_id}")

        # Enhanced debugging for message extraction
        print(f"DEBUG: Context type: {type(context)}")
        print(f"DEBUG: Context message type: {type(context.message)}")
        print(f"DEBUG: Context message: {context.message}")
        
        if hasattr(context.message, 'parts'):
            print(f"DEBUG: Message parts: {context.message.parts}")
            if context.message.parts:
                for i, part in enumerate(context.message.parts):
                    print(f"DEBUG: Part {i}: {part}")
        
        # CORRECTED: Improved query text extraction
        query_text = ""
        if hasattr(context.message, 'parts') and context.message.parts:
            # Join the text from all parts of the message
            # FIX: The Part object is a wrapper, the actual TextPart is in the `root` attribute.
            query_text = "".join(
                p.root.text for p in context.message.parts
                if hasattr(p, "root") and hasattr(p.root, "text") and p.root.text
            )
        elif hasattr(context.message, 'text'):
            query_text = context.message.text
        elif hasattr(context.message, 'content'):
            query_text = context.message.content
        
        # Fallback if text is still empty after attempting extraction
        if not query_text:
            logger.warning("Could not extract text from the message, using a default.")
            query_text = "Hello" # Use a generic greeting as a fallback
        
        print(f"Executing LangGraph agent with query: '{query_text}'")

        try:
            # Use consistent thread ID based on A2A session context
            config = {"configurable": {"thread_id": thread_id}}
            result = self.agent.invoke({"messages": [("user", query_text)]}, config=config)
            print(f"LangGraph agent result: {result}")

            # Extract the final response
            final_text = result["messages"][-1].content
          
            # Send it back
            if final_text:
                updater.add_artifact([TextPart(text=final_text)])
            updater.complete()

        except Exception as e:
            logger.exception("LangGraph agent execution failed")
            error_msg = updater.new_agent_message([TextPart(text=f"Error: {e}")])
            updater.update_status(TaskState.failed, message=error_msg, final=True)

    async def cancel(self, context, event_queue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        cancel_msg = updater.new_agent_message([TextPart(text="Cancellation not supported.")])
        updater.update_status(TaskState.failed, message=cancel_msg, final=True)