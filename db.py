"""Работа с базой данных SQLite."""

import sqlite3
from datetime import date, datetime, timedelta

import config


def get_connection() -> sqlite3.Connection:
    """Вернуть соединение с БД с включённым row_factory."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создать таблицу bookings, если она ещё не существует."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                username   TEXT,
                full_name  TEXT,
                phone      TEXT,
                slot_date  TEXT NOT NULL,
                slot_time  TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (slot_date, slot_time)
            )
            """
        )


def get_week_dates() -> list[tuple[int, str, str, str]]:
    """Вернуть 7 дней начиная с сегодня.

    Каждый элемент: (day_offset, date_str, label, ddmm), где
    label = 'Сегодня' / 'Завтра' / название дня недели,
    date_str в формате YYYY-MM-DD, ddmm в формате DD.MM.
    """
    today = date.today()
    result: list[tuple[int, str, str, str]] = []
    for day_offset in range(7):
        day = today + timedelta(days=day_offset)
        date_str = day.strftime("%Y-%m-%d")
        ddmm = day.strftime("%d.%m")
        if day_offset == 0:
            label = "Сегодня"
        elif day_offset == 1:
            label = "Завтра"
        else:
            label = config.DAYS_RU[day.weekday()]
        result.append((day_offset, date_str, label, ddmm))
    return result


def get_booked_slots(slot_date: str) -> set[str]:
    """Вернуть множество забронированных времён (HH:MM) на указанную дату."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT slot_time FROM bookings WHERE slot_date = ?",
            (slot_date,),
        ).fetchall()
    return {row["slot_time"] for row in rows}


def get_past_slots(slot_date: str) -> set[str]:
    """Вернуть слоты, время которых уже наступило/прошло.

    Для будущих дат возвращает пустое множество.
    """
    if slot_date != date.today().strftime("%Y-%m-%d"):
        return set()
    now_hm = datetime.now().strftime("%H:%M")
    return {t for t in config.SLOT_TIMES if t <= now_hm}


def delete_past_bookings() -> int:
    """Удалить брони, время которых уже прошло.

    Бронь считается прошедшей, если её дата+время раньше текущего момента
    (например, слот 14:00 удаляется начиная с 14:01). Возвращает количество
    удалённых записей.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM bookings WHERE slot_date || ' ' || slot_time < ?",
            (now,),
        )
        return cursor.rowcount


def book_slot(
    user_id: int,
    username: str | None,
    full_name: str | None,
    phone: str | None,
    day_offset: int,
    slot_date: str,
    slot_time: str,
) -> int | None:
    """Забронировать слот.

    Возвращает id новой записи или None, если слот занят, уже прошёл,
    или пользователь уже записан на это время.
    """
    today = date.today().strftime("%Y-%m-%d")
    if slot_date == today and slot_time <= datetime.now().strftime("%H:%M"):
        # Слот уже наступил/прошёл (защита от устаревшей кнопки).
        return None

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    conn.isolation_level = None  # ручное управление транзакцией
    try:
        # BEGIN IMMEDIATE берёт write-lock сразу, поэтому параллельные
        # вызовы book_slot сериализуются: второй ждёт, затем его SELECT
        # уже видит чужую запись и возвращает None — гонка исключена.
        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute(
            """
            SELECT user_id FROM bookings
            WHERE slot_date = ? AND slot_time = ?
            """,
            (slot_date, slot_time),
        ).fetchone()
        if existing is not None:
            # Слот занят (тем же или другим пользователем — записаться нельзя).
            conn.execute("ROLLBACK")
            return None

        cursor = conn.execute(
            """
            INSERT INTO bookings
                (user_id, username, full_name, phone,
                 slot_date, slot_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                full_name,
                phone,
                slot_date,
                slot_time,
                created_at,
            ),
        )
        conn.execute("COMMIT")
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Подстраховка: UNIQUE (slot_date, slot_time) сработал на гонке.
        conn.execute("ROLLBACK")
        return None
    finally:
        conn.close()


def get_user_bookings(user_id: int) -> list[sqlite3.Row]:
    """Вернуть будущие записи пользователя, отсортированные по дате и времени."""
    today = date.today().strftime("%Y-%m-%d")
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT * FROM bookings
            WHERE user_id = ? AND slot_date >= ?
            ORDER BY slot_date, slot_time
            """,
            (user_id, today),
        ).fetchall()


def cancel_booking(booking_id: int, user_id: int) -> bool:
    """Удалить запись пользователя. Вернуть True, если запись была удалена."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM bookings WHERE id = ? AND user_id = ?",
            (booking_id, user_id),
        )
        return cursor.rowcount > 0


def admin_cancel_booking(booking_id: int) -> dict | None:
    """Удалить запись администратором.

    Возвращает данные удалённой записи (dict) или None, если её не было.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        return dict(row)


def get_all_bookings() -> list[sqlite3.Row]:
    """Вернуть все будущие записи, отсортированные по дате и времени."""
    today = date.today().strftime("%Y-%m-%d")
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT * FROM bookings
            WHERE slot_date >= ?
            ORDER BY slot_date, slot_time
            """,
            (today,),
        ).fetchall()


def get_booking_by_id(booking_id: int) -> sqlite3.Row | None:
    """Вернуть одну запись по её id или None."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM bookings WHERE id = ?",
            (booking_id,),
        ).fetchone()
