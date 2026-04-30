#!/bin/bash
WG_IF=$1
SERVER_IP=213.159.68.39
VPN_TABLE=51820
WG_FWMARK=51820
INBOUND_MARK=51821

REAL_GW=$(ip route show default | awk 'NR==1{print $3}')
REAL_IF=$(ip route show default | awk 'NR==1{print $5}')

# WG endpoint must be reachable via real interface (avoid loop)
ip route add 196.196.203.202/32 via ${REAL_GW} dev ${REAL_IF} metric 0 2>/dev/null

# VPN routing table
ip route add default dev ${WG_IF} table ${VPN_TABLE} 2>/dev/null

# Rules (lower = higher priority):
# WG's own encrypted packets -> real interface (prevents loop)
ip rule add fwmark ${WG_FWMARK} table main priority 40 2>/dev/null
# Responses to inbound connections (SSH, nginx) -> real interface
ip rule add fwmark ${INBOUND_MARK} table main priority 50 2>/dev/null
# Everything else (IB Gateway, etc.) -> VPN
ip rule add not fwmark ${INBOUND_MARK} table ${VPN_TABLE} priority 100 2>/dev/null

# Mark packets that are responses to inbound connections to this server
iptables -t mangle -A OUTPUT \
    -m conntrack --ctstate ESTABLISHED,RELATED \
    --ctorigdst ${SERVER_IP} \
    -j MARK --set-mark ${INBOUND_MARK}

echo "[wg-up] Split tunnel active: IB Gateway -> VPN, SSH/nginx -> real IP"
