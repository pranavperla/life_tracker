"""Telegram bot command and message handlers."""

from __future__ import annotations

import logging

from datetime import date, timedelta

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import Config
from db.database import Database
from db import models
from parsers.router import route_message
from parsers.expense_parser import handle_expense, handle_split, handle_lending
from parsers.sms_parser import handle_sms, complete_sms_expense
from parsers.food_parser import handle_food
from bot.advisor import assess_purchase
from bot.keyboards import zero_day_keyboard, recurring_confirm_keyboard
from services.query_service import answer_question
from services.fitbit_service import exchange_code, get_auth_url, sync_recent

logger = logging.getLogger(__name__)

# Conversation state stored per-chat
_pending_sms: dict[int, dict] = {}  # chat_id -> pending SMS expense awaiting category


def _authorized(func):
    """Decorator that rejects unauthorized users."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else 0
        if user_id != Config.TELEGRAM_USER_ID:
            logger.warning("Unauthorized access attempt from user %s", user_id)
            return
        return await func(update, context)
    return wrapper


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.bot_data["db"]


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

@_authorized
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Hey! I'm your personal life tracker.\n\n"
        "Just type naturally to log things:\n"
        "• \"spent 500 on groceries\" — log expense\n"
        "• \"ate dal rice for lunch\" — log food\n"
        "• \"salary 80000\" — log income\n"
        "• Forward a bank SMS — auto-parse expense\n"
        "• \"should I buy X for Y?\" — purchase advice\n"
        "• Ask any question about your data!\n\n"
        "Type /help for all commands."
    )


@_authorized
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 **Commands:**\n\n"
        "/summary — today's overview\n"
        "/week — this week's summary\n"
        "/month — monthly breakdown\n"
        "/export — get Excel file\n"
        "/budget set 50000 — set monthly budget\n"
        "/budget food 15000 — set category budget\n"
        "/income — view income & savings rate\n"
        "/trends — spending trends & anomalies\n"
        "/insights — deep cross-domain analysis\n"
        "/undo — remove last entry\n"
        "/recurring — manage recurring expenses\n"
        "/fitbit — check Fitbit sync status\n"
        "/fitbit_login — get the Fitbit authorization link (open this, not a bookmark)\n"
        "/fitbit_auth CODE — complete Fitbit login (paste OAuth code)\n"
        "/help — this message\n\n"
        "💬 **Or just chat naturally:**\n"
        "• Log expenses, food, income\n"
        "• Forward bank SMS\n"
        "• Ask questions about your data\n"
        "• \"should I buy AirPods for 18000?\"\n"
        "• \"how much did I lend Rahul?\"\n"
        "• \"yesterday uber 200\" (backfill)",
        parse_mode="Markdown",
    )


@_authorized
async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    expenses = await models.get_expenses_for_date(db, today)
    total = sum(e["amount"] for e in expenses)
    food = await models.get_food_for_date(db, today)
    fitbit = await models.get_fitbit_for_date(db, yesterday)

    month_start = date.today().replace(day=1).isoformat()
    month_total = await models.get_total_expenses(db, month_start, today)
    month_year = date.today().strftime("%Y-%m")
    budget_row = await models.get_budget(db, "total", month_year)
    budget = budget_row.get("monthly_limit", Config.DEFAULT_MONTHLY_BUDGET) if budget_row else Config.DEFAULT_MONTHLY_BUDGET

    parts = [f"📊 **Today's Summary** ({today})\n"]

    # Expenses
    if expenses:
        parts.append(f"💰 Spent: ₹{total:,.0f} ({len(expenses)} transactions)")
        for e in expenses[-5:]:
            parts.append(f"  • ₹{e['amount']:,.0f} — {e['category']}: {e['description']}")
    else:
        parts.append("💰 No expenses logged today")

    parts.append(f"\n📅 Month so far: ₹{month_total:,.0f} / ₹{budget:,.0f} "
                 f"(₹{budget - month_total:,.0f} remaining)")

    # Food
    if food:
        parts.append(f"\n🍽 Food: {len(food)} meals logged")
        for f_entry in food:
            cal = f" (~{f_entry['estimated_calories']:.0f} cal)" if f_entry.get("estimated_calories") else ""
            parts.append(f"  • {f_entry['meal_type']}: {f_entry['description']}{cal}")

    # Fitbit (yesterday's sleep)
    if fitbit:
        parts.append("\n😴 Last night's sleep:")
        if fitbit.get("sleep_hours"):
            parts.append(f"  • {fitbit['sleep_hours']:.1f} hrs")
        if fitbit.get("sleep_score"):
            parts.append(f"  • Score: {fitbit['sleep_score']}")
        if fitbit.get("steps"):
            parts.append(f"🚶 Yesterday's steps: {fitbit['steps']:,}")

    await update.message.reply_text("\n".join(parts), parse_mode="Markdown")


@_authorized
async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    week_end = today.isoformat()

    total = await models.get_total_expenses(db, week_start, week_end)
    categories = await models.get_expenses_by_category(db, week_start, week_end)
    tracked = await models.get_tracked_days(db, week_start, week_end)
    days_tracked = len(tracked)
    days_in_week = (today.weekday() + 1)
    avg_daily = total / days_tracked if days_tracked > 0 else 0

    parts = [f"📊 **This Week** ({week_start} → {week_end})\n"]
    parts.append(f"💰 Total: ₹{total:,.0f}")
    parts.append(f"📈 Daily avg: ₹{avg_daily:,.0f} ({days_tracked}/{days_in_week} days tracked)")

    if categories:
        parts.append("\n📂 By category:")
        for c in categories[:8]:
            parts.append(f"  • {c['category']}: ₹{c['total']:,.0f} ({c['count']} txns)")

    await update.message.reply_text("\n".join(parts), parse_mode="Markdown")


@_authorized
async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    month_end = today.isoformat()
    month_year = today.strftime("%Y-%m")

    total = await models.get_total_expenses(db, month_start, month_end)
    income = await models.get_total_income(db, month_start, month_end)
    categories = await models.get_expenses_by_category(db, month_start, month_end)

    budget_row = await models.get_budget(db, "total", month_year)
    budget = budget_row.get("monthly_limit", Config.DEFAULT_MONTHLY_BUDGET) if budget_row else Config.DEFAULT_MONTHLY_BUDGET

    savings_rate = ((income - total) / income * 100) if income > 0 else 0
    tracked = await models.get_tracked_days(db, month_start, month_end)

    parts = [f"📊 **{today.strftime('%B %Y')}**\n"]
    parts.append(f"💰 Spent: ₹{total:,.0f} / ₹{budget:,.0f}")
    parts.append(f"📥 Income: ₹{income:,.0f}")
    parts.append(f"💵 Remaining budget: ₹{budget - total:,.0f}")
    if income > 0:
        parts.append(f"📈 Savings rate: {savings_rate:.1f}%")
    parts.append(f"📅 Days tracked: {len(tracked)}/{today.day}")

    if categories:
        parts.append("\n📂 By category:")
        for c in categories[:10]:
            pct = (c["total"] / total * 100) if total > 0 else 0
            parts.append(f"  • {c['category']}: ₹{c['total']:,.0f} ({pct:.0f}%)")

    await update.message.reply_text("\n".join(parts), parse_mode="Markdown")


@_authorized
async def cmd_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    args = context.args or []
    month_year = date.today().strftime("%Y-%m")

    if len(args) >= 2 and args[0].lower() == "set":
        try:
            limit = float(args[1].replace(",", ""))
        except ValueError:
            await update.message.reply_text("Usage: /budget set 50000")
            return
        await models.set_budget(db, "total", limit, month_year)
        await update.message.reply_text(f"✅ Monthly budget set to ₹{limit:,.0f}")

    elif len(args) >= 2:
        category = args[0]
        try:
            limit = float(args[1].replace(",", ""))
        except ValueError:
            await update.message.reply_text("Usage: /budget food 15000")
            return
        await models.set_budget(db, category, limit, month_year)
        await update.message.reply_text(f"✅ {category} budget set to ₹{limit:,.0f}")

    else:
        budgets = await models.get_all_budgets(db, month_year)
        if budgets:
            lines = [f"📋 **Budgets for {month_year}:**\n"]
            for b in budgets:
                lines.append(f"  • {b['category']}: ₹{b['monthly_limit']:,.0f}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        else:
            await update.message.reply_text(
                f"No budgets set. Default: ₹{Config.DEFAULT_MONTHLY_BUDGET:,.0f}\n"
                "Set one: /budget set 50000"
            )


@_authorized
async def cmd_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    today = date.today()
    month_start = today.replace(day=1).isoformat()

    income_total = await models.get_total_income(db, month_start, today.isoformat())
    expenses_total = await models.get_total_expenses(db, month_start, today.isoformat())
    entries = await models.get_income_range(db, month_start, today.isoformat())

    savings = income_total - expenses_total
    rate = (savings / income_total * 100) if income_total > 0 else 0

    parts = [f"💵 **Income — {today.strftime('%B %Y')}**\n"]
    parts.append(f"📥 Total income: ₹{income_total:,.0f}")
    parts.append(f"💰 Total spent: ₹{expenses_total:,.0f}")
    parts.append(f"💵 Net savings: ₹{savings:,.0f}")
    if income_total > 0:
        parts.append(f"📈 Savings rate: {rate:.1f}%")

    if entries:
        parts.append("\nRecent income:")
        for e in entries[-5:]:
            parts.append(f"  • ₹{e['amount']:,.0f} — {e['source']} ({e['date']})")

    await update.message.reply_text("\n".join(parts), parse_mode="Markdown")


@_authorized
async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    last = await models.get_last_expense(db)
    if not last:
        await update.message.reply_text("Nothing to undo.")
        return

    await models.delete_expense(db, last["id"])
    await update.message.reply_text(
        f"🗑 Removed: ₹{last['amount']:,.0f} — {last['category']}: {last['description']} ({last['date']})"
    )


@_authorized
async def cmd_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    items = await models.get_active_recurring(db)
    if not items:
        await update.message.reply_text(
            "No recurring expenses detected yet. "
            "They'll be auto-detected after you log similar expenses 3+ months in a row."
        )
        return

    parts = ["📋 **Recurring Expenses:**\n"]
    for r in items:
        day_str = f" (day {r['day_of_month']})" if r.get("day_of_month") else ""
        last = f" — last confirmed: {r['last_confirmed']}" if r.get("last_confirmed") else ""
        parts.append(f"  • ₹{r['amount']:,.0f} — {r['description']}{day_str}{last}")

    await update.message.reply_text("\n".join(parts), parse_mode="Markdown")


@_authorized
async def cmd_fitbit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    latest = await models.get_latest_fitbit(db)
    if not latest:
        await update.message.reply_text(
            "No Fitbit data yet. Use /fitbit_login to open the auth link, then /fitbit_auth with the code."
        )
        return

    from datetime import datetime
    last_date = latest.get("date", "unknown")
    today = date.today().isoformat()

    parts = [f"⌚ **Fitbit Status**\n"]
    parts.append(f"Last data: {last_date}")

    if last_date == today or last_date == (date.today() - timedelta(days=1)).isoformat():
        parts.append("✅ Sync looks good!")
    else:
        parts.append(
            "⚠️ Data may be stale. Open your Fitbit app to sync.\n"
            "Samsung S24: Settings > Battery > Background usage limits > "
            "Never sleeping apps > Add Fitbit"
        )

    if latest.get("sleep_hours"):
        parts.append(f"\n😴 Sleep: {latest['sleep_hours']:.1f} hrs (score: {latest.get('sleep_score', 'N/A')})")
    if latest.get("steps"):
        parts.append(f"🚶 Steps: {latest['steps']:,}")
    if latest.get("resting_hr"):
        parts.append(f"❤️ Resting HR: {latest['resting_hr']} bpm")

    await update.message.reply_text("\n".join(parts), parse_mode="Markdown")


@_authorized
async def cmd_fitbit_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the full Fitbit OAuth URL (must not open /oauth2/authorize without query params)."""
    try:
        url = get_auth_url()
    except ValueError as exc:
        await update.message.reply_text(f"⚠️ {exc}")
        return

    redir = (Config.FITBIT_REDIRECT_URI or "").strip()
    await update.message.reply_text(
        "1️⃣ Tap the link below (use this full link — do **not** open Fitbit’s authorize page from a bookmark or empty URL).\n\n"
        f"{url}\n\n"
        "2️⃣ Log in and allow access.\n"
        "3️⃣ Your browser will try to open localhost — copy the **`code=`** value from the address bar.\n"
        "4️⃣ Send: `/fitbit_auth` paste_that_code\n\n"
        f"⚙️ On [dev.fitbit.com](https://dev.fitbit.com/apps), **Callback URL** must match exactly:\n`{redir}`",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


@_authorized
async def cmd_fitbit_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exchange Fitbit OAuth authorization code for tokens."""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: `/fitbit_auth YOUR_CODE`\n\n"
            "First run `/fitbit_login` and open the **full** link it gives you.\n"
            "After you approve, copy the `code=` value from the redirect URL (localhost page error is OK).",
            parse_mode="Markdown",
        )
        return

    code = args[0].strip()
    if "#" in code:
        code = code.split("#")[0]

    db = get_db(context)
    if not Config.FITBIT_CLIENT_ID or not Config.FITBIT_CLIENT_SECRET:
        await update.message.reply_text(
            "Fitbit is not configured. Set FITBIT_CLIENT_ID and FITBIT_CLIENT_SECRET in .env"
        )
        return

    await update.message.reply_text("Connecting to Fitbit...")
    ok, err_detail = await exchange_code(code, db)
    if ok:
        n = await sync_recent(db, days=3)
        await update.message.reply_text(
            f"✅ Fitbit connected. Synced recent data ({n} day(s) with data)."
        )
    else:
        await update.message.reply_text(
            "❌ Fitbit rejected the token exchange. Common causes:\n"
            "• Code expired (open a **new** link from `/fitbit_login` and paste the code immediately)\n"
            "• **Callback URL** on dev.fitbit.com does not match `FITBIT_REDIRECT_URI` in `.env`\n"
            "• Wrong `FITBIT_CLIENT_SECRET`\n\n"
            f"Fitbit said: `{err_detail[:500]}`",
            parse_mode="Markdown",
        )


@_authorized
async def cmd_trends(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    await update.message.reply_text("Analyzing trends...")
    from services.insights_service import generate_trends
    text = await generate_trends(db)
    await update.message.reply_text(text, parse_mode="Markdown")


@_authorized
async def cmd_insights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    await update.message.reply_text("Generating cross-domain insights... 🔍")
    from services.insights_service import generate_insights
    text = await generate_insights(db)
    await update.message.reply_text(text, parse_mode="Markdown")


@_authorized
async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    await update.message.reply_text("Generating Excel report... 📊")
    from services.excel_service import generate_report
    filepath = await generate_report(db)
    await update.message.reply_document(document=open(filepath, "rb"), filename=filepath.name)


# ---------------------------------------------------------------------------
# Callback query handler (inline keyboards)
# ---------------------------------------------------------------------------

@_authorized
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    db = get_db(context)

    if data == "zeroday:yes":
        await models.confirm_zero_day(db, date.today().isoformat())
        await query.edit_message_text("✅ Marked as zero-spend day.")

    elif data == "zeroday:no":
        await query.edit_message_text("OK! Log your expenses whenever you're ready.")

    elif data.startswith("recurring:confirm:"):
        rec_id = int(data.split(":")[-1])
        recurring_list = await models.get_active_recurring(db)
        rec = next((r for r in recurring_list if r["id"] == rec_id), None)
        if rec:
            await models.add_expense(
                db,
                amount=rec["amount"],
                category=rec["category"],
                description=rec["description"],
                source="recurring",
            )
            await models.confirm_recurring(db, rec_id, date.today().isoformat())
            await query.edit_message_text(
                f"✅ Logged recurring: ₹{rec['amount']:,.0f} — {rec['description']}"
            )

    elif data.startswith("recurring:skip:"):
        await query.edit_message_text("⏭ Skipped this month.")


# ---------------------------------------------------------------------------
# Free-text message handler (the main router)
# ---------------------------------------------------------------------------

@_authorized
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if not text:
        return

    db = get_db(context)
    chat_id = update.effective_chat.id

    # Check if we're waiting for SMS clarification
    if chat_id in _pending_sms:
        pending = _pending_sms.pop(chat_id)
        response = await complete_sms_expense(db, pending, category="Miscellaneous", description=text)
        await update.message.reply_text(response)
        return

    # Route through LLM
    parsed = await route_message(text)
    intent = parsed.get("intent", "unknown")

    if intent == "command":
        await update.message.reply_text("Use the /command directly. Type /help to see all commands.")

    elif intent == "expense":
        response = await handle_expense(db, parsed)
        await update.message.reply_text(response)

    elif intent == "sms_forward":
        result = await handle_sms(db, parsed, text)
        if result["needs_clarification"] and result["pending_expense"]:
            _pending_sms[chat_id] = result["pending_expense"]
        await update.message.reply_text(result["response"])

    elif intent == "food":
        response = await handle_food(db, parsed)
        await update.message.reply_text(response)

    elif intent == "income":
        amount = parsed.get("amount", 0)
        source = parsed.get("source", "")
        description = parsed.get("description", "")
        income_date = parsed.get("date")
        if amount > 0:
            result = await models.add_income(
                db, amount=float(amount), source=source,
                description=description, income_date=income_date,
            )
            await update.message.reply_text(
                f"📥 Income logged: ₹{amount:,.0f} from {source}\n📅 {result['date']}"
            )
        else:
            await update.message.reply_text("Couldn't parse the income amount. Try again?")

    elif intent == "lending":
        response = await handle_lending(db, parsed)
        await update.message.reply_text(response)

    elif intent == "purchase_check":
        item = parsed.get("item", "item")
        amount = parsed.get("amount", 0)
        if amount > 0:
            await update.message.reply_text("Let me check your finances... 🔍")
            response = await assess_purchase(db, item, float(amount))
            await update.message.reply_text(response, parse_mode="Markdown")
        else:
            await update.message.reply_text("What's the price? E.g. 'should I buy AirPods for 18000?'")

    elif intent == "question":
        question = parsed.get("question", text)
        await update.message.reply_text("Looking that up... 🔍")
        response = await answer_question(db, question)
        await update.message.reply_text(response)

    elif intent == "correction":
        action = parsed.get("action", "update")
        if action == "delete":
            last = await models.get_last_expense(db)
            if last:
                await models.delete_expense(db, last["id"])
                await update.message.reply_text(
                    f"🗑 Removed: ₹{last['amount']:,.0f} — {last['description']}"
                )
            else:
                await update.message.reply_text("Nothing to delete.")
        else:
            field = parsed.get("field", "amount")
            new_value = parsed.get("new_value")
            last = await models.get_last_expense(db)
            if last and new_value:
                update_data = {}
                if field == "amount":
                    try:
                        update_data["amount"] = float(str(new_value).replace(",", ""))
                    except ValueError:
                        await update.message.reply_text("Couldn't parse the new amount.")
                        return
                elif field in ("category", "description"):
                    update_data[field] = new_value
                if update_data:
                    await models.update_expense(db, last["id"], **update_data)
                    await update.message.reply_text(
                        f"✏️ Updated last expense: {field} → {new_value}"
                    )
            else:
                await update.message.reply_text("Nothing to correct or couldn't understand the correction.")

    elif intent == "split":
        response = await handle_split(db, parsed)
        await update.message.reply_text(response)

    else:
        await update.message.reply_text(
            "I'm not sure what you mean. You can:\n"
            "• Log expenses: \"spent 500 on groceries\"\n"
            "• Log food: \"ate pizza for dinner\"\n"
            "• Ask questions: \"how much did I spend this week?\"\n"
            "• Type /help for all commands"
        )


# ---------------------------------------------------------------------------
# Register all handlers
# ---------------------------------------------------------------------------

def register_handlers(app: Application, db: Database) -> None:
    app.bot_data["db"] = db

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("month", cmd_month))
    app.add_handler(CommandHandler("budget", cmd_budget))
    app.add_handler(CommandHandler("income", cmd_income))
    app.add_handler(CommandHandler("undo", cmd_undo))
    app.add_handler(CommandHandler("recurring", cmd_recurring))
    app.add_handler(CommandHandler("fitbit", cmd_fitbit))
    app.add_handler(CommandHandler("fitbit_login", cmd_fitbit_login))
    app.add_handler(CommandHandler("fitbit_auth", cmd_fitbit_auth))
    app.add_handler(CommandHandler("trends", cmd_trends))
    app.add_handler(CommandHandler("insights", cmd_insights))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
