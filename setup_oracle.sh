#!/bin/bash
# Oracle Cloud Free Tier - Game Update Bot Setup
# Run this on a fresh Ubuntu 22.04 ARM instance

set -e

echo "=== Installing system dependencies ==="
sudo apt update -y
sudo apt install -y python3 python3-pip python3-venv git

echo "=== Cloning repo ==="
cd /opt
sudo git clone https://github.com/coderzero135-dev/game-update-bot.git
sudo chown -R $USER:$USER /opt/game-update-bot
cd /opt/game-update-bot

echo "=== Setting up Python ==="
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "=== Creating .env file ==="
echo "Paste your Discord bot token:"
read -s TOKEN
echo "DISCORD_TOKEN=$TOKEN" > .env

echo "=== Creating systemd service ==="
sudo tee /etc/systemd/system/gamebot.service > /dev/null << EOF
[Unit]
Description=Game Update Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/opt/game-update-bot
ExecStart=/opt/game-update-bot/venv/bin/python /opt/game-update-bot/bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gamebot
sudo systemctl start gamebot

echo ""
echo "=== Done ==="
echo "Check status: sudo systemctl status gamebot"
echo "View logs:   sudo journalctl -u gamebot -f"
echo "Restart:     sudo systemctl restart gamebot"
echo ""
echo "The bot is now running 24/7 with auto-restart."
