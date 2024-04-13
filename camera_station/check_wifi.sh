#!/bin/bash

#Check wifi up
ping -c2 192.168.1.1 > /dev/null
if [ $? == 0 ]
then
  touch wifi-up.txt
fi

#Find out whether rebooted less than a day and if so how many hours ago
uphours=24
uptime | grep -qv day
if [ $? == 0 ]
then
    #Uptime less than a day - if we rebooted less than an hour ago, dont reboot again
    uphours=$(uptime | awk '{print $3}' | awk -F: '{print $1}')
fi
#Check last time could contact wifi AP 
#If greater than 30 mins ago and not rebooted for over an hour, restart wlan0
cnt=$(find ./ -name wifi-up.txt -mmin +30 | wc -l)
if [ $cnt != 0 ] && [ $uphours != 0 ]
then
      #No response from ping to router and we havent rebooted for over an hour
      echo No response from ping to router for more than 30 mins and reboot was $uphours ago - toggling wlan0 interface
      sudo /sbin/ifdown --force wlan0
      sleep 10
      sudo /sbin/ifup --force wlan0
      sleep 10
      #Check if interface now back up
      ifquery --state wlan0
      if [ $? == 1 ]
      then
	  #Failed to restart interface so reboot
          sudo /sbin/shutdown -r now
      fi
fi

#Catch all - If greater than 120 mins ago, reboot
#Note that this will cause a reboot every 2 hours if AP is down
cnt=$(find ./ -name wifi-up.txt -mmin +120 | wc -l)
if [ ${cnt} != 0 ]
then
      sudo /sbin/shutdown -r now
fi
