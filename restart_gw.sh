#!/bin/bash
pkill -f ibcalpha 2>/dev/null
sleep 3
pgrep -f ibcalpha && echo "Still running" || echo "Gateway stopped"
