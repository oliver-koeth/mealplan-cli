# Installation Guide

## Linux VPS (systemd Service)

Use this guide to run `mealplan-cli` UI mode as a persistent background service.

### 1. Install system dependencies

Debian/Ubuntu example:

```bash
sudo apt update
sudo apt install -y python3 python3-venv git
```

### 2. Create a dedicated service user and directories

```bash
sudo useradd --system --create-home --home /opt/mealplan --shell /usr/sbin/nologin mealplan || true
sudo mkdir -p /opt/mealplan/app
sudo chown -R mealplan:mealplan /opt/mealplan
```

### 3. Install the application in a virtual environment

```bash
sudo -u mealplan git clone <YOUR_REPOSITORY_URL> /opt/mealplan/app
sudo -u mealplan python3 -m venv /opt/mealplan/venv
sudo -u mealplan /opt/mealplan/venv/bin/pip install --upgrade pip
sudo -u mealplan /opt/mealplan/venv/bin/pip install /opt/mealplan/app
```

### 4. Configure runtime environment variables

Create `/etc/mealplan.env`:

```bash
sudo tee /etc/mealplan.env >/dev/null <<'EOF'
MEALPLAN_CALENDAR_STORE_PATH=/var/lib/mealplan/calendar.json
MEALPLAN_FOOD_LOG_STORE_PATH=/var/lib/mealplan/food-log.json
MEALPLAN_UI_PORT_START=8765
MEALPLAN_UI_PORT_END=8765
EOF
```

Create storage directory:

```bash
sudo mkdir -p /var/lib/mealplan
sudo chown -R mealplan:mealplan /var/lib/mealplan
sudo chmod 640 /etc/mealplan.env
```

### 5. Create the systemd unit

Create `/etc/systemd/system/mealplan.service`:

```ini
[Unit]
Description=Mealplan CLI UI service
After=network.target

[Service]
Type=simple
User=mealplan
Group=mealplan
WorkingDirectory=/opt/mealplan/app
EnvironmentFile=/etc/mealplan.env
ExecStart=/opt/mealplan/venv/bin/mealplan --ui
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 6. Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mealplan
sudo systemctl status mealplan
```

Follow logs:

```bash
sudo journalctl -u mealplan -f
```

### 7. Verify health endpoint

By default, the UI binds to `127.0.0.1` and uses port `8765`:

```bash
curl http://127.0.0.1:8765/api/v1/health
```

### 8. Update an existing installation

Run updates as root with `sudo`, but execute Git/pip steps as the `mealplan` service user so file ownership stays correct.

Pull latest code:

```bash
sudo -u mealplan git -C /opt/mealplan/app pull --ff-only
```

Reinstall the package into the existing virtual environment:

```bash
sudo -u mealplan /opt/mealplan/venv/bin/pip install --upgrade /opt/mealplan/app
```

Restart the service:

```bash
sudo systemctl restart mealplan
```

Verify startup and health:

```bash
sudo systemctl status mealplan --no-pager
curl http://127.0.0.1:8765/api/v1/health
```

If startup fails, inspect logs:

```bash
sudo journalctl -u mealplan -n 200 --no-pager
```

### Notes

- UI mode is started with `mealplan --ui`.
- For internet-facing access, keep the service on localhost and place Nginx/Caddy in front as a reverse proxy with TLS.
