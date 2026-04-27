sudo cp motion.service /etc/systemd/system/motion.service
sudo systemctl enable motion.service
sudo systemctl start motion.service
sudo systemctl status motion.service

