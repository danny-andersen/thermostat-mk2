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

#Start
only_monitor_when_noones_home=$1

#Check whether we should enable cameras
#For internal cameras only enable when no-one's home
if [ $only_monitor_when_noones_home = 'Y' ]
then
    #Check if anyone's home
    safeDevice=`cat safeDevices.txt`
    dev=$(echo $safeDevice | sed 's/|/ /g')
    home_alone="Y"
    for d in $dev
    do
        ping -c2 $d > /dev/null 2>&1
        if [ $? == 0 ]
        then
            #Device on network
            home_alone="N"
        fi
    done
    #Check if motion is running
    sudo service motion status >/dev/null
    if [ $? -ne 0 ]
    then
        if [ $home_alone = "Y" ]
        then
            #Motion isnt running
            echo "No ones home and motion isnt running"
            sudo service motion start
        fi
    else
        if [ $home_alone = "N" ]
        then
            #Motion is running but someones home
            echo "Stopping motion service"
            sudo service motion stop
        fi
    fi
    if [ $home_alone = "Y" ]
    then
        check_camera_working
    fi
else
    #Check camera hasnt failed
    check_camera_working
    #Check if motion is running
    sudo service motion status >/dev/null
    if [ $? -ne 0 ]
    then
        #Motion isnt running
        echo "Motion service isnt running ??"
        sudo service motion start
    fi
fi

