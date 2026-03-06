# Deal Alert Bot

Multi-site price drop monitor that sends deal alerts to your Telegram channel with affiliate links. Scans **Amazon, Best Buy, Walmart, Target, eBay** for price drops and **Slickdeals + DealNews** for hot curated deals.

## Supported Sites

| Site | Type | Affiliate Program |
|---|---|---|
| **Amazon** | Product tracking + deals | [Amazon Associates](https://affiliate-program.amazon.com) |
| **Best Buy** | Product tracking + deals | [Impact Radius](https://impact.com) |
| **Walmart** | Product tracking + deals | [Impact Radius](https://impact.com) |
| **Target** | Product tracking + deals | [Impact Radius](https://impact.com) |
| **eBay** | Product tracking + deals | [eBay Partner Network](https://partnernetwork.ebay.com) |
| **Slickdeals** | Deal aggregator | Uses store affiliate links |
| **DealNews** | Deal aggregator | Uses store affiliate links |

## Quick Setup (PyCharm)

### 1. Install Dependencies
```bash
cd bot
pip install -r requirements.txt
```

### 2. Create a Telegram Bot & Channel
1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`
2. Copy the bot token
3. Create a Telegram channel (e.g., "Daily Deals & Drops")
4. Add your bot as a channel **administrator**

### 3. Sign Up for Affiliate Programs
- **Amazon**: [affiliate-program.amazon.com](https://affiliate-program.amazon.com) → tag like `yourtag-20`
- **Walmart/Best Buy/Target**: [impact.com](https://impact.com) → search for each store's program
- **eBay**: [partnernetwork.ebay.com](https://partnernetwork.ebay.com) → get your campaign ID

### 4. Configure
```bash
cp .env.example .env
```
Edit `.env` with your credentials.

### 5. Add Products to Track
```bash
# Amazon
python main.py add https://www.amazon.com/dp/B09V3KXJPB

# Best Buy
python main.py add https://www.bestbuy.com/site/some-product/1234567.p

# Walmart
python main.py add https://www.walmart.com/ip/some-product/123456789

# Target
python main.py add https://www.target.com/p/some-product/-/A-12345678

# eBay
python main.py add https://www.ebay.com/itm/123456789

# Bulk add from file (one URL per line, any site)
python main.py add-bulk watchlist.txt
```

### 6. Run
```bash
python main.py run
```

## Telegram Bot Commands

Control the bot directly from Telegram (the primary way to use it):

| Command | Description |
|---|---|
| `/start`, `/help` | Show help and tracking stats |
| `/add <url>` | Track a product from any supported site |
| `/remove <id>` | Stop tracking a product |
| `/status` | Show all tracked products by site |
| `/check` | Check all prices immediately |
| `/deals` | Scan Slickdeals & DealNews now |
| `/sites` | List supported sites |

## CLI Commands (Local Development)

| Command | Description |
|---|---|
| `python main.py run` | Start continuous monitoring (prices + deal scans) |
| `python main.py check` | Check all tracked product prices once |
| `python main.py scan-deals` | Scan Slickdeals & DealNews for hot deals |
| `python main.py scan-all` | Scan ALL sites (retailers + aggregators) |
| `python main.py add <url>` | Add a product from any supported site |
| `python main.py add-bulk <file>` | Add products from a file |
| `python main.py status` | Show tracked products grouped by site |
| `python main.py remove <id>` | Stop tracking a product |
| `python main.py sites` | List all supported sites |

## How It Works

### Product Tracking (Amazon, Best Buy, Walmart, Target, eBay)
1. You add product URLs from any supported store
2. Bot checks prices on a schedule (default: every 60 minutes)
3. When a price drops 15%+ and $5+ (configurable), it sends a Telegram alert
4. The alert contains your **affiliate link** — you earn commission on purchases

### Deal Scanning (Slickdeals, DealNews)
1. Bot scrapes deal aggregator front pages every 2 hours
2. New deals are sent to your Telegram channel automatically
3. Covers deals from hundreds of stores (aggregators curate the best deals)

## Deploy to Railway (24/7 Hosting)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) and create a new project
3. Connect your GitHub repo, set the root directory to `bot/`
4. Add environment variables in Railway's dashboard:
   - `TELEGRAM_BOT_TOKEN` — your bot token
   - `TELEGRAM_CHANNEL_ID` — your channel ID
   - `ADMIN_USER_IDS` — your Telegram user ID (get it from @userinfobot)
   - `DB_PATH` — `/data/deals.db`
   - Plus any affiliate tags you want
5. Add a **Volume** in Railway, mount it at `/data`
6. Deploy — the bot starts automatically and runs 24/7

The bot uses a `worker` process (not a web server), so it stays running continuously.

## Running Locally

### PyCharm
1. Open the `bot` folder as a project
2. Set up a Python interpreter and install requirements
3. Create a Run Configuration:
   - Script: `telegram_bot.py`
   - Working directory: `bot/`
4. Click Run

### Command Line
```bash
cd bot
python telegram_bot.py
```

The CLI entry point (`main.py`) is also still available for local debugging.

## Revenue Strategy

### Commission Rates by Store
| Store | Commission Rate | Cookie Duration |
|---|---|---|
| Amazon | 1-10% (varies by category) | 24 hours |
| Best Buy | 1-7% | 1 day |
| Walmart | 1-4% | 3 days |
| Target | 1-8% | 7 days |
| eBay | 1-6% | 24 hours |

### How to Maximize Revenue
1. **Track 50-100+ products** across all 5 stores
2. **Focus on high-ticket items** ($100+) for bigger commissions
3. **Promote your Telegram channel** on Reddit, Twitter, deal forums
4. **Run during deal events** (Prime Day, Black Friday) — set interval to 15 mins
5. **Use scan-deals** regularly — aggregator deals get the most engagement

### Revenue Potential
| Channel Subscribers | Monthly Clicks | Estimated Commission |
|---|---|---|
| 100 | 200 | $50-200 |
| 1,000 | 2,000 | $500-2,000 |
| 10,000 | 20,000 | $5,000-20,000 |

## File Structure

```
bot/
├── telegram_bot.py      # Telegram bot entry point (primary)
├── main.py              # CLI entry point and scheduler (local dev)
├── scraper.py           # Multi-site scraper router
├── tracker.py           # Deal detection and product management
├── notifier.py          # Telegram alert formatting and sending
├── database.py          # SQLite storage for prices and deals
├── config.py            # Configuration loader
├── requirements.txt     # Python dependencies
├── Dockerfile           # Docker container config (Railway)
├── Procfile             # Process type for Railway
├── .env.example         # Config template
├── sample_watchlist.txt # Example product list
└── scrapers/
    ├── __init__.py      # Scraper registry and auto-detection
    ├── base.py          # Base scraper class
    ├── amazon.py        # Amazon scraper
    ├── bestbuy.py       # Best Buy scraper
    ├── walmart.py       # Walmart scraper
    ├── target.py        # Target scraper
    ├── ebay.py          # eBay scraper
    ├── slickdeals.py    # Slickdeals aggregator
    └── dealnews.py      # DealNews aggregator
```
