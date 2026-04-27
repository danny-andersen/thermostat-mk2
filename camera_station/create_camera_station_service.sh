sudo cp camera_station.service /etc/systemd/system/camera_station.service
sudo systemctl enable camera_station.service
sudo systemctl start camera_station.service
sudo systemctl status camera_station.service

