import os
import requests

def schedule_meeting(title, description, name, phone_number, start_time, end_time):
    """Schedule a meeting via the FastMCP backend."""
    url = f"{os.getenv('MEETING_SCHEDULE_MCP')}/schedule_meeting"
    resp = requests.post(url, json={
        "title": title,
        "description": description,
        "name": name,
        "phone_number": phone_number,
        "start_time": start_time,
        "end_time": end_time
    })
    return resp.json()

def get_free_slots():
    """Retrieve a list of available time slots."""
    url = f"{os.getenv('MEETING_SCHEDULE_MCP')}/get_free_slots"
    return requests.get(url).json()

def add_potential_slot(title, description, name, phone_number, start_time, end_time):
    """Add a potential time slot to the scheduling system."""
    url = f"{os.getenv('MEETING_SCHEDULE_MCP')}/add_potential_slot"
    resp = requests.post(url, json={
        "title": title,
        "description": description,
        "name": name,
        "phone_number": phone_number,
        "start_time": start_time,
        "end_time": end_time
    })
    return resp.json()