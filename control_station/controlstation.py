from datetime import datetime
from os import stat, path, remove
import copy
from multiprocessing import Process
from time import sleep
import subprocess
import atexit

from ctypes import *
from flask import *
from uwsgidecorators import *

import crcmod
import crcmod.predefined
from filelock import FileLock, Timeout

from common.messages import *

# from capture_camera import monitorAndRecord
from common.humidity_sensor import readTemp, readSHTC3Temp


monitorScriptProcess: Process


def getTemp(history: tuple[dict[int, float], dict[int, float]]):
    # Read temp and humidity from sensor and write them to a file
    # This caters for the fact that reading from these can be slow (seconds)
    # and so allows the web server to read the file quickly and respond quickly
    (temp, humid) = readSHTC3Temp()
    # Write out temps to be used by controlstation
    # print(f"Latest temp: {temp}, humid {humid}")
    with open(TEMPERATURE_FILE_NEW, mode="w", encoding="utf-8") as f:
        f.write(f"{temp:.1f}\n")
    with open(HUMIDITY_FILE_NEW, mode="w", encoding="utf-8") as f:
        f.write(f"{humid:.1f}\n")
    # Create a rolling 5 min average for temp and humidity to be used by history
    now = datetime.now()
    (histTempD, histHumidD) = history
    nowmin = now.minute % TEMP_AVERAGE_MIN
    histTemp = histTempD.get(nowmin, -100)
    if histTemp == -100:
        histTempD[nowmin] = temp
    else:
        histTempD[nowmin] = (temp + histTemp) / 2
    nowmin = now.minute % TEMP_AVERAGE_MIN
    histHumid = histHumidD.get(nowmin, -100)
    if histHumid == -100:
        histHumidD[nowmin] = humid
    else:
        histHumidD[nowmin] = (humid + histHumid) / 2
    if nowmin == 0:
        # Calculate temp average
        totalTemp = 0.0
        vals = 0
        for i in range(0, TEMP_AVERAGE_MIN):
            t = histTempD.get(i, -100)
            if t != -100:
                totalTemp += t
                vals += 1
            if i != 0:
                histTempD[i] = -100
        if vals > 1:
            # Only process if it is first time processing this minute
            avgTemp = totalTemp / vals
            with open(TEMP_AVG_FILE, mode="w", encoding="utf-8") as f:
                f.write(f"{avgTemp:.1f}\n")
        elif vals == 0:
            avgTemp = -100  # No measurement made in period
            with open(TEMP_AVG_FILE, mode="w", encoding="utf-8") as f:
                f.write(f"{avgTemp:.1f}\n")
    nowmin = now.minute % HUMID_AVERAGE_MIN
    histHumid = histHumidD.get(nowmin, -100)
    if histHumid == -100:
        histHumidD[nowmin] = humid
    else:
        histHumidD[nowmin] = (humid + histHumid) / 2
    if nowmin == 0:
        # Calculate humid average
        totalHumid = 0.0
        vals = 0
        for i in range(0, HUMID_AVERAGE_MIN):
            h = histHumidD.get(i, -100)
            if h != -100:
                totalHumid += h
                vals += 1
            histHumidD[i] = -100
        if vals > 1:
            # Only process if it is first time processing this minute
            avgHumid = totalHumid / vals
            with open(HUMID_AVG_FILE, mode="w", encoding="utf-8") as f:
                f.write(f"{avgHumid:.0f}\n")
        elif vals == 0:
            avgHumid = -100  # No measurement made in period
            with open(HUMID_AVG_FILE, mode="w", encoding="utf-8") as f:
                f.write(f"{avgHumid:.10f}\n")


def runScript():
    print("Running monitoring script")
    subprocess.run(args=MONITOR_SCRIPT, shell=True)


def runMonitorScript():
    print(f"******Starting monitor script thread loop {MONITOR_SCRIPT}")
    lastTempTime = 0
    lastMonitorTime = 0
    if path.exists(TEMPERATURE_FILE_NEW):
        remove(TEMPERATURE_FILE_NEW)
    if path.exists(HUMIDITY_FILE_NEW):
        remove(HUMIDITY_FILE_NEW)
    if path.exists(TEMP_AVG_FILE):
        remove(TEMP_AVG_FILE)
    if path.exists(HUMID_AVG_FILE):
        remove(HUMID_AVG_FILE)
    sleep(15)
    history: tuple[dict[int, float], dict[int, float]] = (dict(), dict())
    # Wait until server up and running
    while True:
        nowTime = datetime.now().timestamp()
        if (nowTime - lastTempTime) > TEMP_PERIOD:
            # Read temp and humidity and update latest files
            lastTempTime = nowTime
            getTemp(history)
        nowTime = datetime.now().timestamp()
        if (nowTime - lastMonitorTime) > MONITOR_PERIOD:
            # Run the monitor script
            lastMonitorTime = nowTime
            runScript()
        sleep(1)


lock = FileLock("monitor_thread.lock")
app = Flask(__name__)


@postfork
def setup():
    global lock
    global monitorScriptProcess
    try:
        if lock.acquire(1):
            print("Starting monitoring threads")
            # Only one thread gets the lock
            # cameraProcess = Process(target=monitorAndRecord, daemon=False)
            # cameraProcess.start()
            monitorScriptProcess = Process(target=runMonitorScript, daemon=True)
            monitorScriptProcess.start()
            atexit.register(stopMonitoring)
            sleep(10)
            lock.release()
    except Timeout:
        print("This thread skipping creating monitoring threads")
        pass


@signal(3)
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


def getNoMessage():
    msgBytes = getMessageEnvelope(NO_MESSAGE, bytearray(0), 0)
    return Response(response=msgBytes, mimetype="application/octet-stream")


def getMessageEnvelope(mid, content: bytearray, mlen):
    msg = Message()
    msg.id = mid
    msg.len = mlen + 4
    msg.crc = 0
    msgBytes = bytearray(msg) + content
    # print(f"len: {msg.len}, msg: {msgBytes}")
    crc_func = crcmod.predefined.mkCrcFun("crc-aug-ccitt")
    crc = crc_func(msgBytes) & 0xFFFF
    # print(f"CRC crc-aug-ccitt fun: {crc:02x}")
    # msg.crc = short(crc + 2**16).to_bytes(2, 'little')
    # msg.crc = crc.to_bytes(2, 'little')
    msg.crc = crc
    return bytes(bytearray(msg) + content)


def retrieveTempValue(primary, secondary):
    retValue: float = -1000.0
    try:
        with open(primary, "r", encoding="utf-8") as f:
            s = f.readline()
            # Mulitply by 10 as temp in .1 degrees
            retValue = float(s) * 10
    except:
        try:
            with open(secondary, "r", encoding="utf-8") as f:
                str = f.readline()
                # print(f"Set temp str {str[:strLen-1]}")
                # Mulitply by 10 as humidity in .1 degrees
                retValue = float(str) * 10
        except:
            retValue = -1000.0
    return retValue


def readThermStr():
    # Read temp from temp file - use new file if it exist, otherwise use old file
    temp = retrieveTempValue(TEMPERATURE_FILE_NEW, TEMPERATURE_FILE)
    humidity = retrieveTempValue(HUMIDITY_FILE_NEW, HUMIDITY_FILE)
    return (temp, humidity)


def createThermMsg(temp: float, humidity: float):
    tempMsg = Temp()
    tempMsg.temp = c_int16(int(temp))
    tempMsg.humidity = c_int16(int(humidity))
    msgBytes = getMessageEnvelope(SET_THERM_TEMP_MSG, bytearray(tempMsg), sizeof(Temp))
    response = Response(response=msgBytes, mimetype="application/octet-stream")
    # print(f"Temp: {tempMsg.temp}")
    return response


# Format = /message?s=<station number>&rs=<1=rebooted>,&u=<1=update only, no resp msg needed>&t=<thermostat temp>&h=<humidity>&st=<set temp>&r=< mins to set temp, 0 off>&p=<1 sensor triggered, 0 sensor off>
@app.route("/message", methods=["GET"])
def getMessage():
    args = request.args
    stn = args.get("s", type=int)
    if stn:
        sc: StationContext = StationContext.getSavedContext(stn)
    else:
        # No station number given - use default context
        sc: StationContext = StationContext()
    startContext = copy.deepcopy(sc)
    resend = args.get("rs", type=int, default=0)
    if resend > 0:
        # Thermostat has rebooted or reconnected - resend any messages
        if resend == 1:
            print(f"RESET OF STATION {sc.stationNo} DETECTED")
        elif resend == 2:
            print(f"WIFI RESET OF STATION {sc.stationNo} DETECTED")
        sc.motdTime = 0
        sc.tempMotdTime = 0
        sc.setTempTime = 0
        sc.setHolidayTime = 0
        sc.extTempTime = 0
        sc.setSchedTime = 0
        sc.currentTemp = -1000
        sc.currentExtTemp = -1000
        sc.currentSetTemp = -1000
        sc.currentHumidity = -1000
        sc.motdExpiry = MOTD_EXPIRY_SECS
        sc.scheduleMsgs = []
    temp = args.get("t", type=float)
    if temp:
        sc.currentTemp = temp
    humid = args.get("h", type=float)
    if humid:
        sc.currentHumidity = humid
    therm = args.get("st", type=float)
    if therm:
        sc.currentSetTemp = therm
    heat = args.get("r", type=int, default=0)
    if heat or (heat == 0 and sc.currentBoilerStatus > 0):
        sc.currentBoilerStatus = heat
    pir = args.get("p", type=int, default=0)
    if (pir and not sc.displayOn) or (not pir and sc.displayOn):
        sc.displayOn = pir
    if pir:
        sc.lastPirTime = datetime.now().timestamp()
    updateOnly = args.get("u", type=int, default=0)
    if updateOnly:
        response: Response = getNoMessage()
    else:
        # print(f"Station: {stn} Getting next message")
        response: Response = None
        # Currently only the conservatory camera and thermostat stations (1 and 6)
        # check for command type messages - the others are purely update only
        if stn in (1, 6) and path.exists(COMMAND_FILE):
            response = createCommandMsg(stn)
        if stn == 1 and response == None:
            # Thermostat command msg check
            if sc.motdExpiry < TEMP_MOTD_EXPIRY_SECS:
                sc.motdExpiry = TEMP_MOTD_EXPIRY_SECS  # Have a minimum expiry time

            checkAndDeleteFile(MOTD_FILE, sc.motdExpiry)
            checkAndDeleteFile(SET_TEMP_FILE, SET_TEMP_EXPIRY_SECS)
            checkAndDeleteFile(EXTTEMP_FILE, EXT_TEMP_EXPIRY_SECS)
            checkAndDeleteFile(HOLIDAY_FILE, SET_TEMP_EXPIRY_SECS)
            checkAndDeleteFile(SCHEDULE_FILE, SET_SCHED_EXPIRY_SECS)
            if not path.exists(SCHEDULE_FILE):
                sc.setSchedTime = 0
            if sc.tempMotdTime and (
                datetime.now().timestamp() - sc.tempMotdTime > TEMP_MOTD_EXPIRY_SECS
            ):
                # Check if temp motd has expired
                sc.tempMotdTime = 0
                sc.motdTime = 0  # Resend any motd
            if (
                len(sc.scheduleMsgs) == 0
                and path.exists(SCHEDULE_FILE)
                and stat(SCHEDULE_FILE).st_mtime > sc.setSchedTime
            ):
                createScheduleMsgs(sc)
            if len(sc.scheduleMsgs) > 0:
                response = getNextScheduleMsg(sc)
                print(f"Number of schedules remaining to send: {len(sc.scheduleMsgs)}")
            elif (
                path.exists(SET_TEMP_FILE)
                and stat(SET_TEMP_FILE).st_mtime > sc.setTempTime
            ):
                response = getSetTemp(sc)
            elif (
                path.exists(HOLIDAY_FILE)
                and stat(HOLIDAY_FILE).st_mtime > sc.setHolidayTime
            ):
                response = getHoliday(sc)
            elif (
                path.exists(EXTTEMP_FILE)
                and stat(EXTTEMP_FILE).st_mtime > sc.extTempTime
            ):
                response = getExtTemp(sc)
            elif sc.tempMotd:
                response = createMotd(sc.tempMotd)
                sc.tempMotd = None
                sc.tempMotdTime = datetime.now().timestamp()
                # motdTime = 0 #Resend motd after temp motd has expired
            elif (
                not sc.tempMotdTime
                and path.exists(MOTD_FILE)
                and stat(MOTD_FILE).st_mtime > sc.motdTime
            ):
                # Only send new motd if temp Motd has timed out
                response = getMotd(sc)
                sc.motdTime = stat(MOTD_FILE).st_mtime
            else:
                (temp, humidity) = readThermStr()
                if humidity != -1000:
                    sc.currentHumidity = humidity
                if temp != -1000:
                    sc.currentTemp = temp
                    response = createThermMsg(temp, humidity)
                else:
                    pass  # Do something else
        if response == None:
            response = getNoMessage()

    sc.saveStationContext(startContext)
    # Always generate status file to update last heard time
    sc.generateStatusFile()

    return response


@app.route("/datetime", methods=["POST", "GET"])
def getDateTime():
    now = datetime.now()
    dt = DateTimeStruct()
    dt.sec = now.second
    dt.min = now.minute
    dt.hour = now.hour
    dt.dayOfWeek = now.isoweekday()  # 1 = Monday, 7 = Sunday, to match RTC
    dt.dayOfMonth = now.day
    dt.month = now.month
    dt.year = now.year - 2000
    with open("dateMsg", "w", encoding="utf-8") as f:
        f.write(f"Time: {dt.hour}:{dt.min}:{dt.sec}")
    msgBytes = getMessageEnvelope(
        SET_DATE_TIME_MSG, bytearray(dt), sizeof(DateTimeStruct)
    )
    # print(f"DateTime msg")

    return Response(response=msgBytes, mimetype="application/octet-stream")


@app.route("/motd", methods=["GET"])
def getMotd(sc: StationContext = None):
    readSC = False
    if not sc:
        args = request.args
        stn = args.get("s", type=int)
        if stn:
            sc: StationContext = StationContext(stn)
            readSC = True
        else:
            # No station number given - use default context
            sc: StationContext = StationContext()
    motdStr = ""
    checkAndDeleteFile(MOTD_FILE, sc.motdExpiry)
    if path.exists(MOTD_FILE):
        with open(MOTD_FILE, "r", encoding="utf-8") as f:
            motdStr = f.readline()
            exp = int(f.readline())
            sc.motdExpiry = (
                MOTD_EXPIRY_SECS if exp == "" else exp - 10000
            )  # Expire 10s before the thermostat does
            if sc.motdExpiry < TEMP_MOTD_EXPIRY_SECS:
                sc.motdExpiry = (
                    TEMP_MOTD_EXPIRY_SECS  # Have a minimum expiry time of 60 seconds
                )
            sc.motdTime = stat(MOTD_FILE).st_mtime
            sc.tempMotdTime = 0
            motdStr = motdStr[: len(motdStr) - 1]
            resp = createMotd(motdStr, exp)
    else:
        resp = getDefaultMotd()
        sc.motdTime = 0
        sc.tempMotdTime = 0
    if readSC:
        sc.saveStationContext()
    return resp


def getDefaultMotd():
    motdStr = "No weather forecast, please wait....."
    return createMotd(motdStr, TEMP_MOTD_EXPIRY_SECS * 1000)


def createCommandMsg(stn):
    response: Response = None
    msgBytes: bytes = []
    command = ""
    deleteFile = True

    with open(COMMAND_FILE, "r", encoding="utf-8") as f:
        # Command file format: <stn id>:<command>
        try:
            contents = f.readline()
            if ":" in contents:
                fields = contents.split(":")
                if int(fields[0].strip()) == stn:
                    # For this station
                    command = fields[1].strip().lower()
                else:
                    # For another station so dont delete file
                    deleteFile = False
        except:
            print(f"Set Command: Failed")
            pass
    if deleteFile:
        print(
            f"{datetime.now()}: Processed command file: Stn: {stn} command: {command}"
        )
        remove(COMMAND_FILE)
    if command == "reset":
        msgBytes = getMessageEnvelope(RESET_MSG, bytearray(0), 0)
    elif "light" in command:
        lightMsg = LightMsg()
        if "off" in command:
            lightMsg.lightState = 0
        elif "on" in command:
            lightMsg.lightState = 1
        else:
            print(f"Invalid light state in light command: {command}")
            lightMsg = None
        if lightMsg:
            msgBytes = getMessageEnvelope(
                LIGHT_COMMAND_MSG, bytearray(lightMsg), sizeof(LightMsg)
            )
    elif "boost" in command:
        msg = BoostMsg()
        if "off" in command:
            msg.boost = 0
        elif "on" in command:
            msg.boost = 1
        else:
            print(f"Invalid boost state in boost command: {command}")
            msg = None
        if msg:
            msgBytes = getMessageEnvelope(
                BOOST_COMMAND_MSG, bytearray(msg), sizeof(BoostMsg)
            )
    if len(msgBytes) > 0:
        response = Response(response=msgBytes, mimetype="application/octet-stream")
    return response


def createMotd(newMotd, motdExpiry=TEMP_MOTD_EXPIRY_SECS * 1000):
    strLen = len(newMotd) if len(newMotd) < MAX_MOTD_SIZE - 1 else MAX_MOTD_SIZE - 1
    motdStr = bytes(newMotd[:strLen], encoding="utf-8")
    motdLen = len(motdStr) + 1

    # print(f"Str len; {strLen}")
    class Motd(Structure):
        _fields_ = [
            ("expiry", c_uint32),  # Number of millis after which message expires
            ("motdStr", c_char * motdLen),
        ]  # Message of the day, with a minimum of one character

    motd = Motd()
    motd.motdStr = motdStr
    motd.expiry = motdExpiry
    # print(f"Motd: {motd.motdStr} Expiry: {motd.expiry}")
    # print(f"String Len: {motdLen} Len of content: {sizeof(Motd)}")
    msgBytes = getMessageEnvelope(MOTD_MSG, bytearray(motd), sizeof(Motd))
    return Response(response=msgBytes, mimetype="application/octet-stream")


@app.route("/settemp", methods=["GET"])
def getSetTemp(sc: StationContext = None):
    readSC = False
    changed = False
    if not sc:
        args = request.args
        stn = args.get("s", type=int)
        if stn:
            sc: StationContext = StationContext(stn)
            readSC = True
        else:
            # No station number given - use default context
            sc: StationContext = StationContext()
    tempMsg = Temp()
    gotTemp = False
    response: Response = None
    checkAndDeleteFile(SET_TEMP_FILE, SET_TEMP_EXPIRY_SECS)
    if path.exists(SET_TEMP_FILE):
        with open(SET_TEMP_FILE, "r", encoding="utf-8") as f:
            try:
                tempStr = f.readline()
                # print(f"Set temp str {str[:strLen-1]}")
                temp = c_int16(int(float(tempStr) * 10))
                tempMsg.temp = temp
                # print(f"Set Temp {temp}")
                msgBytes = getMessageEnvelope(
                    SET_TEMP_MSG, bytearray(tempMsg), sizeof(Temp)
                )
                response = Response(
                    response=msgBytes, mimetype="application/octet-stream"
                )
                gotTemp = True
                sc.setTempTime = stat(SET_TEMP_FILE).st_mtime + 1
                if readSC:
                    changed = True

            except:
                print(f"Set Temp: Failed")
                pass
    if not gotTemp:
        print(f"No set temp file")
        response = getNoMessage()
    if changed:
        sc.saveStationContext()
        sc.generateStatusFile()

    return response


@app.route("/exttemp", methods=["GET"])
def getExtTemp(sc: StationContext = None):
    extMsg = SetExt()
    gotExt = False
    response: Response = None
    readSC = False
    changed = False
    if not sc:
        args = request.args
        stn = args.get("s", type=int)
        if stn:
            sc: StationContext = StationContext(stn)
            readSC = True
        else:
            # No station number given - use default context
            sc: StationContext = StationContext()
    checkAndDeleteFile(EXTTEMP_FILE, EXT_TEMP_EXPIRY_SECS)
    if path.exists(EXTTEMP_FILE):
        with open(EXTTEMP_FILE, "r", encoding="utf-8") as f:
            try:
                tmpStr = f.readline()
                strLen = len(tmpStr)
                extMsg.setExt = c_int16(int(float(tmpStr[: strLen - 1]) * 10))
                sc.currentExtTemp = extMsg.setExt
                # print(f"Ext Temp {extMsg.setExt}")
                tmpStr = f.readline()
                strLen = len(tmpStr)
                if strLen > MAX_WIND_SIZE:
                    strLen = MAX_WIND_SIZE
                extMsg.windStr = bytes(tmpStr[: strLen - 1], encoding="utf-8")
                # print(f"Wind str {extMsg.windStr}")
                msgBytes = getMessageEnvelope(
                    SET_EXT_MSG, bytearray(extMsg), sizeof(SetExt)
                )
                response = Response(
                    response=msgBytes, mimetype="application/octet-stream"
                )
                gotExt = True
                sc.extTempTime = stat(EXTTEMP_FILE).st_mtime + 1
                if readSC:
                    changed = True
            except:
                print(f"Ext Temp: Failed")
                pass
    if not gotExt:
        print(f"No ext temp file")
        sc.currentExtTemp = -1000.0
        response = getNoMessage()
    if changed:
        sc.saveStationContext()
        sc.generateStatusFile()

    return response


@app.route("/temp", methods=["GET"])
def getThermTemp(sc: StationContext = StationContext()):
    response: Response = None
    (temp, humidity) = readThermStr()
    if temp != -1000:
        sc.currentTemp = temp
        response = createThermMsg(temp, humidity)
    else:
        print(f"No temp file")
        response = getNoMessage()
    if humidity != -1000:
        sc.currentHumidity = float(humidity)
    return response


@app.route("/holiday", methods=["POST", "GET"])
def getHoliday(sc: StationContext = None):
    response: Response = None
    readSC = False
    changed = False
    if not sc:
        args = request.args
        stn = args.get("s", type=int)
        if stn:
            sc: StationContext = StationContext(stn)
            readSC = True
        else:
            # No station number given - use default context
            sc: StationContext = StationContext()
    checkAndDeleteFile(HOLIDAY_FILE, SET_TEMP_EXPIRY_SECS)
    holiday = HolidayStr.loadFromFile(HOLIDAY_FILE)
    if holiday:
        if readSC:
            changed = True
        msgBytes = getMessageEnvelope(
            SET_HOLIDAY_MSG, bytearray(holiday), sizeof(HolidayStr)
        )
        response = Response(response=msgBytes, mimetype="application/octet-stream")
        sc.setHolidayTime = stat(HOLIDAY_FILE).st_mtime + 1
        sc.tempMotd = f"New Hols: St:{holiday.startDate.dayOfMonth}/{holiday.startDate.month} {holiday.startDate.hour}:{holiday.startDate.min} To:{holiday.endDate.dayOfMonth}/{holiday.endDate.month} {holiday.endDate.hour}:{holiday.endDate.min}"
        print(f"Holiday msg: {sc.tempMotd}")
    else:
        print("No holiday file")
        response = getNoMessage()
    if changed:
        sc.saveStationContext()
        sc.generateStatusFile()

    return response


def createScheduleMsgs(sc: StationContext):
    # Create a list of schedule messages to replace the existing schedules

    checkAndDeleteFile(SCHEDULE_FILE, SET_SCHED_EXPIRY_SECS)
    if path.exists(SCHEDULE_FILE):
        sc.setSchedTime = stat(SCHEDULE_FILE).st_mtime + 1

    messages = ScheduleElement.loadSchedulesFromFile(SCHEDULE_FILE)
    noMsgs = len(messages)
    if noMsgs <= 1:
        # File was empty - dont send the delete message
        sc.scheduleMsgs = []
        sc.noOfSchedules = 0
    else:
        sc.tempMotd = f"Rx {noMsgs-1} Schedules"
        sc.scheduleMsgs = messages
        sc.noOfSchedules = noMsgs - 1
    return


def getNextScheduleMsg(sc: StationContext):
    sched = sc.scheduleMsgs[0]
    if sched == None:
        # First delete all schedules
        msgBytes = getMessageEnvelope(DELETE_ALL_SCHEDULES_MSG, bytearray(0), 0)
    else:
        schedMsg: SchedByElem = SchedByElem(sched)
        msgBytes = getMessageEnvelope(
            SCHEDULE_MSG, bytearray(schedMsg), sizeof(SchedByElem)
        )
    sc.scheduleMsgs = sc.scheduleMsgs[1:]
    return Response(response=msgBytes, mimetype="application/octet-stream")


def checkAndDeleteFile(filename, expiry: int):
    if path.exists(filename):
        nowtime = datetime.now().timestamp()
        if nowtime > (stat(filename).st_mtime + expiry):
            # File has expired
            remove(filename)


if __name__ == "__main__":
    setup()
    app.run(debug=True)
