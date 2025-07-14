#!/bin/bash

# Path to the log file
LOG_FILE="/home/danny/camera_with_switch/motion.log"

# Watchdog message to search for
WATCHDOG_MSG="Watchdog timeout"

# Get the system boot time in epoch
#BOOT_TIME=$(who -b | awk '{print $3 " " $4}')
BOOT_TIME=$(uptime --since)
BOOT_EPOCH=$(date -d "$BOOT_TIME" +%s)

# Get current year (since log doesn't include year)
CURRENT_YEAR=$(date +%Y)

# Search the log file for lines containing the message
grep -aF "$WATCHDOG_MSG" "$LOG_FILE" | while read -r line; do
    # Extract the 4th bracketed field (timestamp)
    RAW_TIMESTAMP=$(echo "$line" | grep -oP '(\[[^]]*\])' | sed -n '4p' | tr -d '[]')

    # Reformat: from "Jun 25 12:44:45" to "25 Jun 2025 12:44:45"
    MONTH=$(echo "$RAW_TIMESTAMP" | awk '{print $1}')
    DAY=$(echo "$RAW_TIMESTAMP" | awk '{print $2}')
    TIME=$(echo "$RAW_TIMESTAMP" | awk '{print $3}')
    PARSED_TIMESTAMP="$DAY $MONTH $CURRENT_YEAR $TIME"

    # Convert to epoch
    LOG_EPOCH=$(date -d "$PARSED_TIMESTAMP" +%s 2>/dev/null)

    #echo "boot:"  $BOOT_EPOCH "time:" $TIMESTAMP "watchdog:" $LOG_EPOCH

    # If the log entry is after the last boot, reboot
    if [[ "$LOG_EPOCH" -gt "$BOOT_EPOCH" ]]; then
        echo "Watchdog timeout after boot detected. Rebooting..."
	echo "$(date): Reboot due to watchdog timeout" >> /home/danny/camera_with_switch/watchdog_reboot.log
	if [[ -f /tmp/watchdog_rebooted ]]; then exit 0; fi
	touch /tmp/watchdog_rebooted
        sudo reboot
        exit 0
    fi
done

