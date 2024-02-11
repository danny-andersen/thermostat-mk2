from datetime import datetime
from time import sleep
import requests
import subprocess

from os import listdir
import fnmatch

# import RPi.GPIO as GPIO
# import board
# import digitalio
from gpiozero import MotionSensor, OutputDevice, Button

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
# &r=< mins to set temp, 0 off>
# &p=<1 sensor triggered, 0 sensor off>
def sendMessage():
    url_parts = [f"{ctx.controlstation_url}/message?s={ctx.stationNo}"]
    if ctx.reset:
        url_parts.append("&rs=1")
        ctx.reset = False
    else:
        url_parts.append("&rs=0")
    url_parts.append(f"&p={int(ctx.relay_on)}")
    url_parts.append("&u=1")
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
    ctx.button_start_time = datetime.now().timestamp
    relay_on()


def relay_off():
    if ctx.DEBUG:
        print("Relay OFF")
    ctx.relay_on = False
    ctx.relay.off()


def relay_on():
    if ctx.DEBUG:
        print("Relay ON")

    ctx.relay_on = True
    ctx.relay.on()


def checkPIR(secs: float):
    status = ctx.pir.value
    # if ctx.DEBUG:
    #     print(f"PIR: {'ON' if status else 'OFF'}")
    if status:
        ctx.lastPirTime = secs
        ctx.pir_stat = 1
    elif secs - ctx.lastPirTime > ctx.PIR_TRIGGER_PERIOD:
        ctx.pir_stat = 0


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


def runLoop():
    # This function never returns unless there is an uncaught exception
    # # Use GPIO numbering, not pin numbering
    # GPIO.setmode(GPIO.BCM)
    # GPIO.setup(context.RELAY_OUT, GPIO.OUT)  # Relay output
    # GPIO.setup(context.PIR_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # PIR input
    # # GPIO.setup(context.TEMP_SENSOR, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # DHT22
    # GPIO.setup(context.GREEN_LED, GPIO.OUT)  # Green LED lit when boiler on
    # GPIO.setup(context.RED_LED, GPIO.OUT)  # RED LED lit when boiler off
    # setLED(context, LedColour.AMBER)
    # relay_off(context)

    while True:
        nowTime = datetime.now()
        nowSecs = nowTime.timestamp()
        chgState = False
        button_state = (nowSecs - ctx.button_start_time) < ctx.SWITCH_TRIGGER_PERIOD

        checkPIR(nowSecs)
        if not ctx.relay_on and (ctx.pir_stat or button_state):
            # Turn light on
            relay_on()
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: LIGHT ON")
        elif ctx.relay_on and not ctx.pir_stat and not button_state:
            # Turn light off
            relay_off()
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: LIGHT OFF")
        chgState = chgState or checkForMotionEvents()
        if (nowSecs - ctx.lastMonitorTime) > ctx.MONITOR_PERIOD:
            runScript()
            ctx.lastMonitorTime = nowSecs
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

    ctx.pir = MotionSensor(ctx.PIR_IN)
    ctx.relay = OutputDevice(ctx.RELAY_OUT, active_high=True, initial_value=False)
    ctx.switch = Button(pin=ctx.SWITCH_IN, pull_up=True, bounce_time=1)
    ctx.switch.when_pressed = button_pressed

    sleep(1)

    # relay_off(context)

    if ctx.DEBUG:
        print("Setup complete")

    runLoop()
