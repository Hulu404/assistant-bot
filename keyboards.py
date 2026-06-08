"""Построители клавиатур."""

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from config import SLOT_TIMES
from db import get_booked_slots, get_past_slots, get_week_dates


def days_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора дня на ближайшую неделю (по кнопке на строку)."""
    rows: list[list[InlineKeyboardButton]] = []
    for day_offset, date_str, label, ddmm in get_week_dates():
        unavailable = get_booked_slots(date_str) | get_past_slots(date_str)
        free = len(SLOT_TIMES) - len(unavailable)
        rows.append(
            [
                InlineKeyboardButton(
                    f"{label} {ddmm}  ({free} своб.)",
                    callback_data=f"day:{day_offset}:{date_str}",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


def slots_keyboard(date_str: str, day_offset: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора времени на дату (по 2 слота в ряд)."""
    booked = get_booked_slots(date_str)
    past = get_past_slots(date_str)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for time in SLOT_TIMES:
        if time in past:
            # Прошедшие слоты не показываем вовсе.
            continue
        if time in booked:
            button = InlineKeyboardButton(f"🔒 {time}", callback_data="noop")
        else:
            button = InlineKeyboardButton(
                f"✅ {time}",
                callback_data=f"slot:{day_offset}:{date_str}:{time}",
            )
        row.append(button)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back:days")])
    return InlineKeyboardMarkup(rows)


def contact_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура запроса номера телефона."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def my_bookings_keyboard(bookings) -> InlineKeyboardMarkup:
    """Клавиатура со списком записей пользователя для отмены."""
    rows: list[list[InlineKeyboardButton]] = []
    for booking in bookings:
        rows.append(
            [
                InlineKeyboardButton(
                    f"❌ {booking['slot_date']}  {booking['slot_time']}",
                    callback_data=f"cancel:{booking['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("⬅️ В начало", callback_data="back:start")])
    return InlineKeyboardMarkup(rows)
