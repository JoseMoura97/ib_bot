#!/bin/bash
cat > /etc/systemd/system/ib-socat.service << 'UNIT'
[Unit]
Description=socat proxy for IB Gateway (Docker containers -> localhost:4001)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:4003,bind=0.0.0.0,reuseaddr,fork TCP:127.0.0.1:4001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable ib-socat
systemctl restart ib-socat
systemctl status ib-socat --no-pager
