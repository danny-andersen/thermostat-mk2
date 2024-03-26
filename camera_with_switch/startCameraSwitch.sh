#!/usr/bin/env bash
#killall flutter-pi
source bin/activate
export GPIOZERO_PIN_FACTORY=lgpio
bin/python camera_switch.py
