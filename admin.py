"""Хэндлеры администратора."""

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_ID
from db import admin_cancel_booking, get_all_bookings, get_booking_by_id


def _is_admin(update: Update) -> bool:
    """Проверить, что сообщение пришло от администратора."""
    return update.effective_user is not None and update.effective_user.id == ADMIN_ID


async def cmd_bookings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать администратору все активные записи."""
    if not _is_admin(update):
        return

    bookings = get_all_bookings()
    if not bookings:
        await update.message.reply_text("Активных записей нет.")
        return

    lines = [
        "#{id}  {date} {time}\n  {name}  @{username}  📞{phone}".format(
            id=b["id"],
            date=b["slot_date"],
            time=b["slot_time"],
            name=b["full_name"],
            username=b["username"] or "—",
            phone=b["phone"],
        )
        for b in bookings
    ]
    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_admin_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменить запись администратором: /cancel <id>."""
    if not _is_admin(update):
        return

    if not ctx.args:
        await update.message.reply_text("Использование: /cancel <id записи>")
        return
    try:
        booking_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("ID записи должен быть числом.")
        return

    booking = admin_cancel_booking(booking_id)
    if booking is None:
        await update.message.reply_text(f"Запись #{booking_id} не найдена.")
        return

    await update.message.reply_text(
        f"✅ Запись #{booking_id} отменена:\n"
        f"{booking['slot_date']} {booking['slot_time']} — "
        f"{booking['full_name']} 📞{booking['phone']}"
    )

    try:
        await ctx.bot.send_message(
            chat_id=booking["user_id"],
            text=(
                f"⚠️ Ваша запись на {booking['slot_date']} в {booking['slot_time']} "
                "была отменена администратором.\n"
                "Вы можете записаться снова через /start."
            ),
        )
    except Exception:
        # Пользователь мог заблокировать бота — игнорируем ошибку доставки.
        pass
