#!/bin/bash

# Set the service name and the error message to monitor
SERVICE_NAME="thermostat_ui"
ERROR_MESSAGE="drmModeAtomicCommit: No space left on device"

# Function to check for the error in journalctl
check_error() {
    if journalctl -u "$SERVICE_NAME" -n 5 | grep -q "$ERROR_MESSAGE"; then
        return 0  # Error found
    elif dmesg | grep -q "Resetting GPU"; then
        return 0
    else
        return 1  # Error not found
    fi
}

# Main loop
while true; do
    if check_error; then
        echo "Error detected in $SERVICE_NAME logs. Rebooting..."
        reboot
    fi
    sleep 15
done
