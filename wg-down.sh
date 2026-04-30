#!/bin/bash
WG_IF=$1
SERVER_IP=213.159.68.39
VPN_TABLE=51820
WG_FWMARK=51820
INBOUND_MARK=51821

iptables -t mangle -D OUTPUT \
    -m conntrack --ctstate ESTABLISHED,RELATED \
    --ctorigdst ${SERVER_IP} \
    -j MARK --set-mark ${INBOUND_MARK} 2>/dev/null

ip rule del fwmark ${WG_FWMARK} table main priority 40 2>/dev/null
ip rule del fwmark ${INBOUND_MARK} table main priority 50 2>/dev/null
ip rule del not fwmark ${INBOUND_MARK} table ${VPN_TABLE} priority 100 2>/dev/null
ip route del default dev ${WG_IF} table ${VPN_TABLE} 2>/dev/null
ip route del 196.196.203.202/32 2>/dev/null

echo "[wg-down] Split tunnel removed"
