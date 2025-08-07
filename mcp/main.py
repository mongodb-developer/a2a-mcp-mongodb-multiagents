from fastmcp import FastMCP
from pydantic import BaseModel, Field, BeforeValidator
from datetime import datetime, timedelta
from typing import List, Optional, Annotated # Added Annotated
import motor.motor_asyncio
from bson import ObjectId
import os
from dotenv import load_dotenv
import asyncio

# --- Load .env file ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- MongoDB Configuration ---
MONGO_DETAILS = os.getenv("MONGODB_URI")
DATABASE_NAME = "scheduling_db_fastmcp" # Using a different DB name to avoid conflicts
MEETINGS_COLLECTION = "meeting_slots"

# Global MongoDB client and database
mongo_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
db: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None

async def connect_to_mongo():
    global mongo_client, db
    # Ensure this function is idempotent and safe to call multiple times.
    if db is None or mongo_client is None: # Connect if db or client is not initialized
        print(f"Attempting to connect/reconnect to MongoDB at {MONGO_DETAILS}...")
        if mongo_client: # Close existing client if it exists but db is None (e.g. after a fork or an issue)
            try:
                mongo_client.close()
            except Exception as e:
                print(f"Error closing existing mongo_client: {e}")
        mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DETAILS)
        db = mongo_client[DATABASE_NAME]
        print(f"Connected to MongoDB database: {DATABASE_NAME}")
        # Call initial data setup only if db was just initialized
        await setup_initial_data_if_needed()


async def setup_initial_data_if_needed():
    if db is None:
        # This should ideally not be reached if connect_to_mongo is called first and succeeds
        print("Database not initialized for initial data setup. Attempting connection.")
        await connect_to_mongo()
        if db is None: # Still no DB after trying to connect
            print("Failed to connect to DB for initial data setup.")
            return

    collection = db[MEETINGS_COLLECTION]
    # Check if collection is empty before adding initial data
    # This check should be more robust in a real application (e.g., check for a specific setup document)
    current_count = await collection.count_documents({})
    if current_count == 0:
        print("No existing slots found, adding initial data...")
        initial_slots_data = [
            {"title": "Team Sync", "description": "Weekly team synchronization", "name": "Dev Team", "phone_number": "N/A", "start_time": datetime(2025, 7, 1, 9, 0, 0), "end_time": datetime(2025, 7, 1, 9, 30, 0), "booked": False},
            {"title": "Client Call", "description": "Follow-up with Client X", "name": "Client X", "phone_number": "123-456-7890", "start_time": datetime(2025, 7, 1, 10, 0, 0), "end_time": datetime(2025, 7, 1, 10, 30, 0), "booked": True},
            {"title": "Project Planning", "description": "Plan next sprint", "name": "Project Alpha", "phone_number": "N/A", "start_time": datetime(2025, 7, 1, 11, 0, 0), "end_time": datetime(2025, 7, 1, 11, 30, 0), "booked": False},
        ]
        for slot_dict in initial_slots_data:
            slot_to_insert = MeetingSlotDB(**slot_dict)
            # model_dump(by_alias=True) is important for _id
            db_doc = slot_to_insert.model_dump(by_alias=True) 
            # Ensure _id is ObjectId, Pydantic's default_factory should handle this, but double check
            if isinstance(db_doc.get("_id"), str):
                db_doc["_id"] = ObjectId(db_doc["_id"])
            elif not isinstance(db_doc.get("_id"), ObjectId): # If it's not str or ObjectId, make it one
                db_doc["_id"] = ObjectId()
            await collection.insert_one(db_doc)
        print(f"{len(initial_slots_data)} initial slots added to MongoDB.")
    else:
        print(f"{current_count} slots already exist in the database. Initial data setup skipped.")


async def close_mongo_connection():
    global mongo_client
    if mongo_client:
        print("Closing MongoDB connection...")
        mongo_client.close()
        mongo_client = None
        print("MongoDB connection closed.")

# --- Pydantic Models ---
# Annotated type for ObjectId validation and schema generation for Pydantic V2
PyObjectIdAnnotation = Annotated[
    ObjectId, 
    BeforeValidator(lambda v: ObjectId(v) if ObjectId.is_valid(v) else (_ for _ in ()).throw(ValueError(f"Invalid ObjectId: {v}")))
]

class MeetingSlotBase(BaseModel):
    title: str
    description: Optional[str] = None
    name: Optional[str] = None
    phone_number: Optional[str] = None
    start_time: datetime
    end_time: datetime

class MeetingSlotCreate(MeetingSlotBase):
    pass

class MeetingSlotDB(MeetingSlotBase):
    id: PyObjectIdAnnotation = Field(default_factory=ObjectId, alias="_id") # Use PyObjectIdAnnotation
    booked: bool = False

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True

class MeetingSlotResponse(MeetingSlotBase):
    id: str 
    booked: bool

class ScheduleMeetingRequest(MeetingSlotBase): # Inherits all fields from MeetingSlotBase
    pass

class FreeSlotResponse(BaseModel): # Free slots might not need all details (title, desc etc.)
    start_time: datetime
    end_time: datetime
# Removed duplicate FreeSlotResponse definitions that were here

# --- FastMCP Server Initialization ---
mcp = FastMCP(
    name="SchedulingAgentMCP",
    description="MCP server for the Scheduling Agent, exposing meeting scheduling and slot retrieval tools."
)

# --- Tool Definitions ---
@mcp.tool
async def schedule_meeting(request: ScheduleMeetingRequest) -> MeetingSlotResponse:
    """
    Schedules a new meeting.
    Checks for existing unbooked exact slots first.
    Then checks for overlaps with any booked meetings.
    If no conflicts, creates and books a new meeting slot.
    """
    if db is None:
        await connect_to_mongo() # Ensure connection
        if db is None: # Still None after attempt
             raise Exception("Database not connected. Cannot schedule meeting.")

    collection = db[MEETINGS_COLLECTION]

    existing_slot_data = await collection.find_one(
        {
            "start_time": request.start_time,
            "end_time": request.end_time,
            "booked": False,
        }
    )
    if existing_slot_data:
        # Prepare update data from request, ensuring all fields are included
        update_fields = {
            "booked": True,
            "title": request.title,
            "description": request.description,
            "name": request.name,
            "phone_number": request.phone_number,
            # start_time and end_time are part of the query for finding the slot,
            # so they should match. If we wanted to allow updating them,
            # the logic would be more complex. For now, assume they remain the same.
        }
        updated_slot = await collection.find_one_and_update(
            {"_id": existing_slot_data["_id"]}, # Find by ID
            {"$set": update_fields},
            return_document=motor.motor_asyncio.ReturnDocument.AFTER,
        )
        if updated_slot:
            return MeetingSlotResponse(
                id=str(updated_slot["_id"]),
                title=updated_slot["title"],
                description=updated_slot.get("description"),
                name=updated_slot.get("name"),
                phone_number=updated_slot.get("phone_number"),
                start_time=updated_slot["start_time"], # These come from the DB record
                end_time=updated_slot["end_time"],   # These come from the DB record
                booked=updated_slot["booked"]
            )
        else:
            # This case should ideally not be hit if find_one found a document.
            raise Exception(f"Failed to update existing slot with ID: {existing_slot_data['_id']}")

    overlap_query = {
        "booked": True,
        "$or": [
            {"start_time": {"$lt": request.end_time, "$gte": request.start_time}},
            {"end_time": {"$gt": request.start_time, "$lte": request.end_time}},
            {"start_time": {"$lte": request.start_time}, "end_time": {"$gte": request.end_time}},
        ],
    }
    overlapping_meeting = await collection.find_one(overlap_query)
    if overlapping_meeting:
        # If there's an overlap with a booked meeting, return a dummy response to show the conflict.
        return MeetingSlotResponse(
            id=str(overlapping_meeting["_id"]),
            title="Conflicting Meeting",
            description="Cannot book this slot due to an existing meeting.",
            name=overlapping_meeting.get("name"),
            phone_number=overlapping_meeting.get("phone_number"),
            start_time=overlapping_meeting["start_time"],
            end_time=overlapping_meeting["end_time"],
            booked=False
        )
    # Create new meeting with all details from request
    new_meeting_db = MeetingSlotDB(
        title=request.title,
        description=request.description,
        name=request.name,
        phone_number=request.phone_number,
        start_time=request.start_time, 
        end_time=request.end_time, 
        booked=True
    )
    
    insert_data = new_meeting_db.model_dump(by_alias=True)
    # PyObjectIdAnnotation with default_factory=ObjectId should handle _id creation.
    # No need to manually check/assign ObjectId if Pydantic model is set up correctly.

    result = await collection.insert_one(insert_data)
    
    created_meeting_data = await collection.find_one({"_id": result.inserted_id})
    if created_meeting_data:
        return MeetingSlotResponse(
            id=str(created_meeting_data["_id"]),
            title=created_meeting_data["title"],
            description=created_meeting_data.get("description"),
            name=created_meeting_data.get("name"),
            phone_number=created_meeting_data.get("phone_number"),
            start_time=created_meeting_data["start_time"],
            end_time=created_meeting_data["end_time"],
            booked=created_meeting_data["booked"]
        )
    raise Exception("Failed to create meeting slot after insertion.")

@mcp.tool
async def get_free_slots(start_after: Optional[datetime] = None, duration_minutes: Optional[int] = 30) -> List[FreeSlotResponse]:
    """
    Retrieves a list of currently available (not booked) meeting slots.
    Optionally, filter slots that start after a given datetime.
    """
    if db is None:
        await connect_to_mongo()
        if db is None:
            raise Exception("Database not connected. Cannot get free slots.")
            
    collection = db[MEETINGS_COLLECTION]
    query = {"booked": False}
    if start_after:
        query["start_time"] = {"$gte": start_after}

    free_slots_cursor = collection.find(query).sort("start_time")
    
    available_slots_responses: List[FreeSlotResponse] = []
    async for slot_data in free_slots_cursor:
        available_slots_responses.append(FreeSlotResponse(start_time=slot_data["start_time"], end_time=slot_data["end_time"]))

    if not available_slots_responses:
        now = start_after or datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        if now.minute > 0:
            current_hour += timedelta(hours=1)

        suggested_count = 0
        attempts = 0
        max_attempts = 20

        while suggested_count < 5 and attempts < max_attempts:
            slot_start = current_hour + timedelta(hours=attempts)
            slot_end = slot_start + timedelta(minutes=duration_minutes or 30)
            
            overlap_query = {
                "booked": True,
                "$or": [
                    {"start_time": {"$lt": slot_end, "$gte": slot_start}},
                    {"end_time": {"$gt": slot_start, "$lte": slot_end}},
                    {"start_time": {"$lte": slot_start}, "end_time": {"$gte": slot_end}},
                ],
            }
            overlapping_meeting = await collection.find_one(overlap_query)
            
            if not overlapping_meeting:
                available_slots_responses.append(FreeSlotResponse(start_time=slot_start, end_time=slot_end))
                suggested_count +=1
            attempts += 1
            
    return available_slots_responses

@mcp.tool
async def add_potential_slot(slot_data: MeetingSlotCreate) -> MeetingSlotResponse:
    """
    INTERNAL: Adds a new potential (unbooked) meeting slot to the system.
    This is primarily for testing and populating initial data.
    """
    if db is None:
        await connect_to_mongo()
        if db is None:
            raise Exception("Database not connected. Cannot add slot.")

    collection = db[MEETINGS_COLLECTION]
    
    # Create new slot with all details from slot_data
    new_slot_db = MeetingSlotDB(
        title=slot_data.title,
        description=slot_data.description,
        name=slot_data.name,
        phone_number=slot_data.phone_number,
        start_time=slot_data.start_time,
        end_time=slot_data.end_time,
        booked=False
    )
    insert_data = new_slot_db.model_dump(by_alias=True)
    # PyObjectIdAnnotation with default_factory=ObjectId should handle _id creation.

    result = await collection.insert_one(insert_data)
    created_slot_data = await collection.find_one({"_id": result.inserted_id})

    if created_slot_data:
        return MeetingSlotResponse(
            id=str(created_slot_data["_id"]),
            title=created_slot_data["title"],
            description=created_slot_data.get("description"),
            name=created_slot_data.get("name"),
            phone_number=created_slot_data.get("phone_number"),
            start_time=created_slot_data["start_time"],
            end_time=created_slot_data["end_time"],
            booked=created_slot_data["booked"]
        )
    raise Exception("Failed to add potential slot after insertion.")

# setup_initial_data_if_needed is now called by connect_to_mongo when the DB is first connected.
# main_async is kept for potential direct async testing if desired, but not used by __main__.
async def main_async():
    await connect_to_mongo() 
    # setup_initial_data() is now setup_initial_data_if_needed() and called within connect_to_mongo
    # mcp.run() is blocking, so other async cleanup might need separate handling if run this way
    # For FastMCP CLI (`fastmcp run mcp.main:mcp`), it handles the loop.
    # If running script directly, and mcp.run() is blocking, then close_mongo_connection won't be hit easily.
    # FastMCP's `mcp.run()` is typically for CLI usage or simple scripts.
    # For more complex async management, one might integrate it differently.
    # For now, we assume `mcp.run()` will block and keep the connection open.
    # A proper shutdown sequence would be needed for production.
    
    # The `fastmcp run` command is preferred for running servers.
    # If running this script directly, `mcp.run()` will start the server.
    # The `close_mongo_connection` would ideally be in a shutdown hook.
    # FastMCP doesn't seem to expose explicit shutdown hooks in the same way FastAPI does with lifespan.
    print("Starting FastMCP server... (Use `fastmcp run A2A-MCP/Simple/a2a_agents/mcp/main.py:mcp` to run)")
    # mcp.run() # This would block. For script execution, it's better to use the CLI.
    # The following is just to demonstrate that the script can be imported.
    # To run the server, use: fastmcp run A2A-MCP/Simple/a2a_agents/mcp/main.py:mcp --port 8001


if __name__ == "__main__":
    # connect_to_mongo (which calls setup_initial_data_if_needed) 
    # will be called by each tool if db is None.
    # This ensures the DB connection and initial data setup happens 
    # within the event loop managed by fastmcp when a tool is first called.

    # For direct script execution, mcp.run() will start the server.
    # The first tool call will then trigger connect_to_mongo.
    print("Starting FastMCP server on port 8001 using SSE transport.")
    print("The MCP server tools will connect to MongoDB and setup initial data on their first use if needed.")
    print("To run with FastMCP CLI (recommended): fastmcp run A2A-MCP/Simple/a2a_agents/mcp/main.py:mcp --transport sse --port 8001")
    
    # fastmcp.run() is blocking and manages its own event loop.
    mcp.run(transport="sse", port=8000, host="0.0.0.0")
    
    # If mcp.run() were non-blocking or if we needed explicit cleanup after server stops:
    # try:
    #     mcp.run(transport="sse", port=8001, host="0.0.0.0")
    # finally:
    #     # This part might not be reached if mcp.run() blocks indefinitely and is terminated externally.
    #     # For robust cleanup, a more sophisticated shutdown signal handling would be needed.
    #     if mongo_client:
    #         print("Attempting to close MongoDB connection post server run...")
    #         # Running close_mongo_connection in a new loop if the previous one is closed.
    #         try:
    #             loop = asyncio.get_event_loop()
    #             if loop.is_closed():
    #                 loop = asyncio.new_event_loop()
    #                 asyncio.set_event_loop(loop)
    #             loop.run_until_complete(close_mongo_connection())
    #         except RuntimeError as e:
    #             print(f"Error during final MongoDB connection close: {e}")
