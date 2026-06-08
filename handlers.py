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
        await q.edit_message_text(
            f"Ты выбрал: {date_str} в {slot_time}.\n"
            "Поделись номером телефона для подтверждения записи:"
        )
        await ctx.bot.send_message(
            chat_id=q.message.chat_id,
            text="👇 Нажми кнопку ниже:",
            reply_markup=keyboards.contact_keyboard(),
        )

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

    booking_id = db.book_slot(
        user.id,
        user.username,
        user.full_name,
        phone,
        pending["day_offset"],
        pending["slot_date"],
        pending["slot_time"],
    )
    ctx.user_data.pop("pending", None)

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
        "Посмотреть записи: /my",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _notify_admin(
        ctx,
        "🆕 Новая запись №{id}\n"
        "Дата: {date} {time}\n"
        "Имя: {name}\n"
        "Username: @{username}\n"
        "Телефон: {phone}".format(
            id=booking_id,
            date=pending["slot_date"],
            time=pending["slot_time"],
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
