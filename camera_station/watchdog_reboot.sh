#!/bin/bash

LOGFILE="/home/danny/camera_with_switch/motion.log"
SEARCH="Watchdog timeout did NOT restart"

# --- 1. Get last boot time (epoch seconds) ---
BOOT_TIME=$(who -b | awk '{print $3, $4}')
BOOT_EPOCH=$(date -d "$BOOT_TIME" +%s)

# --- 2. Find the most recent matching log entry ---
LAST_ENTRY=$(grep "$SEARCH" "$LOGFILE" 2>/dev/null| tail -n 1)

# If no entry found, exit quietly
[ -z "$LAST_ENTRY" ] && exit 0

# --- 3. Extract timestamp from the log entry ---
# Example entry:
# [0:motion] [ERR] [ALL] [Aug 02 03:00:31] motion_watchdog: Thread 1 - Watchdog timeout did NOT restart, killing it!
#
# The timestamp is the 4th [...] block.

#echo "Last watchdog log entry: $LAST_ENTRY"
TIMESTAMP=$(echo "$LAST_ENTRY" | awk -F'[][]' '{print $8}')

# --- 4. Convert timestamp to epoch, handling year rollover ---
CURRENT_YEAR=$(date +%Y)
PREV_YEAR=$((CURRENT_YEAR - 1))

# First, assume current year
ENTRY_EPOCH=$(date -d "$TIMESTAMP $CURRENT_YEAR" +%s 2>/dev/null)

if [ -z "$ENTRY_EPOCH" ]; then
    # Parsing failed entirely — safest to stop
    echo "Failed to parse log timestamp $TIMESTAMP with current year. Exiting."
    exit 0
fi

NOW=$(date +%s)

# If the timestamp appears to be in the future, try last year
if (( ENTRY_EPOCH > NOW )); then
    ENTRY_EPOCH=$(date -d "$TIMESTAMP $PREV_YEAR" +%s 2>/dev/null)

    if [ -z "$ENTRY_EPOCH" ]; then
        # Parsing failed again — stop
        echo "Failed to parse log timestamp $TIMESTAMP with previous year. Exiting."
        exit 0
    fi
fi

AGE=$(( NOW - ENTRY_EPOCH ))
#echo "Watchdog log entry timestamp: $TIMESTAMP (epoch: $ENTRY_EPOCH), age: $AGE seconds"

if (( AGE < 0 || AGE > 86400 )); then 
    exit 0
fi

# --- 6. Compare log timestamp to last boot time ---
if (( ENTRY_EPOCH > BOOT_EPOCH )); then
    echo "Watchdog failure occurred after last boot — rebooting system."
    #sudo reboot
fi

exit 0

