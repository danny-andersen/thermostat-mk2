# This example uses BSEC to indicate the IAQ (Air Quality)
# If IAQ is below 100 the red LED will shine
# If IAQ is between 100 and 300 the yellow LED will shine
# If IAQ is over 300 the red LED will shine

import RPi.GPIO as GPIO
from bme68x import BME68X
import bme68xConstants as cnst
import bsecConstants as bsec
from os import path
from time import sleep


def control_LED(iaq):
    if iaq < 100:
        return "GREEN"
    elif 100 <= iaq and iaq < 300:
        return "YELLOW"
    else:
        return "RED"


GPIO.setmode(GPIO.BCM)
BME_POWER_GPIO = 17
GPIO.setup(BME_POWER_GPIO, GPIO.OUT)
# Power on BME sensor
GPIO.output(BME_POWER_GPIO, GPIO.HIGH)
# Wait for power on
sleep(2)
bme = BME68X(cnst.BME68X_I2C_ADDR_HIGH, 0)
bme.set_sample_rate(bsec.BSEC_SAMPLE_RATE_LP)
bme_state_path = "bme688_state_file"
if path.isfile(bme_state_path):
    print("Loading BME688 state file")
    with open(bme_state_path, "r") as stateFile:
        conf_str = stateFile.read()[1:-1]
        conf_list = conf_str.split(",")
        conf_int = [int(x) for x in conf_list]
        bme.set_bsec_state(conf_int)


def get_data(sensor):
    data = {}
    try:
        data = sensor.get_bsec_data()
    except Exception as e:
        print(e)
        return None
    if data == None or data == {}:
        sleep(0.1)
        return None
    else:
        return data


colors = {
    "RED": "\033[91m",
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "GREEN": "\033[92m",
}

while True:
    bsec_data = get_data(bme)
    while bsec_data == None:
        bsec_data = get_data(bme)
    led_color = control_LED(bsec_data["iaq"])
    print(
        colors[led_color]
        + f'IAQ {bsec_data["iaq"]}'
        + " "
        + list(colors.values())[bsec_data["iaq_accuracy"]]
        + f'ACCURACY {bsec_data["iaq_accuracy"]}'
    )
    print(bsec_data)
    sleep(3)
