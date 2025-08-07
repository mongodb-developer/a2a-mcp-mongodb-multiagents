import logging
import asyncio

from a2a.server.agent_execution import AgentExecutor
from a2a.server.event_queue import RequestContext, EventQueue
from a2a.types import Message, Task, TaskStatusUpdateEvent, TaskArtifactUpdateEvent, Part, ErrorEvent
from a2a.message_utils import new_agent_text_message, get_text_from_message

# Assuming the agent.py is in the same directory
from .agent import SupportAgentLogic

logger = logging.getLogger(__name__)

class SupportAgentExecutor(AgentExecutor):
    """
    A2A AgentExecutor for the SupportAgent.
    It uses SupportAgentLogic to handle the core processing.
    """

    def __init__(self):
        super().__init__()
        self.agent_logic = SupportAgentLogic()
        logger.info("SupportAgentExecutor initialized.")

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """
        Handles incoming A2A requests (message/send, message/stream).
        """
        try:
            logger.info(
                f"SupportAgentExecutor: Received execute request. Message ID: {context.message.id}, "
                f"Task ID: {context.message.task_id}, Context ID: {context.message.context_id}"
            )

            query_text = get_text_from_message(context.message)
            if query_text is None:
                logger.warning("SupportAgentExecutor: No text found in incoming message.")
                event_queue.enqueue_event(ErrorEvent(code="INVALID_REQUEST", message="No text content in message."))
                return

            a2a_context_id = context.message.context_id
            a2a_task_id = context.message.task_id
            # from_agent_id = context.message.from_agent_id # Could be useful for logging or logic

            # 1. Load or create session (this also ensures task_id is part of the session state)
            session = await self.agent_logic._load_or_create_session(a2a_context_id, a2a_task_id)
            
            # 2. Add incoming user/client message to history
            # The role here is 'user' as it's the message *to* this agent.
            await self.agent_logic._add_to_history_and_save(
                a2a_context_id, "user", query_text, session
            )
            logger.info(f"SupportAgentExecutor: Added incoming user message to history for context {a2a_context_id}.")

            # 3. Process the message using the agent's core logic
            # The process_message method in SupportAgentLogic will handle:
            # - Deciding if it needs to call another agent (Scheduler)
            # - Interacting with the LLM
            # - Adding its *own* response to the history
            response_text, _, _ = await self.agent_logic.process_message(
                query=query_text,
                context_id=a2a_context_id,
                task_id=a2a_task_id,
                from_agent=context.message.from_agent_id or "client" # Identify caller
            )
            
            logger.info(f"SupportAgentExecutor: Logic processed. Response text: '{response_text}'")

            # 4. Enqueue the agent's response as an A2A Message
            agent_response_message = new_agent_text_message(
                text=response_text,
                context_id=a2a_context_id,
                task_id=a2a_task_id,
                # in_reply_to_message_id=context.message.id # Optional: link to incoming message
            )
            event_queue.enqueue_event(agent_response_message)
            logger.info(f"SupportAgentExecutor: Enqueued agent response for context {a2a_context_id}.")

            # For streaming, if the agent logic produced multiple parts or a stream,
            # you would enqueue multiple events here. For this simple conversion,
            # we assume process_message returns a single consolidated text response.

            # If the task is considered "complete" by this interaction,
            # you might enqueue a TaskStatusUpdateEvent(status="COMPLETED").
            # For now, we'll keep it simple.

        except Exception as e:
            logger.error(f"SupportAgentExecutor: Error during execution: {e}", exc_info=True)
            # Enqueue an ErrorEvent if something goes wrong
            error_event = ErrorEvent(
                code="INTERNAL_ERROR",
                message=str(e),
                task_id=context.message.task_id,
                context_id=context.message.context_id,
            )
            event_queue.enqueue_event(error_event)
        finally:
            # Ensure the queue is closed if no more events are expected for this request.
            # For message/send, this typically happens after the single response.
            # For message/stream, it happens when the stream is done.
            # The A2A server framework might handle closing based on request type.
            # If explicit control is needed: event_queue.close()
            pass


    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """
        Handles requests to cancel an ongoing task.
        """
        logger.warning(
            f"SupportAgentExecutor: Received cancel request for Task ID: {context.message.task_id}. "
            "Cancellation is not fully implemented in this version."
        )
        # Implement cancellation logic if applicable (e.g., stop LLM generation, notify other agents)
        # For now, just acknowledge and send an error or a status update.
        event_queue.enqueue_event(
            ErrorEvent(
                code="NOT_SUPPORTED",
                message="Cancellation is not fully supported by this agent.",
                task_id=context.message.task_id,
                context_id=context.message.context_id,
            )
        )
        # Or, if you can confirm cancellation:
        # event_queue.enqueue_event(
        #     TaskStatusUpdateEvent(
        #         task_id=context.message.task_id,
        #         context_id=context.message.context_id,
        #         status="CANCELLED",
        #     )
        # )

if __name__ == '__main__':
    # This executor is meant to be run by an A2A server, not directly.
    # For testing, you'd typically set up a minimal A2A server
    # or use client tools to send messages to it.
    print("SupportAgentExecutor defined. To use it, integrate with an A2A server application.")
    # Example of how one might test the executor with dummy context/queue (simplified):
    # This is highly simplified and doesn't represent full A2A flow.
    async def test_executor():
        logging.basicConfig(level=logging.INFO)
        executor = SupportAgentExecutor()
        
        class DummyMessage:
            def __init__(self, id, task_id, context_id, text, from_agent_id=None):
                self.id = id
                self.task_id = task_id
                self.context_id = context_id
                self.parts = [Part(type="text", text=text)] if text else []
                self.from_agent_id = from_agent_id
                self.role = "user" # Assuming incoming is from user/client

        class DummyRequestContext:
            def __init__(self, message):
                self.message = message
                # Other fields like auth_token, client_info etc. would be here

        class DummyEventQueue:
            def __init__(self):
                self.events = []
            def enqueue_event(self, event):
                self.events.append(event)
                logger.info(f"DummyEventQueue: Event enqueued: {event.model_dump_json(indent=2)}")
            def close(self):
                logger.info("DummyEventQueue: Closed.")

        print("\n--- Testing SupportAgentExecutor ---")
        
        # Test 1: Basic query
        msg1 = DummyMessage("msg1", "task_exec_1", "ctx_exec_1", "Hello, I need help!")
        req_ctx1 = DummyRequestContext(msg1)
        queue1 = DummyEventQueue()
        await executor.execute(req_ctx1, queue1)
        print(f"Events for msg1: {len(queue1.events)}")
        if queue1.events:
            print(f"First event content: {get_text_from_message(queue1.events[0]) if isinstance(queue1.events[0], Message) else queue1.events[0]}")

        # Test 2: Query that might go to scheduler
        msg2 = DummyMessage("msg2", "task_exec_2", "ctx_exec_1", "Can you schedule a meeting for me?") # Same context
        req_ctx2 = DummyRequestContext(msg2)
        queue2 = DummyEventQueue()
        await executor.execute(req_ctx2, queue2)
        print(f"Events for msg2: {len(queue2.events)}")
        if queue2.events:
            print(f"First event content: {get_text_from_message(queue2.events[0]) if isinstance(queue2.events[0], Message) else queue2.events[0]}")

    # asyncio.run(test_executor()) # Commented out as it requires .env and running dependent services
    print("To test executor properly, run it within an A2A server and use an A2A client.")
