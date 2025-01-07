#!/bin/bash

function check_camera_working {
    LOG_FILE="motion.log"
    SEARCH_PATTERN="Watchdog timeout did NOT restart"
    TIME_THRESHOLD=60

    # Get the current timestamp
    CURRENT_TIMESTAMP=$(date +%s)

    # Calculate the timestamp 60 seconds ago
    TIME_THRESHOLD_TIMESTAMP=$((CURRENT_TIMESTAMP - TIME_THRESHOLD))

    # Search for the entry in the log file within the last 60 seconds
    if grep -q "$SEARCH_PATTERN" "$LOG_FILE"; then
        LAST_ENTRY=$(grep --binary-files=text "$SEARCH_PATTERN" "$LOG_FILE" | grep -Eo "\[.*\]" | tail -n 1 | tr -d '[]' | awk '{print ($4,$5,$6)}')

        if [ -n "$LAST_ENTRY" ]; then
            LAST_ENTRY_TIMESTAMP=$(date -d "$LAST_ENTRY" +%s)

            # Compare timestamps to check if the last entry occurred within the last 60 seconds
            #echo "Last watchdog failure: "$LAST_ENTRY
            if [ "$LAST_ENTRY_TIMESTAMP" -ge "$TIME_THRESHOLD_TIMESTAMP" ]; then
                echo "Camera watchdog failure at $LAST_ENTRY - rebooting"
                sudo /sbin/shutdown -r now
            fi
        fi
    fi
}

function turn_camera_on_off () {
    #Check if motion is running
    state=$1
    #echo "Checking camera running - state is" $state
    sudo systemctl is-active --quiet motion
    if [ $? -ne 0 ]
    then
        echo "N" > camera_status.txt
        if [ $state = "Y" ]
        then
            #Motion isnt running
            echo "Motion isnt running and camera should be on"
            sudo service motion start
            echo "Y" > camera_status.txt
        fi
    else
        echo "Y" > camera_status.txt
        if [ $state = "N" ]
        then
            #Motion is running but should be off
            echo "Stopping motion service"
            sudo service motion stop
            echo "N" > camera_status.txt
        fi
    fi
    #if [ $state = "Y" ]
    #then
    #    check_camera_working
    #fi
}

#Start
camera_on=$1

turn_camera_on_off $camera_on

