if __name__ == "__main__":
	from bs4 import BeautifulSoup
	from datetime import datetime,time
	import sys

	if len(sys.argv) != 2:
		sys.stderr.write("Please provide a file to parse\n")
		sys.exit(1)
	html = BeautifulSoup(open(sys.argv[1]).read(), "lxml")
	# Find sunrise
	sunrise = html.find('th', text="Sunrise today")
	sunriseTime = ''
	if sunrise != None:
		sunriseRow = sunrise.parent
		sunriseTimeCell = sunriseRow.find('td')
		if sunriseTimeCell != None:
			sunriseTime = sunriseTimeCell.text.strip()

	sunset = html.find('th', text="Sunset today")
	sunsetTime = ''
	if sunset != None:
		sunsetRow = sunset.parent
		sunsetTimeCell = sunsetRow.find('td')
		if sunsetTimeCell != None:
			sunsetTime = sunsetTimeCell.text.strip()

	with open("suntimes.txt", "w") as f:
		f.truncate()
		f.write(sunriseTime + "\n")
		f.write(sunsetTime + "\n")
    
