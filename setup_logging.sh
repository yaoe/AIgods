#!/bin/bash

# Phone Chatbot Logging Setup Script
# Sets up log rotation and management for the phone chatbot service

set -e

echo "📝 Setting up Phone Chatbot Logging..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run this script as root (use sudo)"
    exit 1
fi

# Create logrotate configuration for phone chatbot logs
LOGROTATE_FILE="/etc/logrotate.d/phone-chatbot"

cat > "$LOGROTATE_FILE" << EOF
# Phone Chatbot log rotation configuration
# Rotates systemd journal logs for the phone-chatbot service

# Note: systemd journal logs are managed by journald
# This is for any additional log files if created in the future

/var/log/phone-chatbot*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 root root
}
EOF

echo "✅ Created logrotate configuration: $LOGROTATE_FILE"

# Configure journald to limit log size for our service
JOURNALD_CONF="/etc/systemd/journald.conf.d"
mkdir -p "$JOURNALD_CONF"

cat > "$JOURNALD_CONF/phone-chatbot.conf" << EOF
# Phone Chatbot journald configuration
# Limits log size to prevent disk space issues

[Journal]
# Limit total journal size to 100MB
SystemMaxUse=100M
# Keep logs for 7 days
MaxRetentionSec=7d
# Limit individual log files to 10MB
SystemMaxFileSize=10M
EOF

echo "✅ Created journald configuration: $JOURNALD_CONF/phone-chatbot.conf"

# Restart journald to apply new configuration
echo "🔄 Restarting journald service..."
systemctl restart systemd-journald

echo "✅ Logging setup complete!"
echo ""
echo "📋 Log Management Commands:"
echo "   View live logs:           sudo journalctl -u phone-chatbot -f"
echo "   View recent logs:         sudo journalctl -u phone-chatbot -n 50"
echo "   View logs since boot:     sudo journalctl -u phone-chatbot -b"
echo "   View logs from today:     sudo journalctl -u phone-chatbot --since today"
echo "   View error logs only:     sudo journalctl -u phone-chatbot -p err"
echo "   Export logs to file:      sudo journalctl -u phone-chatbot > phone-chatbot.log"
echo ""
echo "📊 Log Configuration:"
echo "   ✓ Logs are stored in systemd journal"
echo "   ✓ Maximum total size: 100MB"
echo "   ✓ Retention period: 7 days"
echo "   ✓ Individual file limit: 10MB"
echo "   ✓ Log rotation configured"