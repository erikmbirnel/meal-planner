# Meal Planner — Setup Checklist

This project is cloned and ready to configure. Everything below is needed before it can run.

---

## Credentials needed

### 1. Telegram bot token
- Create a new bot via [@BotFather](https://t.me/BotFather) on Telegram — `/newbot`
- Add to `.env`: `TELEGRAM_BOT_TOKEN=<token>`
- The chore_master bot token **cannot** be reused (one token per bot)

### 2. Anthropic API key
- https://console.anthropic.com → API Keys → Create Key
- Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`

### 3. Todoist API token
- Todoist → avatar → Settings → Integrations → Developer → Copy API token
- Add to `.env`: `TODOIST_API_TOKEN=<token>`
- Also create a Todoist project named exactly **"Grocery List"** with 13 sections (see README Step 2)

### 4. Google Sheets
- Create a new spreadsheet with 4 tabs: `meals`, `weekly_plans`, `ingredient_mappings`, `recipes`
  (headers documented in README Step 1)
- Copy the Spreadsheet ID from the URL
- Add to `.env`: `GOOGLE_SPREADSHEET_ID=<id>`

### 5. Google credentials
- The chore_master service account **can be reused** — it already has Sheets/Drive API access
- Copy `/home/erik/chore_master/credentials/google_service_account.json` to
  `credentials/google_service_account.json` in this project
- Share the new spreadsheet with the service account email (Editor access)
- Add to `.env`: `GOOGLE_CREDENTIALS_PATH=./credentials/google_service_account.json`

---

## Webhook routing question

The chore_master app already uses `constantine.bericosolutions.com` (port 8001).
This app would need either:
- **Option A**: A different subdomain or path on the same domain (needs nginx/Caddy routing rule)
- **Option B**: A different port (e.g., 8002) exposed in docker-compose and a new webhook URL
- **Option C**: Deploy separately on Render (see README Step 7A, $7/month)

Decide which option before setting:
```
TELEGRAM_WEBHOOK_URL=https://<your-host>/webhook
HOST=0.0.0.0
PORT=8000
```

---

## .env template

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_URL=

GOOGLE_CREDENTIALS_PATH=./credentials/google_service_account.json
GOOGLE_SPREADSHEET_ID=

TODOIST_API_TOKEN=
ANTHROPIC_API_KEY=

HOST=0.0.0.0
PORT=8000
```

---

## Quick start (once credentials are filled in)

```bash
cd /home/erik/meal_planner
cp /home/erik/chore_master/credentials/google_service_account.json credentials/
# fill in .env
docker build -t meal-planner .
docker run -d --restart unless-stopped \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/credentials:/app/credentials \
  --name meal-planner \
  meal-planner
```

Then add 8+ meals via `/add` before trying `/plan`.
