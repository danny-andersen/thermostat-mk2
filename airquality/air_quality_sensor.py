from bme68x import BME68X
import bme68xConstants as cnst
import bsecConstants as bsec
from os import path
from time import sleep
from datetime import datetime, timedelta
import requests

AIRQUALITY_MEASURE_PERIOD = 3
AIRQUALITY_SEND_PERIOD = 30

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

# Format = GET /airqual?&a=<alarm status>&delta=<millis since reading taken>&bv=<battery voltage>&t=<temp>&p=<pressure>
# &h=<humidity&gr=gas_resistance&dac=idac&red=reducing&nh3=NH3&ox=oxidising 
def sendAirQMessage(conf, data: dict[str, str]):
    masterstation_url = conf["masterstation_url"]
    DEBUG = (conf["DEBUG"].lower() == "true") or (conf["DEBUG"].lower() == "yes")
    url_parts = [f"{masterstation_url}/airqual?"]
    url_parts.append(f"&p={data['raw_pressure']}")
    url_parts.append(f"&t={data['temperature']}")
    url_parts.append(f"&h={data['humidity']}")
    url_parts.append(f"&iaq={data['iaq']}")
    url_parts.append(f"&co2={data['co2_equivalent']}")
    url_parts.append(f"&voc={data['breath_voc_equivalent']}")
    url_parts.append(f"&acc={data['iaq_accuracy']}")
    url = "".join(url_parts)
    # Send HTTP request with a 5 sec timeout
    # if DEBUG:
    #     print(f"Sending status update: {url}\n")
    try:
        resp = requests.get(url, timeout=5)
        # print(f"Received response code {resp.status_code}")
    except requests.exceptions.RequestException as re:
        print(f"Failed to send message to masterstation {re}\n")


def airQualitySensor(cfg):
    bme = BME68X(cnst.BME68X_I2C_ADDR_HIGH, 0)
    bme.set_sample_rate(bsec.BSEC_SAMPLE_RATE_LP)
    bme_state_path = "bme688_state_file"
    if (path.isfile(bme_state_path)) :
        with open(bme_state_path, 'r') as stateFile:
            conf_str =  stateFile.read()[1:-1]
            conf_list = conf_str.split(",")
            conf_int = [int(x) for x in conf_list]    
            bme.set_bsec_state(conf_int)
    lastStateDate = datetime.now()
    lastSendTime = 0

    while (True):
        bsec_data = get_data(bme)
        while bsec_data == None:
            bsec_data = get_data(bme)

        dt = datetime.now()
        if (dt.timestamp() - lastSendTime) > AIRQUALITY_SEND_PERIOD:
            sendAirQMessage(cfg, bsec_data)
            lastSendTime = dt.timestamp()
        #Save state every 24 hours
        timeSinceLastSave = dt - lastStateDate
        if (timeSinceLastSave > timedelta(hours=24)) :
            with open(bme_state_path, 'w') as state_file:
               state_file.write(str(bme.get_bsec_state())) 
               state_file.close()
            lastStateDate = dt
    
        sleep(AIRQUALITY_MEASURE_PERIOD)
