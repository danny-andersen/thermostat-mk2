#!/bin/bash
function upload_images {
    if [ $# -gt 0 ]
    then
        echo Uploading $# media files
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

device_change_file=$(date +%Y%m%d)"_cam${1}_change.txt"
video_picture_dir=$2
uploadStatus=N
COMMAND_FILE=command-cam${1}.txt
only_monitor_when_noones_home=N

# echo Running check status with ${1} and $2
#Check wifi up
ping -c2 192.168.1.1 > /dev/null
if [ $? == 0 ]
then
  touch wifi-up.txt
fi

#Check last time could contact wifi AP 
#If greater than 15 mins ago, restart wlan0
cnt=$(find ./ -name wifi-up.txt -mmin +15 | wc -l)
if [ ${cnt} != 0 ]
then
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

# echo "Downloading command file"
./dropbox_uploader.sh download COMMAND_FILE command.txt > /dev/null 2>&1
if [ -f command.txt ]
then
    contents=$(cat command.txt)
    # echo "Running command:" $contents
    if [ $contents = "photo" ];
    then
    	touch take-photo.txt
    fi
    if [ $contents = "video" ];
    then
    	touch take-video.txt
    fi
    if [ $contents = "reset" ];
    then
    	touch resetReq.txt
    fi
    ./dropbox_uploader.sh delete COMMAND_FILE
    rm command.txt
fi

#Check whether we should enable cameras
#For internal cameras only enable when no-one's home
if [ $only_monitor_when_noones_home = 'Y' ]
then
    #Check if anyone's home
    safeDevice=`cat safeDevices.txt`
    dev=$(echo $safeDevice | sed 's/|/ /g')
    home_alone="Y"
    for d in $dev
    do
        ping -c2 $d > /dev/null 2>&1
        if [ $? == 0 ]
        then
            #Device on network
            home_alone="N"
        fi
    done
    #Check if motion is running
    sudo service motion status >/dev/null
    if [ $? -ne 0 ]
    then
        if [ $home_alone = "Y" ]
        then
            #Motion isnt running
            echo "No ones home and motion isnt running"
            sudo service motion start
        fi
    else
        if [ $home_alone = "N" ]
        then
            #Motion is running but someones home
            echo "Stopping motion service"
            sudo service motion stop
        fi
    fi
# else
#     #Check if motion is running
#     sudo service motion status >/dev/null
#     if [ $? -ne 0 ]
#     then
#         #Motion isnt running
#         echo "Motion service isnt running ??"
#         sudo service motion start
#     fi
fi

# echo "Looking for media files and uploading"
#Upload any video or photo not uploaded and delete file
files=$(find $video_picture_dir -type f -name "*.jpeg" -printf "%f\n")
upload_images $files
files=$(find $video_picture_dir -type f -name "*.mp4" -printf "%f\n")
upload_images $files
# files=$(find $video_picture_dir -type f -name "*.mpeg" -printf "%f\n")
# upload_images $files

mins=$(date +%M)

#Check up on temperature
temp="FAIL"
humid="FAIL"

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

