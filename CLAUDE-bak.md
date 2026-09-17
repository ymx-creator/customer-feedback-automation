# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Instructions

**DO NOT add the following lines to commit messages:**
```
🚀 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Project Overview

This is a McDonald's survey automation bot built with Python, Selenium, and Flask. The bot automatically completes McDonald's customer satisfaction surveys at scheduled times and runs as a web service on a Debian server.

## Architecture

- **Flask Web App** (`app.py`): Main entry point that provides health check endpoints and manages the scheduling system
- **Automation Scripts** (`scripts/`): Three specialized Selenium-based automation scripts for different survey types:
  - `mcdo_standard_automation.py`: Restaurant/Drive-thru orders (12:00 Paris / 10:00 UTC)
  - `mcdo_morning_automation.py`: Delivery orders - Morning (10:00 Paris / 08:00 UTC)  
  - `mcdo_night_automation.py`: Delivery orders - Evening (19:00 Paris / 17:00 UTC)

## Development Commands

### Installation
```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running Locally
```bash
# Start Flask app with scheduler
python app.py

# Access endpoints at:
# http://localhost:5000/         - Service info
# http://localhost:5000/health   - Health check
# http://localhost:5000/status   - Next execution times
# http://localhost:5000/monitoring - Complete monitoring
```

### Testing Individual Scripts
```bash
# Test scripts individually (set headless=False for debugging)
python scripts/mcdo_standard_automation.py
python scripts/mcdo_morning_automation.py  
python scripts/mcdo_night_automation.py

# Scripts also accept command line arguments for testing
python scripts/mcdo_standard_automation.py --headless=False
```

### Debian Server Deployment
```bash
# Install Chrome on Debian
sudo apt update
sudo apt install -y wget gnupg
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable

# Run the application
python app.py
```

## Key Technical Details

### Selenium Configuration
- All scripts use headless Chrome with Debian-optimized options
- Chrome binary managed automatically by webdriver-manager
- Shared configuration function `setup_chrome_for_debian()` in each script

### Scheduling System
- Uses `schedule` library with UTC times (converted from Paris timezone)
- Runs in background thread via Flask app
- Scheduler checks every minute for pending jobs

### System Configuration
- Chrome binary managed automatically by webdriver-manager
- Logging configured for console output only (no file logging)
- Optimized for Debian server deployment

### API Endpoints
- `/`: Service information and scheduling details
- `/health`: Health check for monitoring services (UptimeRobot compatible)
- `/status`: Next execution times and detailed status
- `/last-run`: Execution history and success rates
- `/monitoring`: Complete monitoring data with stats and next runs

## Important Notes

- Bot designed for Debian server deployment
- Uses Python timezone handling (`pytz`) for Paris/UTC conversion  
- All automation scripts include comprehensive error handling and retry logic (3 attempts per script)
- Chrome runs with disabled JavaScript and images for performance
- Execution monitoring with success/failure tracking and duration logging

## Production Status and Dokploy Notes

### Current production posture
- The app is considered production-oriented only when run behind Gunicorn with a dedicated scheduler process, not via Flask's built-in development server.
- Public port exposure is forbidden for this project. The web service must stay local-only unless intentionally exposed through a trusted tunnel.
- Dokploy should deploy the project using Docker Compose, not Nixpacks or a direct Python entrypoint, because the app requires browser automation and isolated scheduling.

### Container and runtime architecture
- `Dockerfile` builds the Python runtime, Chromium/ChromeDriver dependencies, and the app.
- `docker-compose.yml` runs two separate services:
  - `web`: Gunicorn serving the Flask app
  - `scheduler`: runs the scheduling logic independently
- This separation keeps HTTP traffic and scheduler logs distinct and avoids duplicate scheduling when multiple workers or replicas exist.

### Security requirements
- Require environment variables for authentication and session protection:
  - `AUTH_PASSWORD`
  - `AUTH_SALT`
  - `SECRET_KEY`
- Session cookies should be hardened with `SESSION_COOKIE_HTTPONLY=true` and `SESSION_COOKIE_SECURE=true` in production.
- For local-only SSH tunnel access, set `SESSION_COOKIE_SECURE=false` temporarily for browser access while the tunnel is used.
- The application should avoid public listening ports and should only be reachable through a trusted internal network or SSH tunnel.

### Logging requirements
- Scheduler logs must be separated from HTTP/web logs.
- Scheduler recap entries should be clearly labeled, for example:
  - `[SCHEDULER_RECAP]`
  - `[DAILY_RECAP]`
- Web/HTTP logs should stay clean and not mix scheduler operational messages.
- The goal is to have a clean recap every scheduler execution and a daily summary at the end of the day.

### Git / deployment hygiene
- Do not touch the `prod` branch for this work.
- Keep the changes on `main` unless explicitly instructed otherwise.
- All production-hardening changes should be staged, committed, and pushed on `main` only.

### SSH tunnel diagnosis
- The tunnel command is expected to be:
  ```bash
  ssh -N -L 5000:127.0.0.1:5000 utilisateur@IP_DU_SERVEUR
  ```
- If SSH returns:
  ```bash
  channel 3: open failed: connect failed: Connection refused
  ```
  it means the remote machine is not listening on `127.0.0.1:5000`.
- The issue is usually not the SSH tunnel itself, but the remote service not being bound or started.
- To confirm, run on the remote server:
  ```bash
  docker ps --format "table {{.Names}}\t{{.Ports}}"
  docker compose ps
  ss -lntp | grep 5000 || netstat -lntp 2>/dev/null | grep 5000
  curl -v http://127.0.0.1:5000/health
  ```
- If `curl` fails with connection refused, the service is not listening, and the SSH tunnel cannot work.

## Debugging and Development

### Testing Scripts Locally
To test automation scripts with visual feedback (non-headless mode):
1. Edit the script file and set `headless=False` in the main function
2. Run script individually: `python scripts/mcdo_standard_automation.py`
3. Watch browser automation in real-time for debugging

### Common Issues
- **Chrome binary not found**: Install Chrome on Debian using the installation commands above
- **Timeout errors**: Increase wait times in script or check internet connection  
- **Element not found**: McDonald's survey site may have changed - inspect HTML elements
- **Scheduler not running**: Check Flask app logs, scheduler runs in background thread
- **Permission issues**: Ensure Chrome is properly installed and accessible

### Log Analysis
- `✅` indicates successful survey completion
- `❌` indicates failure (followed by retry attempts)
- Duration >60s typically indicates successful completion
- Duration <20s usually indicates early failure (connection/site issues)