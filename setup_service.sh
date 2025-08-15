#!/bin/bash

# Phone Chatbot Service Setup Script
# This script sets up the phone chatbot to run automatically on boot

set -e

echo "🤖 Setting up Phone Chatbot Service..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run this script as root (use sudo)"
    exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER=${SUDO_USER:-$USER}
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

echo "📁 Setting up for user: $ACTUAL_USER"
echo "📁 Home directory: $ACTUAL_HOME"
echo "📁 Working directory: $(pwd)"

# Create a proper service file with correct paths
SERVICE_FILE="/etc/systemd/system/phone-chatbot.service"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Phone Chatbot Service
After=network.target
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$(pwd)
Environment=PATH=/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$(pwd)
Environment=HOME=$ACTUAL_HOME
ExecStart=/usr/bin/python3 $(pwd)/src/phone_chatbot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=phone-chatbot

# Restart configuration
StartLimitInterval=60
StartLimitBurst=3

# Security settings
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Created service file: $SERVICE_FILE"

# Reload systemd configuration
echo "🔄 Reloading systemd configuration..."
systemctl daemon-reload

# Enable the service to start on boot
echo "🚀 Enabling service to start on boot..."
systemctl enable phone-chatbot.service

echo "✅ Phone Chatbot Service setup complete!"
echo ""
echo "📋 Service Management Commands:"
echo "   Start service:    sudo systemctl start phone-chatbot"
echo "   Stop service:     sudo systemctl stop phone-chatbot"
echo "   Restart service:  sudo systemctl restart phone-chatbot"
echo "   Check status:     sudo systemctl status phone-chatbot"
echo "   View logs:        sudo journalctl -u phone-chatbot -f"
echo "   Disable service:  sudo systemctl disable phone-chatbot"
echo ""
echo "🔧 The service is now configured to:"
echo "   ✓ Start automatically on boot"
echo "   ✓ Restart automatically if it crashes"
echo "   ✓ Wait 10 seconds between restart attempts"
echo "   ✓ Log to system journal"
echo ""
echo "🚀 To start the service now, run:"
echo "   sudo systemctl start phone-chatbot"