# Meal Planner Bot

A Telegram bot that plans weekly dinners, maintains a meal library in Google Sheets, and generates shopping lists in Todoist. Uses Claude AI for meal generation, ingredient parsing, and recipe writing.

---

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Show help |
| `/plan` | Generate and confirm this week's dinner plan |
| `/week` | Show the current confirmed week plan |
| `/today` | Show today's planned meal with ingredients and recipe |
| `/add` | Add a new meal to the library |
| `/edit` | Edit an existing meal in the library |
| `/recipe` | View or generate a recipe for a meal |
| `/generate` | Generate meal ideas with Claude |
| `/meals` | List all meals (optionally filter: `/meals italian`) |
| `/shopping` | Show current Todoist shopping list |
| `/cancel` | Cancel current operation |

---

## Security — Restricting Access (implement when ready)

Currently the bot responds to anyone who messages it. When you want to lock it down to just you and Becca, here's the plan:

Every Telegram user has a unique numeric **user ID**. The bot can check the ID of whoever sent a message and silently ignore anyone not on an allowlist.

**Step 1** — Message [@userinfobot](https://t.me/userinfobot) on Telegram. It replies with your user ID. Have Becca do the same.

**Step 2** — Add to `.env`:
```env
ALLOWED_USER_IDS=123456789,987654321
```

**Step 3** — Add to `config.py`:
```python
allowed_user_ids: list[int] = Field(default=[], alias="ALLOWED_USER_IDS")

@field_validator("allowed_user_ids", mode="before")
@classmethod
def parse_ids(cls, v):
    if isinstance(v, str):
        return [int(x.strip()) for x in v.split(",") if x.strip()]
    return v
```

**Step 4** — Add a guard to `bot.py`:
```python
def _is_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    from app.config import settings
    if not settings.allowed_user_ids:
        return True  # No allowlist set — open to everyone
    return update.effective_user.id in settings.allowed_user_ids
```

**Step 5** — Add `if not _is_allowed(update, context): return` at the top of every command handler entry point.

If `ALLOWED_USER_IDS` is left empty, the bot stays open to everyone.

---

## What you need before starting

- A Google account
- A Todoist account
- An Anthropic account (claude.ai)
- Your Telegram bot token (from BotFather)
- A place to run the bot (covered at the end)

---

## Step 1 — Google Sheets setup

### 1a. Create the spreadsheet

1. Go to [sheets.google.com](https://sheets.google.com) and create a new blank spreadsheet.
2. Name it something like `Meal Planner`.
3. Create the following tabs (right-click → Rename, or click + to add):

**meals** tab — row 1 headers:
```
id    name    servings    cuisine    staple    ingredients
```

**weekly_plans** tab — row 1 headers:
```
week_start    mon    tue    wed    thu    fri    sat    sun    status    created_at    confirmed_at
```

**ingredient_mappings** tab — row 1 headers:
```
keyword    todoist_section    display_name
```

**recipes** tab — row 1 headers:
```
meal_id    instructions    user_notes    generated_at
```

### 1b. Get the Spreadsheet ID

From the URL:
```
https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit
```
The long string between `/d/` and `/edit` is your **Spreadsheet ID**.

### 1c. Create Google credentials (service account)

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Create a new project named `meal-planner`.
3. Enable **Google Sheets API** and **Google Drive API** (APIs & Services → Library).
4. Go to APIs & Services → Credentials → **+ Create Credentials** → **Service account**.
5. Name it `meal-planner-bot` → Create and continue → Done.
6. Click the service account → **Keys** tab → **Add Key** → **Create new key** → JSON.
7. Save the downloaded file as `credentials/google_service_account.json`.

### 1d. Share the spreadsheet with the service account

1. Open the JSON credentials file and copy the `client_email` value.
2. In Google Sheets, click **Share** and paste that email with **Editor** access.

---

## Step 2 — Todoist setup

### 2a. Create the Grocery List project

1. In Todoist, create a project named exactly `Grocery List`.
2. Add these 13 sections in order:
   - Produce, Meat, Seafood, Dairy & Eggs, Cheese, Bread & Bakery, Pasta & Grains, Canned Goods, Condiments & Sauces, Spices, Frozen, Drinks, Other

### 2b. Get your API token

Todoist → avatar → Settings → Integrations → Developer → Copy API token.

---

## Step 3 — Anthropic API key

[console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key.

---

## Step 4 — Fill in .env

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxYZ
TELEGRAM_WEBHOOK_URL=https://your-app.onrender.com/webhook

# For local/Docker deployment (file path):
GOOGLE_CREDENTIALS_PATH=./credentials/google_service_account.json
# For Render deployment (paste entire contents of the JSON file):
# GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}

GOOGLE_SPREADSHEET_ID=your_spreadsheet_id_here
TODOIST_API_TOKEN=your_todoist_token_here
ANTHROPIC_API_KEY=sk-ant-...

HOST=0.0.0.0
PORT=8000
```

---

## Step 5 — Add seed ingredient mappings

In the `ingredient_mappings` tab, add these rows (keyword → todoist_section → display_name):

| keyword | todoist_section | display_name |
|---------|----------------|--------------|
| chicken | Meat | Chicken |
| beef | Meat | Beef |
| pork | Meat | Pork |
| turkey | Meat | Turkey |
| sausage | Meat | Sausage |
| bacon | Meat | Bacon |
| salmon | Seafood | Salmon |
| shrimp | Seafood | Shrimp |
| tuna | Seafood | Tuna |
| milk | Dairy & Eggs | Milk |
| egg | Dairy & Eggs | Eggs |
| butter | Dairy & Eggs | Butter |
| cream | Dairy & Eggs | Cream |
| yogurt | Dairy & Eggs | Yogurt |
| cheese | Cheese | Cheese |
| parmesan | Cheese | Parmesan |
| mozzarella | Cheese | Mozzarella |
| feta | Cheese | Feta |
| bread | Bread & Bakery | Bread |
| tortilla | Bread & Bakery | Tortillas |
| pasta | Pasta & Grains | Pasta |
| rice | Pasta & Grains | Rice |
| noodle | Pasta & Grains | Noodles |
| quinoa | Pasta & Grains | Quinoa |
| chickpea | Canned Goods | Chickpeas |
| lentil | Canned Goods | Lentils |
| tomato sauce | Canned Goods | Tomato Sauce |
| coconut milk | Canned Goods | Coconut Milk |
| broth | Canned Goods | Broth |
| stock | Canned Goods | Stock |
| olive oil | Condiments & Sauces | Olive Oil |
| soy sauce | Condiments & Sauces | Soy Sauce |
| hot sauce | Condiments & Sauces | Hot Sauce |
| mustard | Condiments & Sauces | Mustard |
| vinegar | Condiments & Sauces | Vinegar |
| cumin | Spices | Cumin |
| paprika | Spices | Paprika |
| oregano | Spices | Oregano |
| thyme | Spices | Thyme |
| cinnamon | Spices | Cinnamon |
| chili powder | Spices | Chili Powder |
| garlic powder | Spices | Garlic Powder |
| onion | Produce | Onion |
| garlic | Produce | Garlic |
| tomato | Produce | Tomatoes |
| pepper | Produce | Bell Pepper |
| lemon | Produce | Lemon |
| lime | Produce | Lime |
| spinach | Produce | Spinach |
| kale | Produce | Kale |
| broccoli | Produce | Broccoli |
| carrot | Produce | Carrots |
| potato | Produce | Potatoes |
| avocado | Produce | Avocado |
| cilantro | Produce | Cilantro |

---

## Step 6 — Test locally

### Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run in polling mode (no webhook needed)

Create `run_polling.py` in the project root:

```python
from app.config import settings
from app.sheets import SheetsClient
from app.todoist_client import TodoistClient
from app.claude_client import ClaudeClient
from app.meal_planner import MealPlanner
from app.bot import register_handlers
from telegram.ext import Application

app = Application.builder().token(settings.telegram_bot_token).build()
sheets = SheetsClient(
    spreadsheet_id=settings.google_spreadsheet_id,
    credentials_path=settings.google_credentials_path,
)
todoist = TodoistClient(settings.todoist_api_token)
claude = ClaudeClient(settings.anthropic_api_key)
app.bot_data["planner"] = MealPlanner(sheets, todoist, claude)
register_handlers(app)
app.run_polling()
```

```bash
python run_polling.py
```

**Test in this order:**
1. `/start` — bot replies with the command list
2. `/add` — add 8 or more meals (the planner needs 7 to fill a week)
3. `/meals` — verify they appear grouped by cuisine
4. `/plan` — generates a draft week; try Swap and Replace buttons, then Confirm
5. `/week` — verify the confirmed plan displays
6. `/today` — verify today's meal shows with ingredients
7. `/recipe` — generate and save a recipe for a meal
8. `/shopping` — check Todoist items were added

---

## Step 7 — Deploy

### Option A: Render (current setup — Hobby plan, $7/month, 24/7)

1. Push to GitHub.
2. In Render, create a **Web Service** inside your existing project.
3. Connect the GitHub repo. Runtime: **Docker**.
4. Add environment variables in the Render dashboard. For Google credentials, set `GOOGLE_CREDENTIALS_JSON` to the full contents of `credentials/google_service_account.json` (paste the entire JSON object).
5. Set `TELEGRAM_WEBHOOK_URL` to `https://YOUR-APP-NAME.onrender.com/webhook`.
6. Deploy. The bot registers its webhook automatically on startup.

Verify: `https://YOUR-APP-NAME.onrender.com/health` should return `{"status":"ok"}`.

### Option B: Oracle Cloud Free Tier (in progress — free forever once provisioned)

Oracle Free Tier includes an **Ampere A1 Flex** instance (up to 4 OCPUs, 24 GB RAM) at no cost. The catch is that capacity is often unavailable in less popular regions.

**Account notes:**
- Home region is **Italy Northwest (Milan)** (`eu-milan-1`) — locked at signup
- Milan only offers E5.Flex and E4.Flex shapes, neither of which are free tier
- Free tier shapes (A1 Flex, E2.1.Micro) require subscribing to additional regions, which is blocked on the free account tier
- Upgrading to Pay-as-you-go unlocks additional regions and removes capacity restrictions; free resources remain free

**When you do get an instance, the setup is:**

1. Create a VCN with internet connectivity (Networking → Virtual Cloud Networks → Start VCN Wizard → "Create VCN with Internet Connectivity").
2. Open ports 80 and 443 in the VCN Security List (ingress, TCP, source 0.0.0.0/0).
3. Open ports on the VM itself:
   ```bash
   sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```
4. Get a free domain from [duckdns.org](https://www.duckdns.org) pointing to the instance's public IP.
5. Install Docker and Caddy:
   ```bash
   sudo apt update && sudo apt install -y docker.io netfilter-persistent
   sudo usermod -aG docker ubuntu
   # Install Caddy (see caddy.run for current apt instructions)
   ```
6. Configure Caddy (`/etc/caddy/Caddyfile`):
   ```
   yourdomain.duckdns.org {
       reverse_proxy localhost:8000
   }
   ```
7. Copy project files to the server and run:
   ```bash
   docker build -t meal-planner .
   docker run -d --restart unless-stopped \
     -p 8000:8000 \
     --env-file .env \
     -v $(pwd)/credentials:/app/credentials \
     --name meal-planner \
     meal-planner
   ```
8. Set `TELEGRAM_WEBHOOK_URL=https://yourdomain.duckdns.org/webhook` in `.env`.
