# Life Tracker

A unified Telegram bot that tracks expenses, food, income, and Fitbit health data. Uses Google Gemini for natural language parsing and cross-domain insights. Runs on your Mac for $0/month.

**Project folder:** name the directory `life-tracker` (or anything you like). If you cloned into `expenses-whatsapp-tracking`, rename it in Finder or run:  
`mv expenses-whatsapp-tracking ~/projects/life-tracker`  
Then `cd` into that folder for all commands below.

---

## What It Does

**Chat naturally to log anything:**
- `spent 500 on groceries` — auto-categorized expense
- `ate dal rice for lunch` — food with nutrition estimates
- `salary 80000` — income tracking
- Forward a bank SMS — auto-parsed UPI transaction
- `should I buy AirPods for 18000?` — purchase advisor
- `how much did I spend on food this month?` — natural language queries

**Automated:**
- Fitbit Charge 6 sync (sleep, steps, heart rate, SpO2, HRV)
- Daily summary at 9 PM (Telegram + email)
- Weekly report on Monday (with Excel attachment)
- Evening nudge if no expenses logged
- Recurring expense detection and reminders
- Daily database backups

---

## Configure `.env` (overview)

1. Copy the template: `cp .env.example .env`
2. Open `.env` in a text editor and replace every placeholder with real values from the sections below.
3. **Never commit `.env`** — it is listed in `.gitignore`.

Each variable is explained in detail next.

---

## 1. Telegram bot token and user ID

### Bot token (`TELEGRAM_BOT_TOKEN`)

1. Open Telegram and search for **[@BotFather](https://t.me/BotFather)**.
2. Start a chat and send `/newbot`.
3. Follow the prompts: choose a **display name** (e.g. “My Life Tracker”) and a **username** ending in `bot` (e.g. `my_life_tracker_xyz_bot`). Usernames must be globally unique.
4. BotFather replies with a message that includes a line like:  
   `Use this token to access the HTTP API:`  
   followed by a long string like `123456789:ABCdefGHI...`
5. Copy that entire string — that is **`TELEGRAM_BOT_TOKEN`**.  
   - If you lose it, send `/token` to BotFather, pick your bot, and it will show the token again (or revoke and issue a new one).

### Your numeric user ID (`TELEGRAM_USER_ID`)

The bot only accepts messages from **you**. Telegram user IDs are integers (no quotes in `.env`).

**Option A — @userinfobot**

1. Open **[@userinfobot](https://t.me/userinfobot)** in Telegram.
2. Send any message; it replies with **Id:** followed by a number (e.g. `123456789`).
3. Put that number in `.env` as `TELEGRAM_USER_ID=123456789` (digits only, no spaces).

**Option B — @RawDataBot**

1. Open **[@RawDataBot](https://t.me/RawDataBot)**, start it, send `/start`.
2. Look for `"id":` in the JSON — use that integer.

---

## 2. Gemini API key (`GEMINI_API_KEY`)

1. Go to **[Google AI Studio](https://aistudio.google.com/)** or **[ai.google.dev](https://ai.google.dev/)**.
2. Sign in with your Google account.
3. Open **Get API key** (or **API keys** in the left menu).
4. Create a key in a Google Cloud project (free tier allows generous daily usage for personal use).
5. Copy the key string — it looks like `AIza...` — and set `GEMINI_API_KEY=...` in `.env`.
6. Restrict the key in Google Cloud Console (optional but recommended): limit to **Generative Language API** only.

**Privacy:** API traffic is governed by Google’s terms; API data is not used to train models for the consumer API path documented for Gemini.

---

## 3. Fitbit app credentials (`FITBIT_CLIENT_ID`, `FITBIT_CLIENT_SECRET`, `FITBIT_REDIRECT_URI`)

These let the app read your Fitbit data from Fitbit’s servers (after you log in once).

1. Go to **[dev.fitbit.com](https://dev.fitbit.com/)** and sign in with the **same Fitbit account** your Charge 6 uses.
2. Open **Register a new application** (or **Manage** → **Register an app**).
3. Fill in:
   - **Application name:** anything (e.g. `Life Tracker Personal`).
   - **Description:** optional.
   - **Application website:** can be `http://localhost` for personal use.
   - **Organization / organization website:** optional.
   - **OAuth 2.0 Application Type:** choose **Personal** (fits a single-user app).
   - **Callback URL / Redirect URL:** must match what you put in `.env`. Default in this project is:  
     `http://localhost:8080/fitbit/callback`  
     Set **`FITBIT_REDIRECT_URI`** to exactly the same string (including `http`, no trailing slash unless you registered it that way).
4. Submit. Fitbit shows **OAuth 2.0 Client ID** and **Client Secret**.
5. Put them in `.env`:
   - `FITBIT_CLIENT_ID=...`
   - `FITBIT_CLIENT_SECRET=...`

**First-time login (after the bot runs):**

1. With dependencies installed and `.env` filled, run:  
   `python -c "from services.fitbit_service import get_auth_url; print(get_auth_url())"`
2. Open the printed URL in a browser, log into Fitbit, click **Allow**.
3. The browser redirects to something like:  
   `http://localhost:8080/fitbit/callback?code=XXXXX&state=...`  
   The page may show “connection refused” — that is OK. **Copy everything after `code=`** until the next `&` (or end of URL). That string is the authorization **code** (often one long token).
4. In Telegram, send:  
   `/fitbit_auth PASTE_THE_CODE_HERE`  
   The bot exchanges the code for access/refresh tokens and stores them in your local database.

---

## 4. Gmail app password (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `NOTIFICATION_EMAIL`)

Used only to **send** daily/weekly summary emails (SMTP). You need a **Google account** with 2-Step Verification enabled.

1. Go to **[Google Account → Security](https://myaccount.google.com/security)**.
2. Enable **2-Step Verification** if it is not already on (required for app passwords).
3. Go to **[App passwords](https://myaccount.google.com/apppasswords)** (search “app passwords” in Google Account if the link redirects).
4. Create an app password:
   - App: **Mail**
   - Device: **Other** → name it e.g. `Life Tracker`
5. Google shows a **16-character password** (often in groups of 4).  
   - In `.env`, set **`GMAIL_APP_PASSWORD`** to that 16 characters **without spaces** (or with spaces — some clients accept both; this project uses the string as-is; remove spaces to be safe).
6. Set **`GMAIL_ADDRESS`** to the full Gmail address that owns that app password (e.g. `you@gmail.com`).
7. Set **`NOTIFICATION_EMAIL`** to the address that should **receive** the summaries — usually the same as `GMAIL_ADDRESS` for personal use.

If you do not want email, you can leave `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` empty; the bot will still work in Telegram (scheduler logs a warning when email is skipped).

---

## Install and run

```bash
cd ~/path/to/life-tracker   # your project folder

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env with the values from the sections above

python main.py
```

Logs are written to **`life_tracker.log`** in the project folder. The SQLite database defaults to **`data/life_tracker.db`**.

---

## Samsung S24: Fitbit background sync

If health data looks stale, Android may be killing the Fitbit app:

1. **Settings → Battery → Background usage limits → Never sleeping apps** → add **Fitbit**.
2. **Settings → Apps → Fitbit → Battery** → **Unrestricted**.

---

## Auto-start on Mac (optional)

1. Edit **`com.pranav.lifetracker.plist`** so every path matches your machine (Python in `.venv`, project folder — use your real `life-tracker` path).
2. Copy to LaunchAgents and load:

```bash
cp com.pranav.lifetracker.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.pranav.lifetracker.plist
```

Check: `launchctl list | grep lifetracker`

To stop: `launchctl unload ~/Library/LaunchAgents/com.pranav.lifetracker.plist`

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List all commands |
| `/summary` | Today's overview |
| `/week` | This week's summary |
| `/month` | Monthly breakdown |
| `/export` | Get Excel report |
| `/budget set 50000` | Set monthly budget |
| `/budget food 15000` | Set category budget |
| `/income` | View income and savings rate |
| `/trends` | Spending trends and anomalies |
| `/insights` | Cross-domain analysis |
| `/undo` | Remove last entry |
| `/recurring` | Recurring expenses |
| `/fitbit` | Fitbit sync status |
| `/fitbit_auth CODE` | Complete Fitbit OAuth (paste `code` from redirect URL) |

---

## Natural Language Examples

**Expenses:** `uber 200`, `rent 25000`, `yesterday groceries 1500`, `dinner 2000 split 4`

**Food:** `ate 2 rotis dal and rice for lunch`, `had pizza for dinner`

**Lending:** `lent Rahul 5000`, `Rahul paid back 2000`, `how much does Rahul owe me?`

**Questions:** spending queries, sleep vs food, trends.

**Purchase advisor:** `should I buy AirPods for 18000?`

---

## Security

- Bot is locked to your Telegram user ID (rejects everyone else).
- Data stays on your machine (`data/life_tracker.db`); backups in `backups/`.
- No inbound ports; the bot uses Telegram long polling.
- Keep `.env` private; never commit it.

---

## Cost

| Component | Cost |
|-----------|------|
| Gemini 2.0 Flash | Free tier (limits apply) |
| Telegram Bot API | Free |
| Fitbit Web API | Free (personal) |
| Gmail SMTP | Free |
| **Total** | **$0/month** for typical personal use |
