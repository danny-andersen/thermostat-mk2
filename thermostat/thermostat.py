import sys

import configparser
from datetime import datetime
from time import sleep
import requests
import RPi.GPIO as GPIO
import crcmod
import crcmod.predefined

from common.humidity_sensor import readTemp
from common.messages import *


# Format = /message?s=<station number>&rs=<1=rebooted>,&u=<1=update only, no resp msg needed>&t=<thermostat temp>&h=<humidity>&st=<set temp>&r=< mins to set temp, 0 off>&p=<1 sensor triggered, 0 sensor off>
def sendMessage(conf, ctx: StationContext):
    station_num = conf["station_num"]
    controlstation_url = conf["masterstation_url"]
    url_parts = [f"{controlstation_url}/message?s={station_num}&u=1"]
    if ctx.reset:
        url_parts.append("&rs=1")
        ctx.reset = False
    else:
        url_parts.append("&rs=0")
    url_parts.append(f"&p={ctx.current_pir_stat}")
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
    except FileNotFoundError:
        print(f"Locally saved schedule file {LOCAL_SCHEDULE_FILE} not found ")
    finally:
        fp.close()


def saveSchedules(ctx: StationContext):
    try:
        fp = open(LOCAL_SCHEDULE_FILE, "w", encoding="UTF-8")
        json.dump(ctx.schedules, fp)
    except:
        print(f"Failed to save schedules to {LOCAL_SCHEDULE_FILE}: {sys.exc_info()[0]}")
    finally:
        fp.close()


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
    except FileNotFoundError:
        print(f"Locally saved schedule file {LOCAL_HOLIDAY_FILE} not found ")
    finally:
        fp.close()


def saveHoliday(ctx: StationContext):
    try:
        fp = open(LOCAL_HOLIDAY_FILE, "w", encoding="UTF-8")
        json.dump(ctx.schcurrentHolidayedules, fp)
    except:
        print(f"Failed to save schedules to {LOCAL_HOLIDAY_FILE}: {sys.exc_info()[0]}")
    finally:
        fp.close()


def processResponseMsg(ctx: StationContext, resp: requests.Response):
    respContent: bytes = resp.content
    (msgId, mlen, crc) = Message.unpack(respContent)
    resp.content[2] = b"0"
    resp.content[3] = b"0"
    # print(f"len: {msg.len}, msg: {msgBytes}")
    crc_func = crcmod.predefined.mkCrcFun("crc-aug-ccitt")
    calc_crc = crc_func(respContent) & 0xFFFF
    if calc_crc != crc:
        print(
            f"Failed to receive correct CRC for message: {respContent} Calc-CRC: {calc_crc} rx-CRC: {crc}"
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
    ctx: StationContext, nowTime: datetime.datetime, wantNext: bool = False
) -> ScheduleElement:
    priority = 0
    next_mins = 1440
    retSched: ScheduleElement = ScheduleElement()
    curr_day = (
        nowTime.weekday() + 1
    )  # Python is 0-6 but the original 'C' code it was 1 - 7
    minOfDay = (nowTime.hour * 60) + nowTime.min
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
    return retSched


def setLED(colour: LedColour):
    if colour == LedColour.GREEN:
        GPIO.output(GREEN_LED, GPIO.HIGH)
        GPIO.output(RED_LED, GPIO.LOW)
    elif colour == LedColour.RED:
        GPIO.output(GREEN_LED, GPIO.LOW)
        GPIO.output(RED_LED, GPIO.HIGH)
    elif colour == LedColour.AMBER:
        GPIO.output(GREEN_LED, GPIO.HIGH)
        GPIO.output(RED_LED, GPIO.HIGH)
    else:
        GPIO.output(GREEN_LED, GPIO.LOW)
        GPIO.output(RED_LED, GPIO.LOW)


def relay_off():
    GPIO.output(RELAY_OUT, GPIO.LOW)
    setLED(LedColour.RED)


def relay_on():
    GPIO.output(RELAY_OUT, GPIO.HIGH)
    setLED(LedColour.GREEN)


def runLoop(cfg: configparser.ConfigParser, context: StationContext):
    # This function never returns unless there is an uncaught exception
    while True:
        nowTime = datetime.now().timestamp()
        chgState = False
        if (nowTime - context.lastTempTime) > TEMP_PERIOD:
            # Not received a temp update from control for more than a set period - read local
            context.lastTempTime = nowTime
            (context.currentTemp, context.currentHumidity) = readTemp(True)
        currentSchedule: ScheduleElement = retrieveScheduledSetTemp(context, nowTime)
        schedSetTemp = currentSchedule.temp / 10.0
        checkOnHoliday(context, nowTime)
        if context.currentSetTemp != -100:
            if not context.heat_on and context.currentTemp < schedSetTemp:
                relay_on()
                context.heat_on = True
                chgState = True
            elif context.heat_on and context.currentTemp > schedSetTemp + HYSTERISIS:
                relay_off()
                context.heat_on = False
                chgState = True
        else:
            if not context.heat_on and context.currentTemp < context.sentSetTemp:
                relay_on()
                context.heat_on = True
                chgState = True
            elif (
                context.heat_on
                and context.currentTemp > context.sentSetTemp + HYSTERISIS
            ):
                relay_off()
                context.heat_on = False
                chgState = True
        pir_stat = checkPIR()
        if not context.current_pir_stat and pir_stat:
            # Signal for display to be turned on
            displayOn()
            context.current_pir_stat = True
            chgState = True
        elif context.current_pir_stat and not pir_stat:
            # Signal for display to be turned off
            displayOff()
            context.current_pir_stat = pir_stat
            chgState = True
        if chgState or (nowTime - lastMessageTime) > GET_MSG_PERIOD:
            # Send update in status and get any messages from control station
            while chgState:
                chgState = sendMessage(cfg, context)

        sleep(1)


if __name__ == "__main__":
    print("Starting thermostat service")
    config = configparser.ConfigParser()
    config.read("./thermostat.ini")
    cfg = config["setup"]

    gpio_cfg = config["GPIO"]
    RELAY_OUT = int(gpio_cfg["RELAY_OUT"])
    PIR_IN = int(gpio_cfg["PIR_IN"])
    GREEN_LED = int(gpio_cfg["GREEN_LED"])
    RED_LED = int(gpio_cfg["RED_LED"])

    timings_cfg = config
    TEMP_PERIOD = int(timings_cfg["TEMP_PERIOD"])
    HYSTERISIS = float(cfg["HYSTERISIS"])
    GET_MSG_PERIOD = int(timings_cfg["GET_MSG_PERIOD"])

    # Use GPIO numbering, not pin numbering
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RELAY_OUT, GPIO.OUT)  # Relay output
    GPIO.setup(PIR_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Relay output
    GPIO.setup(GREEN_LED, GPIO.OUT)  # Green LED lit when boiler on
    GPIO.setup(RED_LED, GPIO.OUT)  # RED LED lit when boiler off
    setLED(LedColour.AMBER)

    # Read temp from DS18B20, which is a quick read on a Pi as its simply reading a file
    (currentTemp, humidity) = readTemp(True)
    lastTempTime = datetime.now()
    context: StationContext = StationContext()

    cfg["reset"] = "True"

    readSchedules(context)
    readHoliday(context)

    relay_off()

    sleep(15)

    runLoop(cfg, context)
