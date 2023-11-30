import sys
from os import path, remove

from datetime import datetime
from time import sleep
import requests
import pickle

# import RPi.GPIO as GPIO
# import board
# import digitalio
from gpiozero import LED, MotionSensor, OutputDevice
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
    url_parts = [f"{ctx.controlstation_url}/message?s={ctx.station_num}"]
    if ctx.reset:
        url_parts.append("&rs=1")
        ctx.reset = False
    else:
        url_parts.append("&rs=0")
    url_parts.append(f"&p={ctx.pir_stat}")
    url_parts.append(f"&t={ctx.currentTemp*10}")
    url_parts.append(f"&h={ctx.currentHumidity*10}")
    url_parts.append(f"&st={ctx.currentSetTemp*10}")
    url_parts.append(f"&r={ctx.heat_on}")
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
        else:
            print(
                f"Failed to send message to control station: Response: {resp.status_code}"
            )

    except requests.exceptions.RequestException as re:
        print(f"Failed to send message to control station {re}")

    return chgState


def newSetTempMsg(ctx: StationContext, msgBytes: bytes):
    tempMsg = Temp.unpack(msgBytes)
    ctx.currentSetTemp = tempMsg.temp / 10
    ctx.setTempTime = datetime.now().timestamp()
    if ctx.DEBUG:
        print(f"Received Set thermostat temp {ctx.currentSetTemp}C")
    return True


def extTempMsg(ctx: StationContext, msgBytes: bytes):
    extMsg = SetExt.unpack(msgBytes)
    ctx.currentExtTemp = extMsg.setExt / 10
    ctx.windStr = str(extMsg.windStr)
    if ctx.DEBUG:
        print(f"Received Ext temp {ctx.currentExtTemp}C , wind {ctx.windStr}")
    return True


def setCurrentTempMsg(ctx: StationContext, msgBytes: bytes):
    tempMsg = Temp.unpack(msgBytes)
    ctx.currentTemp = tempMsg.temp / 10.0
    ctx.currentHumidity = tempMsg.humidity / 10.0
    ctx.TEMP_PERIOD = int(ctx.config["timings"]["TEMP_PERIOD"])
    ctx.lastTempTime = datetime.now().timestamp()
    if ctx.DEBUG:
        print(
            f"Received current temp {ctx.currentTemp}C, humidity {ctx.currentHumidity}"
        )
    return False


def setScheduleMsg(ctx: StationContext, msgBytes: bytes):
    sched = SchedByElem.unpack(msgBytes)
    elem = ScheduleElement(sched.day, sched.start, sched.end, sched.temp)
    ctx.schedules.add(elem)
    if ctx.DEBUG:
        print(f"Received schedule {elem} total schedules: {len(ctx.schedules)}")
    saveSchedules(ctx)
    # Return true as will be receiving new schedules
    return True


def deleteAllSchedulesMsg(ctx: StationContext):
    ctx.schedules = set()
    if path.exists(LOCAL_SCHEDULE_FILE):
        remove(LOCAL_SCHEDULE_FILE)
    if ctx.DEBUG:
        print("Deleted all schedules")

    # Return true as will be receiving new schedules
    return True


def readSchedules(ctx: StationContext):
    # Read file containing locally saved schedules
    if path.exists(LOCAL_SCHEDULE_FILE):
        ctx.schedules = ScheduleElement.loadSchedulesFromFile(LOCAL_SCHEDULE_FILE)
        ctx.schedules.remove(None)  # This is a dummy entry used by the control station
        for sched in ctx.schedules:
            sched.temp = sched.temp / 10.0
    else:
        print(f"Locally saved schedule file {LOCAL_SCHEDULE_FILE} not found ")


def saveSchedules(ctx: StationContext):
    ScheduleElement.saveSchedulesToFile(ctx.schedules, LOCAL_SCHEDULE_FILE)


def setHolidayMsg(ctx: StationContext, msgBytes: bytes):
    hols: HolidayStr = HolidayStr.unpack(msgBytes)
    holiday: Holiday = Holiday(hols)
    ctx.currentHoliday = holiday
    HolidayStr.saveToFile(LOCAL_HOLIDAY_FILE, hols)
    if ctx.DEBUG:
        print(
            f"Received new holiday: start: {datetime.fromtimestamp(holiday.startDate)} end: {datetime.fromtimestamp(holiday.endDate)}"
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
            f"Failed to receive correct CRC for message: {respContent} Bytes: {msgBytes} Calc-CRC: {calc_crc:X} rx-CRC: {crc:X}"
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
            print(f"Need to implement Motd {msgBytes}")
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
    if ctx.DEBUG:
        print(f"Set LED to {colour.name}")

    # GPIO.setmode(GPIO.BCM)
    if colour == LedColour.GREEN:
        # GPIO.output(ctx.GREEN_LED, GPIO.HIGH)
        # GPIO.output(ctx.RED_LED, GPIO.LOW)
        ctx.greenLED.on()
        ctx.redLED.off()
    elif colour == LedColour.RED:
        # GPIO.output(ctx.GREEN_LED, GPIO.LOW)
        # GPIO.output(ctx.RED_LED, GPIO.HIGH)
        ctx.greenLED.off()
        ctx.redLED.on()
    elif colour == LedColour.AMBER:
        # GPIO.output(ctx.GREEN_LED, GPIO.HIGH)
        # GPIO.output(ctx.RED_LED, GPIO.HIGH)
        ctx.greenLED.on()
        ctx.redLED.on()
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
    setLED(ctx, LedColour.RED)


def relay_on(ctx: StationContext):
    if ctx.DEBUG:
        print("Relay ON")
    # GPIO.output(ctx.RELAY_OUT, GPIO.HIGH)
    ctx.relay.on()
    setLED(ctx, LedColour.GREEN)


def checkPIR(ctx: StationContext, nowSecs: float):
    # High = off, Low = on (triggered)
    # GPIO.setmode(GPIO.BCM)
    # status = not GPIO.input(ctx.PIR_IN)
    status = ctx.pir.value
    # if ctx.DEBUG:
    #     print(f"PIR: {'ON' if status else 'OFF'}")
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
        if (nowSecs - ctx.lastTempTime) > ctx.TEMP_PERIOD:
            # Not received a temp update from control for more than a set period - read local
            ctx.lastTempTime = nowSecs
            # While not getting temp from control station, read locally more regularly
            ctx.TEMP_PERIOD = ctx.GET_MSG_PERIOD
            (ctx.currentTemp, ctx.currentHumidity) = readTemp(False)
            if ctx.DEBUG:
                print(
                    f"Read local temp: {ctx.currentTemp} Humidity: {ctx.currentHumidity}"
                )

        if (nowSecs - ctx.setTempTime) > ctx.SET_TEMP_PERIOD:
            # Manually set temp has expired
            ctx.currentManSetTemp = -100
            ctx.setTempTime = nowSecs
        schedSetTemp = retrieveScheduledSetTemp(ctx, nowTime)
        holidayTemp = checkOnHoliday(ctx, nowSecs)
        # We have three set temperatures:
        # currentManSetTemp is one that has been set onscreen or sent remotely
        # schedSetTemp is one from the current schedule
        # holidayTemp is set if we are in a holiday period
        # Precedence: currentSetTemp > holidayTemp > schedSetTemp
        if ctx.currentManSetTemp != -100:
            ctx.currentSetTemp = ctx.currentManSetTemp
        elif holidayTemp != -100:
            ctx.currentSetTemp = holidayTemp
        elif schedSetTemp != -100:
            ctx.currentSetTemp = schedSetTemp
        else:
            ctx.currentSetTemp = ctx.DEFAULT_TEMP

        if ctx.DEBUG:
            print(
                f"{nowTime}: Calculated Set temp: {ctx.currentSetTemp} Sched temp: {schedSetTemp} Holiday temp: {holidayTemp} Current Temp: {ctx.currentTemp}\n"
            )
        if not ctx.heat_on and (
            ctx.currentTemp < ctx.currentSetTemp and ctx.currentTemp != -100
        ):
            # Only turn on heating if have a valid temp reading
            relay_on(ctx)
            ctx.heat_on = True
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: HEAT ON")
        elif ctx.heat_on and ctx.currentTemp > (ctx.currentSetTemp + ctx.HYSTERISIS):
            relay_off(ctx)
            ctx.heat_on = False
            chgState = True
            if ctx.DEBUG:
                print(f"{nowTime}: HEAT OFF")
        # relay_on(ctx)
        # sleep(1)
        # relay_off(ctx)
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

    # # Read temp from DHT22
    # (currentTemp, humidity) = readTemp(False)
    nowSecs = datetime.now().timestamp()
    context.lastTempTime = 0
    context.lastMessageTime = 0

    context.reset = 1

    # # Use GPIO numbering, not pin numbering
    # GPIO.setmode(GPIO.BCM)
    # GPIO.setup(context.RELAY_OUT, GPIO.OUT)  # Relay output
    # GPIO.setup(context.PIR_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # PIR input
    # # GPIO.setup(context.TEMP_SENSOR, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # DHT22
    # GPIO.setup(context.GREEN_LED, GPIO.OUT)  # Green LED lit when boiler on
    # GPIO.setup(context.RED_LED, GPIO.OUT)  # RED LED lit when boiler off
    context.relay = OutputDevice(
        context.RELAY_OUT, active_high=True, initial_value=False
    )
    context.redLED = LED(context.RED_LED)
    context.greenLED = LED(context.GREEN_LED)
    context.pir = MotionSensor(context.PIR_IN)
    setLED(context, LedColour.AMBER)
    # relay_off(context)

    readSchedules(context)
    readHoliday(context)

    sleep(5)
    if context.DEBUG:
        print("Setup complete")

    setLED(context, LedColour.RED)
    runLoop(context)
