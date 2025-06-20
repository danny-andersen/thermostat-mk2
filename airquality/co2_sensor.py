from time import sleep
from datetime import datetime, timedelta
import requests
import configparser

from sensirion_i2c_driver import LinuxI2cTransceiver, I2cConnection, CrcCalculator
from sensirion_i2c_driver.errors import I2cError
from sensirion_driver_adapters.i2c_adapter.i2c_channel import I2cChannel
from sensirion_i2c_scd4x.device import Scd4xDevice


CO2_MEASURE_PERIOD = 30  # in microseconds == 30 seconds


# Format = GET /airqual?&a=<alarm status>&delta=<millis since reading taken>&bv=<battery voltage>&t=<temp>&p=<pressure>
# &h=<humidity&gr=gas_resistance&dac=idac&red=reducing&nh3=NH3&ox=oxidising
def sendCO2Message(conf, co2):
    masterstation_url = conf["masterstation_url"]
    DEBUG = (conf["DEBUG"].lower() == "true") or (conf["DEBUG"].lower() == "yes")
    url_parts = [f"{masterstation_url}/airqual?"]
    url_parts.append(f"&co2={co2}")
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
        # Use the software I2C bus (GPIO pins 23 + 24), which comes out as i2c-3
        # Need to add dtoverlay=i2c-gpio,bus=3 to config.txt to enable this
        with LinuxI2cTransceiver('/dev/i2c-3') as i2c_transceiver:
            channel = I2cChannel(I2cConnection(i2c_transceiver),
                                slave_address=0x62,
                                crc=CrcCalculator(8, 0x31, 0xff, 0x0))
            sensor = Scd4xDevice(channel)
            sleep(0.03)

            # Ensure sensor is in clean state
            try:
                sensor.wake_up()
                sensor.stop_periodic_measurement()
                sensor.reinit()
            except I2cError as er:
                print(f"Failed to initialize CO2 sensor (retrying in 30): {er}")
                sleep(30)
                break

            # Read out information about the sensor
            serial_number = sensor.get_serial_number()
            print(f"serial number: {serial_number}"
                )

            # Start periodic measurements (5sec interval)
            sensor.start_periodic_measurement()
            
            sendTime = datetime.now() - timedelta(seconds = 30)

            while True:
                try:
                    data_ready = sensor.get_data_ready_status()
                    startWait = datetime.now()
                    while not data_ready:
                        data_ready = sensor.get_data_ready_status()
                        if (datetime.now() - startWait).seconds >= CO2_MEASURE_PERIOD: 
                            # If we have not received a measurement in the last 30 seconds, reinitialize the sensor
                            print("CO2 sensor did not return data in time, reinitializing...")  
                            sensor.wake_up()
                            sensor.stop_periodic_measurement()
                            sensor.reinit()
                            sensor.start_periodic_measurement(0)                            
                            startWait = datetime.now()
                            sleep(5)
                        else:
                            sleep(0.5)

            #     If ambient pressure compenstation during measurement
            #     is required, you should call the respective functions here.
            #     Check out the header file for the function definition.
                    (co2, temperature, relative_humidity
                                ) = sensor.read_measurement()
                    now = datetime.now()
                    if DEBUG:
                        print(f"CO2 concentration [ppm]: {co2}"
                            )
                        print(f"Temperature [°C]: {temperature}"
                            )
                        print(f"Relative Humidity [RH]: {relative_humidity}"
                            )
                    if co2 != 400:
                        #Valid value
                        if (now - sendTime).seconds >= CO2_MEASURE_PERIOD: 
                            sendCO2Message(cfg, co2)
                            sendTime = datetime.now()
                except Exception as e:
                    print(f"Reading CO2: Failed to measure CO2 sensor: {e}")
                    sensor.wake_up()
                    sensor.stop_periodic_measurement()
                    sensor.reinit()
                    sensor.start_periodic_measurement(0)
                except I2cError as er:
                    print(f"Reading CO2: I2C error: {er}")
                    sensor.wake_up()
                    sensor.stop_periodic_measurement()
                    sensor.reinit()
                    sensor.start_periodic_measurement(0)
                except IOError as ie:
                    print(f"Reading CO2: IO error: {ie}")
                    sensor.wake_up()
                    sensor.stop_periodic_measurement()
                    sensor.reinit()
                    sensor.start_periodic_measurement(0)
                sleep(5)


if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read("../camera_station/camera_station.ini")
    cfg = config["setup"]
    cfg["DEBUG"] = "True"

    co2Sensor(cfg)

