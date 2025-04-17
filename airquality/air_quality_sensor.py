import RPi.GPIO as GPIO
from os import path
from time import sleep
from datetime import datetime, timedelta
import requests
import configparser

from bme68x import BME68X
import bme68xConstants as cnst
import bsecConstants as bsec

from scd4x import SCD4X


CO2_MEASURE_PERIOD = 30

AIRQUALITY_MEASURE_PERIOD = 2800000  # in microseconds == 2.8 seconds
AIRQUALITY_SEND_PERIOD = 30


def get_data(sensor):
    data = {}
    try:
        data = sensor.get_bsec_data()
    except Exception as e:
        print(e)
        return None
    if data == None or data == {}:
        # Sensor not ready for next measurement - wait a bit
        # Note that it must not exceed 3.1875 seconds between calls
        sleep(0.1)
        return None
    else:
        return data


# Format = GET /airqual?&a=<alarm status>&delta=<millis since reading taken>&bv=<battery voltage>&t=<temp>&p=<pressure>
# &h=<humidity&gr=gas_resistance&dac=idac&red=reducing&nh3=NH3&ox=oxidising
def sendAirQMessage(conf, data: dict[str, str]):
    masterstation_url = conf["masterstation_url"]
    DEBUG = (conf["DEBUG"].lower() == "true") or (conf["DEBUG"].lower() == "yes")
    url_parts = [f"{masterstation_url}/airqual?"]
    url_parts.append(f"&p={data['raw_pressure']:.2f}")
    url_parts.append(f"&t={data['raw_temperature']:.2f}")
    url_parts.append(f"&h={data['raw_humidity']:.2f}")
    url_parts.append(f"&iaq={data['iaq']:.2f}")
    url_parts.append(f"&co2={data['co2_equivalent']:.2f}")
    url_parts.append(f"&voc={data['breath_voc_equivalent']:.2f}")
    url_parts.append(f"&acc={data['iaq_accuracy']}")
    url = "".join(url_parts)
    # Send HTTP request with a 3 sec timeout
    # if DEBUG:
    #     print(f"Sending status update: {url}\n")
    try:
        resp = requests.get(url, timeout=3)
        # print(f"Received response code {resp.status_code}")
    except requests.exceptions.RequestException as re:
        print(f"Failed to send message to masterstation {re}\n")


# Format = GET /airqual?&a=<alarm status>&delta=<millis since reading taken>&bv=<battery voltage>&t=<temp>&p=<pressure>
# &h=<humidity&gr=gas_resistance&dac=idac&red=reducing&nh3=NH3&ox=oxidising
def sendCO2Message(conf, co2):
    masterstation_url = conf["masterstation_url"]
    DEBUG = (conf["DEBUG"].lower() == "true") or (conf["DEBUG"].lower() == "yes")
    url_parts = [f"{masterstation_url}/airqual?"]
    url_parts.append(f"&co2={co2:.2f}")
    url = "".join(url_parts)
    # Send HTTP request with a 3 sec timeout
    # if DEBUG:
    #     print(f"Sending status update: {url}\n")
    try:
        resp = requests.get(url, timeout=3)
        # print(f"Received response code {resp.status_code}")
    except requests.exceptions.RequestException as re:
        print(f"Failed to send message to masterstation {re}\n")


def airQualitySensor(cfg):
    GPIO.setmode(GPIO.BCM)
    BME_POWER_GPIO = 17
    GPIO.setup(BME_POWER_GPIO, GPIO.OUT)
    # Make sure sensor has been powered down
    GPIO.output(BME_POWER_GPIO, GPIO.LOW)
    sleep(2)
    lastStateDate = datetime.now()
    while True:
        # Outer loop allows sensor device to be restarted if calibration is lost
        DEBUG = (cfg["DEBUG"].lower() == "true") or (cfg["DEBUG"].lower() == "yes")
        # Power on BME sensor
        GPIO.output(BME_POWER_GPIO, GPIO.HIGH)
        # Wait for power on
        sleep(30)
        bmeUp = False
        scd4xUp = False
        while not bmeUp or not scd4xUp:
            try:
                bme = BME68X(cnst.BME68X_I2C_ADDR_HIGH, 0)
                bmeUp = True
            except Exception as e:
                print(f"Failed to start Airquality sensor: {e}\n")
                sleep(15)
            try:
                device = SCD4X(quiet=True if DEBUG else False)
                device.start_periodic_measurement()
                scd4xUp = True
            except Exception as e:
                print(f"Failed to initialise SC4X C02 sensor {e}\n")
                sleep(15)

        bme.set_sample_rate(bsec.BSEC_SAMPLE_RATE_LP)
        bme_state_path = "bme688_state_file"
        if path.isfile(bme_state_path):
            print("Loading state file")
            with open(bme_state_path, "r") as stateFile:
                conf_str = stateFile.read()[1:-1]
                conf_list = conf_str.split(",")
                conf_int = [int(x) for x in conf_list]
                bme.set_bsec_state(conf_int)
        lastSendTime = 0
        lastCO2Time = 0
        calibrated = False
        co2FailCount = 0

        while True:
            bsec_data = get_data(bme)
            while bsec_data is None:
                bsec_data = get_data(bme)
            dt = datetime.now()
            if calibrated and bsec_data["iaq_accuracy"] == 0:
                # Calibration has been lost - restart sensor
                print("BME Calibration lost - restarting sensor\n")
                break
            if bsec_data["iaq_accuracy"] == 3:
                calibrated = True
            if DEBUG:
                print(bsec_data)

            if (dt.timestamp() - lastSendTime) > AIRQUALITY_SEND_PERIOD:
                sendAirQMessage(cfg, bsec_data)
                lastSendTime = dt.timestamp()
            # Save state every 24 hours
            timeSinceLastSave = dt - lastStateDate
            if calibrated and timeSinceLastSave > timedelta(hours=24):
                with open(bme_state_path, "w") as state_file:
                    state_file.write(str(bme.get_bsec_state()))
                    state_file.close()
                    lastStateDate = dt

            if (dt.timestamp() - lastCO2Time) >= CO2_MEASURE_PERIOD:
                try:
                    co2, temperature, relative_humidity, timestamp = device.measure()
                    co2FailCount = 0
                    if co2 > 420:
                        # Only send valid values, i.e. greater than ambient CO2 levels - initial power up of sensor has low readings
                        sendCO2Message(cfg, co2)
                        lastCO2Time = dt.timestamp()
                    if DEBUG:
                        print(
                            f"""Time: {dt.strftime("%Y/%m/%d %H:%M:%S:%f %Z %z")}, CO2: {co2:.2f} PPM, Temperature: {temperature:.4f}c, Humidity: {relative_humidity:.2f}%RH"""
                        )
                except Exception as e:
                    print(f"Failed to read CO2 sensor: {e}\n")
                    co2FailCount += 1
                    if co2FailCount > 5:
                        print("CO2 sensor not responding - restarting device\n")
                        scd4xUp = False

            if not scd4xUp:
                try:
                    device = SCD4X(quiet=True if DEBUG else False)
                    device.start_periodic_measurement()
                    co2FailCount = 0
                    scd4xUp = True
                except Exception as e:
                    print(f"Failed to initialise SCD4X C02 sensor {e}\n")

            st = datetime.now()
            execTime = (st - dt).microseconds
            sleepTime = AIRQUALITY_MEASURE_PERIOD - execTime
            if sleepTime > 0:
                sleep(sleepTime / 1000000.0)

        # Lost device or calibration - power down
        print("BME device not responding or lost calibration - restarting")
        GPIO.output(BME_POWER_GPIO, GPIO.LOW)
        sleep(30)


if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read("../camera_station/camera_station.ini")
    cfg = config["setup"]
    cfg["DEBUG"] = "True"

    airQualitySensor(cfg)
