# common/langgraph_agent.py

import os
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from .langgraph_tools import schedule_meeting, get_free_slots, add_potential_slot

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




def prompt(state, store):
    """Prepare the messages for the LLM by injecting memories."""
    memories = store.search(
        ("memories",),
        query=state["messages"][-1].content,
    )
    system_msg = f"""You are an assistant that have access to tools and memory

## Memories
<memories>
{memories}
</memories>
"""
    return [{"role": "system", "content": system_msg}, *state["messages"]]

def create_agent(system_prompt=None, tools=None):
    """
    Creates a LangGraph ReAct agent backed by OpenAI.
    Requires OPENAI_API_KEY in your environment.
    """
    client = MongoClient(os.environ["MONGODB_URI"])  # Ensure MONGO_URI is set in your environment
    db = client["memories"]
    collection = db["a2a_memory_store"]


    # Create store directly
    store = MongoDBStore(collection=collection,index_config=VectorIndexConfig(fields=None, filters=None ,
                                            dims=1024, embed=VoyageAIEmbeddings(model="voyage-3.5")  # Pass an instance of VoyageAIEmbeddings
                                        ) )

    checkpointer = MongoDBSaver(client, db_name="memories", collection_name="a2a_thread_checkpoints")


    # 1. Initialize the OpenAI chat model
    # llm = ChatOpenAI(
    #     model_name="gpt-4o",    # or "gpt-4" if you have access
    #     temperature=0.0,
    #     openai_api_key=os.environ["OPENAI_API_KEY"],
    # )

    llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    max_tokens=None,
    timeout=None,
    # other params...
)


    # client = MultiServerMCPClient(
    #     {
           
    #         "scheduler": {
    #             # Ensure you start your scheduler server on port 8000
    #             "url": "http://localhost:8001/sse",
    #             "transport": "sse",
    #         }
    #     }
    # )
    # tools = asyncio.run(client.get_tools())

    tools = tools or []

    # 2. Define your tools (unchanged)
    tools.append(create_manage_memory_tool(namespace=("memories")))

    # 3. System prompt
    prompt = (
        system_prompt or
        "You are a specialized assistant for smart watches and calendar scheduling. "
        "Use the provided tools to answer questions, retrieve information, or schedule meetings."
    )

    # 4. Build the ReAct agent
    return create_react_agent(model=llm, tools=tools, prompt=prompt, store=store, checkpointer=checkpointer)