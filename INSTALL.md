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

Pull latest code, reinstall the package into the existing virtual environment, and restart the service:

```bash
sudo -u mealplan git -C /opt/mealplan/app pull --ff-only
sudo -u mealplan /opt/mealplan/venv/bin/pip install --upgrade /opt/mealplan/app
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

### 9. Publish as `https://mealplan.tcfix.me` (Route 53 CLI + Nginx TLS)

This keeps the app bound to localhost (`127.0.0.1:8765`) and exposes it securely through Nginx.

Prerequisites:

- Your VPS has a stable public IPv4 (preferably an Elastic IP).
- AWS CLI is installed and authenticated with credentials that can manage Route 53 records.
- Your `tcfix.me` hosted zone already exists in Route 53.

Install required packages:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx curl unzip
```

Install AWS CLI v2 (official AWS installer):

```bash
ARCH="$(dpkg --print-architecture)"
if [ "$ARCH" = "amd64" ]; then
  AWS_ZIP_URL="https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip"
elif [ "$ARCH" = "arm64" ]; then
  AWS_ZIP_URL="https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip"
else
  echo "Unsupported architecture: $ARCH" && exit 1
fi

curl -fsSL "$AWS_ZIP_URL" -o awscliv2.zip
unzip -q awscliv2.zip
sudo ./aws/install
aws --version
```

Set variables:

```bash
export ROOT_DOMAIN="tcfix.me"
export FQDN="mealplan.tcfix.me"
export SERVER_IPV4="<YOUR_PUBLIC_IPV4>"
```

Resolve the hosted zone ID via AWS CLI:

```bash
export HOSTED_ZONE_ID="$(aws route53 list-hosted-zones-by-name \
  --dns-name "$ROOT_DOMAIN" \
  --query 'HostedZones[0].Id' \
  --output text | sed 's|/hostedzone/||')"
echo "$HOSTED_ZONE_ID"
```

Create or update the Route 53 A record:

```bash
cat >/tmp/mealplan-route53-upsert.json <<EOF
{
  "Comment": "Point mealplan subdomain to VPS",
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "$FQDN",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [
          { "Value": "$SERVER_IPV4" }
        ]
      }
    }
  ]
}
EOF

aws route53 change-resource-record-sets \
  --hosted-zone-id "$HOSTED_ZONE_ID" \
  --change-batch file:///tmp/mealplan-route53-upsert.json
```

Verify DNS propagation:

```bash
dig +short "$FQDN"
```

Create Nginx reverse proxy config at `/etc/nginx/sites-available/mealplan.tcfix.me`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name mealplan.tcfix.me;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Enable the site and reload Nginx:

```bash
sudo ln -sf /etc/nginx/sites-available/mealplan.tcfix.me /etc/nginx/sites-enabled/mealplan.tcfix.me
sudo nginx -t
sudo systemctl reload nginx
```

Issue and install the TLS certificate (Let’s Encrypt):

```bash
sudo certbot --nginx \
  -d mealplan.tcfix.me \
  --redirect \
  --agree-tos \
  -m <YOUR_EMAIL> \
  --no-eff-email
```

Validate HTTPS:

```bash
curl -I https://mealplan.tcfix.me
curl https://mealplan.tcfix.me/api/v1/health
```

Validate certificate auto-renew:

```bash
sudo certbot renew --dry-run
```

If UFW is enabled, allow web traffic:

```bash
sudo ufw allow 'Nginx Full'
```

### Notes

- UI mode is started with `mealplan --ui`.
- For internet-facing access, keep the service on localhost and place Nginx/Caddy in front as a reverse proxy with TLS.
