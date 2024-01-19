from os import path, remove
from subprocess import run, Popen

from datetime import datetime
from time import sleep
import requests

# import RPi.GPIO as GPIO
# import board
# import digitalio
from gpiozero import LED, MotionSensor, OutputDevice
import crcmod
import crcmod.predefined

# import sys
# sys.path.insert(0, "../common")
from common.humidity_sensor import readSHTC3Temp
from common.messages import *


# Format = /message?
# s=<station number>
# &rs=<1=rebooted>,
# &u=<1=update only, no resp msg needed>
# &t=<thermostat temp>
# &h=<humidity>
# &st=<set temp>
# &r=< mins to set temp, 0 off>
# &p=<1 sensor triggered, 0 sensor off>
def sendMessage(ctx: StationContext):
    url_parts = [f"{ctx.controlstation_url}/message?s={ctx.stationNo}"]
    if ctx.reset:
        url_parts.append("&rs=1")
        ctx.reset = False
    else:
        url_parts.append("&rs=0")
    url_parts.append(f"&p={ctx.pir_stat}")
    url_parts.append(f"&t={int(ctx.currentTemp)}")
    url_parts.append(f"&h={int(ctx.currentHumidity)}")
    url_parts.append(f"&st={int(ctx.currentSetTemp)}")
    url_parts.append(f"&r={int(ctx.currentBoilerStatus)}")
    url_parts.append(f"&u={0}")
    url = "".join(url_parts)
    chgState = False
    # Send HTTP request with a 5 sec timeout
    # print("Sending status update")
    try:
        resp = requests.get(url, timeout=5)
        # print(f"Received response code {resp.status_code}")
        if resp.status_code == 200:
            chgState = processResponseMsg(ctx, resp)
            flickerLED(ctx)
        else:
            print(
                f"{datetime.now()}: Failed to send message to control station: Response: {resp.status_code}"
            )

    except requests.exceptions.RequestException as re:
        print(f"{datetime.now()}: Failed to send message to control station {re}")

    return chgState


def newSetTempMsg(ctx: StationContext, msgBytes: bytes):
    tempMsg = Temp.unpack(msgBytes)
    ctx.currentManSetTemp = tempMsg.temp
    ctx.setTempTime = datetime.now().timestamp()
    if ctx.DEBUG:
        print(
            f"{datetime.now()}: Received Set thermostat temp {ctx.currentManSetTemp/10}C"
        )
    return True


def extTempMsg(ctx: StationContext, msgBytes: bytes):
    extMsg = SetExt.unpack(msgBytes)
    ctx.currentExtTemp = float(extMsg.setExt)
    ctx.windStr = "".join([chr(i) for i in extMsg.windStr])
    if ctx.DEBUG:
        print(
            f"{datetime.now()}: Received Ext temp {ctx.currentExtTemp/10}C , wind {extMsg.windStr} -> {ctx.windStr}"
        )
    # Write to local file for local UI to pick up
    with open(EXTTEMP_FILE, "w", encoding="UTF-8") as fp:
        fp.write(f"{ctx.currentExtTemp/10}\n")
        fp.write(f"{ctx.windStr}\n")
    return True


def setMotd(ctx: StationContext, msgBytes: bytes):
    mlen = len(msgBytes)
    # Create pascal byte array to unpack string
    pascal = bytearray(mlen + 1)
    i = 0
    for b in msgBytes:
        if i == 4:
            # Set pascal string length
            pascal[i] = mlen - 4
            i += 1
        pascal[i] = b
        i += 1
    (ctx.motdExpiry, motdBytes) = unpack(f"<I{mlen-3}p", pascal)
    checkedBytes = bytearray()
    for b in motdBytes:
        checkedBytes.append(32 if b == 0 else b)
    ctx.currentMotd = checkedBytes.decode("UTF-8")
    if ctx.DEBUG:
        print(
            f"{datetime.now()}: Received motd expiry {ctx.motdExpiry}: {motdBytes} -> {ctx.currentMotd}"
        )
    # Write to local file
    with open(MOTD_FILE, "w", encoding="UTF-8") as fp:
        fp.write(f"{ctx.currentMotd}\n")
    return True


def setCurrentTempMsg(ctx: StationContext, msgBytes: bytes):
    tempMsg = Temp.unpack(msgBytes)
    ctx.currentTemp = tempMsg.temp
    ctx.currentHumidity = tempMsg.humidity
    ctx.TEMP_PERIOD = int(ctx.config["timings"]["TEMP_PERIOD"])
    ctx.lastTempTime = datetime.now().timestamp()
    if ctx.DEBUG:
        print(
            f"{datetime.now()}: Received current temp {ctx.currentTemp/10}C, humidity {ctx.currentHumidity/10}"
        )
    return False


def setScheduleMsg(ctx: StationContext, msgBytes: bytes):
    sched = SchedByElem.unpack(msgBytes)
    elem = ScheduleElement(sched.day, sched.start, sched.end, sched.temp)
    ctx.schedules.add(elem)
    if ctx.DEBUG:
        print(
            f"{datetime.now()}: Received schedule {elem} total schedules: {len(ctx.schedules)}"
        )
    saveSchedules(ctx)
    # Return true as will be receiving new schedules
    return True


def deleteAllSchedulesMsg(ctx: StationContext):
    ctx.schedules = set()
    if path.exists(LOCAL_SCHEDULE_FILE):
        remove(LOCAL_SCHEDULE_FILE)
    if ctx.DEBUG:
        print(f"{datetime.now()}: Deleted all schedules")

    # Return true as will be receiving new schedules
    return True


def readSchedules(ctx: StationContext):
    # Read file containing locally saved schedules
    if path.exists(LOCAL_SCHEDULE_FILE):
        ctx.schedules = ScheduleElement.loadSchedulesFromFile(LOCAL_SCHEDULE_FILE)
        ctx.schedules.remove(None)  # This is a dummy entry used by the control station
        # Need to divide all temps by 10 as they have been multiplied by 10x in ScheduleElement
        for sched in ctx.schedules:
            sched.temp = sched.temp / 10.0
    else:
        print(
            f"{datetime.now()}: Locally saved schedule file {LOCAL_SCHEDULE_FILE} not found "
        )


def saveSchedules(ctx: StationContext):
    ScheduleElement.saveSchedulesToFile(ctx.schedules, LOCAL_SCHEDULE_FILE)


def setHolidayMsg(ctx: StationContext, msgBytes: bytes):
    if len(msgBytes) == 13:
        hols: HolidayStr = HolidayStr.unpack(msgBytes)
    else:
        # old school message with no mins set
        hols: HolidayStr = HolidayStr.unpackNoMins(msgBytes)
    holiday: Holiday = Holiday(hols)
    ctx.currentHoliday = holiday
    HolidayStr.saveToFile(LOCAL_HOLIDAY_FILE, hols)
    if ctx.DEBUG:
        print(
            f"{datetime.now()}: Received new holiday: start: {datetime.fromtimestamp(holiday.startDate)} end: {datetime.fromtimestamp(holiday.endDate)}"
        )
    return True


def readHoliday(ctx: StationContext):
    # Read file containing locally saved holiday
    hols = HolidayStr.loadFromFile(LOCAL_HOLIDAY_FILE)
    ctx.currentHoliday = Holiday(hols)
    # if path.exists(LOCAL_HOLIDAY_FILE):
    #     with open(LOCAL_HOLIDAY_FILE, "rb") as fp:
    #         ctx.currentHoliday = pickle.load(fp)
    # else:
    #     print(f"Locally saved holiday file {LOCAL_HOLIDAY_FILE} not found ")


# def saveHoliday(ctx: StationContext):
#     with open(LOCAL_HOLIDAY_FILE, "wb") as fp:
#         pickle.dump(ctx.currentHoliday, fp)
#     fp.close()
#     # except:
#     #     print(f"Failed to save holiday to {LOCAL_HOLIDAY_FILE}: {sys.exc_info()[0]}")


def processResponseMsg(ctx: StationContext, resp: requests.Response):
    respContent: bytes = resp.content
    headerBytes: bytes = respContent[0:4]
    (msgId, mlen, crc) = Message.unpack(headerBytes)
    msgBytes = bytearray(respContent)
    msgBytes[2:3] = b"\x00"
    msgBytes[3:4] = b"\x00"
    chgState = False
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
        if msgId == REQ_STATUS_MSG:
            chgState = True
        elif msgId == SET_TEMP_MSG:
            chgState = newSetTempMsg(ctx, msgBytes)
        elif msgId == SET_EXT_MSG:
            chgState = extTempMsg(ctx, msgBytes)
        elif msgId == SCHEDULE_MSG:
            chgState = setScheduleMsg(ctx, msgBytes)
        elif msgId == DELETE_ALL_SCHEDULES_MSG:
            chgState = deleteAllSchedulesMsg(ctx)
        elif msgId == SET_HOLIDAY_MSG:
            chgState = setHolidayMsg(ctx, msgBytes)
        elif msgId == SET_THERM_TEMP_MSG:
            chgState = setCurrentTempMsg(ctx, msgBytes)
        elif msgId == MOTD_MSG:
            # print(f"Motd: {respContent}")
            chgState = setMotd(ctx, msgBytes)
        else:
            print(f"Ignoring un-implemented msg {msgId}")
        return chgState


# void getSetPoint(SchedUnion *schedule, uint16_t mins, int currDay, bool nextSched)


def retrieveScheduledSetTemp(
    ctx: StationContext, nowTime: datetime, wantNext: bool = False
) -> float:
    priority = 0
    next_mins = 1440
    retSched: ScheduleElement = ScheduleElement()
    curr_day = (
        nowTime.weekday() + 1
    )  # Python is 0-6 but the original 'C' code it was 1 - 7
    minOfDay = (nowTime.hour * 60) + nowTime.minute
    # Note: = "0" for every day,
    # "0x0100" for Weekday (Mon - Fri),
    # "0x0200" for Weekend (Sat, Sun),
    # 7 - Sunday, 0 - Monday, 3 - Tuesday,....7 - Saturday

    for sched in ctx.schedules:
        if (
            not wantNext
            and sched.start == 0
            and sched.end == 0
            and sched.day == 0
            and priority == 0
        ):
            # This schedule matches all days and times
            retSched = sched
        elif (not wantNext and sched.start <= minOfDay and sched.end > minOfDay) or (
            wantNext and sched.start > minOfDay and sched.start < next_mins
        ):
            if sched.day == 0 and priority <= 1:
                priority = 1
                next_mins = sched.start
                retSched = sched
            if (
                sched.day == 0x200
                and (curr_day == 6 or curr_day == 7)
                and priority <= 2
            ):
                priority = 2
                next_mins = sched.start
                retSched = sched
            if (
                sched.day == 0x100
                and (curr_day >= 1 and curr_day <= 5)
                and priority <= 2
            ):
                priority = 2
                next_mins = sched.start
                retSched = sched
            if sched.day == curr_day and priority <= 3:
                priority = 3
                next_mins = sched.start
                retSched = sched
    return retSched.temp


def checkOnHoliday(ctx: StationContext, secs: float):
    retTemp = -1000.0
    if secs > ctx.currentHoliday.startDate and secs < ctx.currentHoliday.endDate:
        # On holiday
        retTemp = ctx.currentHoliday.temp
    return retTemp


def setLED(ctx: StationContext, colour: LedColour):
    if ctx.DEBUG:
        print(f"Set LED to {colour.name}")

    # GPIO.setmode(GPIO.BCM)
    if colour == LedColour.GREEN:
        # GPIO.output(ctx.GREEN_LED, GPIO.HIGH)
        # GPIO.output(ctx.RED_LED, GPIO.LOW)
        ctx.redLED.off()
        ctx.greenLED.on()
        ctx.blueLED.off()
    elif colour == LedColour.RED:
        # GPIO.output(ctx.GREEN_LED, GPIO.LOW)
        # GPIO.output(ctx.RED_LED, GPIO.HIGH)
        ctx.redLED.on()
        ctx.greenLED.off()
        ctx.blueLED.off()
    elif colour == LedColour.BLUE:
        ctx.redLED.off()
        ctx.greenLED.off()
        ctx.blueLED.on()
    elif colour == LedColour.AMBER:
        # GPIO.output(ctx.GREEN_LED, GPIO.HIGH)
        # GPIO.output(ctx.RED_LED, GPIO.HIGH)
        ctx.redLED.on()
        ctx.greenLED.on()
        ctx.blueLED.off()
    elif colour == LedColour.PURPLE:
        # GPIO.output(ctx.GREEN_LED, GPIO.HIGH)
        # GPIO.output(ctx.RED_LED, GPIO.HIGH)
        ctx.redLED.on()
        ctx.greenLED.off()
        ctx.blueLED.on()
    elif colour == LedColour.CYAN:
        # GPIO.output(ctx.GREEN_LED, GPIO.HIGH)
        # GPIO.output(ctx.RED_LED, GPIO.HIGH)
        ctx.redLED.off()
        ctx.greenLED.on()
        ctx.blueLED.on()
    elif colour == LedColour.WHITE:
        # GPIO.output(ctx.GREEN_LED, GPIO.HIGH)
        # GPIO.output(ctx.RED_LED, GPIO.HIGH)
        ctx.redLED.on()
        ctx.greenLED.on()
        ctx.blueLED.on()
    else:
        # GPIO.output(ctx.GREEN_LED, GPIO.LOW)
        # GPIO.output(ctx.RED_LED, GPIO.LOW)
        ctx.greenLED.off()
        ctx.redLED.off()


def relay_off(ctx: StationContext):
    if ctx.DEBUG:
        print("Relay OFF")
    # GPIO.setmode(GPIO.BCM)
    # GPIO.output(ctx.RELAY_OUT, GPIO.LOW)
    ctx.relay.off()
    setLED(ctx, LedColour.BLUE)


def flickerLED(ctx: StationContext):
    ctx.greenLED.on()
    sleep(0.05)
    ctx.greenLED.off()
    sleep(0.05)
    ctx.greenLED.on()
    sleep(0.05)
    ctx.greenLED.off()


def relay_on(ctx: StationContext):
    if ctx.DEBUG:
        print("Relay ON")
    # GPIO.output(ctx.RELAY_OUT, GPIO.HIGH)
    ctx.relay.on()
    setLED(ctx, LedColour.RED)


def checkPIR(ctx: StationContext, secs: float):
    # High = off, Low = on (triggered)
    # GPIO.setmode(GPIO.BCM)
    # status = not GPIO.input(ctx.PIR_IN)
    status = ctx.pir.value
    # if ctx.DEBUG:
    #     print(f"PIR: {'ON' if status else 'OFF'}")
    if status:
        ctx.lastPirTime = secs
        ctx.pir_stat = 1
    elif secs - ctx.lastPirTime > ctx.PIR_TRIGGER_PERIOD:
        ctx.pir_stat = 0


def displayOn(ctx: StationContext):
    # Tell UI that display should be updated
    with open(DISPLAY_ON_FILE, "w", encoding="utf-8") as f:
        # Note that contents arent used
        f.write("ON")

    # Turn backlight on to show display
    if ctx.DEBUG:
        print("Turning Backlight on")
    run([BACKLIGHT_CMD, "-b", ctx.BACKLIGHT_BRIGHT], check=False)


def displayOff(ctx: StationContext):
    # Remove file to tell display to stop updating
    remove(DISPLAY_ON_FILE)
    # Turn backlight off
    if ctx.DEBUG:
        # print(f"UI status: {ctx.ui_process.poll()}")
        print("Turning Backlight off")
    run([BACKLIGHT_CMD, "-b", "0"], check=False)


def runLoop(ctx: StationContext):
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
        # Check for a local setTemp file - this is set by the GUI
        if path.exists(SET_TEMP_FILE):
            with open(SET_TEMP_FILE, "r", encoding="utf-8") as f:
                try:
                    tempStr = f.readline()
                    # print(f"Set temp str {str[:strLen-1]}")
                    ctx.currentManSetTemp = float(tempStr) * 10
                    chgState = True
                    if ctx.DEBUG:
                        print(
                            f"{nowTime}: Local Set temp set: {ctx.currentManSetTemp/10} "
                        )
                    remove(SET_TEMP_FILE)
                except:
                    print(f"{nowTime}: Set Temp: Failed")
                    ctx.currentManSetTemp = -1000
        # Check for a local boost file - this is set by the GUI
        if path.exists(BOOST_FILE):
            with open(BOOST_FILE, "r", encoding="utf-8") as f:
                try:
                    boostStr: str = f.readline()
                    # if "ON" in boostStr:
                    #     ctx.boostTime = nowSecs
                    # else:
                    #     ctx.boostTime = 0
                    # chgState = True
                    if ctx.DEBUG:
                        print(f"{nowTime}: BOOST: {boostStr} ")
                    remove(BOOST_FILE)
                except:
                    print(f"{nowTime}: Boost read: Failed")
                    ctx.currentManSetTemp = -1000
        if (nowSecs - ctx.lastTempTime) > ctx.TEMP_PERIOD:
            # Not received a temp update from control for more than a set period - read local
            ctx.lastTempTime = nowSecs
            # While not getting temp from control station, read locally more regularly
            ctx.TEMP_PERIOD = ctx.GET_MSG_PERIOD
            (ctx.currentTemp, ctx.currentHumidity) = readSHTC3Temp()
            ctx.currentTemp *= 10
            ctx.currentHumidity *= 10
            if ctx.DEBUG:
                print(
                    f"{nowTime}: Read local temp: {ctx.currentTemp/10} Humidity: {ctx.currentHumidity/10}"
                )

        if (nowSecs - ctx.setTempTime) > ctx.SET_TEMP_PERIOD:
            # Manually set temp has expired
            ctx.currentManSetTemp = -1000
            ctx.setTempTime = nowSecs
            chgState = True
        schedSetTemp = retrieveScheduledSetTemp(ctx, nowTime)
        holidayTemp = checkOnHoliday(ctx, nowSecs)
        # We have three set temperatures:
        # currentManSetTemp is one that has been set onscreen or sent remotely
        # schedSetTemp is one from the current schedule
        # holidayTemp is set if we are in a holiday period
        # Precedence:  holidayTemp >currentSetTemp > schedSetTemp
        saveTemp = ctx.currentSetTemp
        if holidayTemp != -1000:
            ctx.currentSetTemp = holidayTemp
        elif ctx.currentManSetTemp != -1000:
            ctx.currentSetTemp = ctx.currentManSetTemp
        elif schedSetTemp != -1000:
            ctx.currentSetTemp = schedSetTemp
        else:
            ctx.currentSetTemp = ctx.DEFAULT_TEMP
        if saveTemp != ctx.currentSetTemp:
            chgState = True

        # if ctx.DEBUG:
        #     print(
        #         f"{nowTime}: Calculated Set temp: {ctx.currentSetTemp} Sched temp: {schedSetTemp} Holiday temp: {holidayTemp} Current Temp: {ctx.currentTemp}\n"
        #     )
        if not ctx.currentBoilerStatus and (
            (ctx.currentTemp < ctx.currentSetTemp and ctx.currentTemp != -1000)
            or nowSecs - ctx.boostTime < ctx.BOOST_PERIOD
        ):
            # Only turn on heating if have a valid temp reading
            relay_on(ctx)
            ctx.currentBoilerStatus = 1
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: HEAT ON")
        elif ctx.currentBoilerStatus and (
            ctx.currentTemp > (ctx.currentSetTemp + ctx.HYSTERISIS)
            and ctx.boostTime == 0
        ):
            relay_off(ctx)
            ctx.currentBoilerStatus = 0
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: HEAT OFF")
        # relay_on(ctx)
        # sleep(1)
        # relay_off(ctx)
        checkPIR(ctx, nowSecs)
        if not ctx.displayOn and ctx.pir_stat:
            displayOn(ctx)
            ctx.displayOn = True
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: PIR ON")
        elif ctx.displayOn and not ctx.pir_stat:
            # Signal for display to be turned off
            displayOff(ctx)
            ctx.displayOn = False
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: PIR OFF")
        if chgState or ((nowSecs - ctx.lastMessageTime) > ctx.GET_MSG_PERIOD):
            # Send update in status and get any messages from control station
            chgState = True
            ctx.generateStatusFile()
            while chgState:
                chgState = sendMessage(ctx)
                ctx.lastMessageTime = nowSecs
                ctx.generateStatusFile()

        sleep(0.5)


if __name__ == "__main__":
    print("Starting thermostat service")
    context: StationContext = StationContext(configFile="./thermostat.ini")

    # # Read temp from DHT22
    # (currentTemp, humidity) = readTemp(False)

    context.lastTempTime = datetime.now().timestamp()
    context.lastMessageTime = 0

    context.reset = 1
    context.redLED = LED(context.RED_LED)
    context.greenLED = LED(context.GREEN_LED)
    context.blueLED = LED(context.BLUE_LED)
    context.pir = MotionSensor(context.PIR_IN)
    context.relay = OutputDevice(
        context.RELAY_OUT, active_high=True, initial_value=False
    )
    setLED(context, LedColour.GREEN)
    sleep(1)

    context.lastPirTime = datetime.now().timestamp()
    context.pir_stat = 1
    displayOn(context)
    setLED(context, LedColour.AMBER)
    sleep(1)

    readSchedules(context)
    setLED(context, LedColour.RED)
    sleep(1)

    readHoliday(context)
    setLED(context, LedColour.WHITE)
    sleep(1)

    setLED(context, LedColour.CYAN)
    sleep(1)

    # relay_off(context)

    if context.DEBUG:
        print("Setup complete")

    setLED(context, LedColour.BLUE)
    runLoop(context)
