#!/bin/bash
cd /root/neonoffice
while true; do
    echo "[$(date)] Starting agent..."
    python3 agent.py 2>&1 | tee -a /tmp/neonagent.log
    echo "[$(date)] Agent exited, restarting in 5s..."
    sleep 5
done
