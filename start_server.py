#!/usr/bin/env python3
"""
Startup script for the DnD Chat FastAPI server with HTTPS support
"""

from src.app import app

import uvicorn
import ssl
import os

# HTTPS configuration
def create_ssl_context():
    """Create SSL context for HTTPS"""
    # Default paths for SSL certificates
    cert_file = os.getenv('SSL_CERT_FILE', '/etc/ssl/certs/server.crt')
    key_file = os.getenv('SSL_KEY_FILE', '/etc/ssl/private/server.key')
    
    # Check if certificate files exist
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print(f"Using SSL certificates: {cert_file}, {key_file}")
        return {
            "ssl_certfile": cert_file,
            "ssl_keyfile": key_file
        }
    else:
        # Generate self-signed certificate for development
        print("SSL certificates not found. Generating self-signed certificate for development...")
        try:
            import subprocess
            
            # Create certificates directory if it doesn't exist
            os.makedirs('/tmp/ssl', exist_ok=True)
            cert_file = '/tmp/ssl/server.crt'
            key_file = '/tmp/ssl/server.key'
            
            # Generate self-signed certificate
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:4096',
                '-keyout', key_file, '-out', cert_file,
                '-days', '365', '-nodes',
                '-subj', '/C=US/ST=State/L=City/O=Organization/CN=localhost'
            ], check=True, capture_output=True)
            
            print(f"Generated self-signed certificate: {cert_file}")
            return {
                "ssl_certfile": cert_file,
                "ssl_keyfile": key_file
            }
        except Exception as e:
            print(f"Failed to generate SSL certificate: {e}")
            print("Falling back to HTTP on port 8000")
            return None

# Try to set up HTTPS
ssl_config = create_ssl_context()
if not ssl_config:
    raise ValueError("SSL configuration could not be created.")

uvicorn.run(
    app,
    host="0.0.0.0",
    port=8443,
    ssl_certfile=ssl_config["ssl_certfile"],
    ssl_keyfile=ssl_config["ssl_keyfile"]
)
