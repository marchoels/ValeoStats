# ValeoBot - OnlyMonster Telegram Statistics Bot

A professional Telegram bot for tracking OnlyFans revenue through the OnlyMonster API.

## Features

✅ **Revenue Tracking**
- Track daily revenue (OnlyFans day: 1 AM - 1 AM Berlin time)
- View today's and yesterday's earnings
- Multi-platform support (OnlyFans, Fansly)

✅ **Automated Reports**
- Daily revenue reports sent automatically at 1:00 AM Berlin time
- Detailed transaction counts and currency information

✅ **Multi-Chat Support**
- Link different Telegram chats to different models
- Manage multiple agencies/creators from one bot

✅ **Professional Architecture**
- Clean, maintainable code structure
- Proper error handling and logging
- Type hints and documentation

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Telegram Bot Token (from @BotFather)
- OnlyMonster API Token

### Installation

1. **Clone or download the bot files**

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

The `.env` file is already configured with your tokens:
```env
TG_BOT_TOKEN=8004971439:AAHWEAkyNlGciqM8rd0r9TmIg8_UeVhys9w
OM_API_TOKEN=om_token_240f8b884b067f993ecf6486f8cd4ed8f8bdb1f02039e5b20ce1c2f6281b9f3f
OM_BASE_URL=https://omapi.onlymonster.ai
```

4. **Run the bot**
```bash
python bot.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and help |
| `/help` | Show help message |
| `/link <platform> <account_id>` | Link chat to a model |
| `/unlink` | Remove model link from chat |
| `/today` | Show today's revenue |
| `/yesterday` | Show yesterday's revenue |
| `/stats` | Show current statistics |

### Example Usage

```
/link onlyfans 454315739
```
This links the current Telegram chat to the OnlyFans account with ID 454315739.

After linking, you can use:
```
/today
```
To see today's earnings.

## OnlyFans Day Calculation

The bot uses OnlyFans' revenue day, which runs from **1:00 AM to 12:59:59 AM** the next day in **Berlin timezone**.

Example:
- Day starts: Dec 27, 2025 01:00:00 (Berlin)
- Day ends: Dec 28, 2025 00:59:59 (Berlin)

## Deployment Options

### Option 1: VPS/Cloud Server (Recommended)

Deploy on any VPS provider:

**DigitalOcean, Linode, AWS, etc.**
```bash
# SSH into your server
ssh user@your-server-ip

# Clone your code
git clone <your-repo> valeobot
cd valeobot

# Install dependencies
pip install -r requirements.txt

# Run with screen or tmux
screen -S valeobot
python bot.py
# Press Ctrl+A then D to detach
```

**Using systemd (persistent service)**
Create `/etc/systemd/system/valeobot.service`:
```ini
[Unit]
Description=ValeoBot Telegram Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/valeobot
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable valeobot
sudo systemctl start valeobot
sudo systemctl status valeobot
```

### Option 2: Railway.app (Easy, Free Tier Available)

1. Create `railway.json`:
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python bot.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

2. Push to GitHub and connect to Railway
3. Set environment variables in Railway dashboard

### Option 3: Render.com (Free Tier)

1. Create `render.yaml`:
```yaml
services:
  - type: web
    name: valeobot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python bot.py
    envVars:
      - key: TG_BOT_TOKEN
        sync: false
      - key: OM_API_TOKEN
        sync: false
      - key: OM_BASE_URL
        value: https://omapi.onlymonster.ai
```

2. Connect GitHub repo to Render
3. Set environment variables

### Option 4: Heroku

1. Create `Procfile`:
```
worker: python bot.py
```

2. Deploy:
```bash
heroku create your-valeobot
heroku config:set TG_BOT_TOKEN=your_token
heroku config:set OM_API_TOKEN=your_token
git push heroku main
heroku ps:scale worker=1
```

### Option 5: Docker

1. Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

2. Build and run:
```bash
docker build -t valeobot .
docker run -d --name valeobot \
  -e TG_BOT_TOKEN=your_token \
  -e OM_API_TOKEN=your_token \
  valeobot
```

## File Structure

```
valeobot/
├── bot.py                 # Main bot application
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (keep secret!)
├── chat_mapping.json     # Chat-to-model mappings (auto-generated)
└── README.md             # This file
```

## Storage

The bot stores chat-to-model mappings in `chat_mapping.json`. This file is automatically created and updated when you use the `/link` command.

Example `chat_mapping.json`:
```json
{
  "-4871991173": {
    "platform": "onlyfans",
    "platform_account_id": "454315739"
  }
}
```

**Important:** Back up this file if you have many linked chats!

## Architecture Highlights

### Clean Code Structure
- **Data Models**: Using Python dataclasses for type safety
- **Separation of Concerns**: API client, storage, formatting are separate classes
- **Error Handling**: Comprehensive try-catch blocks with logging
- **Type Hints**: Full type annotations for better IDE support

### OnlyMonster API Integration
- Custom session with persistent headers
- Proper timezone handling (UTC ↔ Berlin)
- Transaction aggregation and currency handling
- Configurable request limits

### Telegram Bot Features
- Command handlers with argument validation
- Markdown formatting for beautiful messages
- Scheduled jobs with timezone awareness
- Error recovery and logging

## Security Notes

⚠️ **Keep your tokens secret!**
- Never commit `.env` to public repositories
- Use environment variables in production
- Rotate tokens if exposed

## Troubleshooting

### Bot doesn't respond
- Check if bot is running: `ps aux | grep bot.py`
- Check logs for errors
- Verify Telegram token is correct

### API errors
- Verify OnlyMonster API token is valid
- Check if account ID exists and is accessible
- Review API rate limits

### Daily reports not sending
- Ensure bot is running continuously
- Check server timezone settings
- Verify chat_mapping.json exists and is valid

## Support

For OnlyMonster API questions:
- Documentation: https://docs.onlymonster.ai/
- Support: Contact OnlyMonster support team

## License

Private use only.

---

**Built with ❤️ for efficient agency management**
