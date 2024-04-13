#!/bin/bash

#Check up on temperature
temp="FAIL"
humid="FAIL"
uploadStatus=N
device_change_file=$(date +%Y%m%d)"_cam${1}_change.txt"

if [ -f temp_avg.txt ]
then
    temp=$(cat temp_avg.txt)
    if [ $temp != "-100.0" ]
    then
        if [ ! -f temp_avg.old ]
        then
            cp temp_avg.txt temp_avg.old
        fi
        oldtemp=$(cat temp_avg.old)
        grep -q ":Temp:" $device_change_file
        tempInStatus=$?
        if [ $oldtemp != $temp ] || [ $tempInStatus != 0 ]
        then
            echo $temp > temp_avg.old
            time=$(date +%H%M)
            echo ${time}":Temp:"${temp} >> $device_change_file
            uploadStatus=Y
        fi
    fi
fi
if [ -f humidity_avg.txt ]
then
    humid=$(cat humidity_avg.txt)
    if [ $humid != "-100" ]
    then
        if [ ! -f humidity_avg.old ]
        then
            cp humidity_avg.txt humidity_avg.old
        fi
        oldhumid=$(cat humidity_avg.old)
        grep -q ":Humidity:" $device_change_file
        humidInStatus=$?
        #Round to nearest integer (as humidity changes alot at 0.1% accuracy)
        # humidity=$(echo $humid | awk '{printf("%.0f\n", $1)}')
        if [ $oldhumid != $humid ] || [ $humidInStatus != 0 ]
        then
            echo $humid > humidity_avg.old
            time=$(date +%H%M)
            echo ${time}":Humidity:"${humid} >> $device_change_file
            uploadStatus=Y
        fi
    fi
fi


if [ ${uploadStatus} = "Y" ]
then
    ./dropbox_uploader.sh upload $device_change_file $device_change_file > /dev/null 2>&1
fi

