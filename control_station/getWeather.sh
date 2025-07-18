#wget http://weather.yahooapis.com/forecastrss?w=28915&u=c
#wget -O yahooWeather.json https://query.yahooapis.com/v1/public/yql?q=select%20*%20from%20weather.forecast%20where%20woeid%20%3D%2028915&format=json&env=store%3A%2F%2Fdatatables.org%2Falltableswithkeys

#BBC
#wget -O bbc-weather.html http://www.bbc.co.uk/weather/2642573
#python parse_bbc.py bbc-weather.html
#Met Office
wget -O suntimes.xml "https://www.sunrise-and-sunset.com/en/sun/united-kingdom/middlewich"
python parse_sunrise_sunset.py suntimes.xml
#wget -O met-forecast.xml "http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/xml/352627?res=3hourly&key=5b71c02f-a1fd-4a43-9d15-cf3315d75ba9"
curl -X GET "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly?includeLocationName=true&latitude=53.195&longitude=-2.438" \
 -H "accept: application/json"\
 -H @met-office-api-key.txt \
    -o met-forecast.json -s

python parse_met_office.py met-forecast.json

