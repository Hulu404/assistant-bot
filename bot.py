"""Точка входа Telegram-бота для записи на встречу."""

import logging

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from telegram.ext import ContextTypes

from admin import cmd_admin_cancel, cmd_bookings
from config import BOT_TOKEN
from db import delete_past_bookings, init_db
from handlers import cmd_my, cmd_start, on_callback, on_contact

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# Как часто чистить прошедшие брони (в секундах).
CLEANUP_INTERVAL = 300


async def _cleanup_past_bookings(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Периодически удалять брони с истёкшим временем."""
    deleted = delete_past_bookings()
    if deleted:
        logger.info("Удалено прошедших броней: %d", deleted)


def main() -> None:
    """Собрать приложение, зарегистрировать хэндлеры и запустить polling."""
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("my", cmd_my))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.CONTACT, on_contact))
    app.add_handler(CommandHandler("bookings", cmd_bookings))
    app.add_handler(CommandHandler("cancel", cmd_admin_cancel))

    # Чистим прошедшие брони сразу при старте и далее по интервалу.
    app.job_queue.run_repeating(_cleanup_past_bookings, interval=CLEANUP_INTERVAL, first=0)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
