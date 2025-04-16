from time import sleep
from datetime import datetime, timedelta
import requests
import configparser

from datetime import datetime, timezone

from scd4x import SCD4X


CO2_MEASURE_PERIOD = 30 * 1000000  # in microseconds == 30 seconds


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


def co2Sensor(cfg):
    DEBUG = (cfg["DEBUG"].lower() == "true") or (cfg["DEBUG"].lower() == "yes")
    while True:
        # Let everything start up
        sleep(30)
        try:
            device = SCD4X(quiet=True if DEBUG else False)
            device.start_periodic_measurement()
            while True:
                try:
                    co2, temperature, relative_humidity, timestamp = device.measure()
                except Exception as e:
                    print(f"Failed to measure CO2 sensor: {e}")
                    break
                dt = datetime.now()
                if DEBUG:
                    print(
                        f"""
        Time:        {dt.strftime("%Y/%m/%d %H:%M:%S:%f %Z %z")}
        CO2:         {co2:.2f}PPM
        Temperature: {temperature:.4f}c
        Humidity:    {relative_humidity:.2f}%RH"""
                    )
                sendCO2Message(cfg, co2)
                st = datetime.now()
                execTime = (st - dt).microseconds
                sleepTime = CO2_MEASURE_PERIOD - execTime
                if sleepTime > 0:
                    sleep(sleepTime / 1000000.0)
        except Exception as e:
            print(f"Failed to initialise SC4X C02 sensor {e}, restarting")


if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read("../camera_station/camera_station.ini")
    cfg = config["setup"]
    cfg["DEBUG"] = "True"

    co2Sensor(cfg)
