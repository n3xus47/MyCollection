#!/bin/bash
# Helper script to find your computer's IP address for the Flutter app

echo "Finding your IP address..."
echo ""

# Try different methods to find IP
if command -v ip &> /dev/null; then
    IP=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -1)
elif command -v ifconfig &> /dev/null; then
    IP=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
elif command -v hostname &> /dev/null; then
    IP=$(hostname -I | awk '{print $1}')
else
    echo "Could not find IP address automatically."
    echo "Please check your network settings manually."
    exit 1
fi

if [ -z "$IP" ]; then
    echo "Could not find IP address automatically."
    echo "Please check your network settings manually."
    exit 1
fi

echo "Your IP address is: $IP"
echo ""
echo "Update the baseUrl in frontend/lib/services/api_service.dart to:"
echo "  static const String baseUrl = 'http://$IP:8000';"
echo ""
echo "For Android Emulator, use: http://10.0.2.2:8000"
echo ""
