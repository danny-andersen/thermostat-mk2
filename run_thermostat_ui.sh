#!/usr/bin/env bash
while $(sleep 10); do
  echo "waiting for systemd to finish booting..."
  if systemctl is-system-running | grep -qE "running|degraded"; then
    break
  fi
done
/home/danny/Backlight/Raspi_USB_Backlight_nogui -b 8
flutter-pi --videomode 1024x600 -r 270 --release thermostat-flutter/
#flutter-pi --videomode 240x320 -d "100, 200" --release thermostat-flutter/
#flutter-pi --videomode 600x1024 --release thermostat-flutter/
/home/danny/Backlight/Raspi_USB_Backlight_nogui -b 0
