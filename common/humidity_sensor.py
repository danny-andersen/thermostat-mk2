from time import sleep
from os import stat, path, remove
import glob
import re

import adafruit_dht
from board import D18

THERM_FILE = "/sys/bus/w1/devices/28*/w1_slave"
# THERM_FILE = "w1_slave"


def readDHTTemp():
    # Read DHT22 device
    dht_device = adafruit_dht.DHT22(pin=D18, use_pulseio=False)
    retryCount = 0
    gotValue = False
    # Try reading the device three times
    while not gotValue and retryCount < 5:
        retryCount += 1
        try:
            # dht_device.measure()
            # sleep(2)
            humidity = dht_device.humidity
            # print(f"Humidity: {humidity}")
            temperature = dht_device.temperature
            # print(f"Temp: {temperature}")
            if humidity is not None and temperature is not None:
                gotValue = True
            else:
                sleep(1)
        except RuntimeError as re:
            # print(re)
            sleep(2)
    dht_device.exit()

    if gotValue:
        return (temperature, humidity)
    else:
        return (-100, -100)


def readTemp(tempOnly: bool = False):
    if not tempOnly:
        (temp, humidity) = readDHTTemp()
        if temp < -20 or humidity == 100:
            # print("Failed to read temp from humidity sensor, trying thermometer\n")
            # Cant trust DHT reading, use thermometer
            temp = -100
            humidity = -100
    else:
        humidity = -100
    if tempOnly or temp == -100:
        # Try DS18B20 one-wire device
        temp = -100
        therms = glob.glob(THERM_FILE)
        if len(therms) > 0:
            thermDevice = therms[0]
            with open(thermDevice, "r", encoding="utf-8") as f:
                s = f.readline()
                # print(f"Temp 1st str: {str}")
                slen = len(s)
                if s and slen > 4 and s[slen - 4] == "Y":
                    # Temp reading is good
                    try:
                        s = f.readline()
                        # print(f"Temp 2nd str: {str}")
                        temp = round(int(re.split("=", s)[1]) / 100) / 10
                    except:
                        print("Temp: Failed")
                        pass
    return (temp, humidity)


# (temperature, humidity) = readTemp()
# if temperature != -1:
#     print(f"{temperature:0.1f} {humidity:0.1f}")
# else:
#     print("FAIL")
