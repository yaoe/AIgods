#!/bin/bash

# Phone Chatbot Service Test Script
# Tests the service installation and functionality

echo "🧪 Testing Phone Chatbot Service..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test functions
test_service_exists() {
    echo -n "📄 Checking if service file exists... "
    if [ -f "/etc/systemd/system/phone-chatbot.service" ]; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗${NC}"
        return 1
    fi
}

test_service_enabled() {
    echo -n "🚀 Checking if service is enabled... "
    if systemctl is-enabled phone-chatbot &>/dev/null; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗${NC}"
        return 1
    fi
}

test_service_active() {
    echo -n "⚡ Checking if service is running... "
    if systemctl is-active phone-chatbot &>/dev/null; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗${NC}"
        return 1
    fi
}

test_dependencies() {
    echo "🔍 Checking dependencies..."
    
    # Check Python
    echo -n "  Python 3... "
    if command -v python3 &>/dev/null; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
    fi
    
    # Check if main script exists
    echo -n "  Main script... "
    if [ -f "/workspace/src/phone_chatbot.py" ]; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
    fi
    
    # Check .env file
    echo -n "  Environment file... "
    if [ -f "/workspace/.env" ]; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${YELLOW}⚠${NC} (.env file not found)"
    fi
}

show_service_status() {
    echo ""
    echo "📊 Service Status:"
    systemctl status phone-chatbot --no-pager -l
}

show_recent_logs() {
    echo ""
    echo "📝 Recent Logs (last 10 lines):"
    journalctl -u phone-chatbot -n 10 --no-pager
}

# Main test execution
echo "Running service tests..."
echo ""

# Check if running as root for service tests
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}⚠${NC} Some tests require root privileges. Run with sudo for complete testing."
    echo ""
fi

# Run tests
test_dependencies
echo ""

if [ "$EUID" -eq 0 ]; then
    test_service_exists
    test_service_enabled
    test_service_active
    
    show_service_status
    show_recent_logs
else
    echo "🔒 Skipping service tests (requires root)"
fi

echo ""
echo "🎯 Manual Test Commands:"
echo "  Check status:     sudo systemctl status phone-chatbot"
echo "  View live logs:   sudo journalctl -u phone-chatbot -f"
echo "  Start service:    sudo systemctl start phone-chatbot"
echo "  Stop service:     sudo systemctl stop phone-chatbot"
echo ""
echo "✅ Test complete!"