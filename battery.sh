#!/bin/bash

# Prompt for current battery percentage using gum input
current_percent=$(gum input --placeholder "e.g. 45" --prompt "Current battery %:")

# Validate input is a number between 0 and 100
if ! [[ "$current_percent" =~ ^[0-9]+$ ]] || [ "$current_percent" -lt 0 ] || [ "$current_percent" -gt 100 ]; then
  echo "❌ Invalid input. Please enter a number between 0 and 100."
  exit 1
fi

# Ask for battery capacity, default to 50 kWh if blank
capacity_kwh=$(gum input --placeholder "50" --prompt "Battery capacity in kWh (default 50):")
capacity_kwh=${capacity_kwh:-50}

# Ask for price per kWh, default to 0.899 if blank
price_kwh=$(gum input --placeholder "0.0899" --prompt "Price per kWh (default 0.0899):")
price_kwh=${price_kwh:-0.0899}

# Validate numeric input for capacity and price
if ! [[ "$capacity_kwh" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "❌ Invalid battery capacity. Must be a number."
  exit 1
fi
if ! [[ "$price_kwh" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "❌ Invalid price. Must be a number."
  exit 1
fi

# Target charge level
target_percent=80

# Calculate percentage to add
percent_to_add=$((target_percent - current_percent))

if [ "$percent_to_add" -le 0 ]; then
  echo "✅ Battery is already at or above ${target_percent}%."
  exit 0
fi

# Calculate kWh needed and cost using bc
kwh_needed=$(echo "scale=4; $capacity_kwh * $percent_to_add / 100" | bc -l)
cost=$(echo "scale=4; $kwh_needed * $price_kwh" | bc -l)

# Round to 2 decimal places for display
kwh_needed_rounded=$(printf "%.2f" "$kwh_needed")
cost_rounded=$(printf "%.2f" "$cost")

# Save the kWh needed to a JSON file
printf '{"kwh_needed": %s}' "$kwh_needed_rounded" >battery.json

echo "🔋 You need approximately $kwh_needed_rounded kWh to reach $target_percent% charge."
echo "💰 Estimated cost: £$cost_rounded"

# Ensure required env vars are set
if [[ -z "$MYENERGI_SERIAL" || -z "$MYENERGI_KEY" ]]; then
  echo "❌ Please set MYENERGI_SERIAL and MYENERGI_KEY environment variables."
  exit 1
fi
# Construct URL
base_url="https://s18.myenergi.net"
endpoint="/cgi-zappi-mode-Z${MYENERGI_SERIAL}-0-11-${kwh_needed}-0500"
full_url="${base_url}${endpoint}"
# Make request
# echo "📡 Sending Smart Boost request to Zappi for ${kwh_needed_rounded} kWh..."
echo "📡 request ${kwh_needed_rounded} kWh..."
# curl --diges -u "$MYENERGI_SERIAL:$MYENERGI_KEY" --location "$full_url"
