# Amaterasu Esports Stats

A Telegram bot for real-time Dota 2 player statistics, built with Python and aiogram 3.
Integrated with OpenDota API to fetch player profiles, hero stats, and match history.

🤖 [@amaterasu_stats_bot](https://t.me/amaterasu_stats_bot) | 📢 [Amaterasu Esports](https://t.me/amaterasu_esports)

---

## Features

- Player profile lookup by Steam Account ID or nickname search
- Medal/rank display with custom Telegram Premium emoji per rank tier
- Win/loss ratio with color-coded winrate indicators (🔴🟠🟢🟣)
- Top-8 signature heroes sorted by total games played
- Last 8 matches with KDA, duration, and OpenDota match links
- Inline keyboard navigation between stats, heroes, and matches
- Private profile detection with graceful fallback messages
- Response caching (10 min TTL) to reduce API load
- Full HTML entity escaping for arbitrary Steam nicknames
- Deployed on Railway via Docker, runs 24/7

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Bot Framework | aiogram 3 (async, FSM, Router) |
| HTTP Client | aiohttp (async, ClientTimeout) |
| External API | OpenDota API (no key required) |
| Containerization | Docker (python:3.11-slim) |
| Hosting | Railway |
| Config | python-dotenv |

---

## Project Structure
amaterasu-stats/
├── handlers/
│   └── dota.py         # Command handlers, callback queries, inline keyboards
├── services/
│   └── opendota.py     # Async OpenDota API client (players, heroes, matches, search)
├── utils/
│   └── formatters.py   # Response formatters with Markdown/HTML, emoji rendering
├── config.py           # Constants, brand config, medal map, hero emoji map
├── main.py             # Bot entrypoint, Dispatcher setup, polling
├── Dockerfile          # python:3.11-slim, non-root build
├── requirements.txt
└── .env.example

## Architecture
User → Telegram → aiogram Router → Handler
↓
services/opendota.py  ←→  OpenDota API
↓
utils/formatters.py
↓
HTML response → Telegram
- **Handlers** receive updates and orchestrate async API calls via `asyncio.gather`
- **Services** are pure async functions with no framework dependency — independently testable
- **Formatters** handle all text rendering, HTML escaping, and emoji injection
- **Config** centralizes all magic strings, limits, and brand assets

---

## Commands

| Command | Description |
|---|---|
| `/stats <account_id>` | Player profile: rank, MMR estimate, total matches, winrate |
| `/heroes <account_id>` | Top-8 heroes by games played with winrate indicators |
| `/matches <account_id>` | Last 8 matches: result, hero, KDA, duration, match ID |
| `/search <nickname>` | Steam nickname search, returns account IDs |

---

## Local Setup

```bash
git clone https://github.com/Catharsjs/Amaterasu-Stats.git
cd Amaterasu-Stats

python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # Linux/macOS

pip install -r requirements.txt

cp .env.example .env
# Add your BOT_TOKEN to .env

python main.py
```

---

## Deployment

The bot is containerized with Docker and deployed on Railway.
Railway auto-deploys on every push to `main`.

Environment variables required:

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram Bot API token from @BotFather |

---

## API Reference

Uses [OpenDota API](https://docs.opendota.com/) — free tier, no API key required for basic endpoints.

| Endpoint | Usage |
|---|---|
| `GET /players/{id}` | Player profile, rank tier, MMR estimate |
| `GET /players/{id}/wl` | Win/loss totals |
| `GET /players/{id}/heroes` | Hero stats sorted by games played |
| `GET /players/{id}/recentMatches` | Last N matches |
| `GET /search?q={query}` | Player search by nickname |
| `GET /heroes` | Full hero list for ID→name mapping |

---

## Ukrainian

Telegram-бот для перегляду статистики Dota 2 у реальному часі.

**Команди:**
- `/stats <ID>` — профіль гравця: ранк, кількість матчів, вінрейт
- `/heroes <ID>` — топ-8 сигнатурних героїв за кількістю ігор
- `/matches <ID>` — останні 8 матчів з KDA і тривалістю
- `/search <нікнейм>` — пошук гравця за Steam нікнеймом

**Стек:** Python 3.11 · aiogram 3 · aiohttp · OpenDota API · Docker · Railway