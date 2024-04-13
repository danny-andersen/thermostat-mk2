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

./check_wifi.sh
./check_camera.sh $only_monitor_when_noones_home
./check_temp.sh $CAM_NUM

COMMAND_FILE=command-cam${CAM_NUM}.txt

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


# echo "Looking for media files and uploading"
#Upload any video or photo not uploaded and delete file
files=$(find $video_picture_dir -type f -name "*.jpeg" -printf "%f\n")
upload_images $files
files=$(find $video_picture_dir -type f -name "*.mp4" -printf "%f\n")
upload_images $files
# files=$(find $video_picture_dir -type f -name "*.mpeg" -printf "%f\n")
# upload_images $files

