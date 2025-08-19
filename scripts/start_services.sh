#!/bin/bash

# This script automates the startup of all services for the A2A MCP App.
# It starts each service in a separate background process and provides a
# graceful shutdown mechanism.

echo "================================================="
echo "  A2A MCP Application Services Startup Script"
echo "================================================="
echo
echo "INFO: Make sure you have already installed dependencies with 'uv sync'"
echo "      and configured all required '.env' files before running this."
echo

# Function to shut down all services using pkill
cleanup() {
    echo ""
    echo "Shutting down all services..."
    # Use pkill to find and kill processes by their command line signature.
    # The -f flag matches against the full command line, making it specific.
    pkill -f "mcp/main.py"
    pkill -f "scheduling_agent/main.py"
    pkill -f "support_agent/main.py"
    pkill -f "host_agent/app.py"

    # Optional: On macOS, you can also close the terminal windows that were opened.
    # osascript -e 'tell application "Terminal" to close (windows whose name contains "A2A Service:")'

    echo "All services have been stopped."
    exit 0
}

# Trap signals to ensure cleanup runs when the script is stopped.
trap cleanup SIGINT EXIT

# --- OS-Specific Configuration ---
# This script uses 'osascript' for macOS. For Linux, you might use 'gnome-terminal' or 'konsole'.

# Get the absolute path of the project root directory (assumes this script is in a 'scripts' subdir)
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." &> /dev/null && pwd)

echo "INFO: Project root detected at: $PROJECT_ROOT"
echo "INFO: This script will open new Terminal windows for each service."
echo

# Function to run a command in a new Terminal window on macOS
run_in_new_terminal() {
    local title="$1"
    local command="$2"
    osascript \
        -e "tell application \"Terminal\"" \
        -e "    activate" \
        -e "    do script \"cd '$PROJECT_ROOT' && $command\"" \
        -e "    set custom title of front window to \"A2A Service: $title\"" \
        -e "end tell" > /dev/null
}

# Start services in new terminals
echo "[1/4] Starting MCP Server in a new terminal..."
run_in_new_terminal "MCP Server" "uv run mcp/main.py"
sleep 3

echo "[2/4] Starting Scheduling Agent in a new terminal..."
run_in_new_terminal "Scheduling Agent" "uv run scheduling_agent/main.py --port 8001"
sleep 3

echo "[3/4] Starting Support Agent in a new terminal..."
run_in_new_terminal "Support Agent" "uv run support_agent/main.py --port 8002"
sleep 3

echo "[4/4] Starting Host Agent and UI in a new terminal..."
run_in_new_terminal "Host Agent UI" "uv run host_agent/app.py"
sleep 3

echo
echo "================================================="
echo "           All services are running!"
echo "================================================="
echo
echo "Service Ports:"
echo "  - MCP Server:        8000 (default)"
echo "  - Scheduling Agent:  8001"
echo "  - Support Agent:     8002"
echo "  - Host Agent and UI: 8083"
echo
echo "Access the Gradio UI at: http://0.0.0.0:8083/"
echo "Each service is running in a separate terminal window."
echo
echo "Press Ctrl+C in THIS terminal to stop all services and close this window."
echo

# Wait indefinitely to keep this script alive. This allows the 'trap' command
# to catch Ctrl+C and run the cleanup function.
tail -f /dev/null