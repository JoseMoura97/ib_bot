#!/bin/bash
pkill -f "socat.*4003" 2>/dev/null
sleep 1
nohup socat TCP-LISTEN:4003,bind=0.0.0.0,reuseaddr,fork TCP:127.0.0.1:4001 > /tmp/socat.log 2>&1 &
sleep 2
ss -tlnp | grep 4003 && echo "socat proxy running on :4003 -> 127.0.0.1:4001" || echo "socat failed"
