from datetime import datetime, timedelta
from time import sleep
import requests
from multiprocessing import Process
import atexit
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
import crcmod
import crcmod.predefined


# Use a global as switch callback needs it
ctx: StationContext = None
monitorScriptProcess: Process
lastTimePressed: datetime
chgState = False


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
    # url_parts.append("&u=1")
    url_parts.append(f"&r={int(ctx.relay_on)}")
    url = "".join(url_parts)
    chg = False
    # Send HTTP request with a 3 sec timeout
    if ctx.DEBUG:
        print(f"{datetime.now()}: Sending status update {url}")
    try:
        resp = requests.get(url, timeout=3)
        # print(f"Received response code {resp.status_code}")
        if resp.status_code != 200:
            print(
                f"{datetime.now()}: Failed to send message to control station: Response: {resp.status_code}"
            )
        else:
            chg = processResponseMsg(resp)

    except requests.exceptions.RequestException as re:
        print(f"{datetime.now()}: Failed to send message to control station {re}")

    return chg


def processResponseMsg(resp: requests.Response):
    respContent: bytes = resp.content
    headerBytes: bytes = respContent[0:4]
    (msgId, mlen, crc) = Message.unpack(headerBytes)
    msgBytes = bytearray(respContent)
    msgBytes[2:3] = b"\x00"
    msgBytes[3:4] = b"\x00"
    chg = False
    # print(f"len: {msg.len}, msg: {msgBytes}")
    crc_func = crcmod.predefined.mkCrcFun("crc-aug-ccitt")
    calc_crc = crc_func(msgBytes) & 0xFFFF
    if calc_crc != crc:
        print(
            f"{datetime.now()}: Failed to receive correct CRC for message: {respContent} Bytes: {msgBytes} Calc-CRC: {calc_crc:X} rx-CRC: {crc:X}"
        )
    else:
        msgArray = bytearray()
        for i in range(4, mlen):
            msgArray.append(respContent[i])
        msgBytes: bytes = bytes(msgArray)
        if msgId == LIGHT_COMMAND_MSG:
            chg = light_command(msgBytes)
        # else:
        #     if ctx.DEBUG:
        #         print(f"Ignoring un-implemented msg {msgId}")
        return chg


def light_command(msgBytes: bytes):
    lightMsg = LightMsg.unpack(msgBytes)
    nowTime = datetime.now()
    if lightMsg.lightState == 0:
        # Turn lights off
        if ctx.DEBUG:
            print(f"{nowTime}: Lights OFF command rx")
        ctx.button_start_time = 0
        ctx.lastPirTime = 0
    else:
        if ctx.DEBUG:
            print(f"{nowTime}: Lights ON command rx")
        ctx.button_start_time = datetime.now().timestamp()
    checkLightSwitch(nowTime)
    return False


def button_pressed():
    global lastTimePressed
    global ctx

    nowTime = datetime.now()
    deltaPressed = nowTime - lastTimePressed
    lastTimePressed = nowTime
    if deltaPressed < timedelta(milliseconds=500):
        # Only triggered less than 0.5secs ago - ignore
        if ctx.DEBUG:
            print(f"{nowTime}: Debounce: Delta {deltaPressed}")
        return
    if ctx.DEBUG:
        print(f"{nowTime}: BUTTON pressed: Delta {deltaPressed}")
    if pir_state(nowTime) or button_state(nowTime):
        # Button pressed when lights on - turn them off
        if ctx.DEBUG:
            print(f"{nowTime}: Turning lights off")
        ctx.button_start_time = 0
        ctx.lastPirTime = 0
    else:
        # Start button period
        if ctx.DEBUG:
            print(f"{nowTime}: Turning lights on")
        ctx.button_start_time = nowTime.timestamp()
    checkLightSwitch(nowTime)


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
    nowTime = datetime.now()
    if ctx.DEBUG:
        print(f"{nowTime}: PIR Triggered")
    ctx.lastPirTime = nowTime.timestamp()
    checkLightSwitch(nowTime)


def checkLightSwitch(nowTime: datetime):
    global chgState
    new_button_state = button_state(nowTime)
    new_pir_stat = pir_state(nowTime)
    if new_pir_stat != ctx.pir_stat:
        ctx.pir_stat = new_pir_stat
        chgState = True

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
    # if ctx.DEBUG:
    #     print(f"{nowTime}: Calling check script {cmd}\n")
    subprocess.run(args=cmd, shell=True, check=False)


def button_state(nowTime: datetime):
    return (nowTime.timestamp() - ctx.button_start_time) < ctx.SWITCH_TRIGGER_PERIOD


def pir_state(nowTime: datetime):
    return (nowTime.timestamp() - ctx.lastPirTime) < ctx.PIR_TRIGGER_PERIOD


def stopMonitoring():
    global monitorScriptProcess
    print("SIGQUIT received: stopping monitor process")
    if monitorScriptProcess:
        print("Terminating monitor process")
        monitorScriptProcess.terminate()
        sleep(0.5)
        if monitorScriptProcess.is_alive():
            print("Killing monitor process")
            monitorScriptProcess.kill()


def runMonitorScript():
    print("******Starting monitor script thread loop")
    lastMonitorTime = 0
    sleep(15)
    # Wait until server up and running
    while True:
        nowTime = datetime.now().timestamp()
        if (nowTime - lastMonitorTime) > ctx.MONITOR_PERIOD:
            # Run the monitor script
            lastMonitorTime = nowTime
            runScript()
        sleep(5)


def runLoop():
    global chgState
    while True:
        nowTime = datetime.now()
        nowSecs = nowTime.timestamp()

        # Turn light on if button pressed or pir triggers
        checkLightSwitch(nowTime)
        motion_state = checkForMotionEvents()
        if motion_state != ctx.camera_motion:
            chgState = True
            ctx.camera_motion = motion_state
        if chgState or ((nowSecs - ctx.lastMessageTime) > ctx.GET_MSG_PERIOD):
            chgState = sendMessage()
            ctx.lastMessageTime = nowSecs

        sleep(0.5)


if __name__ == "__main__":
    print("Starting camera-switch service")
    ctx = StationContext(configFile="./camera_switch.ini")
    lastTimePressed = datetime.now()

    ctx.lastMessageTime = 0

    ctx.reset = 1

    ctx.pir = LightSensor(ctx.PIR_IN, charge_time_limit=0.02)
    ctx.pir.when_light = pir_triggered
    ctx.switch = Button(pin=ctx.SWITCH_IN, pull_up=True, hold_time=0.1)
    ctx.switch.when_held = button_pressed

    ctx.relay = OutputDevice(ctx.RELAY_OUT, active_high=True, initial_value=False)

    sleep(1)

    monitorScriptProcess = Process(target=runMonitorScript, daemon=True)
    monitorScriptProcess.start()
    atexit.register(stopMonitoring)

    if ctx.DEBUG:
        print("Setup complete")

    runLoop()
