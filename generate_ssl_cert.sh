#!/bin/bash
#
# Generate SSL certificate for HTTPS server
#

set -e

# Create SSL directory
mkdir -p /tmp/ssl

# Certificate paths
CERT_FILE="/tmp/ssl/server.crt"
KEY_FILE="/tmp/ssl/server.key"

echo "Generating self-signed SSL certificate..."

# Generate private key and certificate
openssl req -x509 -newkey rsa:4096 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -days 365 \
    -nodes \
    -subj "/C=US/ST=State/L=City/O=DnDChat/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1,IP:10.0.0.112"

echo "SSL certificate generated:"
echo "  Certificate: $CERT_FILE"
echo "  Private Key: $KEY_FILE"
echo ""
echo "Set environment variables:"
echo "  export SSL_CERT_FILE=$CERT_FILE"
echo "  export SSL_KEY_FILE=$KEY_FILE"
echo ""
echo "Or run the server with:"
echo "  SSL_CERT_FILE=$CERT_FILE SSL_KEY_FILE=$KEY_FILE python start_server.py"