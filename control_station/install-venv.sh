python -m venv /home/danny/control_station
cd /home/danny/control_station
ln -s ../common common
source bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

