import logging
from a2a.types import TextPart, TaskState
from a2a.server.agent_execution import AgentExecutor
from a2a.server.tasks import TaskUpdater

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

        # Enhanced debugging for message extraction
        print(f"DEBUG: Context type: {type(context)}")
        print(f"DEBUG: Context message type: {type(context.message)}")
        print(f"DEBUG: Context message: {context.message}")
        print(f"DEBUG: Context message attributes: {dir(context.message)}")
        
        if hasattr(context.message, 'parts'):
            print(f"DEBUG: Message parts: {context.message.parts}")
            if context.message.parts:
                for i, part in enumerate(context.message.parts):
                    print(f"DEBUG: Part {i}: {part}")
                    print(f"DEBUG: Part {i} attributes: {dir(part)}")
        
        # Improved query text extraction
        query_text = ""
        if hasattr(context.message, 'parts') and context.message.parts:
            query_text = "".join(
                p.text for p in context.message.parts
                if hasattr(p, "text") and p.text
            )
        elif hasattr(context.message, 'text'):
            query_text = context.message.text
        elif hasattr(context.message, 'content'):
            query_text = context.message.content
        
        # Fallback to string representation if still empty
        if not query_text:
            query_text = str(context.message) if context.message else "Hello"
        
        print(f"Executing LangGraph agent with query: '{query_text}'")

        try:
            # 1. Invoke the LangGraph agent synchronously
            config = {"configurable": {"thread_id": context.task_id}}
            result = self.agent.invoke({"messages": [("user", query_text)]}, config=config)
            print (f"LangGraph agent result: {result}")

            # 2. Extract the final response
            final_text = result["messages"][-1].content
          
            # 3. Send it back
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