# A2A MCP App - LangGraph Agent Architecture with Advanced Memory

> ### This repo is built on top of Google's a2a code example with LangGraph integration.
> Code origin: https://github.com/google-a2a/a2a-samples/tree/main/samples/a2a-adk-app
>

This project demonstrates an Agent-to-Agent (A2A) communication setup featuring **LangGraph ReAct agents** with advanced memory capabilities. The system includes a routing agent, support/scheduling agents powered by LangGraph, and a dedicated MCP server for managing meeting schedules. MongoDB serves as the backbone for both persistent data storage and sophisticated agent memory management using **langmem**, **MongoDBSaver**, and **MongoDBStore**.

## Agent Interaction Flow

```mermaid
graph TD
    User[User] --> UIAgent["Host Agent / UI"]
    UIAgent --> RoutingAgent["Routing Agent (Conceptual)"]
    RoutingAgent -- "Scheduling Task" --> LangGraphAgent["Support/Scheduling Agent (LangGraph ReAct)"]
    LangGraphAgent -->|"Uses Tools via MCP"| SchedulingAgentMCP["SchedulingAgentMCP (FastMCP Server)"]
    LangGraphAgent -->|"Memory Management"| LangMemTool["langmem Memory Tool"]
    LangGraphAgent -->|"Checkpoints"| MongoDBSaver["MongoDBSaver (Conversation History)"]
    LangGraphAgent -->|"Vector Memory"| MongoDBStore["MongoDBStore (Semantic Memory)"]
    SchedulingAgentMCP -- "CRUD Operations" --> MongoDBDatastore["(MongoDB: Meeting Slots Data)"]
    LangMemTool --> MongoDBStore
    MongoDBSaver --> MongoDBMemoryDB["(MongoDB: Thread Checkpoints)"]
    MongoDBStore --> MongoDBMemoryDB2["(MongoDB: Vector Memory Store)"]

    subgraph "LangGraph Agents"
        LangGraphAgent
        LangMemTool
    end

    subgraph "MCP Services"
        SchedulingAgentMCP
    end

    subgraph "Memory Infrastructure"
        MongoDBSaver
        MongoDBStore
    end

    style User fill:#f9f,stroke:#333,stroke-width:2px
    style UIAgent fill:#bbf,stroke:#333,stroke-width:2px
    style RoutingAgent fill:#lightgrey,stroke:#333,stroke-width:2px
    style LangGraphAgent fill:#9f9,stroke:#333,stroke-width:2px
    style SchedulingAgentMCP fill:#9cf,stroke:#333,stroke-width:2px
    style MongoDBDatastore fill:#ff9,stroke:#333,stroke-width:2px
    style MongoDBSaver fill:#f96,stroke:#333,stroke-width:2px
    style MongoDBStore fill:#f96,stroke:#333,stroke-width:2px
    style LangMemTool fill:#6f9,stroke:#333,stroke-width:2px
    style MongoDBMemoryDB fill:#ff9,stroke:#333,stroke-width:2px
    style MongoDBMemoryDB2 fill:#ff9,stroke:#333,stroke-width:2px
```

1.  **User Interaction**: A user interacts with a primary interface or a "host" agent.
2.  **Routing Agent (Conceptual)**: The initial request is (conceptually) processed by a routing agent. This agent determines the nature of the request and forwards it to the appropriate specialized agent. For scheduling-related tasks, it routes to the LangGraph Support/Scheduling Agent.
3.  **LangGraph Support/Scheduling Agent**:
    *   This agent is built using **LangGraph's ReAct architecture** with OpenAI GPT-4o as the language model.
    *   Features advanced memory capabilities through multiple MongoDB integrations.
    *   Uses **langmem** for intelligent memory management and retrieval.
    *   Maintains conversation history through **MongoDBSaver** checkpoints.
    *   Stores semantic memories in **MongoDBStore** with vector embeddings.
    *   Connects to the `SchedulingAgentMCP` to perform scheduling actions.
4.  **SchedulingAgentMCP (FastMCP Server)**:
    *   This is a dedicated MCP server (implemented in `mcp/main.py` using the `fastmcp` library).
    *   It exposes tools specifically for managing meeting schedules (e.g., `schedule_meeting`, `get_free_slots`).
    *   It uses MongoDB as its backend data store to persist meeting slot information.

## MongoDB Integration Details

```mermaid
graph LR
    subgraph "SchedulingAgentMCP (FastMCP Server)"
        direction LR
        ToolSchedule["schedule_meeting Tool"] --> DBMongo1["(MongoDB: scheduling_db_fastmcp/meeting_slots)"]
        ToolGetSlots["get_free_slots Tool"] --> DBMongo1
        ToolAddSlot["add_potential_slot Tool"] --> DBMongo1
    end

    subgraph "LangGraph Agent Memory System"
        direction LR
        LangGraphAgent["LangGraph Agent"] -->|"Conversation Checkpoints"| MongoDBSaver["MongoDBSaver"]
        LangGraphAgent -->|"Vector Memory Search"| MongoDBStore["MongoDBStore"]
        LangGraphAgent -->|"Memory Management"| LangMemTool["langmem Tool"]
        MongoDBSaver --> DBMongo2["(MongoDB: memories/a2a_thread_checkpoints)"]
        MongoDBStore --> DBMongo3["(MongoDB: memories/a2a_memory_store)"]
        LangMemTool --> MongoDBStore
    end

    style ToolSchedule fill:#9cf,stroke:#333,stroke-width:2px
    style ToolGetSlots fill:#9cf,stroke:#333,stroke-width:2px
    style ToolAddSlot fill:#9cf,stroke:#333,stroke-width:2px
    style LangGraphAgent fill:#9f9,stroke:#333,stroke-width:2px
    style MongoDBSaver fill:#f96,stroke:#333,stroke-width:2px
    style MongoDBStore fill:#f96,stroke:#333,stroke-width:2px
    style LangMemTool fill:#6f9,stroke:#333,stroke-width:2px
    style DBMongo1 fill:#ff9,stroke:#333,stroke-width:2px
    style DBMongo2 fill:#ff9,stroke:#333,stroke-width:2px
    style DBMongo3 fill:#ff9,stroke:#333,stroke-width:2px
```

MongoDB serves multiple sophisticated purposes in this LangGraph-powered system:

### 1. Data Store for SchedulingAgentMCP

*   **Implementation**: The `fastmcp` server located at `mcp/main.py` directly interacts with a MongoDB database to manage meeting slots.
*   **Database & Collection**:
    *   Database Name: `scheduling_db_fastmcp` (configurable in `main.py`)
    *   Collection Name: `meeting_slots` (configurable in `main.py`)
*   **Functionality**:
    *   The `schedule_meeting` tool creates new meeting documents or updates existing ones in this collection.
    *   The `get_free_slots` tool queries this collection to find unbooked time slots.
    *   The `add_potential_slot` tool allows for adding new slot documents directly.
*   **Data Model**: Meeting slots are stored with details such as `title`, `description`, `name`, `phone_number`, `start_time`, `end_time`, and a `booked` status.
*   **Connection**: The `fastmcp` server uses the `motor` library for asynchronous MongoDB operations. The connection URI is loaded from the `MONGODB_URI` variable in the `.env` file located at `mcp/.env`.

### 2. Advanced LangGraph Memory System

The LangGraph agents use a sophisticated three-tier memory architecture powered by MongoDB:

#### **MongoDBSaver (Conversation Checkpoints)**
*   **Purpose**: Stores conversation state and agent execution checkpoints for resuming conversations.
*   **Implementation**: Uses `langgraph-checkpoint-mongodb` package.
*   **Database & Collection**: 
    *   Database Name: `memories`
    *   Collection Name: `a2a_thread_checkpoints`
*   **Functionality**: Enables conversation persistence across sessions, allowing agents to resume exactly where they left off.

#### **MongoDBStore (Vector Memory Store)**
*   **Purpose**: Stores semantic memories using vector embeddings for intelligent memory retrieval.
*   **Implementation**: Uses `langgraph-store-mongodb` with OpenAI embeddings (1536 dimensions).
*   **Database & Collection**:
    *   Database Name: `memories`
    *   Collection Name: `a2a_memory_store`
*   **Functionality**: Enables semantic search over past interactions, user preferences, and contextual information.

#### **langmem Integration**
*   **Purpose**: Provides intelligent memory management tools for the LangGraph agents.
*   **Implementation**: Uses the `langmem` library with `create_manage_memory_tool()`.
*   **Functionality**: 
    *   Automatically stores important information from conversations.
    *   Retrieves relevant memories based on current context.
    *   Manages memory lifecycle and relevance scoring.

### 3. Environment Configuration

The system requires the following environment variables:

*   **MONGODB_URI**: MongoDB connection string for all memory operations.
*   **GOOGLE_API_KEY**: Required for both the `gemini-flash-2.5` language 
*   **VOYAGE_API_KEY**: Required for `voyage-3.5` embedding model

*   **MEETING_SCHEDULE_MCP**: URL for the scheduling MCP server (e.g., `http://localhost:8000/sse`).

These should be configured in the respective `.env` files:
*   For MCP Server: `mcp/.env`
*   For Agents: `support_agent/.env`, `scheduling_agent/.env`, `host_agent/.env`

## Quick Start

### Install prerequisites

```bash
cd a2a_agents
uv sync
# or alternatively
pip install -e .
```

### Setup Environment Variables

Copy `.env.example` to `.env` in the following folders and configure with your credentials:
- `host_agent/.env`
- `support_agent/.env` 
- `scheduling_agent/.env`
- `mcp/.env`

Required environment variables:
```bash
# MongoDB connection for memory and data persistence
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/database

# Google API Key
GOOGLE_API_KEY=your-google-api-key
VOYAGE_API_KEY=your-voyageai-api-key

# MCP server endpoint for scheduling tools
MEETING_SCHEDULE_MCP=http://localhost:8000/sse
```



### Run MCP server for meeting schedules control 

```
# seperate terminal
cd mcp 
uv run main.py
```

### Run Scheduling agent

```
# seperate terminal
uv run scheuling_agent/main.py --port 8001
```

### Run support agent
```
# seperate terminal
uv run support_agent/main.py --port 8002
```

### Run host agent and app

```
# seperate terminal
cd host_agent
uv run app.py
```

When the app.py is up you can access it via http://0.0.0.0:8083/ 

![A2A-example](./A2A-example.png)

## Key Features & Benefits

This LangGraph-powered A2A system provides several advanced capabilities:

### **Advanced Memory Architecture**
- **Persistent Conversations**: Resume conversations exactly where they left off using MongoDBSaver checkpoints
- **Semantic Memory**: Intelligent retrieval of relevant past interactions using vector embeddings
- **Contextual Awareness**: langmem automatically manages important information across conversations

### **Modern Agent Framework**
- **LangGraph ReAct**: Multi-step reasoning with tool usage capabilities

- **A2A Integration**: Full compatibility with Google's Agent-to-Agent framework

### **Scalable Architecture**
- **MongoDB Backend**: Robust data persistence for both operational data and memory
- **MCP Integration**: Extensible tool system via Model Context Protocol
- **Microservices Design**: Independent agents and services for better maintainability

This sophisticated use of MongoDB – as both a transactional data store for scheduling tools and an advanced memory backend for LangGraph agents – enables a truly intelligent and stateful A2A system that learns and adapts over time.
