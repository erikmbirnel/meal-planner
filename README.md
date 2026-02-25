# Meal Planner Bot

A Telegram bot that plans weekly dinners, maintains a meal library in Google Sheets, and generates shopping lists in Todoist. Uses Claude AI for meal generation.

---

## Security — Restricting Access (implement when ready)

Currently the bot responds to anyone who messages it. When you want to lock it down to just you and Becca, here's the plan:

### How it works

Every Telegram user has a unique numeric **user ID**. The bot can check the ID of whoever sent a message and silently ignore anyone not on an allowlist.

### Step 1 — Find your Telegram user IDs

Message [@userinfobot](https://t.me/userinfobot) on Telegram. It replies with your user ID (a number like `123456789`). Have Becca do the same.

### Step 2 — Add IDs to .env

```env
ALLOWED_USER_IDS=123456789,987654321
```

### Step 3 — Add the setting to config.py

```python
allowed_user_ids: list[int] = Field(default=[], alias="ALLOWED_USER_IDS")

@field_validator("allowed_user_ids", mode="before")
@classmethod
def parse_ids(cls, v):
    if isinstance(v, str):
        return [int(x.strip()) for x in v.split(",") if x.strip()]
    return v
```

### Step 4 — Add a guard function to bot.py

```python
def _is_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    from app.config import settings
    if not settings.allowed_user_ids:
        return True  # No allowlist set — open to everyone
    return update.effective_user.id in settings.allowed_user_ids
```

### Step 5 — Add the check to every handler entry point

At the top of `start`, `plan`, `add_meal_start`, `generate_start`, `list_meals`, and `shopping`:

```python
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update, context):
        return  # Silently ignore
    ...
```

### Notes

- Silently ignoring (returning without reply) is better than sending an error — it doesn't confirm the bot exists to strangers.
- If `ALLOWED_USER_IDS` is left empty in `.env`, the bot stays open to everyone (current behaviour).
- No library changes needed — this is pure application logic.

---

## What you need before starting

- A Google account
- A Todoist account
- An Anthropic account (claude.ai)
- Your Telegram bot token (you already have this from BotFather)
- A place to run the bot (covered at the end)

---

## Step 1 — Google Sheets setup

You need two things from Google: a **spreadsheet** (the database) and **credentials** (a key that lets the bot read/write it).

### 1a. Create the spreadsheet

1. Go to [sheets.google.com](https://sheets.google.com) and create a new blank spreadsheet.
2. Name it something like `Meal Planner`.
3. At the bottom of the screen you'll see a tab called `Sheet1`. Right-click it → **Rename** → type `meals`.
4. Click the **+** button at the bottom left to add a second tab. Rename it `weekly_plans`.
5. Add a third tab. Rename it `ingredient_mappings`.

Now add column headers to each tab. Click cell A1 in each tab and type these exactly (one word per cell, moving right with Tab):

**meals tab** — row 1:
```
id    name    servings    cuisine    staple    ingredients
```

**weekly_plans tab** — row 1:
```
week_start    mon    tue    wed    thu    fri    sat    sun    status    created_at    confirmed_at
```

**ingredient_mappings tab** — row 1:
```
keyword    todoist_section    display_name
```

### 1b. Get the Spreadsheet ID

Look at the URL in your browser. It looks like:
```
https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit
```

The long string of letters and numbers between `/d/` and `/edit` is your **Spreadsheet ID**. Copy it — you'll need it for `.env`.

### 1c. Create Google credentials (service account)

This creates a "robot" Google account that the bot uses to access the spreadsheet.

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. At the top, click the project dropdown → **New Project**. Name it `meal-planner` and click **Create**.
3. Make sure your new project is selected in the dropdown.
4. In the left sidebar, go to **APIs & Services** → **Library**.
5. Search for `Google Sheets API`. Click it → click **Enable**.
6. Search for `Google Drive API`. Click it → click **Enable**.
7. In the left sidebar, go to **APIs & Services** → **Credentials**.
8. Click **+ Create Credentials** at the top → choose **Service account**.
9. Fill in **Service account name**: `meal-planner-bot`. Click **Create and continue**.
10. Skip the optional steps and click **Done**.
11. You'll now see your service account in the list. Click on it.
12. Go to the **Keys** tab → **Add Key** → **Create new key** → choose **JSON** → click **Create**.
13. A `.json` file will download automatically. This is your credentials file.

**Move that file** into the `credentials/` folder inside this project and rename it to `google_service_account.json`.

The path in `.env` stays as the default: `./credentials/google_service_account.json`

### 1d. Share the spreadsheet with the service account

1. Open the JSON credentials file in any text editor.
2. Find the line that says `"client_email"` — it will look like `meal-planner-bot@meal-planner-xxxxx.iam.gserviceaccount.com`.
3. Copy that email address.
4. Go back to your Google Sheet. Click the **Share** button (top right).
5. Paste that email address in the "Add people" box. Make sure it has **Editor** access. Click **Send**.

The bot can now read and write your spreadsheet.

---

## Step 2 — Todoist setup

### 2a. Create the Italian Store project

1. In Todoist, click **+** next to **Projects** in the sidebar → name it exactly `Italian Store`.
2. Open the project. Click **Add section** and create all 13 sections in this exact order:
   - Produce
   - Meat
   - Seafood
   - Dairy & Eggs
   - Cheese
   - Bread & Bakery
   - Pasta & Grains
   - Canned Goods
   - Condiments & Sauces
   - Spices
   - Frozen
   - Drinks
   - Other

   (The names must match exactly — the bot routes ingredients to sections by name.)

3. Optional: share the project with your partner. Open the project → click the **...** menu → **Share project**.

### 2b. Get your API token

1. Go to [todoist.com](https://todoist.com) in a browser (the token is not accessible from the mobile app).
2. Click your **avatar / profile picture** in the top-left corner → **Settings**.
3. Click the **Integrations** tab.
4. Inside Integrations, click the **Developer** sub-tab at the top.
5. Click **Copy API token**.

That token goes in `.env` as `TODOIST_API_TOKEN`.

---

## Step 3 — Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com).
2. Sign in, then go to **API Keys** in the left sidebar.
3. Click **Create Key**. Give it a name like `meal-planner`. Copy the key immediately — it won't be shown again.

That goes in `.env` as `ANTHROPIC_API_KEY`.

---

## Step 4 — Fill in .env

Copy the example file and fill it in:

```bash
cp .env.example .env
```

Open `.env` in a text editor. Fill in each value:

```env
# You already have this from BotFather
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxYZ

# Leave this alone for now — you'll set it when you deploy
TELEGRAM_WEBHOOK_URL=https://your-vps-domain.com/webhook

# Leave as-is (the file you saved to credentials/)
GOOGLE_CREDENTIALS_PATH=./credentials/google_service_account.json

# The long ID from the spreadsheet URL (Step 1b)
GOOGLE_SPREADSHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms

# From Todoist Settings → Integrations (Step 2b)
TODOIST_API_TOKEN=your_todoist_token_here

# From console.anthropic.com (Step 3)
ANTHROPIC_API_KEY=sk-ant-...

# Leave these as-is
HOST=0.0.0.0
PORT=8000
```

---

## Step 5 — Add seed ingredient mappings

The bot uses the `ingredient_mappings` tab to know which Todoist section to put each ingredient in. Without entries here, everything lands in "Other".

Go to your `ingredient_mappings` tab and add these rows (keyword in column A, section in column B, display name in column C):

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

You can add more any time. The bot checks if a keyword appears anywhere in the ingredient name, so `chicken` will match `chicken breast`, `chicken thighs`, etc.

---

## Step 6 — Test locally first

Before deploying to a server, test on your own computer. This avoids needing a domain or HTTPS.

### Install Python dependencies

```bash
cd meal_planner
python3 -m venv venv
source venv/bin/activate      # on Mac/Linux
pip install -r requirements.txt
```

### Run in polling mode (no webhook needed)

Create a file called `run_polling.py` in the project root:

```python
from app.config import settings
from app.sheets import SheetsClient
from app.todoist_client import TodoistClient
from app.claude_client import ClaudeClient
from app.meal_planner import MealPlanner
from app.bot import register_handlers
from telegram.ext import Application

app = Application.builder().token(settings.telegram_bot_token).build()
sheets = SheetsClient(settings.google_credentials_path, settings.google_spreadsheet_id)
todoist = TodoistClient(settings.todoist_api_token)
claude = ClaudeClient(settings.anthropic_api_key)
app.bot_data["planner"] = MealPlanner(sheets, todoist, claude)
register_handlers(app)
app.run_polling()
```

Run it:

```bash
python run_polling.py
```

If everything is set up correctly you'll see log lines appear and no errors. Open Telegram, message your bot `/start`.

**Test in this order:**
1. `/start` — bot replies with the command list
2. `/add` — add 8 or more meals manually (the planner needs 7 to fill a week)
3. `/meals` — verify they appear, grouped by cuisine
4. `/plan` — generates a draft week; try Swap and Replace buttons
5. Confirm the plan — check that Todoist gets items added
6. `/generate` — generate and save Claude-suggested meals

---

## Step 7 — Deploy to a server

This is only needed so the bot works 24/7 without your laptop being on.

### Easiest option: Railway or Render (no server management)

1. Push this project to a private GitHub repo.
2. Go to [railway.app](https://railway.app) or [render.com](https://render.com) and connect your repo.
3. Set all the environment variables from `.env` in their dashboard.
4. Upload your `google_service_account.json` as a secret file (both platforms support this).
5. They'll give you a public HTTPS URL like `https://meal-planner-xxxx.railway.app`.
6. Set `TELEGRAM_WEBHOOK_URL=https://meal-planner-xxxx.railway.app/webhook` in the dashboard env vars.
7. Deploy. The bot will register its webhook automatically on startup.

### VPS option (Oracle Cloud Free Tier, Hetzner, etc.)

1. Provision a server running Ubuntu.
2. Install Docker: `sudo apt install docker.io`
3. Point a domain at the server's IP (or use a free subdomain from duckdns.org).
4. Set up HTTPS with nginx + Let's Encrypt (certbot).
5. Copy your project files to the server.
6. Run:
   ```bash
   docker build -t meal-planner .
   docker run -d \
     --restart=always \
     -p 8000:8000 \
     --env-file .env \
     -v $(pwd)/credentials:/app/credentials \
     meal-planner
   ```
7. Configure nginx to forward `https://your-domain.com/webhook` → `http://localhost:8000/webhook`.

### Setting the webhook (automatic)

The bot sets its own webhook on startup via the `TELEGRAM_WEBHOOK_URL` env var — you don't need to do it manually. You can verify it worked by visiting:

```
https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo
```

It should show your URL and `"pending_update_count": 0`.

---

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Show help |
| `/plan` | Generate this week's dinner plan |
| `/add` | Add a new meal to the library |
| `/generate` | Generate meal ideas with Claude |
| `/meals` | List all meals (optionally filter: `/meals italian`) |
| `/shopping` | Show current Todoist shopping list |
| `/cancel` | Cancel current operation |
