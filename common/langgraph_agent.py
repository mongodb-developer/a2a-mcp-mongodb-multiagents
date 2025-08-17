# common/langgraph_agent.py

import os
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.utils.config import get_store
from langmem import create_manage_memory_tool

#from langchain_openai.embeddings import OpenAIEmbeddings  # Import OpenAIEmbeddings

from langchain_voyageai import VoyageAIEmbeddings  # Import VoyageAIEmbeddings

from pymongo import MongoClient
from langgraph.store.mongodb.base import MongoDBStore, VectorIndexConfig # Import MongoDBStore
from langchain_core.tools import tool # Import tool decorator
#from langchain_mcp_adapters.client import MultiServerMCPClient



# 2. Initialize the MongoDB checkpointer for conversation history




def create_memory_enhanced_prompt(system_prompt=None):
    """Create a memory-enhanced prompt function that injects memories into the conversation."""
    base_system_prompt = (
        system_prompt or
        "You are a specialized assistant for smart watches and calendar scheduling. "
        "Use the provided tools to answer questions, retrieve information, or schedule meetings."
    )
    
    def prompt_with_memory(state, *, store):
        """Prepare the messages for the LLM by injecting memories."""
        try:
            # Get the latest user message for memory search
            latest_message = state["messages"][-1]
            query_text = ""
            
            # Extract text content from the message
            if hasattr(latest_message, 'content'):
                query_text = latest_message.content
            elif isinstance(latest_message, tuple) and len(latest_message) > 1:
                query_text = latest_message[1]  # For ("user", "message") format
            elif isinstance(latest_message, dict) and 'content' in latest_message:
                query_text = latest_message['content']
            
            # Search for relevant memories
            memories = store.search(
                ("memories",),
                query=query_text,
                limit=5  # Limit to most relevant memories
            )
            
            # Format memories for injection
            memory_text = ""
            if memories:
                memory_items = []
                for memory in memories:
                    if hasattr(memory, 'value') and isinstance(memory.value, dict):
                        # Handle langmem memory format
                        if 'text' in memory.value:
                            memory_items.append(f"- {memory.value['text']}")
                        else:
                            memory_items.append(f"- {memory.value}")
                    elif hasattr(memory, 'value'):
                        memory_items.append(f"- {memory.value}")
                    elif isinstance(memory, dict) and 'value' in memory:
                        memory_items.append(f"- {memory['value']}")
                    else:
                        memory_items.append(f"- {str(memory)}")
                
                if memory_items:
                    memory_text = f"""

## Relevant Memories
<memories>
{chr(10).join(memory_items)}
</memories>
"""
            
            # Create enhanced system message
            enhanced_system_msg = f"""{base_system_prompt}{memory_text}

Remember to use the manage_memory tool to store important information from conversations for future reference."""
            
            return [{"role": "system", "content": enhanced_system_msg}] + state["messages"]
            
        except Exception as e:
            print(f"Warning: Memory injection failed: {e}")
            # Fallback to basic system prompt
            return [{"role": "system", "content": base_system_prompt}] + state["messages"]
    
    return prompt_with_memory

def create_agent(system_prompt=None, tools=None):
    """
    Creates a LangGraph ReAct agent with memory integration.
    Requires MONGODB_URI and VOYAGE_API_KEY in your environment.
    """
    client = MongoClient(os.environ["MONGODB_URI"])
    db = client["agent_memory"]
    collection = db["a2a_memory_store"]

    # Create store directly
    store = MongoDBStore(
        collection=collection,
        index_config=VectorIndexConfig(
            fields=None, 
            filters=None,
            dims=1024, 
            embed=VoyageAIEmbeddings(model="voyage-3.5")
        ),
        auto_index_timeout=70
    )

    checkpointer = MongoDBSaver(client, db_name="agent_memory", collection_name="a2a_thread_checkpoints")

    # Initialize the Gemini chat model
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        max_tokens=None,
        timeout=None,
    )

    tools = tools or []

    # Add memory management tool
    tools.append(create_manage_memory_tool(namespace=("memories",)))

    # Create memory-enhanced prompt function
    memory_prompt_func = create_memory_enhanced_prompt(system_prompt)

    print("DEBUG: Creating LangGraph agent with memory integration")
    print(f"DEBUG: Store type: {type(store)}")
    print(f"DEBUG: Checkpointer type: {type(checkpointer)}")
    print(f"DEBUG: Tools count: {len(tools)}")

    # Build the ReAct agent with memory-enhanced prompt
    return create_react_agent(
        model=llm, 
        tools=tools, 
        prompt=memory_prompt_func,  # Use prompt parameter for memory injection
        store=store, 
        checkpointer=checkpointer
    )
