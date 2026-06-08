"""Хэндлеры пользователя."""

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

import db
import keyboards
from config import ADMIN_ID


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать /start — показать выбор дня."""
    await update.message.reply_text(
        "👋 Привет! Выбери удобный день для записи:",
        reply_markup=keyboards.days_keyboard(),
    )


async def cmd_my(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать /my — показать записи пользователя."""
    bookings = db.get_user_bookings(update.effective_user.id)
    if not bookings:
        await update.message.reply_text("У тебя пока нет записей. Нажми /start, чтобы записаться.")
        return
    await update.message.reply_text(
        "🗓 Твои записи:",
        reply_markup=keyboards.my_bookings_keyboard(bookings),
    )


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать все CallbackQuery."""
    q = update.callback_query
    data = q.data

    if data == "noop":
        await q.answer("Это время уже занято 🔒", show_alert=True)
        return

    await q.answer()
    prefix = data.split(":", 1)[0]

    if prefix == "day":
        _, day_offset, date_str = data.split(":")
        await q.edit_message_text(
            f"Выбери время на {date_str}:",
            reply_markup=keyboards.slots_keyboard(date_str, int(day_offset)),
        )

    elif prefix == "slot":
        _, day_offset, date_str, slot_time = data.split(":", 3)
        ctx.user_data["pending"] = {
            "day_offset": int(day_offset),
            "slot_date": date_str,
            "slot_time": slot_time,
        }
        ctx.user_data.pop("awaiting_address", None)
        await q.edit_message_text(
            f"Ты выбрал: {date_str} в {slot_time}.\n"
            "Выбери формат встречи:",
            reply_markup=keyboards.format_keyboard(),
        )

    elif prefix == "fmt":
        pending = ctx.user_data.get("pending")
        if not pending:
            await q.edit_message_text("Сессия устарела. Начни заново: /start")
            return
        meeting_format = data.split(":")[1]
        pending["meeting_format"] = meeting_format
        if meeting_format == "offline":
            ctx.user_data["awaiting_address"] = True
            await q.edit_message_text(
                "📍 Офлайн-встреча. Напиши одним сообщением адрес, где встретимся:"
            )
            return
        pending["address"] = None
        await q.edit_message_text("🌐 Онлайн-встреча.")
        await _ask_phone(ctx, q.message.chat_id)

    elif prefix == "back":
        await q.edit_message_text(
            "👋 Привет! Выбери удобный день для записи:",
            reply_markup=keyboards.days_keyboard(),
        )

    elif prefix == "cancel":
        booking_id = int(data.split(":")[1])
        booking = db.get_booking_by_id(booking_id)
        ok = db.cancel_booking(booking_id, q.from_user.id)
        if not ok:
            await q.edit_message_text("Не удалось отменить запись 🤔")
            return
        await q.edit_message_text(
            f"✅ Запись отменена: {booking['slot_date']} в {booking['slot_time']}."
        )
        await _notify_admin(
            ctx,
            "❌ Отмена записи №{id}\n"
            "Дата: {date} {time}\n"
            "Клиент: {name} (@{username})".format(
                id=booking_id,
                date=booking["slot_date"],
                time=booking["slot_time"],
                name=booking["full_name"],
                username=booking["username"] or "—",
            ),
        )


async def on_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Принять адрес офлайн-встречи и перейти к запросу телефона."""
    if not ctx.user_data.get("awaiting_address"):
        # Бот не ждёт адрес — игнорируем произвольный текст.
        return
    pending = ctx.user_data.get("pending")
    if not pending:
        ctx.user_data.pop("awaiting_address", None)
        await update.message.reply_text("Сессия устарела. Начни заново: /start")
        return

    pending["address"] = update.message.text.strip()
    ctx.user_data.pop("awaiting_address", None)
    await update.message.reply_text(f"📍 Адрес сохранён: {pending['address']}")
    await _ask_phone(ctx, update.message.chat_id)


async def _ask_phone(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Попросить пользователя поделиться номером телефона."""
    await ctx.bot.send_message(
        chat_id=chat_id,
        text="Поделись номером телефона для подтверждения записи 👇",
        reply_markup=keyboards.contact_keyboard(),
    )


def _format_label(meeting_format: str | None, address: str | None) -> str:
    """Человекочитаемое описание формата встречи."""
    if meeting_format == "offline":
        return f"📍 Офлайн — {address}"
    return "🌐 Онлайн"


async def on_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать присланный контакт — завершить бронирование."""
    pending = ctx.user_data.get("pending")
    if not pending:
        await update.message.reply_text(
            "Сначала выбери день и время через /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    user = update.effective_user
    phone = update.message.contact.phone_number
    meeting_format = pending.get("meeting_format")
    address = pending.get("address")

    booking_id = db.book_slot(
        user.id,
        user.username,
        user.full_name,
        phone,
        pending["day_offset"],
        pending["slot_date"],
        pending["slot_time"],
        meeting_format,
        address,
    )
    ctx.user_data.pop("pending", None)
    ctx.user_data.pop("awaiting_address", None)

    if booking_id is None:
        await update.message.reply_text(
            "К сожалению, это время только что заняли 😔 Выбери другое:",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text(
            "Выбери удобный день:",
            reply_markup=keyboards.days_keyboard(),
        )
        return

    await update.message.reply_text(
        f"✅ Готово! Ты записан на {pending['slot_date']} в {pending['slot_time']}.\n"
        f"Формат: {_format_label(meeting_format, address)}\n"
        "Посмотреть записи: /my",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _notify_admin(
        ctx,
        "🆕 Новая запись №{id}\n"
        "Дата: {date} {time}\n"
        "Формат: {fmt}\n"
        "Имя: {name}\n"
        "Username: @{username}\n"
        "Телефон: {phone}".format(
            id=booking_id,
            date=pending["slot_date"],
            time=pending["slot_time"],
            fmt=_format_label(meeting_format, address),
            name=user.full_name,
            username=user.username or "—",
            phone=phone,
        ),
    )


async def _notify_admin(ctx: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Отправить уведомление администратору (без падения, если недоступен)."""
    if not ADMIN_ID:
        return
    try:
        await ctx.bot.send_message(chat_id=ADMIN_ID, text=text)
    except Exception:
        # Админ мог не запускать бота — игнорируем ошибку доставки.
        pass
