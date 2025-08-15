# Phone Chatbot Service Setup

This guide will help you set up the Phone Chatbot to run automatically on boot and restart if it crashes.

## 🚀 Quick Setup

1. **Run the setup script as root:**
   ```bash
   sudo ./setup_service.sh
   ```

2. **Optionally set up logging management:**
   ```bash
   sudo ./setup_logging.sh
   ```

3. **Start the service:**
   ```bash
   sudo systemctl start phone-chatbot
   ```

## 📋 Service Management

### Basic Commands
- **Start service:** `sudo systemctl start phone-chatbot`
- **Stop service:** `sudo systemctl stop phone-chatbot`
- **Restart service:** `sudo systemctl restart phone-chatbot`
- **Check status:** `sudo systemctl status phone-chatbot`
- **Enable on boot:** `sudo systemctl enable phone-chatbot`
- **Disable on boot:** `sudo systemctl disable phone-chatbot`

### Viewing Logs
- **Live logs:** `sudo journalctl -u phone-chatbot -f`
- **Recent logs:** `sudo journalctl -u phone-chatbot -n 50`
- **Today's logs:** `sudo journalctl -u phone-chatbot --since today`
- **Error logs only:** `sudo journalctl -u phone-chatbot -p err`

## 🔧 Service Configuration

The service is configured with:
- **Auto-restart:** Service restarts automatically if it crashes
- **Restart delay:** 10 seconds between restart attempts
- **Start limit:** Maximum 3 restart attempts per minute
- **Boot startup:** Starts automatically when system boots
- **Logging:** All output goes to system journal

## 🛠 Manual Setup (Alternative)

If you prefer to set up manually:

1. **Copy service file:**
   ```bash
   sudo cp phone-chatbot.service /etc/systemd/system/
   ```

2. **Edit paths in service file:**
   ```bash
   sudo nano /etc/systemd/system/phone-chatbot.service
   ```
   Update `WorkingDirectory`, `ExecStart`, and `User` fields as needed.

3. **Reload and enable:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable phone-chatbot
   sudo systemctl start phone-chatbot
   ```

## 🐛 Troubleshooting

### Service won't start
```bash
# Check service status for errors
sudo systemctl status phone-chatbot

# Check recent logs
sudo journalctl -u phone-chatbot -n 20
```

### Permission issues
- Ensure the service runs as the correct user (usually `pi`)
- Check that the user has access to audio devices
- Verify GPIO permissions if using hardware

### Environment variables
The service loads environment variables from the working directory's `.env` file. Ensure:
- `.env` file exists in `/workspace/`
- Contains all required API keys
- Has correct file permissions

### Audio device issues
```bash
# List audio devices
python3 list_audio_devices.py

# Test audio in the service environment
sudo -u pi python3 /workspace/src/phone_chatbot.py
```

## 📊 Monitoring

### Check if service is running
```bash
sudo systemctl is-active phone-chatbot
```

### View service uptime
```bash
sudo systemctl show phone-chatbot --property=ActiveEnterTimestamp
```

### Monitor resource usage
```bash
# CPU and memory usage
sudo systemctl status phone-chatbot

# Detailed process info
ps aux | grep phone_chatbot
```

## 🔄 Updates

When you update the code:
1. **Stop the service:** `sudo systemctl stop phone-chatbot`
2. **Update your code**
3. **Start the service:** `sudo systemctl start phone-chatbot`

Or simply restart:
```bash
sudo systemctl restart phone-chatbot
```

The service will automatically pick up code changes on restart.