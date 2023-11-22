import sys

from datetime import datetime
from time import sleep
import requests
import RPi.GPIO as GPIO
import crcmod
import crcmod.predefined

# sys.path.insert(0, "../common")
from common.humidity_sensor import readTemp
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
    url_parts = [f"{ctx.controlstation_url}/message?s={ctx.station_num}&u=1"]
    if ctx.reset:
        url_parts.append("&rs=1")
        ctx.reset = False
    else:
        url_parts.append("&rs=0")
    url_parts.append(f"&p={ctx.pir_stat}")
    url_parts.append(f"&t={ctx.currentTemp}")
    url_parts.append(f"&h={ctx.currentHumidity}")
    url_parts.append(f"&st={ctx.currentSetTemp}")
    url_parts.append(f"&r={ctx.heat_on}")
    url = "".join(url_parts)
    chgState = False
    # Send HTTP request with a 5 sec timeout
    # print("Sending status update")
    try:
        resp = requests.get(url, timeout=5)
        # print(f"Received response code {resp.status_code}")
        if resp.status_code == 200:
            chgState = processResponseMsg(ctx, resp)
        else:
            print(
                f"Failed to send message to control station: Response: {resp.status_code}"
            )

    except requests.exceptions.RequestException as re:
        print(f"Failed to send message to control station {re}")

    return chgState


def newSetTempMsg(ctx: StationContext, msgBytes: bytearray):
    tempMsg = Temp(msgBytes)
    ctx.currentSetTemp = tempMsg.temp
    ctx.setTempTime = datetime.now().timestamp()
    return True


def extTempMsg(ctx: StationContext, msgBytes: bytearray):
    extMsg = SetExt(msgBytes)
    ctx.currentExtTemp = extMsg.setExt
    ctx.windStr = str(extMsg.windStr)
    return True


def setCurrentTempMsg(ctx: StationContext, msgBytes: bytearray):
    tempMsg = Temp(msgBytes)
    ctx.currentTemp = tempMsg.temp
    return True


def setScheduleMsg(ctx: StationContext, msgBytes: bytearray):
    sched = SchedByElem(msgBytes)
    elem = ScheduleElement(sched.day, sched.start, sched.end, sched.temp)
    ctx.schedules.append(elem)
    saveSchedules(ctx)
    # Return true as will be receiving new schedules
    return True


def deleteAllSchedulesMsg(ctx: StationContext):
    ctx.schedules = set()
    saveSchedules(ctx)
    # Return true as will be receiving new schedules
    return True


def readSchedules(ctx: StationContext):
    # Read file containing locally saved schedules
    try:
        fp = open(LOCAL_SCHEDULE_FILE, "r", encoding="UTF-8")
        ctx.schedules = json.load(fp)
        fp.close()
    except FileNotFoundError:
        print(f"Locally saved schedule file {LOCAL_SCHEDULE_FILE} not found ")


def saveSchedules(ctx: StationContext):
    try:
        fp = open(LOCAL_SCHEDULE_FILE, "w", encoding="UTF-8")
        json.dump(ctx.schedules, fp)
        fp.close()
    except:
        print(f"Failed to save schedules to {LOCAL_SCHEDULE_FILE}: {sys.exc_info()[0]}")


def setHolidayMsg(ctx: StationContext, msgBytes: bytearray):
    hols = HolidayStr(msgBytes)
    holiday = Holiday()
    holiday.startDate = datetime.datetime(
        hols.startdate.year,
        hols.startdate.month,
        hols.startdate.dayOfMonth,
        hols.startdate.hour,
    ).timestamp
    holiday.endDate = datetime.datetime(
        hols.endDate.year,
        hols.endDate.month,
        hols.endDate.dayOfMonth,
        hols.endDate.hour,
    ).timestamp
    holiday.temp = hols.temp / 10.0
    ctx.currentHoliday = holiday
    return False


def readHoliday(ctx: StationContext):
    # Read file containing locally saved holiday
    try:
        fp = open(LOCAL_HOLIDAY_FILE, "r", encoding="UTF-8")
        ctx.currentHoliday = json.load(fp)
        fp.close()
    except FileNotFoundError:
        print(f"Locally saved holiday file {LOCAL_HOLIDAY_FILE} not found ")


def saveHoliday(ctx: StationContext):
    try:
        fp = open(LOCAL_HOLIDAY_FILE, "w", encoding="UTF-8")
        json.dump(ctx.schcurrentHolidayedules, fp)
        fp.close()
    except:
        print(f"Failed to save holiday to {LOCAL_HOLIDAY_FILE}: {sys.exc_info()[0]}")


def processResponseMsg(ctx: StationContext, resp: requests.Response):
    respContent: bytes = resp.content
    (msgId, mlen, crc) = Message.unpack(respContent)
    msgBytes = bytearray(respContent)
    msgBytes[2:3] = b"\x00"
    msgBytes[3:4] = b"\x00"
    chgState = False
    # print(f"len: {msg.len}, msg: {msgBytes}")
    crc_func = crcmod.predefined.mkCrcFun("crc-aug-ccitt")
    calc_crc = crc_func(msgBytes) & 0xFFFF
    if calc_crc != crc:
        print(
            f"Failed to receive correct CRC for message: {respContent} Bytes: {msgBytes} Calc-CRC: {calc_crc:X} rx-CRC: {crc:X}"
        )
    else:
        msgBytes = bytearray()
        for i in range(4, mlen):
            msgBytes.append(respContent[i])
        if msgId == REQ_STATUS_MSG:
            chgState = True
        elif msgId == SET_TEMP_MSG:
            newSetTempMsg(ctx, msgBytes)
        elif msgId == SET_EXT_MSG:
            extTempMsg(ctx, msgBytes)
        elif msgId == SCHEDULE_MSG:
            setScheduleMsg(ctx, msgBytes)
        elif msgId == DELETE_ALL_SCHEDULES_MSG:
            deleteAllSchedulesMsg(ctx)
        elif msgId == SET_HOLIDAY_MSG:
            setHolidayMsg(ctx, msgBytes)
        elif msgId == SET_THERM_TEMP_MSG:
            setCurrentTempMsg(ctx, msgBytes)
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
    return retSched.temp / 10.0


def checkOnHoliday(ctx: StationContext, nowSecs: float):
    retTemp = -100.0
    if nowSecs > ctx.currentHoliday.startDate and nowSecs < ctx.currentHoliday.endDate:
        # On holiday
        retTemp = ctx.currentHoliday.temp
    return retTemp


def setLED(ctx: StationContext, colour: LedColour):
    if colour == LedColour.GREEN:
        GPIO.output(ctx.GREEN_LED, GPIO.HIGH)
        GPIO.output(ctx.RED_LED, GPIO.LOW)
    elif colour == LedColour.RED:
        GPIO.output(ctx.GREEN_LED, GPIO.LOW)
        GPIO.output(ctx.RED_LED, GPIO.HIGH)
    elif colour == LedColour.AMBER:
        GPIO.output(ctx.GREEN_LED, GPIO.HIGH)
        GPIO.output(ctx.RED_LED, GPIO.HIGH)
    else:
        GPIO.output(ctx.GREEN_LED, GPIO.LOW)
        GPIO.output(ctx.RED_LED, GPIO.LOW)


def relay_off(ctx: StationContext):
    GPIO.output(ctx.RELAY_OUT, GPIO.HIGH)
    setLED(ctx, LedColour.RED)


def relay_on(ctx: StationContext):
    GPIO.output(ctx.RELAY_OUT, GPIO.LOW)
    setLED(ctx, LedColour.GREEN)


def checkPIR(ctx: StationContext, nowSecs: float):
    # High = off, Low = on (triggered)
    status = not GPIO.input(ctx.PIR_IN)
    if status:
        ctx.lastPirTime = nowSecs
        ctx.pir_stat = 1
    elif nowSecs - ctx.lastPirTime > ctx.PIR_TRIGGER_PERIOD:
        ctx.pir_stat = 0


def displayOn(ctx: StationContext):
    # TODO: Drive display backlight on
    pass


def runLoop(ctx: StationContext):
    # This function never returns unless there is an uncaught exception
    while True:
        nowTime = datetime.now()
        nowSecs = nowTime.timestamp()
        chgState = False
        if (nowSecs - ctx.lastTempTime) > ctx.TEMP_PERIOD:
            # Not received a temp update from control for more than a set period - read local
            ctx.lastTempTime = nowSecs
            (ctx.currentTemp, ctx.currentHumidity) = readTemp(True)
            if ctx.DEBUG:
                print(
                    f"Read local temp: {ctx.currentTemp} Humidity: {ctx.currentHumidity}"
                )

        if (nowSecs - ctx.setTempTime) > ctx.SET_TEMP_PERIOD:
            # Manually set temp has expired
            ctx.currentSetTemp = -100
            ctx.setTempTime = nowSecs
        schedSetTemp = retrieveScheduledSetTemp(ctx, nowTime)
        holidayTemp = checkOnHoliday(ctx, nowSecs)
        # We have three set temperatures:
        # currentSetTemp is one that has been set onscreen or sent remotely
        # schedSetTemp is one from the current schedule
        # holidayTemp is set if we are in a holiday period
        # Precedence: currentSetTemp > holidayTemp > schedSetTemp
        if ctx.currentSetTemp != -100:
            setTemp = ctx.currentSetTemp
        elif holidayTemp != -100:
            setTemp = holidayTemp
        elif schedSetTemp != -100:
            setTemp = schedSetTemp
        else:
            setTemp = ctx.DEFAULT_TEMP

        if ctx.DEBUG:
            print(
                f"{nowTime}: Calculated Set temp: {setTemp} Sched temp: {schedSetTemp} Holiday temp: {holidayTemp} Current Temp: {ctx.currentTemp}\n"
            )
        if not ctx.heat_on and (ctx.currentTemp < setTemp and ctx.currentTemp != -100):
            # Only turn on heating if have a valid temp reading
            relay_on(ctx)
            ctx.heat_on = True
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: HEAT ON")
        elif ctx.heat_on and ctx.currentTemp > (setTemp + ctx.HYSTERISIS):
            relay_off(ctx)
            ctx.heat_on = False
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: HEAT OFF")

        checkPIR(ctx, nowSecs)
        if ctx.pir_stat:
            # Signal for display to be turned on
            displayOn(ctx)
        if not ctx.currentPirStatus and ctx.pir_stat:
            ctx.currentPirStatus = 1
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: PIR ON")
        elif ctx.currentPirStatus and not ctx.pir_stat:
            # Signal for display to be turned off
            # displayOff(ctx)
            ctx.currentPirStatus = False
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: PIR OFF")
        if chgState or ((nowSecs - ctx.lastMessageTime) > ctx.GET_MSG_PERIOD):
            # Send update in status and get any messages from control station
            chgState = True
            while chgState:
                chgState = sendMessage(ctx)
                ctx.lastMessageTime = nowSecs

        sleep(1)


if __name__ == "__main__":
    print("Starting thermostat service")
    context: StationContext = StationContext(configFile="./thermostat.ini")

    # Use GPIO numbering, not pin numbering
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(context.RELAY_OUT, GPIO.OUT)  # Relay output
    GPIO.setup(context.PIR_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Relay output
    GPIO.setup(context.TEMP_SENSOR, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # DHT22
    GPIO.setup(context.GREEN_LED, GPIO.OUT)  # Green LED lit when boiler on
    GPIO.setup(context.RED_LED, GPIO.OUT)  # RED LED lit when boiler off
    setLED(context, LedColour.AMBER)

    # Read temp from DS18B20, which is a quick read on a Pi as its simply reading a file
    (currentTemp, humidity) = readTemp(True)
    nowSecs = datetime.now().timestamp()
    context.lastTempTime = nowSecs
    context.lastMessageTime = nowSecs

    context.reset = 1

    readSchedules(context)
    readHoliday(context)

    relay_off(context)

    sleep(5)

    setLED(context, LedColour.RED)

    runLoop(context)
