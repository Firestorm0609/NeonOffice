#!/bin/bash
# Run the agent continuously (every 15 seconds)
cd "$(dirname "$0")"
while true; do
    python3 tick.py 2>/dev/null
    cp data/agent_state.json /var/www/hoodstreet/agent_state.json 2>/dev/null
    sleep 13
done
