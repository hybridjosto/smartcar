#!/bin/bash
#TODO: check if time is 00 00, if so, send fast charge mode
# Construct URL
base_url="https://s18.myenergi.net"
endpoint="/cgi-zappi-mode-Z${MYENERGI_SERIAL}-1-0-0000"
full_url="${base_url}${endpoint}"
# Make request
echo "📡 Sending Smart Boost request to Zappi for ..."
curl --digest -u "$MYENERGI_SERIAL:$MYENERGI_KEY" --location "$full_url"
