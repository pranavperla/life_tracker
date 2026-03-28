"""Inline keyboards for Telegram bot interactions."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_keyboard(prefix: str = "confirm") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Correct", callback_data=f"{prefix}:yes"),
            InlineKeyboardButton("❌ Wrong", callback_data=f"{prefix}:no"),
        ]
    ])


def zero_day_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Yes, zero-spend day", callback_data="zeroday:yes"),
            InlineKeyboardButton("Let me log now", callback_data="zeroday:no"),
        ]
    ])


def recurring_confirm_keyboard(rec_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"recurring:confirm:{rec_id}"),
            InlineKeyboardButton("❌ Skip this month", callback_data=f"recurring:skip:{rec_id}"),
        ]
    ])
