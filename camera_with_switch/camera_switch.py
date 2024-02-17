from datetime import datetime
from time import sleep
import requests
import subprocess

from os import listdir
import fnmatch

# import RPi.GPIO as GPIO
# import board
# import digitalio
from gpiozero import LightSensor, OutputDevice, Button

# import sys
# sys.path.insert(0, "../common")
from common.messages import *

# Use a global as switch callback needs it
ctx: StationContext = None


# Format = /message?
# s=<station number>
# &rs=<1=rebooted>,
# &u=<1=update only, no resp msg needed>
# &t=<thermostat temp>
# &h=<humidity>
# &st=<set temp>
# &r=< mins to set temp, 1 on or 0 off>
# &p=<1 sensor triggered, 0 sensor off>
def sendMessage():
    url_parts = [f"{ctx.controlstation_url}/message?s={ctx.stationNo}"]
    if ctx.reset:
        url_parts.append("&rs=1")
        ctx.reset = False
    else:
        url_parts.append("&rs=0")
    url_parts.append(f"&p={int(ctx.pir_stat or ctx.camera_motion)}")
    url_parts.append("&u=1")
    url_parts.append(f"&r={int(ctx.relay_on)}")
    url = "".join(url_parts)
    chgState = False
    # Send HTTP request with a 5 sec timeout
    # print("Sending status update")
    try:
        resp = requests.get(url, timeout=5)
        # print(f"Received response code {resp.status_code}")
        if resp.status_code != 200:
            print(
                f"{datetime.now()}: Failed to send message to control station: Response: {resp.status_code}"
            )
    except requests.exceptions.RequestException as re:
        print(f"{datetime.now()}: Failed to send message to control station {re}")

    return chgState


def button_pressed():
    if ctx.DEBUG:
        print(f"{datetime.now()}: BUTTON pressed")
    if pir_state() or button_state():
        # Button pressed when lights on - turn them off
        print(f"{datetime.now()}: Turning lights off")
        ctx.button_start_time = 0
        ctx.lastPirTime = 0
    else:
        # Start button period
        ctx.button_start_time = datetime.now().timestamp()


def relay_off():
    if ctx.DEBUG:
        print(f"{datetime.now()}: Relay OFF")
    ctx.relay_on = False
    ctx.relay.off()


def relay_on():
    if ctx.DEBUG:
        print(f"{datetime.now()}: Relay ON")
    ctx.relay_on = True
    ctx.relay.on()


def pir_triggered():
    if ctx.DEBUG:
        print(f"{datetime.now()}: PIR Triggered")
    ctx.lastPirTime = datetime.now().timestamp()


def checkForMotionEvents():
    # If there is a file in the motion directory, it signifies that a motion event is underway
    # Check for any mp4 files
    mpgs = fnmatch.filter(listdir(ctx.video_dir), "*.mp4")
    motion_detected = False
    if len(mpgs) > 0:
        motion_detected = True
    return motion_detected


def runScript():
    cmd = f"{ctx.CHECK_WIFI_SCRIPT} {ctx.stationNo} {ctx.video_dir}"
    if ctx.DEBUG:
        print(f"Calling check script {cmd}\n")
    subprocess.run(args=cmd, shell=True, check=False)


def button_state():
    return (
        datetime.now().timestamp() - ctx.button_start_time
    ) < ctx.SWITCH_TRIGGER_PERIOD


def pir_state():
    return (datetime.now().timestamp() - ctx.lastPirTime) < ctx.PIR_TRIGGER_PERIOD


def runLoop():
    while True:
        nowTime = datetime.now()
        nowSecs = nowTime.timestamp()
        chgState = False
        new_button_state = button_state()
        new_pir_stat = pir_state()
        if new_pir_stat != ctx.pir_stat:
            ctx.pir_stat = new_pir_stat
            chgState = True

        # Turn light on if button pressed or pir triggers
        if not ctx.relay_on and (ctx.pir_stat or new_button_state):
            # Turn light on
            relay_on()
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: LIGHT ON")
        elif ctx.relay_on and not ctx.pir_stat and not new_button_state:
            # Turn light off
            relay_off()
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: LIGHT OFF")
        if (nowSecs - ctx.lastMonitorTime) > ctx.MONITOR_PERIOD:
            runScript()
            ctx.lastMonitorTime = nowSecs
        motion_state = checkForMotionEvents()
        if motion_state != ctx.camera_motion:
            chgState = True
            ctx.camera_motion = motion_state
        if chgState or ((nowSecs - ctx.lastMessageTime) > ctx.GET_MSG_PERIOD):
            # Send update in status
            sendMessage()
            ctx.lastMessageTime = nowSecs

        sleep(1)


if __name__ == "__main__":
    print("Starting camera-switch service")
    ctx = StationContext(configFile="./camera_switch.ini")

    ctx.lastMessageTime = 0

    ctx.reset = 1

    ctx.pir = LightSensor(ctx.PIR_IN)
    ctx.pir.when_light = pir_triggered
    ctx.switch = Button(pin=ctx.SWITCH_IN, pull_up=True)
    ctx.switch.when_pressed = button_pressed

    ctx.relay = OutputDevice(ctx.RELAY_OUT, active_high=True, initial_value=False)

    sleep(1)

    if ctx.DEBUG:
        print("Setup complete")

    runLoop()
