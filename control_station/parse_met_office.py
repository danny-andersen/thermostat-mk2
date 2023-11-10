if __name__ == "__main__":
    from datetime import datetime, time, timedelta
    import sys
    import xml.etree.ElementTree as ET

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

    rainThreshold = 25  # Report rain >25%
    rainIfOver = 9
    tree = ET.parse(sys.argv[1])
    root = tree.getroot()

    # Find start of hourly forecast
    now = datetime.today()
    today = now.strftime("%Y-%m-%dZ")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%dZ")
    t = now.time()
    nowMins = (t.hour * 60) + t.minute
    sepMins = 24 * 60
    forecast = None
    inTomorrow = False
    temp = 0
    rainTime = -1
    days = root.iter("Period")
    for day in days:
        # Find the closest forecast to now
        if day.get("value") == today:
            for rep in day.findall("Rep"):
                sep = abs(nowMins - int(rep.text))
                if sep < sepMins:
                    forecast = rep
                    sepMins = sep
        if day.get("value") == tomorrow:
            # Get mins from midnight
            mins = 24 * 60 - nowMins
            for rep in day.findall("Rep"):
                sep = mins + int(rep.text)
                if sep < sepMins:
                    # Nearest forecast is in tomorrow's
                    inTomorrow = True
                    forecast = rep
                    sepMins = sep
    nowWeather = int(forecast.get("W"))
    # Get next weather
    nextForecast = None
    nextWeather = -1
    nextTemp = -255
    precipTime = None
    stopRaining = None
    days = root.iter("Period")
    for day in days:
        if day.get("value") == today:
            for rep in day.findall("Rep"):
                if int(rep.text) > int(forecast.text):
                    if nextTemp == -255:
                        # Use the next forecast temp to average
                        nextTemp = int(rep.get("T"))
                    # Rain more likely than not
                    if precipTime == None and int(rep.get("Pp")) > rainThreshold:
                        precipTime = rep
                    # Rain stopping
                    if stopRaining == None and int(rep.get("Pp")) <= rainThreshold:
                        stopRaining = rep
                    if (
                        nextForecast == None
                        and weatherText[int(rep.get("W"))] != weatherText[nowWeather]
                    ):
                        nextForecast = rep
                        nextWeather = int(rep.get("W"))
        # if day.get("value") == tomorrow:
        #     mins = 24 * 60 - nowMins
        #     for rep in day.findall("Rep"):
        #         if int(rep.text) + 180 < int(forecast.text):
        #             # Look in tomorrows forecast up to 3 hours before current time
        #             if precipTime == None and int(rep.get("Pp")) > rainThreshold:
        #                 # Rain more likely than not
        #                 precipTime = rep
        #             if stopRaining == None and int(rep.get("Pp")) <= rainThreshold:
        #                 # Rain stopping
        #                 stopRaining = rep
        #             if nextTemp == -255:
        #                 nextTemp = int(rep.get("T"))
        #             if (
        #                 nextWeather == -1
        #                 and weatherText[int(rep.get("W"))] != weatherText[nowWeather]
        #             ):
        #                 nextForecast = rep
        #                 nextWeather = int(rep.get("W"))
    # print nextWeather, day.get('value'), today, tomorrow
    if int(forecast.text) > nowMins or inTomorrow or nextTemp == -255:
        # Forecast is in the future - use its temperature
        temp = int(forecast.get("T"))
    else:
        # Forecast is in the past - use average of it and next temperature
        temp = (int(forecast.get("T")) + nextTemp) / 2.0

    wind = f"{forecast.get('S')}-{forecast.get('G')}mph"
    dirn = forecast.get("D")
    if len(dirn) + len(wind) >= 10:
        wind += dirn
    else:
        wind += f" {dirn}"
    # print forecast.text, nextForecast.text
    # print forecast.get('T'), nextTemp, temp, wind
    # print nowWeather, nextWeather
    # print weatherText[nowWeather], weatherText[nextWeather]
    # print precipTime.text, precipTime.get('Pp')
    # print stopRaining.text, stopRaining.get('Pp')
    nextTime = -1
    if nextForecast != None:
        nextTime = int(nextForecast.text) / 60
    rainProb = int(forecast.get("Pp"))
    rainStr = ""
    if rainProb > rainThreshold or nowWeather >= rainIfOver:
        rainStr = f" ({rainProb}%)"
    if nextTime >= 0:
        forecastText = f"{weatherText[nowWeather]}{rainStr} until {nextTime :.0f}00"
    else:
        forecastText = f"{weatherText[nowWeather]}{rainStr} all day!"

    # Currently not raining (probably)
    if rainProb <= rainThreshold and precipTime != None:
        rainTime = int(precipTime.text) / 60
        forecastText += ". Rain (%s%%) at %0d00" % (
            precipTime.get("Pp"),
            rainTime,
        )
    elif nextForecast != None:
        rainProb = int(nextForecast.get("Pp"))
        rainStr = ""
        if rainProb > rainThreshold or nextWeather >= rainIfOver:
            rainStr = " (%s%%)" % rainProb
        forecastText += " and then %s%s" % (weatherText[nextWeather], rainStr)
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

    if nextTime >= 0:
        if now.hour > nextTime:
            expiry = (24 - now.hour + nextTime) * 3600 * 1000
        else:
            expiry = (nextTime - now.hour) * 3600 * 1000
    else:
        # If no next forecast, expire after two hours
        expiry = 2 * 3600 * 1000

    # print forecastText, expiry
    # print wind, temp

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
