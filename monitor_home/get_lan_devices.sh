#!/bin/bash
function upload_images {
    if [ $# -gt 0 ]
    then
        for file in $*
        do
            if ! fuser "$video_picture_dir/$file"; then
                mod_date=$(date -r "$video_picture_dir/$file" +%Y-%m-%d)
                ./dropbox_uploader.sh mkdir $video_picture_dir/$mod_date/
                ./dropbox_uploader.sh upload $video_picture_dir/$file $video_picture_dir/$mod_date/$file
                rm $video_picture_dir/$file
            fi
        done
    fi
}


#Start
cd "$(dirname "$0")"

device_change_file=$(date +%Y%m%d)"_device_change.txt"
sensor_dir=/sys/bus/w1/devices/28-051673fdeeff
masterstation=../control_station
video_picture_dir=motion_images/
safeDevice=`cat safeDevices.txt`
uploadStatus=N

#Check wifi up
ping -c2 192.168.1.1 > /dev/null
if [ $? == 0 ]
then
  touch wifi-up.txt
fi

#Find out whether rebooted less than a day and if so how many hours ago
uphours=24
uptime | grep -v day
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

#Catch all - If greater than 60 mins ago, reboot
#Note that this will cause a reboot every hour if AP is down
cnt=$(find ./ -name wifi-up.txt -mmin +60 | wc -l)
if [ ${cnt} != 0 ]
then
      sudo /sbin/shutdown -r now
fi

dev=$(echo $safeDevice | sed 's/|/ /g')
for d in $dev
do
	ping -c2 $d > /dev/null 2>&1
	if [ $? == 0 ]
	then
        #Device on network
        grep -q $d lan_devices.txt
        if [ $? == 1 ]
        then
            # Device not listed - add
    		echo $d >> lan_devices.txt
          	dateStr=`date +%H%M`
            echo $dateStr':Device:New:'$d >> $device_change_file
         	uploadStatus=Y
        fi
        grep -q $d $device_change_file
        if [ $? == 1 ]
        then
            # Device not in change file (probably as new day)
          	dateStr=`date +%H%M`
            echo $dateStr':Device:New:'$d >> $device_change_file
         	uploadStatus=Y
        fi
    else
        #Device not on network
        grep -q $d lan_devices.txt
        if [ $? == 0 ]
        then
            #Device no longer found - remove
            grep -v $d lan_devices.txt > lan_devices.new
            mv lan_devices.new lan_devices.txt
          	dateStr=`date +%H%M`
            echo $dateStr':Device:Gone:'$d >> $device_change_file
         	uploadStatus=Y
        fi
	fi
done	

if [ ! -f thermostat_status.txt ]
then
    >thermostat_status.txt
fi

diff -q ${masterstation}/status.txt thermostat_status.txt >/dev/null
if [ $? -eq 1 ]
then
	# echo "Uploading changed thermostat status"
	cp ${masterstation}/status.txt thermostat_status.txt
	./dropbox_uploader.sh upload thermostat_status.txt thermostat_status.txt > /dev/null 2>&1
fi

if [ ! -f cam0_status.txt ]
then
    >cam0_status.txt
fi

diff -q ${masterstation}/2_status.txt 2_status.txt >/dev/null
if [ $? -eq 1 ]
then
	cp ${masterstation}/2_status.txt 2_status.txt
	./dropbox_uploader.sh upload 2_status.txt 2_status.txt > /dev/null 2>&1
	# ./dropbox_uploader.sh upload 2_status.txt external_status.txt > /dev/null 2>&1
fi

diff -q ${masterstation}/3_status.txt 3_status.txt >/dev/null
if [ $? -eq 1 ]
then
	cp ${masterstation}/3_status.txt 3_status.txt
	./dropbox_uploader.sh upload 3_status.txt 3_status.txt > /dev/null 2>&1
fi

diff -q ${masterstation}/4_status.txt 4_status.txt >/dev/null
if [ $? -eq 1 ]
then
	cp ${masterstation}/4_status.txt 4_status.txt
	./dropbox_uploader.sh upload 4_status.txt 4_status.txt > /dev/null 2>&1
fi

diff -q ${masterstation}/5_status.txt 5_status.txt >/dev/null
if [ $? -eq 1 ]
then
	cp ${masterstation}/5_status.txt 5_status.txt
	./dropbox_uploader.sh upload 5_status.txt 5_status.txt > /dev/null 2>&1
fi

diff -q ${masterstation}/6_status.txt 6_status.txt >/dev/null
if [ $? -eq 1 ]
then
	cp ${masterstation}/6_status.txt 6_status.txt
	./dropbox_uploader.sh upload 6_status.txt 6_status.txt > /dev/null 2>&1
fi

./dropbox_uploader.sh download command.txt command.txt > /dev/null 2>&1
if [ -f command.txt ]
then
    # contents=$(cat command.txt)
    # # echo "Running command:" $contents
    # if [ $contents = "temp" ];
    # then
    #     if [ -f ${sensor_dir}/temperature ]
    #     then
    #             #temp=$(grep "t=" $sensor_dir/w1_slave | awk '{print $10}' | awk -F= '{print $2}')
    #         temp=$(cat ${sensor_dir}/temperature)
    #         temp=$(echo "scale=2; $temp / 1000" | bc -l)
    #         upload_temp
    #     fi
    # fi
    # if [ $contents = "photo" ];
    # then
    # 	touch take-photo.txt
    # fi
    # if [ $contents = "video" ];
    # then
    # 	touch take-video.txt
    # fi
    # if [ $contents = "reset" ];
    # then
    # 	touch $masterstation/resetReq.txt
    # fi
    # if [ $contents = "light" ];
    # then
    # 	touch $masterstation/resetReq.txt
    # fi
    echo "Received command: "
    cat command.txt
    mv command.txt $masterstation
    ./dropbox_uploader.sh delete command.txt
fi

./dropbox_uploader.sh download setTemp.txt setTemp.txt > /dev/null 2>&1
if [ -f setTemp.txt ]
then
    mv setTemp.txt $masterstation
    ./dropbox_uploader.sh delete setTemp.txt
fi

./dropbox_uploader.sh download setSchedule.txt setSchedule.txt > /dev/null 2>&1
if [ -f setSchedule.txt ]
then
    mv setSchedule.txt $masterstation/schedule.txt
    ./dropbox_uploader.sh delete setSchedule.txt
fi

./dropbox_uploader.sh download holiday.txt holiday.txt > /dev/null 2>&1
if [ -f holiday.txt ]
then
    mv holiday.txt $masterstation/holiday.txt
    ./dropbox_uploader.sh delete holiday.txt
fi
	 
#Upload any video or photo not uploaded and delete file
# files=$(find $video_picture_dir -type f -name "*.jpeg" -printf "%f\n")
# upload_images $files
# files=$(find $video_picture_dir -type f -name "*.mp4" -printf "%f\n")
# upload_images $files
# files=$(find $video_picture_dir -type f -name "*.mpeg" -printf "%f\n")
# upload_images $files

mins=$(date +%M)

# #Refresh picture every hour
# if [ $mins -eq 0 ]
# then
#     touch take-photo.txt
# fi

#Update weather every 30mins
istime=$((10#$mins % 30))
if ! [ -f $masterstation/motd.txt ] || [ $istime -eq 0 ] 
then
    #motd timed out - get a new one
   cd ${masterstation}
   ./getWeather.sh > /dev/null 2>&1
   cd -
fi

#Check up on temperature
temp="FAIL"
humid="FAIL"
if [ -f temp_avg.txt ]
then
    temp=$(cat temp_avg.txt)
    if [ $temp != "-100.0" ]
    then
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

# tempHumidity=$(python ../masterstation/humidity_sensor.py)
# read -ra arr <<<"$tempHumidity"
# if [ ${arr[0]} == "FAIL" ]
# then
#     #Use other temp sensor if available
#     if [ -f ${sensor_dir}/temperature ]
#     then
#         #temp=$(grep "t=" ${sensor_dir}/w1_slave | awk '{print $10}' | awk -F= '{print $2}')
#         temp=$(cat ${sensor_dir}/temperature)
#         if [ ${#temp} -gt 3 ]
#         then
#             temp=$(echo $temp | awk '{printf("%.1f\n", $1/1000.0)}')
#         else
#             temp="FAIL"
#         fi
#     fi
# else
#     temp=${arr[0]}
#     humid=${arr[1]}
# fi

#Record when boiler is on/off
if [ -f ${masterstation}/status.txt ]
then
    state=$(grep "Heat on" ${masterstation}/status.txt | awk '{print $3}' )
    oldstate=$(cat boilerState.txt)
    if [ $oldstate != $state ] 
    then
        echo $state > boilerState.txt
    	time=$(date +%H%M)
	if [ $state = 'Yes' ]
	then
		state='On'
	else
		state='Off'
	fi
    	echo ${time}":Boiler:"${state} >> $device_change_file
	uploadStatus=Y
    fi
fi

if [ ${uploadStatus} = "Y" ]
then
    ./dropbox_uploader.sh upload $device_change_file $device_change_file > /dev/null 2>&1
fi

