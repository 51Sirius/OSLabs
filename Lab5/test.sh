#!/bin/bash

HISTORY_DIR="./process_memory_history"

mkdir -p "$HISTORY_DIR"

if [[ "$1" == "--show" ]]; then
    if [[ -n $(ls -A "$HISTORY_DIR") ]]; then
        for history_file in "$HISTORY_DIR"/*; do
            process_info=$(basename "$history_file" .log)
            echo "Process: $process_info"
            echo "Memory Usage History:"
            cat "$history_file"
            echo ""
        done
    else
        echo "No memory usage history available."
    fi
else
    ps -e -o pid,comm --no-headers | while read -r pid comm; do
        mem_usage=$(pmap -x "$pid" 2>/dev/null | awk '/total/ {print $3}')
        if [[ -n "$mem_usage" ]]; then
            history_file="$HISTORY_DIR/${comm}_${pid}.log"
            echo "$(date +'%Y-%m-%d %H:%M:%S') $mem_usage" >> "$history_file"
        fi
    done
fi
