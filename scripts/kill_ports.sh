#!/bin/bash

# A script to find and kill processes running on specified ports.

# --- Configuration ---
# Define the ports you want to clear
PORTS=(8000 8001 8002 8083)

# --- Colors for neat output ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting process cleanup for specified ports...${NC}"
echo "================================================"

# --- Main Loop ---
for PORT in "${PORTS[@]}"; do
    echo -e "Checking port ${GREEN}${PORT}${NC}..."

    # Find the PID using the port. The '-t' flag gives only the PID.
    PID=$(lsof -ti :$PORT)

    if [ -n "$PID" ]; then
        echo -e "  -> Process found with PID: ${RED}${PID}${NC}. Terminating..."
        kill -9 $PID
        echo -e "  -> ${GREEN}Process ${PID} terminated.${NC}"
    else
        echo -e "  -> ${YELLOW}No process found on this port.${NC}"
    fi
    echo "------------------------------------------------"
done

echo -e "${GREEN}Cleanup script finished.${NC}"