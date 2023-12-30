from ctypes import *
from os import path
import json
from struct import unpack
from enum import Enum
import configparser
from datetime import datetime
import jsonpickle


MAX_MESSAGE_SIZE = 128
MAX_WIND_SIZE = 12
MAX_MOTD_SIZE = 90

NO_MESSAGE = 0
REQ_STATUS_MSG = 1
STATUS_MSG = 2
SET_TEMP_MSG = 3
SET_EXT_MSG = 4
ADJ_SETTIME_CONST_MSG = 5
MOTD_MSG = 6
GET_SCHEDULES_MSG = 7
SCHEDULE_MSG = 8
DELETE_ALL_SCHEDULES_MSG = 9
DELETE_SCHEDULE_MSG = 10
SET_DATE_TIME_MSG = 11
SET_HOLIDAY_MSG = 12
SET_THERM_TEMP_MSG = 13
RESET_MSG = 14

MOTD_FILE = "motd.txt"
MOTD_EXPIRY_SECS = 3600  # an hour
SCHEDULE_FILE = "schedule.txt"
EXTTEMP_FILE = "setExtTemp.txt"
HOLIDAY_FILE = "holiday.txt"
SET_TEMP_FILE = "setTemp.txt"
STATUS_FILE = "status.txt"
STATION_FILE = "-context.json"
RESET_FILE = "resetReq.txt"
TEMPERATURE_FILE_NEW = "../monitor_home/temperature.txt"
HUMIDITY_FILE_NEW = "../monitor_home/humidity.txt"
TEMPERATURE_FILE = "../monitor_home/temp_avg.txt"
HUMIDITY_FILE = "../monitor_home/humidity_avg.txt"
TEMP_AVERAGE_MIN = (
    5  # Number of mins at which to average temp over for historic change file
)
TEMP_AVG_FILE = "../monitor_home/temp_avg.txt"
HUMID_AVERAGE_MIN = (
    15  # Number of mins at which to average humidity over for historic change file
)
HUMID_AVG_FILE = "../monitor_home/humidity_avg.txt"

MONITOR_SCRIPT = "/home/danny/digi-thermostat/monitor_home/get_lan_devices.sh"
MONITOR_PERIOD = 30  # number of seconds between running monitor script
TEMP_PERIOD = 30  # number of seconds between reading temp + humidty

EXT_TEMP_EXPIRY_SECS = 3600  # an hour
SET_TEMP_EXPIRY_SECS = 30 * 60  # 30 mins
SET_SCHED_EXPIRY_SECS = 30 * 60  # 30 mins
TEMP_MOTD_EXPIRY_SECS = 60  # 1 min


class LedColour(Enum):
    RED = 1
    GREEN = 2
    AMBER = 3
    OFF = 4


LOCAL_SCHEDULE_FILE = "./schedules.txt"
LOCAL_HOLIDAY_FILE = "./holiday.txt"
UI_PROCESS_ARGS = [
    "flutter-pi",
    "--videomode",
    "1024x600",
    "-r",
    "270",
    "--release",
    "/home/danny/thermostat-flutter/",
]
BACKLIGHT_CMD = "/home/danny/Backlight/Raspi_USB_Backlight_nogui"


class Status(Structure):
    _fields_ = [
        ("currentTemp", c_short),
        ("setTemp", c_short),
        ("heatOn", c_ubyte),
        ("minsToSet", c_ubyte),
        ("extTemp", c_short),
        ("noOfSchedules", c_ubyte),
    ]


class SetExt(Structure):
    _fields_ = [("setExt", c_short), ("windStr", c_char * MAX_WIND_SIZE)]

    @staticmethod
    def unpack(msgBytes: bytes):
        (ext, wstr) = unpack(f"<h{MAX_WIND_SIZE}s", msgBytes)
        return SetExt(ext, wstr)


class Temp(Structure):
    _fields_ = [
        ("temp", c_short),
        ("humidity", c_short),
    ]

    @staticmethod
    def unpack(msgBytes: bytes):
        (t, h) = unpack("<hh", msgBytes)
        return Temp(t, h)


class AdjSetTimeConstants(Structure):
    _fields_ = [
        ("degPerHour", c_short),  # in tenths of a degree - 50 = 5.0
        ("extAdjustment", c_short),
    ]  # in tenths


# class Motd(Structure):
#     _fields_ = [
#         ("motdStr", c_char * MAX_MOTD_SIZE), #Message of the day, with a minimum of one character
#         ("expiry", c_ulong)] #Number of millis after which message expires


class DateTimeStruct(LittleEndianStructure):
    _fields_ = [
        ("sec", c_ubyte),
        ("min", c_ubyte),
        ("hour", c_ubyte),
        ("dayOfWeek", c_ubyte),
        ("dayOfMonth", c_ubyte),
        ("month", c_ubyte),
        ("year", c_ubyte),
    ]


class HolidayDateStr(Structure):
    _fields_ = [
        ("min", c_ubyte),
        ("hour", c_ubyte),
        ("dayOfMonth", c_ubyte),
        ("month", c_ubyte),
        ("year", c_ubyte),
    ]

    @staticmethod
    def unpack(msgBytes: bytes):
        (minute, h, d, m, y) = unpack("<BBBBB", msgBytes)
        return HolidayDateStr(minute, h, d, m, y)


class HolidayStr(Structure):
    _fields_ = [
        ("startDate", HolidayDateStr),
        ("endDate", HolidayDateStr),
        ("temp", c_short),
        ("valid", c_ubyte),
    ]

    @staticmethod
    def unpack(msgBytes: bytes):
        sd = HolidayDateStr.unpack(msgBytes[0:5])
        ed = HolidayDateStr.unpack(msgBytes[5:10])
        (t, v) = unpack("<hB", msgBytes[10:13])
        return HolidayStr(sd, ed, t, v)

    @staticmethod
    def loadFromFile(filename: str):
        holiday = None
        if path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                try:
                    linestr = f.readline()
                    start = linestr.split(",")
                    if "Start" in start[0]:
                        sd = HolidayDateStr()
                        sd.year = int(start[1])
                        sd.month = int(start[2])
                        sd.dayOfMonth = int(start[3])
                        sd.hour = int(start[4])
                        if len(start) == 6:
                            sd.min = int(start[5])
                        else:
                            sd.min = 0
                        linestr = f.readline()
                        end = linestr.split(",")
                        if "End" in end[0]:
                            ed = HolidayDateStr()
                            ed.year = int(end[1])
                            ed.month = int(end[2])
                            ed.dayOfMonth = int(end[3])
                            ed.hour = int(end[4])
                            if len(end) == 6:
                                ed.min = int(end[5])
                            else:
                                ed.min = 0
                            linestr = f.readline()
                            temp = linestr.split(",")
                            if "Temp" in temp[0]:
                                holiday = HolidayStr()
                                holiday.startDate = sd
                                holiday.endDate = ed
                                holiday.temp = c_int16(int(float(temp[1]) * 10))
                                holiday.valid = 1
                except TypeError as error:
                    print(f"Set Holiday: Failed: {error}")
                    pass
        return holiday

    @staticmethod
    def saveToFile(filename: str, hols):
        with open(filename, "w", encoding="utf-8") as f:
            dt: HolidayDateStr = hols.startDate
            f.write(f"Start,{dt.year},{dt.month},{dt.dayOfMonth},{dt.hour},{dt.min}\n")
            dt: HolidayDateStr = hols.endDate
            f.write(f"End,{dt.year},{dt.month},{dt.dayOfMonth},{dt.hour},{dt.min}\n")
            f.write(f"Temp,{hols.temp}\n")


class Holiday:
    startDate: float = 0.0
    endDate: float = 0.0
    temp: float = 10.0

    def __init__(self, *args):
        if len(args) == 3:
            self.startDate = args[0]
            self.endDate = args[1]
            self.temp = args[2]
        elif len(args) == 1:
            if args[0]:
                hols = args[0]
                self.startDate = datetime(
                    hols.startDate.year + 2000,
                    hols.startDate.month,
                    hols.startDate.dayOfMonth,
                    hols.startDate.hour,
                    hols.startDate.min,
                ).timestamp()
                self.endDate = datetime(
                    hols.endDate.year + 2000,
                    hols.endDate.month,
                    hols.endDate.dayOfMonth,
                    hols.endDate.hour,
                    hols.endDate.min,
                ).timestamp()
                self.temp = hols.temp / 10.0
            # load = json.loads(args[0])
            # self.__dict__.update(**load)

    # def getJson(self):
    #     return json.dumps(self.__dict__)


# Struct is long word padded...
# Used to pass a bytes message between control and outstations
class SchedByElem(LittleEndianStructure):
    _fields_ = [
        ("day", c_ushort),  # = "0" for every day, "0x0100" for Weekday (Mon - Fri),
        # "0x0200" for Weekend (Sat, Sun), 1 - Sunday, 2 - Monday, 3 - Tuesday,....7 - Saturday
        ("start", c_ushort),  # Start minute (0 - 1440)
        ("end", c_ushort),  # End time minute (0 - 1440)
        ("temp", c_short),
    ]  # Set temperature tenths of C, 180 = 18.0C

    @staticmethod
    def unpack(msgBytes: bytes):
        (d, s, e, t) = unpack("<HHHh", msgBytes)
        return SchedByElem(d, s, e, t)

    def __init__(self, *args):
        if len(args) == 4:
            self.day = args[0]
            self.start = args[1]
            self.end = args[2]
            self.temp = args[3]
        elif len(args) == 1:
            sched: ScheduleElement = args[0]
            self.day = sched.day
            self.start = sched.start
            self.end = sched.end
            self.temp = sched.temp


# Used as the internal representation of a schedule
class ScheduleElement:
    day: int = 0  # = "0" for every day, "0x0100" for Weekday (Mon - Fri),
    # "0x0200" for Weekend (Sat, Sun), 1 - Sunday, 2 - Monday, 3 - Tuesday,....7 - Saturday
    start: int = 0  # Start minute (0 - 1440)
    end: int = 1440  # End time minute (0 - 1440)
    temp: int = -1000  # Set temperature tenths of C, 180 = 18.0C

    def __init__(self, *args):
        if len(args) == 4:
            self.day = args[0]
            self.start = args[1]
            self.end = args[2]
            self.temp = args[3]
        elif len(args) == 1:
            # Construct from a text file line
            sched = args[0].split(",")
            self.day = 0xFF
            if "Mon-Sun" in sched[0]:
                self.day = 0x0000
            elif "Mon-Fri" in sched[0]:
                self.day = 0x0100
            elif "Sat-Sun" in sched[0]:
                self.day = 0x0200
            elif "Sun" in sched[0]:
                self.day = 0x0007
            elif "Mon" in sched[0]:
                self.day = 0x0001
            elif "Tue" in sched[0]:
                self.day = 0x0002
            elif "Wed" in sched[0]:
                self.day = 0x0003
            elif "Thu" in sched[0]:
                self.day = 0x0004
            elif "Fri" in sched[0]:
                self.day = 0x0005
            elif "Sat" in sched[0]:
                self.day = 0x0006
            else:
                print(f"Unidentified Day specified in schedule: {str}")
            if self.day != 0xFF:
                shours = int(sched[1][0:2])
                smins = int(sched[1][2:4])
                self.start = shours * 60 + smins
                ehours = int(sched[2][0:2])
                emins = int(sched[2][2:4])
                self.end = ehours * 60 + emins
                temp = float(sched[3]) * 10
                self.temp = int(temp)

    def to_string(self):
        retStr = None
        dayStr = None
        if self.day == 0x0000:
            dayStr = "Mon-Sun"
        elif self.day == 0x0100:
            dayStr = "Mon-Fri"
        elif self.day == 0x0200:
            dayStr = "Sat-Sun"
        elif self.day == 0x0007:
            dayStr = "Sun"
        elif self.day == 0x0001:
            dayStr = "Mon"
        elif self.day == 0x0002:
            dayStr = "Tue"
        elif self.day == 0x0003:
            dayStr = "Wed"
        elif self.day == 0x0004:
            dayStr = "Thu"
        elif self.day == 0x0005:
            dayStr = "Fri"
        elif self.day == 0x0006:
            dayStr = "Sat"
        else:
            print(f"Unidentified Day specified in schedule: {str}")
        if dayStr:
            retStr = f"{dayStr},{int(self.start/60):02d}{self.start %60:02d},{int(self.end/60):02d}{self.end %60:02d},{self.temp}\n"
        return retStr

    @staticmethod
    def loadSchedulesFromFile(filename: str):
        messages: list[ScheduleElement] = []
        with open(filename, "r", encoding="utf-8") as f:
            messages.append(None)
            try:
                for linestr in f:
                    # Read line, split by "," then process + create one message per line (schedule)
                    element: ScheduleElement = ScheduleElement(linestr)
                    messages.append(element)
                    # print(f"Schedule: Day: {schedMsg.day} Start: {schedMsg.start}, End: {schedMsg.end}, Temp: {schedMsg.temp}\n")
            except:
                print(f"Processing schedule file failed")
                messages = []
                pass
        return messages

    @staticmethod
    def saveSchedulesToFile(schedules: set, filename: str):
        with open(filename, "w", encoding="utf-8") as f:
            for sched in list(schedules):
                f.write(sched.to_string())

    # def getJson(self):
    #     return json.dumps(self.__dict__)


# class Schedules:
#     elements: set[ScheduleElement]

#     def __init__(self, jsonStr=None):
#         if jsonStr:
#             load = json.loads(jsonStr)
#             self.__dict__.update(**load)

#     def getJson(self):
#         return json.dumps(self.__dict__)


class Message(LittleEndianStructure):
    _fields_ = [("id", c_ubyte), ("len", c_ubyte), ("crc", c_ushort)]

    @staticmethod
    def unpack(msgBytes: bytes):
        # print(msgBytes)
        return unpack("<BBH", msgBytes)


class StationContext:
    stationNo: int = -1
    motdExpiry = MOTD_EXPIRY_SECS
    motdTime: int = 0
    schedSentTime = 0
    extTempTime = 0
    setTempTime = 0
    setHolidayTime = 0
    setSchedTime = 0
    scheduleMsgs: list = []
    tempMotd: str = None
    tempMotdTime = 0
    currentSetTemp: float = -1000.0  # current set temp
    currentManSetTemp: float = (
        -1000.0
    )  # current set temp set from control or on thermostat
    currentBoilerStatus = 0.0  # off
    currentPirStatus = 0  # off
    currentTemp: float = -1000.0
    currentHumidity: float = -1000.0
    currentExtTemp: float = -1000.0
    noOfSchedules = 0

    # Non-persisted fields:
    currentMotd = ""
    lastMonitorTime = 0
    lastMessageTime = 0
    lastTempTime = 0
    lastPirTime = 0
    pir_stat = 0
    heat_on = False
    currentSentThermTemp = 1000.0
    manHolidayTemp = 1000.0
    lastScheduledTemp = 1000.0
    isDefaultSchedule = False
    onHoliday = False
    windStr = ""
    reset = 0
    controlStationUrl = ""
    ui_process = None

    # Constants overriden by .ini file
    RELAY_OUT = 27
    PIR_IN = 17
    GREEN_LED = 23
    RED_LED = 24
    TEMP_SENSOR: int = 18
    TEMP_PERIOD: int = 60
    PIR_TRIGGER_PERIOD = 30
    HYSTERISIS: float = 0.2
    GET_MSG_PERIOD = 15
    DEFAULT_TEMP = 10.0
    SET_TEMP_PERIOD: int = 3600
    DEBUG = False

    schedules: {ScheduleElement} = set()
    currentHoliday: Holiday = Holiday()
    config: configparser.ConfigParser = configparser.ConfigParser()

    relay = None
    redLED = None
    greenLED = None
    pir = None

    def __init__(self, stn=-1, configFile="") -> None:
        self.stationNo = stn
        if configFile != "":
            # Load initial config from config file
            self.config.read(configFile)
            setup_cfg = self.config["setup"]
            self.HYSTERISIS = float(setup_cfg["HYSTERISIS"])
            self.DEFAULT_TEMP = float(setup_cfg["DEFAULT_TEMP"])
            self.DEBUG = bool(setup_cfg["DEBUG"])
            self.stationNo = int(setup_cfg["station_num"])
            self.controlstation_url = setup_cfg["controlstation_url"]

            gpio_cfg = self.config["GPIO"]
            self.RELAY_OUT = int(gpio_cfg["RELAY_OUT"])
            self.PIR_IN = int(gpio_cfg["PIR_IN"])
            self.GREEN_LED = int(gpio_cfg["GREEN_LED"])
            self.RED_LED = int(gpio_cfg["RED_LED"])
            self.TEMP_SENSOR = int(gpio_cfg["TEMP_SENSOR"])

            timings_cfg = self.config["timings"]
            self.TEMP_PERIOD = int(timings_cfg["TEMP_PERIOD"])
            self.SET_TEMP_PERIOD = int(timings_cfg["SET_TEMP_PERIOD"])
            self.GET_MSG_PERIOD = int(timings_cfg["GET_MSG_PERIOD"])
            self.PIR_TRIGGER_PERIOD = int(timings_cfg["PIR_TRIGGER_PERIOD"])
            # print(f"TEMP PERIOD: {self.TEMP_PERIOD}, MSG_PERIOD: {self.GET_MSG_PERIOD}")

    # def __init__(self, stn) -> None:
    #     self.stationNo = stn
    #     self.__init__()

    # Gets the current global variables from a file
    # This allows multiple app threads to use the same values
    # Each station is single threaded and so there is no need for locks - the station number is sufficient
    @staticmethod
    def getSavedContext(stationNo):
        sc = StationContext(stationNo)
        stationFile = f"{stationNo}{STATION_FILE}"
        if path.exists(stationFile):
            try:
                with open(stationFile, "r", encoding="utf-8") as f:
                    jsonStr = f.read()
                    sc = jsonpickle.decode(jsonStr)

                    # loadStatus = json.loads(jsonStr)
                    # self.__dict__.update(**loadStatus)
            except:
                print(
                    f"Failed to load json data from station context file {stationFile}"
                )
        return sc

    def saveStationContext(self, oldContext: object = None):
        # First determine if anything has changed - only update context file if it has
        changed = False
        if self.stationNo != -1 and self != oldContext:
            changed = True
            # save context
            jsonStr = jsonpickle.encode(self)
            # Write json to station file
            with open(f"{self.stationNo}{STATION_FILE}", "w", encoding="utf-8") as f:
                try:
                    f.write(jsonStr)
                except:
                    print("Failed to write context file")
        return changed

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StationContext):
            # don't attempt to compare against unrelated types
            return NotImplemented
        return (
            self.currentBoilerStatus == other.currentBoilerStatus
            and self.currentExtTemp == other.currentExtTemp
            and self.currentPirStatus == other.currentPirStatus
            and self.currentSetTemp == other.currentSetTemp
            and self.currentTemp == other.currentTemp
            and self.currentHumidity == other.currentHumidity
            and self.extTempTime == other.extTempTime
            and self.motdExpiry == other.motdExpiry
            and self.motdTime == other.motdTime
            and self.noOfSchedules == other.noOfSchedules
            and self.schedSentTime == other.schedSentTime
            and self.scheduleMsgs == other.scheduleMsgs
            and self.setHolidayTime == other.setHolidayTime
            and self.setTempTime == other.setTempTime
            and self.tempMotd == other.tempMotd
            and self.tempMotdTime == other.tempMotdTime
            and self.stationNo == other.stationNo
        )

    def generateStatusFile(self):
        # print("Generate status file")
        now: datetime = datetime.now()
        try:
            if self.stationNo == 1:
                statusFile = STATUS_FILE
            else:
                statusFile = f"{self.stationNo}_{STATUS_FILE}"

            with open(statusFile, "w", encoding="utf-8") as statusf:
                if self.currentTemp != -1000:
                    statusf.write(f"Current temp: {self.currentTemp/10:0.1f}\n")
                else:
                    statusf.write("Current temp: Not Set\n")
                statusf.write(f"Current humidity: {self.currentHumidity/10:0.1f}\n")
                statusf.write(f"Current set temp: {self.currentSetTemp/10:0.1f}\n")
                heatOn = "No" if self.currentBoilerStatus == 0 else "Yes"
                statusf.write(f"Heat on? {heatOn}\n")
                statusf.write(f"Mins to set temp: {self.currentBoilerStatus}\n")
                if self.currentExtTemp < 1000:
                    statusf.write(f"External temp: {self.currentExtTemp/10:0.2f}\n")
                else:
                    statusf.write("External temp: Not Set\n")
                statusf.write(f"No of Schedules: {self.noOfSchedules}\n")
                statusf.write(f"Last heard time: {now.strftime('%Y%m%d %H:%M:%S')}\n")
                statusf.write(
                    f"Last PIR Event time: {datetime.fromtimestamp(self.lastPirTime).strftime('%Y%m%d %H:%M:%S') if self.lastPirTime != 0 else 'Never'}\n"
                )
                statusf.write(f"PIR:{self.currentPirStatus}\n")

        except:
            print("Failed to write status file")
