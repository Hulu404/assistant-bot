"""Конфигурация бота."""

import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0").strip())

DB_PATH: str = "bot.db"

# Доступные слоты времени: каждый час с 09:00 до 18:00 (10 слотов).
SLOT_TIMES: list[str] = [f"{hour:02d}:00" for hour in range(9, 19)]

# Названия дней недели на русском, начиная с понедельника (Monday == 0).
DAYS_RU: list[str] = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]
