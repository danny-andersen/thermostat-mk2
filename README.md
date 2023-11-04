# thermostat-mk2
Second generation of the digi-thermostat repo, using pizero 2w and a 7" LCD screen to run both the thermostat and control station functions.

The original project can be found in digi-thermostat and used an Arduino to provide the digital thermostat functions and drove a 4 line 20 col LCD screen to show current status etc.
It also included a masterstation that ran on a raspberry pi 3B that provided all of the in-station functionality. 

This has run successfully for over 6 years, controlling the heating in my house but with the appearance (and availability!) of the Pi Zero 2W and cheap hi resolution LCDs, 
it was decided to re-write this and host both the thermostat and the control / in-station on the same Pi. 

In addition, the use of a hi-res LCD screen meant that the display could use flutter-pi to render the display. 
This is held in the thermostat-flutter repo, which was written orginally for displaying and controlling the thermostat remotely via a mobile phone. 
The power of flutter is its native multi-platform support and it allows the same display to be shown on the thermostat LCD screen. 
