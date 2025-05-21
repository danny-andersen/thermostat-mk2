import argparse
import time
from sensirion_i2c_driver import LinuxI2cTransceiver, I2cConnection, CrcCalculator
from sensirion_driver_adapters.i2c_adapter.i2c_channel import I2cChannel
from sensirion_i2c_scd4x.device import Scd4xDevice

parser = argparse.ArgumentParser()
parser.add_argument('--i2c-port', '-p', default='/dev/i2c-3')
args = parser.parse_args()

with LinuxI2cTransceiver(args.i2c_port) as i2c_transceiver:
    channel = I2cChannel(I2cConnection(i2c_transceiver),
                         slave_address=0x62,
                         crc=CrcCalculator(8, 0x31, 0xff, 0x0))
    sensor = Scd4xDevice(channel)
    time.sleep(0.03)

    # Ensure sensor is in clean state
    sensor.wake_up()
    sensor.stop_periodic_measurement()
    sensor.reinit()

    # Read out information about the sensor
    serial_number = sensor.get_serial_number()
    print(f"serial number: {serial_number}"
          )

    #     If temperature offset and/or sensor altitude compensation
    #     is required, you should call the respective functions here.
    #     Check out the header file for the function definitions.

    # Start periodic measurements (5sec interval)
    sensor.start_periodic_measurement()

    #     If low-power mode is required, switch to the low power
    #     measurement function instead of the standard measurement
    #     function above. Check out the header file for the definition.
    #     For SCD41, you can also check out the single shot measurement example.
    while True:

        #     Slow down the sampling to 0.2Hz.
        time.sleep(5.0)
        data_ready = sensor.get_data_ready_status()
        while not data_ready:
            time.sleep(0.1)
            data_ready = sensor.get_data_ready_status()

        #     If ambient pressure compenstation during measurement
        #     is required, you should call the respective functions here.
        #     Check out the header file for the function definition.
        (co2_concentration, temperature, relative_humidity
         ) = sensor.read_measurement()

        #     Print results in physical units.
        print(f"CO2 concentration [ppm]: {co2_concentration}"
              )
        print(f"Temperature [°C]: {temperature}"
              )
        print(f"Relative Humidity [RH]: {relative_humidity}"
              )

