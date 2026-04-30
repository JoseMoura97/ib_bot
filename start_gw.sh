#!/bin/bash
# Kill any existing gateway
pkill -9 -f ibgateway 2>/dev/null
pkill -9 -f IbcGateway 2>/dev/null
sleep 2

# Ensure VNC is running
if ! pgrep -f x11vnc > /dev/null; then
    x11vnc -display :1 -passwd ibbot -forever -bg -quiet
    echo "VNC started"
else
    echo "VNC already running"
fi

# Start IB Gateway
DISPLAY=:1 nohup /opt/ibgateway/ibgateway > /tmp/gw.log 2>&1 &
GW_PID=$!
echo "IB Gateway started PID=$GW_PID"
sleep 3

# Check it's running
if kill -0 $GW_PID 2>/dev/null; then
    echo "Gateway running OK"
else
    echo "Gateway died - check /tmp/gw.log"
    tail -5 /tmp/gw.log
fi
