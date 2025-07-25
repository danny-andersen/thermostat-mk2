from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import sys
import json

if len(sys.argv) != 2:
    sys.stderr.write("Please provide a file to parse\n")
    sys.exit(1)

weatherText = dict(
    [
        (0, "Clear night"),
        (1, "Sunny day"),
        (2, "Partly cloudy"),
        (3, "Partly cloudy"),
        (4, "Not used"),
        (5, "Mist"),
        (6, "Fog"),
        (7, "Cloudy"),
        (8, "Overcast"),
        (9, "Light rain shower"),
        (10, "Light rain shower"),
        (11, "Drizzle"),
        (12, "Light rain"),
        (13, "Heavy rain shower"),
        (14, "Heavy rain shower"),
        (15, "Heavy rain"),
        (16, "Sleet shower"),
        (17, "Sleet shower"),
        (18, "Sleet"),
        (19, "Hail shower"),
        (20, "Hail shower"),
        (21, "Hail"),
        (22, "Light snow shower"),
        (23, "Light snow shower"),
        (24, "Light snow"),
        (25, "Heavy snow shower"),
        (26, "Heavy snow shower"),
        (27, "Heavy snow"),
        (28, "Thunder shower"),
        (29, "Thunder shower"),
        (30, "Thunder"),
    ]
)

def getWeatherCode(code):
    if code == 3: code = 2
    if code == 10: code = 9
    if code == 14: code = 13
    if code == 17: code = 16
    if code == 20: code = 19
    if code == 23: code = 22
    if code == 26: code = 25
    if code == 29: code = 28
    return code
    
rainThreshold = 25  # Report rain >25%
rainIfOver = 9

# Load JSON from a file
with open(sys.argv[1], "r") as file:
    data = json.load(file)

# Extracting variables
feature = data['features'][0]
coords = feature['geometry']['coordinates']
props = feature['properties']
timeseries = props['timeSeries']

# Define timezones
utc = ZoneInfo("UTC")
local_tz = ZoneInfo("Europe/London") 

now = datetime.now(local_tz)
# print(f"Current time: {now}")
maxSecsToNextForecast = 23 * 3600
forecast = None
inTomorrow = False
temp = 0
rainTime = -1

# print(f"Coordinates: Longitude={coords[0]}, Latitude={coords[1]}, Altitude={coords[2]}")
# print(f"Request Point Distance: {props['requestPointDistance']} meters")
# print(f"Model Run Date: {props['modelRunDate']}")
# print("Time Series Data:")

# Sort entries by datetime (although they should already be sorted)
sorted_time_series = sorted(
    timeseries,
    key=lambda entry: datetime.strptime(entry['time'], "%Y-%m-%dT%H:%MZ").replace(tzinfo=utc).astimezone(local_tz)
)

    # print(f"\nTime: {}")
    # print(f"  Screen Temp: {entry['screenTemperature']} °C")
    # print(f"  Dew Point Temp: {entry['screenDewPointTemperature']} °C")
    # print(f"  Feels Like Temp: {entry['feelsLikeTemperature']} °C")
    # print(f"  Wind Speed: {entry['windSpeed10m']} m/s")
    # print(f"  Gust Speed: {entry['windGustSpeed10m']} m/s")
    # print(f"  Humidity: {entry['screenRelativeHumidity']} %")
    # print(f"  UV Index: {entry['uvIndex']}")
    # print(f"  Precipitation Rate: {entry['precipitationRate']} mm/h")
    # print(f"  Probability of Precipitation: {entry['probOfPrecipitation']} %")    # Find start of hourly forecast

for entry in sorted_time_series:
    entry_time = datetime.strptime(entry["time"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=utc).astimezone(local_tz)
    # print(f"Current time: {now}, checking {entry_time}, probOfPrecipitation: {entry['probOfPrecipitation']}")
    if now - entry_time < timedelta(hours=1):
        # Found the current hourly forecast
        forecast = entry
        nowWeather = getWeatherCode(int(forecast["significantWeatherCode"]))
        forecastDate = datetime.strptime(forecast["time"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=utc).astimezone(local_tz)
        raining = int(forecast["probOfPrecipitation"]) > rainThreshold
        rainProb = int(forecast["probOfPrecipitation"])
        forecastTime = entry_time
        break

nextForecast = None
nextWeather = -1
nextTemp = -255
nextTimeHour = -1
nextRainProp = 0

# Get next weather
for entry in sorted_time_series:
    entry_time = datetime.strptime(entry["time"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=utc).astimezone(local_tz)
    if (entry_time > forecastDate) and ((entry_time - forecastDate).total_seconds() < maxSecsToNextForecast):
        # print(f"Next weather: checking {entry_time}, probOfPrecipitation: {entry['probOfPrecipitation']}")
        if nextTemp == -255:
            nextTemp = float(entry["screenTemperature"])
            # print(f"Next temp: {nextTemp} at {entry_time}")
        entryWeather = getWeatherCode(entry["significantWeatherCode"])
        if (entryWeather != nowWeather):    
            nextForecast = entry
            nextWeather = entryWeather
            nextRainProp = int(entry["probOfPrecipitation"])
            nextTimeHour = entry_time.hour
            break

if forecastDate.hour > now.hour or nextTemp == -255:
    # Forecast is in the future - use its temperature
    temp = float(forecast["screenTemperature"])
else:
    # Forecast is in the past - use average of it and next temperature
    temp = (float(forecast["screenTemperature"]) + nextTemp) / 2.0
    
precipTime = None
precipPercent = 0
stopRaining = None
# Find time of next rain or when it stops raining
for entry in sorted_time_series:
    entry_time = datetime.strptime(entry["time"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=utc).astimezone(local_tz)
    if entry_time > forecastDate:
        if int(entry["probOfPrecipitation"]) >= rainThreshold and precipTime is None:
            # If it is likely to rain
            precipTime = entry_time
            precipPercent = int(entry["probOfPrecipitation"])
        if raining and int(entry["probOfPrecipitation"]) < rainThreshold and stopRaining is None:
            # If it is likely to stop raining
            stopRaining = entry_time

#Convert wind speed to mph
if forecast.get('windSpeed10m') is None:
    windms = '?'
else:
    # Convert m/s to mph
    windms = forecast['windSpeed10m'] * 2.23694
if forecast.get('windGustSpeed10m') is None:
    windgustms = '?'
else:
    # Convert m/s to mph
    windgustms = forecast['windGustSpeed10m'] * 2.23694


wind = f"{windms:.0f}-{windgustms:.0f}mph"
dirn = forecast['windDirectionFrom10m']
#Convert direction to compass direction
if dirn is None or dirn == "":
    dirn = "?"
else:
    dirn = int(dirn)
    if dirn < 0 or dirn > 360:
        dirn = "?"
    else:
        # Convert to compass direction
        directions = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        ]
        dirn = directions[int((dirn + 11.25) / 22.5) % 16]
        
# if len(dirn) + len(wind) >= 10:
#     wind += dirn
# else:
wind += f" {dirn}"

# print forecast.text, nextForecast.text
# print forecast.get('T'), nextTemp, temp, wind
# print nowWeather, nextWeather
# print weatherText[nowWeather], weatherText[nextWeather]
# print precipTime.text, precipTime.get('Pp')
# print stopRaining.text, stopRaining.get('Pp')

rainStr = ""
if rainProb > rainThreshold or nowWeather >= rainIfOver:
    rainStr = f" ({rainProb}%)"
nextRainStr = ""
if nextRainProp > rainThreshold or nextWeather >= rainIfOver:
    nextRainStr = f" ({nextRainProp}%)"
if nextTimeHour >= 0:
    forecastText = f"{weatherText[nowWeather]}{rainStr} until {nextTimeHour :.0f}00 and then {weatherText[nextWeather]}{nextRainStr}"
else:
    forecastText = f"{weatherText[nowWeather]}{rainStr} all {'day' if forecastTime.hour < 18 else 'night'}!"

# Currently not raining (probably) but rain is expected
if rainProb <= rainThreshold and precipTime != None and nextRainStr == "":
    forecastText += ". Rain at %0d00 (%s%%)" % (
        precipTime.hour,
        precipPercent,
    )

# Read in sunrise + sunset times
with open("suntimes.txt", "r") as f:
    sunrise = f.readline().strip("\n").strip()
    sunset = f.readline().strip("\n").strip()
if sunrise != "" and sunset != "":
    sunriseHr = int(sunrise.split(":")[0])
    sunsetHr = int(sunset.split(":")[0])
    riseDelta = abs(now.hour - sunriseHr)
    setDelta = abs(now.hour - sunsetHr)
    if riseDelta <= 2:
        forecastText = "Sunrise at %s, %s" % (sunrise, forecastText)
    elif setDelta <= 2:
        forecastText = "Sunset at %s, %s" % (sunset, forecastText)

# Expire forecast after one hour
expiry = 1 * 3600 * 1000

# print (f"Date: {forecastDate} Forecast: {forecastText}")
# print (wind, temp)
# print (sunrise, sunset)

# Save output into files for sending to thermostat
# Save first hour temp as ext temp
with open("setExtTemp.txt", "w") as f:
    f.truncate()
    f.write(str(temp) + "\n")
    f.write(wind + "\n")
# Add expiry to motd
with open("motd.txt", "w") as f:
    f.truncate()
    f.write(forecastText + "\n")
    f.write("%d" % expiry + "\n")
