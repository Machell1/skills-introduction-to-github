# Deal Alert Bot

Amazon price drop monitor that sends deal alerts to your Telegram channel with your affiliate links. Every purchase through your link earns you 4-10% commission.

## Quick Setup (PyCharm)

### 1. Install Dependencies
```bash
cd bot
pip install -r requirements.txt
```

### 2. Create a Telegram Bot
1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token you receive

### 3. Create a Telegram Channel
1. Create a new Telegram channel (e.g., "Daily Deals & Drops")
2. Add your bot as an **administrator** of the channel
3. Get the channel ID:
   - Public channel: use `@yourchannel` format
   - Private channel: forward a message from the channel to [@userinfobot](https://t.me/userinfobot)

### 4. Get an Amazon Affiliate Tag
1. Sign up at [Amazon Associates](https://affiliate-program.amazon.com)
2. Your tag will look like `yourtag-20`

### 5. Configure the Bot
```bash
cp .env.example .env
```
Edit `.env` with your credentials:
```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHANNEL_ID=@yourdealchannel
AMAZON_AFFILIATE_TAG=yourtag-20
CHECK_INTERVAL_MINUTES=60
MIN_DROP_PERCENT=15
MIN_DROP_DOLLARS=5
```

### 6. Add Products to Track
```bash
# Add a single product
python main.py add https://www.amazon.com/dp/B09V3KXJPB

# Add from a file (one URL/ASIN per line)
python main.py add-bulk sample_watchlist.txt
```

### 7. Run the Bot
```bash
python main.py run
```
The bot will check prices every hour (configurable) and send Telegram alerts when prices drop.

## Commands

| Command | Description |
|---|---|
| `python main.py run` | Start continuous monitoring |
| `python main.py check` | Check all prices once |
| `python main.py add <url>` | Add a product to track |
| `python main.py add-bulk <file>` | Add products from a file |
| `python main.py status` | Show all tracked products |
| `python main.py remove <asin>` | Stop tracking a product |

## Running in PyCharm

1. Open the `bot` folder as a project in PyCharm
2. Set up a Python interpreter and install requirements
3. Create a Run Configuration:
   - Script: `main.py`
   - Parameters: `run`
   - Working directory: `bot/`
4. Click Run

## How to Maximize Revenue

1. **Track 50-100+ popular products** across electronics, home, and tech
2. **Focus on high-ticket items** ($100+) for bigger commissions
3. **Promote your Telegram channel** on social media, Reddit deal communities
4. **Lower thresholds** for popular items (even 10% drops on popular items get clicks)
5. **Check during deal events** (Prime Day, Black Friday) - set interval to 15 minutes

## Revenue Potential

| Channel Subscribers | Monthly Clicks | Estimated Commission |
|---|---|---|
| 100 | 200 | $50-150 |
| 1,000 | 2,000 | $500-1,500 |
| 10,000 | 20,000 | $5,000-15,000 |

Amazon Associates pays 4-10% depending on category. A single person buying a $1,000 TV through your link = $40-100 commission.
