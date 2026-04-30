#!/bin/bash
set -euo pipefail

SSL_DIR="/etc/ssl/ibbot"
DAYS=365
SUBJECT="/C=FI/ST=Helsinki/O=IBBot/CN=213.159.68.39"

mkdir -p "$SSL_DIR"

if [ -f "$SSL_DIR/fullchain.pem" ] && [ -f "$SSL_DIR/privkey.pem" ]; then
    EXPIRY=$(openssl x509 -enddate -noout -in "$SSL_DIR/fullchain.pem" 2>/dev/null | cut -d= -f2)
    echo "Existing cert expires: $EXPIRY"
    if openssl x509 -checkend 604800 -noout -in "$SSL_DIR/fullchain.pem" 2>/dev/null; then
        echo "Certificate still valid for >7 days. Skipping regeneration."
        echo "To force, delete $SSL_DIR/fullchain.pem and re-run."
        exit 0
    fi
    echo "Certificate expiring soon, regenerating..."
fi

openssl req -x509 -nodes -newkey rsa:2048 \
    -days "$DAYS" \
    -keyout "$SSL_DIR/privkey.pem" \
    -out "$SSL_DIR/fullchain.pem" \
    -subj "$SUBJECT" \
    -addext "subjectAltName=IP:213.159.68.39"

chmod 600 "$SSL_DIR/privkey.pem"
chmod 644 "$SSL_DIR/fullchain.pem"

echo "Self-signed certificate generated at $SSL_DIR (valid ${DAYS} days)"
echo "  cert: $SSL_DIR/fullchain.pem"
echo "  key:  $SSL_DIR/privkey.pem"
