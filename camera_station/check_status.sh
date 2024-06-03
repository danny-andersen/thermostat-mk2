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

CAM_NUM=$1
video_picture_dir=$2
only_monitor_when_noones_home='N'
COMMAND_FILE=command-cam${CAM_NUM}.txt

# echo "Downloading command file"
./dropbox_uploader.sh download $COMMAND_FILE command.txt > /dev/null 2>&1
if [ -f command.txt ]
then
    contents=$(cat command.txt)
    # echo "Running command:" $contents
    ./dropbox_uploader.sh delete $COMMAND_FILE
    rm command.txt
    if [ $contents = "photo" ];
    then
    	touch take-photo.txt
    fi
    if [ $contents = "video" ];
    then
    	touch take-video.txt
    fi
    if [ $contents = "camera-on" ];
    then
        echo "Received camera ON command"
        force_camera_on='Y'
        echo "Y" > camera_set_state.txt
    fi
    if [ $contents = "camera-off" ];
    then
        echo "Received camera OFF command"
        echo "N" > camera_set_state.txt
    fi
    if [ $contents = "reset" ];
    then
        sudo reboot
    fi
fi

#Camera Logic:
#Basically if camera cmd is set to off or not set and only monitor when noones home is set then camera is turned on if noones home
#Otherwise, if camera cmd is not set or set to on, camera is on.
#If command to turn camera on is received:
#   camera_set_state=Y, camera_on=Y, regardless of only_monitor setting
#If command to turn off camera is received:
#   camera_set_state=N, camera_on= if only monitor = Y then (if noones home then Y else N) else N


if [ -f camera_set_state.txt ]
then
    camera_set_state=$(cat camera_set_state.txt)
else
    camera_set_state='?'
fi

#Check whether we should enable cameras
#For internal cameras only turn off when someones home unless forced on by a command
if [ $camera_set_state = 'Y' ]
then
    camera_on='Y'
else
    if [ $only_monitor_when_noones_home = 'Y' ]
    then
        #echo "Checking if anyones home"
        camera_on='Y'
        #Check if anyone's home
        safeDevice=`cat safeDevices.txt`
        dev=$(echo $safeDevice | sed 's/|/ /g')
        for d in $dev
        do
            ping -c2 $d > /dev/null 2>&1
            if [ $? == 0 ]
            then
                #Device on network and only monitor when no-ones home
                camera_on='N'
                #echo "Someones home so camera should be off"
            fi
        done
    else
        if [ $camera_set_state = 'N' ]
        then
            camera_on='N'
        else
            camera_on='Y'
        fi
    fi
fi

./check_wifi.sh
./check_camera.sh $camera_on
./check_temp.sh $CAM_NUM


# echo "Looking for media files and uploading"
#Upload any video or photo not uploaded and delete file
files=$(find $video_picture_dir -type f -name "*.jpeg" -printf "%f\n")
upload_images $files
files=$(find $video_picture_dir -type f -name "*.mp4" -printf "%f\n")
upload_images $files
# files=$(find $video_picture_dir -type f -name "*.mpeg" -printf "%f\n")
# upload_images $files

