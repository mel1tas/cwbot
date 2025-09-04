import disnake
from disnake.ext import commands
import sqlite3
import os
import random
import time
import json
import asyncio
import contextlib
import re
import math
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from datetime import datetime
from typing import Union, Optional
from typing import Optional, List
from datetime import timedelta

from config import TOKEN

intents = disnake.Intents.all()

bot = commands.Bot(command_prefix="!", intents=intents)

MONEY_EMOJI = "<:kto_udalit_ban:1400415456392642572>"
CURRENCY = "€"
SHOW_BALANCE_FIELD = True

INV_PERMISSION_TIMEOUT = 120  # секунд
DEFAULT_SELL_PERCENT = 0.5
SHOP_ITEMS_PER_PAGE = 5
SHOP_VIEW_TIMEOUT = 120

# ===== Простые настройки доступа к командам =====
# Укажите здесь ID ролей (int) или строку "Administrator", которым разрешено использовать команду.
# Пустой список => команда доступна всем.
ALLOWED_SHOP = []
ALLOWED_CREATE_ITEM = ["Administrator", 1365552181020987492]
ALLOWED_DELETE_ITEM = ["Administrator"]
ALLOWED_BUY = []
ALLOWED_SELL = ["Administrator"]
ALLOWED_ITEM_INFO = []
ALLOWED_INV = []
ALLOWED_EXPORT = []
ALLOWED_USE = []
ALLOWED_GIVE_ITEM = ["Administrator", 1335508574335537192, 1335506833166827520]
ALLOWED_TAKE_ITEM = ["Administrator"]
ALLOWED_BALANCE = []
ALLOWED_PAY = []
ALLOWED_WORK = [1326654711918759988, 1326654711918759987, 1326654711905910793]
ALLOWED_SET_WORK = ["Administrator"]

# Новые права для денежных операций
ALLOWED_ADD_MONEY = ["Administrator"]
ALLOWED_REMOVE_MONEY = ["Administrator"]
ALLOWED_RESET_MONEY = ["Administrator"]
ALLOWED_ADD_MONEY_ROLE = ["Administrator"]
ALLOWED_REMOVE_MONEY_ROLE = ["Administrator"]
ALLOWED_RESET_MONEY_ROLE = ["Administrator"]

# ===== Конфигурация Всемирного банка =====
# УКАЖИТЕ ID роли Президента ниже:
PRESIDENT_ROLE_ID = 123456789012345678  # Замените на реальный ID роли Президента
DEFAULT_COMMISSION_PERCENT = 5  # по умолчанию 5%
ALLOWED_WORLDBANK = []  # просмотр доступен всем
ALLOWED_WORLDBANK_MANAGE = ["Administrator", PRESIDENT_ROLE_ID]  # управлять могут админы и Президент

# ===== Доступ для доходных ролей и коллекта =====
ALLOWED_ROLE_INCOME = ["Administrator"]  # кто может настраивать !role-income
ALLOWED_COLLECT = []  # кто может использовать !collect (пусто = все)
ALLOWED_LOG_MENU = ["Administrator"]  # кто может использовать !logmenu (пусто = все)
ALLOWED_INCOME_LIST = []  # кто может использовать !income-list (пусто = все)
ALLOWED_ROLE_COMMANDS = ["Administrator", 1365552181020987492]  # имя-метка под ваш permission-роутер

# ===== Доступ для стран =====
ALLOWED_CREATE_COUNTRY = ["Administrator"]
ALLOWED_EDIT_COUNTRY = ["Administrator"]
ALLOWED_DELETE_COUNTRY = ["Administrator"]
ALLOWED_COUNTRY_LIST = []  # список доступен всем
ALLOWED_REG_COUNTRY = ["Administrator"]
ALLOWED_UNREG_COUNTRY = ["Administrator"]

def is_user_allowed_for(allowed: list[Union[int, str]], member: disnake.Member) -> bool:
    """
    Возвращает True, если член сервера имеет доступ на основе списка allowed.
    allowed: список из чисел (ID ролей) и/или строки "Administrator".
    Пустой список => доступ всем.
    """
    if not allowed:
        return True
    # Разрешить администраторам, если явно указано "Administrator"
    if any(isinstance(x, str) and x.strip().lower() == "administrator" for x in allowed):
        if member.guild_permissions.administrator:
            return True
    user_role_ids = {r.id for r in member.roles}
    for x in allowed:
        if isinstance(x, int):
            if x in user_role_ids:
                return True
        elif isinstance(x, str):
            s = x.strip()
            if s.isdigit() and int(s) in user_role_ids:
                return True
    return False


async def ensure_allowed_ctx(ctx: commands.Context, allowed: list[Union[int, str]]) -> bool:
    """Проверяет доступ для автора команды. Возвращает True если доступ разрешён, иначе отправляет сообщение и возвращает False."""
    if not ctx.guild:
        # В ЛС роли недоступны; если список пуст — разрешаем; иначе запрещаем.
        if not allowed:
            return True
        await ctx.send(embed=error_embed("Доступ запрещён", "Эта команда должна использоваться на сервере."))
        return False
    if is_user_allowed_for(allowed, ctx.author):
        return True
    await ctx.send(embed=error_embed("Доступ запрещён", "У вас нет прав на использование этой команды."))
    return False
# ===============================================

# ===== Подсказки по использованию команд =====
USAGE_HINTS: dict[str, str] = {
    "shop": "!shop [страница]",
    "create-item": "!create-item",
    "buy": "!buy [кол-во] <название|ID>",
    "sell": "!sell [кол-во] <название|ID>",
    "item-info": "!item-info <название|ID>",
    "inv": "!inv [страница]",
    "use": "!use <название|ID> [кол-во]",
    "give-item": "!give-item @пользователь <название|ID> [кол-во]",
    "take-item": "!take-item @пользователь <название|ID> [кол-во]",
    "balance": "!balance [@пользователь]",
    "pay": "!pay @получатель <сумма>",
    "work": "!work",
    "set-work": "!set-work",
    "top": "!top [страница]",
    "help": "!help [команда]",
    "export": "!export @пользователь <Название предмета> <Кол-во> <Цена>",
    # Новые подсказки по деньгам
    "add-money": "!add-money @пользователь <сумма>",
    "remove-money": "!remove-money @пользователь <сумма>",
    "reset-money": "!reset-money @пользователь",
    "add-money-role": "!add-money-role @роль <сумма>",
    "remove-money-role": "!remove-money-role @роль <сумма>",
    "reset-money-role": "!reset-money-role @роль",
    # Всемирный банк
    "worldbank": "!worldbank",
    # Доходные роли
    "role-income": "!role-income",
    "collect": "!collect",
    "income-list": "!income-list",
    # Логи
    "logmenu": "!logmenu",
}

def usage_embed(cmd_name: str) -> disnake.Embed:
    usage = USAGE_HINTS.get(cmd_name, f"!{cmd_name}")
    return disnake.Embed(
        title="Подсказка по использованию",
        description=f"Правильное использование команды:\n`{usage}`",
        color=disnake.Color.orange()
    )
# ============================================
import math
from typing import List, Tuple, Optional

def get_db_path():
    return os.path.join(os.path.dirname(__file__), 'economy.db')

def setup_database():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            guild_id INTEGER,
            user_id INTEGER,
            balance INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventories (
            guild_id INTEGER,
            user_id INTEGER,
            item_id INTEGER,
            quantity INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, item_id)
        )
    """)

    # Рекомендуемый индекс для быстрых запросов топа по балансу
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_balances_guild_balance
        ON balances (guild_id, balance DESC)
    """)

    # УДАЛЕНО: таблица permissions и всё связанное с ней

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_settings (
            guild_id INTEGER PRIMARY KEY,
            min_income INTEGER NOT NULL,
            max_income INTEGER NOT NULL,
            cooldown_seconds INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_cooldowns (
            guild_id INTEGER,
            user_id INTEGER,
            last_ts INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    # Всемирный банк: комиссия и бюджет
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worldbank (
            guild_id INTEGER PRIMARY KEY,
            commission_percent INTEGER NOT NULL,
            bank_balance INTEGER NOT NULL
        )
    """)

    # Доходные роли: конфигурация
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_incomes (
            guild_id INTEGER,
            role_id INTEGER,
            income_type TEXT NOT NULL,       -- 'money' | 'items'
            money_amount INTEGER DEFAULT 0,  -- если income_type='money'
            items_json TEXT,                 -- JSON: [{"item_id": int, "qty": int}, ...] если income_type='items'
            cooldown_seconds INTEGER NOT NULL DEFAULT 86400,
            PRIMARY KEY (guild_id, role_id)
        )
    """)

    # Доходные роли: кулдауны по пользователю
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_income_cooldowns (
            guild_id INTEGER,
            role_id INTEGER,
            user_id INTEGER,
            last_ts INTEGER,
            PRIMARY KEY (guild_id, role_id, user_id)
        )
    """)

# Логи доходных ролей: конфигурация канала логов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_logs (
            guild_id INTEGER PRIMARY KEY,
            role_income_log_channel_id INTEGER
        )
    """)

MAX_SQL_INT = 9_223_372_036_854_775_807
MIN_SQL_INT = -9_223_372_036_854_775_808


def safe_int(v: int, *, name: str = "value", min_v: int = 0, max_v: int = MAX_SQL_INT) -> int:
    """Преобразует значение в ``int``, поддерживая человеко-понятные суффиксы.

    Поддерживаемые суффиксы (регистр не важен, пробелы игнорируются):

    - ``к`` – тысячи
    - ``кк`` или ``млн`` / ``миллион`` – миллионы
    - ``ккк`` или ``млрд`` / ``миллиард`` – миллиарды

    В числах допускаются десятичные точки и запятые (``18,3к`` или ``18.3млн``).
    Также проверяется выход за пределы допустимого диапазона SQLite.
    """
    
    try:
        if isinstance(v, str):
            s = (v or "").strip().lower().replace(" ", "").replace(",", ".")
            m = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)(ккк|кк|к|млрд|млн|миллиард|миллион)?', s)
            if not m:
                raise ValueError
            num, suffix = m.groups()
            mult_map = {
                None: 1,
                "к": 1_000,
                "кк": 1_000_000,
                "млн": 1_000_000,
                "миллион": 1_000_000,
                "ккк": 1_000_000_000,
                "млрд": 1_000_000_000,
                "миллиард": 1_000_000_000,
            }
            iv = int(float(num) * mult_map[suffix])
        else:
            iv = int(v)
    except Exception:
        raise ValueError(f"{name}: не число.")
    if iv < min_v or iv > max_v:
        raise ValueError(f"{name}: выходит за допустимые пределы [{min_v}; {max_v}].")
    return iv

def get_top_balances(guild_id: int, limit: int, offset: int = 0) -> List[Tuple[int, int]]:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, balance
        FROM balances
        WHERE guild_id = ?
        ORDER BY balance DESC, user_id ASC
        LIMIT ? OFFSET ?
    """, (guild_id, limit, offset))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_balances_count(guild_id: int) -> int:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM balances WHERE guild_id = ?", (guild_id,))
    result = cursor.fetchone()
    total = result[0] if result and result[0] is not None else 0
    conn.close()
    return total

# >>> ДОБАВИТЬ ПОСЛЕ СОЗДАНИЯ ТАБЛИЦ И ПЕРЕД conn.commit()
def ensure_role_incomes_extra_columns():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("PRAGMA table_info(role_incomes)")
    cols = {row[1] for row in c.fetchall()}

    # кто добавил запись и когда
    if "created_by" not in cols:
        c.execute("ALTER TABLE role_incomes ADD COLUMN created_by INTEGER")
    if "created_ts" not in cols:
        c.execute("ALTER TABLE role_incomes ADD COLUMN created_ts INTEGER")

    conn.commit()
    conn.close()

# вызвать миграцию
ensure_role_incomes_extra_columns()


def migrate_roles_columns():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT id, roles_required_buy, roles_required_sell, roles_granted_on_buy, roles_removed_on_buy FROM items")
    rows = c.fetchall()
    for iid, rb, rs, gb, rm in rows:
        rb2 = csv_from_ids(parse_roles_field(rb)) or None
        rs2 = csv_from_ids(parse_roles_field(rs)) or None
        gb2 = csv_from_ids(parse_roles_field(gb)) or None
        rm2 = csv_from_ids(parse_roles_field(rm)) or None
        if (rb2 != (rb or None)) or (rs2 != (rs or None)) or (gb2 != (gb or None)) or (rm2 != (rm or None)):
            c.execute("""
                UPDATE items SET roles_required_buy=?, roles_required_sell=?, roles_granted_on_buy=?, roles_removed_on_buy=?
                WHERE id=?
            """, (rb2, rs2, gb2, rm2, iid))
    conn.commit()
    conn.close()


def get_balance(guild_id: int, user_id: int) -> int:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM balances WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    result = cursor.fetchone()
    if result:
        balance = result[0]
    else:
        cursor.execute("INSERT INTO balances (guild_id, user_id, balance) VALUES (?, ?, ?)", (guild_id, user_id, 0))
        conn.commit()
        balance = 0
    conn.close()
    return balance

def update_balance(guild_id: int, user_id: int, amount: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO balances (guild_id, user_id, balance) VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = balance + ?
    """, (guild_id, user_id, amount, amount))
    conn.commit()
    conn.close()

def set_balance(guild_id: int, user_id: int, new_balance: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO balances (guild_id, user_id, balance) VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = excluded.balance
    """, (guild_id, user_id, new_balance))
    conn.commit()
    conn.close()

# >>> ВСТАВИТЬ В БЛОК DB-ХЕЛПЕРОВ (рядом с другими функциями для sqlite)

def admin_reset_inventories(guild_id: int) -> tuple[int, int]:
    """
    Сбрасывает инвентари всех пользователей: DELETE FROM inventories WHERE guild_id=?
    Возвращает (deleted_rows, users_affected)
    """
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM inventories WHERE guild_id = ?", (guild_id,))
    total_rows, users = c.fetchone() or (0, 0)
    c.execute("DELETE FROM inventories WHERE guild_id = ?", (guild_id,))
    conn.commit()
    conn.close()
    return int(total_rows or 0), int(users or 0)

def admin_reset_balances(guild_id: int) -> tuple[int, int, int]:
    """
    Сбрасывает балансы всех пользователей до 0.
    Возвращает (affected_rows, total_rows, sum_before)
    """
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(SUM(balance),0) FROM balances WHERE guild_id = ?", (guild_id,))
    total_rows, sum_before = c.fetchone() or (0, 0)
    c.execute("UPDATE balances SET balance = 0 WHERE guild_id = ? AND balance != 0", (guild_id,))
    affected = c.rowcount or 0
    conn.commit()
    conn.close()
    return int(affected), int(total_rows or 0), int(sum_before or 0)

def admin_reset_worldbank(guild_id: int) -> tuple[int, int]:
    """
    Сбрасывает бюджет Всемирного банка до 0. Комиссию не трогаем.
    Возвращает (before, after)
    """
    conn = sqlite3.connect(get_db_path())
    _ensure_worldbank_row(conn, guild_id)
    c = conn.cursor()
    c.execute("SELECT bank_balance FROM worldbank WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    before = int(row[0]) if row else 0
    c.execute("UPDATE worldbank SET bank_balance = 0 WHERE guild_id = ?", (guild_id,))
    conn.commit()
    conn.close()
    return before, 0

def admin_clear_shop(guild_id: int) -> dict:
    """
    Полная очистка магазина:
      - собираем список item_id для гильдии,
      - удаляем инвентари только по этим item_id,
      - чистим item_shop_state, item_user_daily,
      - удаляем сами items.
    Возвращает словарь с подсчитанной статистикой.
    """
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()

    # Сбор статистики до удаления
    c.execute("SELECT id FROM items WHERE guild_id = ?", (guild_id,))
    item_ids = [int(r[0]) for r in c.fetchall()]

    stats = {
        "items": len(item_ids),
        "inv_rows": 0,
        "shop_state": 0,
        "user_daily": 0,
    }

    if item_ids:
        # Сколько записей инвентарей будет удалено
        placeholders = ",".join("?" for _ in item_ids)
        c.execute(f"SELECT COUNT(*) FROM inventories WHERE guild_id = ? AND item_id IN ({placeholders})", (guild_id, *item_ids))
        stats["inv_rows"] = int(c.fetchone()[0] or 0)

        # Удалить инвентари по этим предметам
        c.execute(f"DELETE FROM inventories WHERE guild_id = ? AND item_id IN ({placeholders})", (guild_id, *item_ids))

    # Состояние магазина
    c.execute("SELECT COUNT(*) FROM item_shop_state WHERE guild_id = ?", (guild_id,))
    stats["shop_state"] = int(c.fetchone()[0] or 0)
    c.execute("DELETE FROM item_shop_state WHERE guild_id = ?", (guild_id,))

    # Дневные лимиты
    c.execute("SELECT COUNT(*) FROM item_user_daily WHERE guild_id = ?", (guild_id,))
    stats["user_daily"] = int(c.fetchone()[0] or 0)
    c.execute("DELETE FROM item_user_daily WHERE guild_id = ?", (guild_id,))

    # Удалить сами предметы
    c.execute("DELETE FROM items WHERE guild_id = ?", (guild_id,))

    conn.commit()
    conn.close()
    return stats

def admin_clear_role_incomes(guild_id: int) -> tuple[int, int]:
    """
    Удаляет все доходные роли и их кулдауны для гильдии.
    Возвращает (roles_deleted, cooldown_rows_deleted)
    """
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM role_incomes WHERE guild_id = ?", (guild_id,))
    roles_deleted = int(c.fetchone()[0] or 0)
    c.execute("DELETE FROM role_incomes WHERE guild_id = ?", (guild_id,))

    c.execute("SELECT COUNT(*) FROM role_income_cooldowns WHERE guild_id = ?", (guild_id,))
    cds_deleted = int(c.fetchone()[0] or 0)
    c.execute("DELETE FROM role_income_cooldowns WHERE guild_id = ?", (guild_id,))

    conn.commit()
    conn.close()
    return roles_deleted, cds_deleted

# ======== Всемирный банк: функции БД ========
def _ensure_worldbank_row(conn, guild_id: int):
    c = conn.cursor()
    c.execute("SELECT commission_percent, bank_balance FROM worldbank WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO worldbank (guild_id, commission_percent, bank_balance) VALUES (?, ?, ?)",
                  (guild_id, DEFAULT_COMMISSION_PERCENT, 0))
        conn.commit()

def get_worldbank(guild_id: int) -> tuple[int, int]:
    conn = sqlite3.connect(get_db_path())
    _ensure_worldbank_row(conn, guild_id)
    c = conn.cursor()
    c.execute("SELECT commission_percent, bank_balance FROM worldbank WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return DEFAULT_COMMISSION_PERCENT, 0
    return int(row[0]), int(row[1])

def set_commission_percent(guild_id: int, percent: int):
    conn = sqlite3.connect(get_db_path())
    _ensure_worldbank_row(conn, guild_id)
    c = conn.cursor()
    c.execute("UPDATE worldbank SET commission_percent = ? WHERE guild_id = ?", (percent, guild_id))
    conn.commit()
    conn.close()

def change_worldbank_balance(guild_id: int, delta: int) -> bool:
    conn = sqlite3.connect(get_db_path())
    _ensure_worldbank_row(conn, guild_id)
    c = conn.cursor()
    c.execute("SELECT bank_balance FROM worldbank WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    cur = int(row[0]) if row else 0
    new_val = cur + int(delta)
    if new_val < 0:
        conn.close()
        return False
    c.execute("UPDATE worldbank SET bank_balance = ? WHERE guild_id = ?", (new_val, guild_id))
    conn.commit()
    conn.close()
    return True

def get_worldbank_balance(guild_id: int) -> int:
    return get_worldbank(guild_id)[1]


def setup_country_tables():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    # Базовое создание
    c.execute("""
        CREATE TABLE IF NOT EXISTS countries (
            guild_id INTEGER,
            code TEXT,
            name TEXT NOT NULL,
            flag TEXT,
            ruler TEXT,
            continent TEXT,
            territory_km2 INTEGER,
            population INTEGER,
            sea_access INTEGER,
            created_by INTEGER,
            created_ts INTEGER,
            updated_ts INTEGER,
            license_role_id INTEGER,
            PRIMARY KEY (guild_id, code)
        )
    """)
    # Регистрации
    c.execute("""
        CREATE TABLE IF NOT EXISTS country_registrations (
            guild_id INTEGER,
            code TEXT,
            user_id INTEGER,
            registered_ts INTEGER,
            PRIMARY KEY (guild_id, code),
            UNIQUE (guild_id, user_id)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_countries_name ON countries (guild_id, name)")
    # Миграция license_role_id
    c.execute("PRAGMA table_info(countries)")
    cols = {row[1] for row in c.fetchall()}
    if "license_role_id" not in cols:
        c.execute("ALTER TABLE countries ADD COLUMN license_role_id INTEGER")
    conn.commit()
    conn.close()


@bot.listen("on_ready")
async def _countries_reviews_on_ready():
    setup_country_tables()
    print("Таблицы стран и отзывов готовы.")
    
    
CONTINENTS = [
    "Африка",
    "Антарктида",
    "Азия",
    "Европа",
    "Северная Америка",
    "Южная Америка",
    "Австралия и Океания"
]

def _now_ts() -> int:
    return int(time.time())

def country_get_by_code_or_name(guild_id: int, code_or_name: str) -> Optional[dict]:
    if not code_or_name:
        return None
    q = code_or_name.strip()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Сначала точный код (верхний регистр)
    c.execute("SELECT * FROM countries WHERE guild_id=? AND upper(code)=upper(?)", (guild_id, q))
    row = c.fetchone()
    if not row:
        # По имени (LIKE, без учета регистра)
        c.execute("SELECT * FROM countries WHERE guild_id=? AND lower(name)=lower(?)", (guild_id, q))
        row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def country_exists_code(guild_id: int, code: str) -> bool:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT 1 FROM countries WHERE guild_id=? AND upper(code)=upper(?)", (guild_id, code.strip()))
    ok = c.fetchone() is not None
    conn.close()
    return ok

def country_insert_or_update(
    guild_id: int,
    old_code: Optional[str],
    code: str,
    name: str,
    flag: str,
    ruler: str,
    continent: str,
    territory_km2: int,
    population: int,
    sea_access: bool,
    actor_id: int,
    license_role_id: Optional[int] = None
) -> tuple[bool, str | None]:
    code = code.strip().upper()
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    ts = _now_ts()
    try:
        if old_code is None:
            if country_exists_code(guild_id, code):
                conn.close()
                return False, "Страна с таким кодом уже существует."
            c.execute("""
                INSERT INTO countries
                (guild_id, code, name, flag, ruler, continent, territory_km2, population, sea_access,
                 created_by, created_ts, updated_ts, license_role_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (guild_id, code, name, flag, ruler, continent, territory_km2, population, 1 if sea_access else 0,
                  actor_id, ts, ts, license_role_id))
            conn.commit()
        else:
            # проверка смены кода
            if old_code.strip().upper() != code and country_exists_code(guild_id, code):
                conn.close()
                return False, "Новый код уже занят другой страной."
            c.execute("""
                UPDATE countries
                   SET code=?, name=?, flag=?, ruler=?, continent=?, territory_km2=?, population=?,
                       sea_access=?, updated_ts=?, license_role_id=?
                 WHERE guild_id=? AND upper(code)=upper(?)
            """, (code, name, flag, ruler, continent, territory_km2, population,
                  1 if sea_access else 0, ts, license_role_id, guild_id, old_code.strip().upper()))
            if c.rowcount == 0:
                conn.close()
                return False, "Страна для редактирования не найдена."
            if old_code.strip().upper() != code:
                c.execute("""
                    UPDATE country_registrations
                       SET code=?
                     WHERE guild_id=? AND upper(code)=upper(?)
                """, (code, guild_id, old_code.strip().upper()))
            conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Ошибка базы данных: {e}"
    conn.close()
    return True, None

# === НОРМАЛИЗАЦИЯ ФЛАГОВ ===
FLAG_ALIAS_RE = re.compile(r"^:flag_([a-z]{2}):$", re.I)

def code_to_flag_emoji(code: str) -> str:
    """
    Превращает ISO-код страны (например, 'KZ') в региональные индикаторы (флаг-эмодзи).
    """
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    base = 0x1F1E6
    return "".join(chr(base + (ord(ch) - ord('A'))) for ch in code)

def normalize_flag_emoji(flag_raw: str, code_hint: Optional[str] = None) -> str:
    """
    Превращает ':flag_kz:' в '🇰🇿'. Если передан Unicode — вернёт как есть.
    Если flag_raw пуст, а есть code_hint — можно fallback-ом построить флаг по коду.
    """
    if not flag_raw and code_hint:
        return code_to_flag_emoji(code_hint)

    s = (flag_raw or "").strip()
    m = FLAG_ALIAS_RE.fullmatch(s)
    if m:
        return code_to_flag_emoji(m.group(1))

    # Если уже юникод-флаг — возвращаем как есть
    return s

def country_get_registration_for_user(guild_id: int, user_id: int) -> Optional[str]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT code FROM country_registrations WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def country_get_occupant(guild_id: int, code: str) -> Optional[int]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT user_id FROM country_registrations WHERE guild_id=? AND upper(code)=upper(?)", (guild_id, code.strip().upper()))
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else None

def country_delete(guild_id: int, code_or_name: str) -> tuple[bool, str | None, Optional[str]]:
    """
    Возвращает (успех, ошибка, удалённый_код)
    """
    info = country_get_by_code_or_name(guild_id, code_or_name)
    if not info:
        return False, "Страна не найдена.", None
    code = info["code"]
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    try:
        c.execute("DELETE FROM country_registrations WHERE guild_id=? AND upper(code)=upper(?)", (guild_id, code))
        c.execute("DELETE FROM countries WHERE guild_id=? AND upper(code)=upper(?)", (guild_id, code))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Ошибка удаления: {e}", None
    conn.close()
    return True, None, code

def countries_list_all(guild_id: int) -> list[dict]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM countries WHERE guild_id=? ORDER BY name COLLATE NOCASE", (guild_id,))
    rows = [dict(r) for r in c.fetchall()]
    # Подтянем регистрации
    c.execute("SELECT code, user_id FROM country_registrations WHERE guild_id=?", (guild_id,))
    reg = {(r[0] or "").upper(): int(r[1]) for r in c.fetchall()}
    conn.close()
    for r in rows:
        r["registered_user_id"] = reg.get((r["code"] or "").upper())
    return rows

def country_register_user(guild_id: int, code: str, user_id: int) -> tuple[bool, str | None]:
    code = code.strip().upper()
    # Проверим, что страна есть
    if not country_exists_code(guild_id, code):
        return False, "Страна с таким кодом не найдена."
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    try:
        # Пользователь не должен быть уже зарегистрирован на другую страну
        c.execute("SELECT code FROM country_registrations WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        row = c.fetchone()
        if row:
            conn.close()
            return False, f"Пользователь уже зарегистрирован на страну с кодом {row[0]}."
        # Страна не должна быть занята
        c.execute("SELECT user_id FROM country_registrations WHERE guild_id=? AND upper(code)=upper(?)", (guild_id, code))
        row = c.fetchone()
        if row:
            conn.close()
            return False, "Эта страна уже занята другим пользователем."
        c.execute("INSERT INTO country_registrations (guild_id, code, user_id, registered_ts) VALUES (?, ?, ?, ?)",
                  (guild_id, code, user_id, _now_ts()))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Ошибка базы данных: {e}"
    conn.close()
    return True, None

def country_unregister_user(guild_id: int, user_id: int) -> tuple[bool, str | None, Optional[str]]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT code FROM country_registrations WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "Этот пользователь не зарегистрирован ни на одну страну.", None
    code = row[0]
    try:
        c.execute("DELETE FROM country_registrations WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Ошибка базы данных: {e}", None
    conn.close()
    return True, None, code

from dataclasses import dataclass

@dataclass
class CountryDraft:
    editing_code: Optional[str] = None
    name: str = ""
    flag: str = ""
    code: str = ""
    ruler: str = ""
    continent: Optional[str] = None
    territory_km2: Optional[int] = None
    population: Optional[int] = None
    sea_access: Optional[bool] = None
    license_role_id: Optional[int] = None   # <<< НОВОЕ


def _ok(v) -> bool:
    return v not in (None, "", 0)

def _chip(ok: bool) -> str:
    return "✅" if ok else "❌"

def _fmt_bool(b: Optional[bool]) -> str:
    if b is None:
        return "—"
    return "Присутствует" if b else "Отсутствует"

class CountryNameModal(disnake.ui.Modal):
    def __init__(self, view_ref, draft: CountryDraft):
        components = [
            disnake.ui.TextInput(label="Название страны", custom_id="name", style=disnake.TextInputStyle.short, max_length=64, required=True, value=draft.name)
        ]
        super().__init__(title="Название страны", components=components)
        self.view_ref = view_ref
    async def callback(self, inter: disnake.ModalInteraction):
        name = inter.text_values["name"].strip()
        if not name:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Название не может быть пустым."), ephemeral=True)
        self.view_ref.draft.name = name
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)

class CountryFlagModal(disnake.ui.Modal):
    def __init__(self, view_ref, draft: CountryDraft):
        components = [disnake.ui.TextInput(label="Эмодзи флага страны", custom_id="flag", style=disnake.TextInputStyle.short, max_length=16, required=True, value=draft.flag)]
        super().__init__(title="Флаг страны", components=components)
        self.view_ref = view_ref
    async def callback(self, inter: disnake.ModalInteraction):
        raw = inter.text_values["flag"].strip()
        if not raw:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Укажите эмодзи флага."), ephemeral=True)
        # НОРМАЛИЗАЦИЯ: ':flag_kz:' -> '🇰🇿'
        normalized = normalize_flag_emoji(raw, code_hint=(self.view_ref.draft.code or None))
        self.view_ref.draft.flag = normalized
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)

class CountryCodeModal(disnake.ui.Modal):
    def __init__(self, view_ref, draft: CountryDraft):
        components = [disnake.ui.TextInput(label="Код страны (буквы)", custom_id="code", style=disnake.TextInputStyle.short, max_length=8, required=True, value=draft.code)]
        super().__init__(title="Код страны", components=components)
        self.view_ref = view_ref
    async def callback(self, inter: disnake.ModalInteraction):
        code = inter.text_values["code"].strip().upper()
        if not re.fullmatch(r"[A-ZА-ЯЁ]{2,8}", code):
            return await inter.response.send_message(embed=error_embed("Ошибка", "Код должен состоять из 2–8 букв."), ephemeral=True)
        # Если создаём новую — проверим уникальность сразу
        if self.view_ref.draft.editing_code is None and country_exists_code(inter.guild.id, code):
            return await inter.response.send_message(embed=error_embed("Ошибка", "Страна с таким кодом уже существует."), ephemeral=True)
        self.view_ref.draft.code = code
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)

class CountryRulerModal(disnake.ui.Modal):
    def __init__(self, view_ref, draft: CountryDraft):
        components = [disnake.ui.TextInput(label="Правитель страны", custom_id="ruler", style=disnake.TextInputStyle.short, max_length=64, required=True, value=draft.ruler)]
        super().__init__(title="Правитель страны", components=components)
        self.view_ref = view_ref
    async def callback(self, inter: disnake.ModalInteraction):
        val = inter.text_values["ruler"].strip()
        if not val:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Укажите имя правителя."), ephemeral=True)
        self.view_ref.draft.ruler = val
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)

class CountryNumberModal(disnake.ui.Modal):
    def __init__(self, view_ref, label: str, field_key: str, value: Optional[int]):
        components = [disnake.ui.TextInput(label=label, custom_id="num", style=disnake.TextInputStyle.short, required=True, value=(str(value) if value else ""))]
        super().__init__(title=label, components=components)
        self.view_ref = view_ref
        self.field_key = field_key
    async def callback(self, inter: disnake.ModalInteraction):
        raw = inter.text_values["num"].strip()
        try:
            num = safe_int(raw, name="Число", min_v=1)
        except ValueError as e:
            return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)
        if self.field_key == "territory":
            self.view_ref.draft.territory_km2 = num
        elif self.field_key == "population":
            self.view_ref.draft.population = num
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)

class ContinentSelectView(disnake.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=60)
        self.parent_view = parent_view

    @disnake.ui.string_select(
        custom_id="continent_select",
        placeholder="Выберите континент",
        options=[disnake.SelectOption(label=c, value=c) for c in CONTINENTS]
    )
    async def on_select(self, select: disnake.ui.StringSelect, inter: disnake.MessageInteraction):
        self.parent_view.draft.continent = select.values[0]
        await inter.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)

class SeaAccessSelectView(disnake.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=60)
        self.parent_view = parent_view

    @disnake.ui.string_select(
        custom_id="sea_access_select",
        placeholder="Выберите наличие выхода в море",
        options=[
            disnake.SelectOption(label="Присутствует", value="yes"),
            disnake.SelectOption(label="Отсутствует", value="no"),
        ]
    )
    async def on_select(self, select: disnake.ui.StringSelect, inter: disnake.MessageInteraction):
        self.parent_view.draft.sea_access = (select.values[0] == "yes")
        await inter.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)

# ===== Вью выбора лицензии (универсальная) =====

def build_license_pick_embed(invoker: disnake.Member, title: str = "Выбор роли лицензии", current_role_id: Optional[int] = None) -> disnake.Embed:
    cur_txt = f"Текущая: <@&{current_role_id}>\n" if current_role_id else ""
    e = disnake.Embed(
        title=title,
        description=(cur_txt + "Выберите роль (можно искать) и нажмите «Подтвердить»."),
        color=disnake.Color.from_rgb(88, 101, 242)
    )
    e.set_author(name=invoker.display_name, icon_url=invoker.display_avatar.url)
    return e


class LicenseRolePickView(disnake.ui.View):
    """
    Универсальное окно выбора роли лицензии в стиле !role-income:
    - RoleSelect с поиском
    - Кнопки Подтвердить/Отмена
    - Ephemeral
    """
    def __init__(
        self,
        ctx: commands.Context,
        on_pick,  # async def (role_id: int, inter: disnake.MessageInteraction) -> None
        current_role_id: Optional[int] = None,
        timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.on_pick = on_pick
        self.current_role_id = current_role_id
        self.message: Optional[disnake.Message] = None
        self._chosen_role_id: Optional[int] = None

        # Выбор роли (как в !role-income: с поиском, 1 значение)
        self.role_select = disnake.ui.RoleSelect(
            custom_id="license_pick_role",
            placeholder="Выберите роль лицензии (можно искать)",
            min_values=1,
            max_values=1
        )
        self.btn_confirm = disnake.ui.Button(label="Подтвердить", style=disnake.ButtonStyle.primary, custom_id="license_pick_confirm")
        self.btn_cancel  = disnake.ui.Button(label="Отмена",      style=disnake.ButtonStyle.secondary, custom_id="license_pick_cancel")

        async def on_role_pick(i: disnake.MessageInteraction):
            picked = self.role_select.values[0] if self.role_select.values else None
            if not picked:
                return await i.response.send_message("Не удалось определить роль.", ephemeral=True)
            if picked.is_default():
                return await i.response.send_message("Нельзя выбрать @everyone.", ephemeral=True)
            self._chosen_role_id = int(picked.id)
            await i.response.defer()

        async def on_confirm(i: disnake.MessageInteraction):
            if not self._chosen_role_id:
                return await i.response.send_message("Сначала выберите роль.", ephemeral=True)
            await self.on_pick(self._chosen_role_id, i)
            # Закрываем мини-меню
            try:
                await i.response.edit_message(content=f"✅ Роль выбрана: <@&{self._chosen_role_id}>", view=None, embed=None)
            except Exception:
                await i.followup.send(f"✅ Роль выбрана: <@&{self._chosen_role_id}>", ephemeral=True)

        async def on_cancel(i: disnake.MessageInteraction):
            try:
                await i.response.edit_message(content="Отменено.", view=None, embed=None)
            except Exception:
                await i.followup.send("Отменено.", ephemeral=True)

        self.role_select.callback = on_role_pick
        self.btn_confirm.callback = on_confirm
        self.btn_cancel.callback = on_cancel

        self.add_item(self.role_select)
        self.add_item(self.btn_confirm)
        self.add_item(self.btn_cancel)

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.ctx.author.id:
            await inter.response.send_message("Это меню не для вас.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        try:
            for c in self.children:
                if isinstance(c, (disnake.ui.Button, disnake.ui.SelectBase)):
                    c.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

class CountryWizard(disnake.ui.View):
    def __init__(self, ctx: commands.Context, existing: Optional[dict] = None):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.message: Optional[disnake.Message] = None
        self.draft = CountryDraft()
        if existing:
            self.draft.editing_code = existing["code"]
            self.draft.name = existing.get("name") or ""
            self.draft.flag = existing.get("flag") or ""
            self.draft.code = existing.get("code") or ""
            self.draft.ruler = existing.get("ruler") or ""
            self.draft.continent = existing.get("continent") or None
            self.draft.territory_km2 = existing.get("territory_km2")
            self.draft.population = existing.get("population")
            self.draft.license_role_id = existing.get("license_role_id")
            if existing.get("sea_access") is not None:
                self.draft.sea_access = bool(int(existing["sea_access"]))

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Эта панель доступна только создателю.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> disnake.Embed:
        e = disnake.Embed(
            title="Cоздание страны" if self.draft.editing_code is None else "Редактирование страны",
            color=disnake.Color.blurple()
        )
        e.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)
        # Прогресс: 8 шагов
        steps_ok = [
            _ok(self.draft.name),
            _ok(self.draft.flag),
            _ok(self.draft.code),
            _ok(self.draft.ruler),
            _ok(self.draft.continent),
            _ok(self.draft.territory_km2),
            _ok(self.draft.population),
            self.draft.sea_access is not None
        ]
        nums = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣"]
        progress = "  ".join(f"{nums[i]} {_chip(ok)}" for i, ok in enumerate(steps_ok))
        e.description = f"Прогресс: {progress}"

        lic_str = f"<@&{self.draft.license_role_id}>" if self.draft.license_role_id else "—"
        e.add_field(
            name="Параметры страны",
            value="\n".join([
                f"• Название страны: {self.draft.name or '—'}",
                f"• Флаг страны: {self.draft.flag or '—'}",
                f"• Код страны: {self.draft.code or '—'}",
                f"• Правитель: {self.draft.ruler or '—'}",
                f"• Континент: {self.draft.continent or '—'}",
                f"• Территория: {format_number(self.draft.territory_km2) + ' км²' if self.draft.territory_km2 else '—'}",
                f"• Население: {format_number(self.draft.population) if self.draft.population else '—'}",
                f"• Выход в море: {_fmt_bool(self.draft.sea_access)}",
                f"• Лицензия: {lic_str}",
            ]),
            inline=False
        )
        e.add_field(
            name="Подсказки",
            value=(
                "• Заполняйте параметры кнопками ниже.\n"
                "• Код страны должен быть уникальным и состоит из букв (например: RU, FRA).\n"
                "• Континент и «Выход в море» выбираются из меню.\n"
                "• Нажмите «Создать страну» или «Сохранить» после завершения."
            ),
            inline=False
        )
        # Если уже есть регистрация — покажем, кто привязан
        if self.draft.editing_code:
            # Найдем пользователя, зарегистрированного на эту страну
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()
            c.execute("SELECT user_id FROM country_registrations WHERE guild_id=? AND upper(code)=upper(?)", (self.ctx.guild.id, self.draft.editing_code))
            row = c.fetchone()
            conn.close()
            if row:
                user = self.ctx.guild.get_member(int(row[0]))
                e.add_field(name="Пользователь", value=(user.mention if user else f"<@{row[0]}>"), inline=False)
        return e

    @disnake.ui.button(label="Название", style=disnake.ButtonStyle.primary, row=0)
    async def btn_name(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(CountryNameModal(self, self.draft))

    @disnake.ui.button(label="Флаг", style=disnake.ButtonStyle.primary, row=0)
    async def btn_flag(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(CountryFlagModal(self, self.draft))

    @disnake.ui.button(label="Код страны", style=disnake.ButtonStyle.primary, row=0)
    async def btn_code(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(CountryCodeModal(self, self.draft))

    @disnake.ui.button(label="Правитель", style=disnake.ButtonStyle.primary, row=0)
    async def btn_ruler(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(CountryRulerModal(self, self.draft))

    @disnake.ui.button(label="Континент", style=disnake.ButtonStyle.secondary, row=1)
    async def btn_continent(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.edit_message(embed=self.build_embed(), view=ContinentSelectView(self))

    @disnake.ui.button(label="Территория", style=disnake.ButtonStyle.secondary, row=1)
    async def btn_territory(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(CountryNumberModal(self, "Размер территории (км²) — только числа", "territory", self.draft.territory_km2))

    @disnake.ui.button(label="Население", style=disnake.ButtonStyle.secondary, row=1)
    async def btn_population(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(CountryNumberModal(self, "Население — только числа", "population", self.draft.population))

    @disnake.ui.button(label="Выход в море", style=disnake.ButtonStyle.secondary, row=1)
    async def btn_sea(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.edit_message(embed=self.build_embed(), view=SeaAccessSelectView(self))
    
    @disnake.ui.button(label="Лицензия", style=disnake.ButtonStyle.secondary, custom_id="step_license", row=1)
    async def _open_license(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        async def on_pick(role_id: int, i: disnake.MessageInteraction):
            self.draft.license_role_id = role_id
            # Обновим главное сообщение мастера
            if self.message:
                with contextlib.suppress(Exception):
                    await self.message.edit(embed=self.build_embed(), view=self)

        emb = build_license_pick_embed(
            invoker=inter.user,
            title="Выбор роли лицензии для страны",
            current_role_id=self.draft.license_role_id
        )

        picker = LicenseRolePickView(self.ctx, on_pick=on_pick, current_role_id=self.draft.license_role_id)
        try:
            await inter.response.send_message(embed=emb, view=picker, ephemeral=True)
        except Exception:
            await inter.followup.send(embed=emb, view=picker, ephemeral=True)

        with contextlib.suppress(Exception):
            picker.message = await inter.original_message()

    @disnake.ui.button(label="Создать страну", style=disnake.ButtonStyle.success, row=2)
    async def btn_save(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        d = self.draft
        if not all([
            d.name.strip(),
            d.flag.strip(),
            d.code.strip(),
            d.ruler.strip(),
            d.continent,
            isinstance(d.territory_km2, int) and d.territory_km2 > 0,
            isinstance(d.population, int) and d.population > 0,
            d.sea_access is not None
        ]):
            return await inter.response.send_message(embed=error_embed("Ошибка", "Заполните все параметры перед сохранением."), ephemeral=True)

        ok, err = country_insert_or_update(
            guild_id=inter.guild.id,
            old_code=d.editing_code,
            code=d.code,
            name=d.name,
            flag=d.flag,
            ruler=d.ruler,
            continent=d.continent,
            territory_km2=d.territory_km2,
            population=d.population,
            sea_access=bool(d.sea_access),
            actor_id=inter.user.id,
            license_role_id=self.draft.license_role_id
        )
        if not ok:
            return await inter.response.send_message(embed=error_embed("Не удалось сохранить", err or "Неизвестная ошибка."), ephemeral=True)

        title = "✅ Страна создана" if d.editing_code is None else "✅ Изменения сохранены"
        lic_txt = f"<@&{d.license_role_id}>" if d.license_role_id else "—"
        done = disnake.Embed(title=title, color=disnake.Color.green())
        done.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)
        done.description = (
            f"{d.flag} {d.name} ({d.code})\n"
            f"Правитель: {d.ruler}\n"
            f"Континент: {d.continent}\n"
            f"Территория: {format_number(d.territory_km2)} км²\n"
            f"Население: {format_number(d.population)}\n"
            f"Выход в море: {_fmt_bool(d.sea_access)}\n"
            f"Лицензия: {lic_txt}"
        )
        await inter.response.edit_message(embed=done, view=None)

    async def on_timeout(self):
        try:
            for child in self.children:
                if isinstance(child, (disnake.ui.Button, disnake.ui.SelectBase)):
                    child.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass
        
        
class RoleSearchModal(disnake.ui.Modal):
    def __init__(self, view_ref, title="Поиск роли"):
        components = [
            disnake.ui.TextInput(
                label="Введите часть названия роли",
                custom_id="query",
                style=disnake.TextInputStyle.short,
                required=False,
                placeholder="например: экономика"
            )
        ]
        super().__init__(title=title, components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        query = (inter.text_values.get("query") or "").strip().lower()
        self.view_ref.update_options(query)
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)

class RoleSelectView(disnake.ui.View):
    """
    Универсальный выбор роли с поиском. on_pick(role_id) — коллбек для установки значения.
    """
    def __init__(self, ctx: commands.Context, title: str, on_pick):
        super().__init__(timeout=120)
        self.ctx = ctx
        self._title = title
        self._on_pick = on_pick
        self._query = ""
        self.message: Optional[disnake.Message] = None

        self.select = disnake.ui.StringSelect(
            placeholder="Выберите роль… (до 25 совпадений)",
            min_values=1, max_values=1, options=[]
        )
        self.select.callback = self._select_cb
        self.add_item(self.select)
        # кнопка поиска
        self.add_item(disnake.ui.Button(label="Поиск роли", style=disnake.ButtonStyle.secondary, custom_id="search_btn"))
        # привяжем обработчик к кнопке
        for child in self.children:
            if isinstance(child, disnake.ui.Button) and child.custom_id == "search_btn":
                async def _open_modal(inter: disnake.MessageInteraction):
                    await inter.response.send_modal(RoleSearchModal(self, title="Поиск роли"))
                child.callback = _open_modal
                break

        self.update_options("")

    def _roles_by_query(self, query: str) -> list[disnake.Role]:
        roles = [r for r in self.ctx.guild.roles if r != self.ctx.guild.default_role]
        if query:
            roles = [r for r in roles if query in r.name.lower()]
        roles.sort(key=lambda r: r.position, reverse=True)
        return roles[:25]

    def update_options(self, query: str):
        self._query = query or ""
        roles = self._roles_by_query(self._query)
        opts = [disnake.SelectOption(label=r.name, value=str(r.id), description=f"ID: {r.id}") for r in roles]
        self.select.options = opts

    def build_embed(self) -> disnake.Embed:
        e = disnake.Embed(title=self._title, description=("Отфильтровано по: " + (self._query or "—")), color=disnake.Color.blurple())
        e.set_author(name=self.ctx.guild.name, icon_url=getattr(self.ctx.guild.icon, "url", None))
        return e

    async def _select_cb(self, inter: disnake.MessageInteraction):
        role_id = int(self.select.values[0])
        await inter.response.defer()
        # коллбек родителя
        await self._on_pick(role_id)
        # завершаем вспомогательное меню
        try:
            for ch in self.children:
                if isinstance(ch, (disnake.ui.Button, disnake.ui.StringSelect)):
                    ch.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except:
            pass
        
        
@bot.command(name="create-country")
async def create_country_cmd(ctx: commands.Context):
    if not await ensure_allowed_ctx(ctx, ALLOWED_CREATE_COUNTRY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    view = CountryWizard(ctx)
    emb = view.build_embed()
    msg = await ctx.send(embed=emb, view=view)
    view.message = msg

@bot.command(name="edit-country")
async def edit_country_cmd(ctx: commands.Context, *, code_or_name: str):
    if not await ensure_allowed_ctx(ctx, ALLOWED_EDIT_COUNTRY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    info = country_get_by_code_or_name(ctx.guild.id, code_or_name)
    if not info:
        return await ctx.send(embed=error_embed("Не найдено", f"Страна «{code_or_name}» не найдена."))
    view = CountryWizard(ctx, existing=info)
    emb = view.build_embed()
    msg = await ctx.send(embed=emb, view=view)
    view.message = msg

@bot.command(name="delete-country")
async def delete_country_cmd(ctx: commands.Context, *, code_or_name: str):
    if not await ensure_allowed_ctx(ctx, ALLOWED_DELETE_COUNTRY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    info = country_get_by_code_or_name(ctx.guild.id, code_or_name)
    if not info:
        return await ctx.send(embed=error_embed("Не найдено", f"Страна «{code_or_name}» не найдена."))
    warn = disnake.Embed(
        title="Удаление страны",
        description=f"Вы уверены, что хотите удалить {info.get('flag') or ''} {info['name']} ({info['code']})?\nВведите в чат: удалить",
        color=disnake.Color.red()
    )
    prompt = await ctx.send(embed=warn)
    def check(m: disnake.Message):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
    try:
        msg = await ctx.bot.wait_for("message", check=check, timeout=30.0)
        with contextlib.suppress(Exception):
            await msg.delete()
        if msg.content.strip().lower() != "удалить":
            with contextlib.suppress(Exception):
                await prompt.delete()
            return await ctx.send("Удаление отменено.", delete_after=10)
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            await prompt.delete()
        return await ctx.send("Время на подтверждение истекло.", delete_after=10)
    ok, err, del_code = country_delete(ctx.guild.id, code_or_name)
    if not ok:
        return await ctx.send(embed=error_embed("Ошибка", err or "Не удалось удалить."))
    done = disnake.Embed(title="✅ Удалено", description=f"Страна ({info['flag']}) {info['name']} ({info['code']}) удалена.", color=disnake.Color.green())
    await ctx.send(embed=done)

class CountryListView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, data: list[dict]):
        super().__init__(timeout=120.0)  # только keyword-аргумент timeout
        self.ctx = ctx
        self.data = data
        self.page = 0
        self.per_page = 5
        self.max_page = max(0, (len(self.data) - 1) // self.per_page)
        self.author_id = ctx.author.id

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Эта панель доступна только инициатору.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> disnake.Embed:
        e = disnake.Embed(title="Список стран", color=disnake.Color.blurple())
        e.set_author(name=self.ctx.guild.name, icon_url=getattr(self.ctx.guild.icon, "url", None))
        start = self.page * self.per_page
        chunk = self.data[start:start+self.per_page]
        if not chunk:
            e.description = "Страны не созданы."
            e.set_footer(text=f"Страница {self.page+1}/{self.max_page+1}")
            return e

        blocks = []
        for r in chunk:
            uid = r.get("registered_user_id")
            user_txt = "—"
            if uid:
                m = self.ctx.guild.get_member(int(uid))
                user_txt = (m.mention if m else f"<@{uid}>")
            lic_txt = f"<@&{int(r['license_role_id'])}>" if r.get("license_role_id") else "—"
            sea = _fmt_bool(bool(r.get("sea_access"))) if r.get("sea_access") is not None else "—"
            blocks.append(
                "\n".join([
                    f"{r.get('flag') or ''} {r['name']} ({r['code']})",
                    f"• Правитель: {r.get('ruler') or '—'}",
                    f"• Континент: {r.get('continent') or '—'}",
                    f"• Территория: {format_number(r.get('territory_km2') or 0)} км²",
                    f"• Население: {format_number(r.get('population') or 0)}",
                    f"• Выход в море: {sea}",
                    f"• Лицензия: {lic_txt}",
                    f"• Пользователь: {user_txt}",
                ])
            )
        e.description = "\n\n".join(blocks)
        e.set_footer(text=f"Страница {self.page+1}/{self.max_page+1}")
        return e

    @disnake.ui.button(label="Назад", style=disnake.ButtonStyle.secondary)
    async def prev(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.page > 0:
            self.page -= 1
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    @disnake.ui.button(label="Вперед", style=disnake.ButtonStyle.primary)
    async def next(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.page < self.max_page:
            self.page += 1
        await inter.response.edit_message(embed=self.build_embed(), view=self)

@bot.command(name="country-list")
async def country_list_cmd(ctx: commands.Context):
    if not await ensure_allowed_ctx(ctx, ALLOWED_COUNTRY_LIST):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    data = countries_list_all(ctx.guild.id)
    view = CountryListView(ctx, data)
    emb = view.build_embed()
    msg = await ctx.send(embed=emb, view=view)
    view.message = msg

@bot.command(name="reg-country")
async def reg_country_cmd(ctx: commands.Context, member: disnake.Member, code: str):
    if not await ensure_allowed_ctx(ctx, ALLOWED_REG_COUNTRY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    info = country_get_by_code_or_name(ctx.guild.id, code)
    if not info:
        return await ctx.send(embed=error_embed("Ошибка", "Страна с таким кодом не найдена."))

    # Проверка: пользователь уже зарегистрирован?
    existing_code = country_get_registration_for_user(ctx.guild.id, member.id)
    if existing_code:
        ex = country_get_by_code_or_name(ctx.guild.id, existing_code)
        flag = ex.get("flag") or ""
        name = ex.get("name") or existing_code
        code_up = ex.get("code") or existing_code
        return await ctx.send(
            embed=error_embed(
                "Неудачная регистрация",
                f"Пользователь {member.mention} уже зарегистрирован на страну {flag} | {name} ({code_up})."
            )
        )

    # Проверка: страна занята?
    occupant_id = country_get_occupant(ctx.guild.id, info["code"])
    if occupant_id:
        occ_member = ctx.guild.get_member(int(occupant_id))
        flag = info.get("flag") or ""
        name = info.get("name") or info["code"]
        code_up = info["code"]
        return await ctx.send(
            embed=error_embed(
                "Неудачная регистрация",
                 f"Страна {flag} | {name} ({code_up}) уже занята пользователем {occ_member.mention if occ_member else f'<@{occupant_id}>'}."
            )
        )

    # Регистрируем
    ok, err = country_register_user(ctx.guild.id, info["code"], member.id)
    if not ok:
        return await ctx.send(embed=error_embed("Регистрация не выполнена", err or "Ошибка"))

    # Подготовим нормализованный флаг для отображения/ника
    flag_disp = normalize_flag_emoji(info.get("flag") or "", code_hint=info.get("code"))

    # Сообщение об успехе
    e = disnake.Embed(
        title="✅ Успешная регистрация",
        description=f"{member.mention} зарегистрирован(а) на страну: {flag_disp} {info['name']} ({info['code']})",
        color=disnake.Color.green()
    )
    e.add_field(name="Правитель", value=info.get("ruler") or "—", inline=True)
    e.add_field(name="Континент", value=info.get("continent") or "—", inline=True)
    e.add_field(name="Территория", value=f"{format_number(info.get('territory_km2') or 0)} км²", inline=True)
    e.add_field(name="Население", value=f"{format_number(info.get('population') or 0)}", inline=True)
    sea = _fmt_bool(bool(info.get("sea_access"))) if info.get("sea_access") is not None else "—"
    e.add_field(name="Выход в море", value=sea, inline=True)
    lic_txt = f"<@&{int(info['license_role_id'])}>" if info.get("license_role_id") else "—"
    e.add_field(name="Лицензия", value=lic_txt, inline=True)
    await ctx.send(embed=e)

    # Смена ника: "<флаг> | <Название>"
    desired = f"{flag_disp} | {info['name']}"
    if len(desired) > 32:
        desired = desired[:32]
    with contextlib.suppress(Exception):
        await member.edit(nick=desired, reason="Регистрация на страну")

    # Выдача лицензии страны
    lic_id = info.get("license_role_id")
    if lic_id:
        role = ctx.guild.get_role(int(lic_id))
        if role:
            can, why = _bot_can_apply(ctx.guild, role, member)
            if can:
                with contextlib.suppress(Exception):
                    await member.add_roles(role, reason="Регистрация на страну — выдача лицензии страны")
            else:
                # Не критично: просто сообщим в консоль/лог
                print(f"[reg-country] Не удалось выдать роль лицензии: {why}")

@bot.command(name="unreg-country")
async def unreg_country_cmd(ctx: commands.Context, member: disnake.Member):
    if not await ensure_allowed_ctx(ctx, ALLOWED_UNREG_COUNTRY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    ok, err, code = country_unregister_user(ctx.guild.id, member.id)
    if not ok:
        return await ctx.send(embed=error_embed("Снятие не выполнено", err or "Ошибка"))
    e = disnake.Embed(title="✅ Снятие с страны", description=f"{member.mention} снят(а) с регистрации.", color=disnake.Color.green())
    if code:
        e.set_footer(text=f"Код страны: {code}")
    await ctx.send(embed=e)
    
@bot.command(name="country-user")
async def country_user_cmd(ctx: commands.Context, member: disnake.Member):
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    code = country_get_registration_for_user(ctx.guild.id, member.id)
    if not code:
        e = disnake.Embed(
            title="Информация о стране пользователя",
            description=f"{member.mention} не зарегистрирован(а) за какую-либо страну.",
            color=disnake.Color.red()
        )
        e.set_author(name=ctx.guild.name, icon_url=getattr(ctx.guild.icon, "url", None))
        return await ctx.send(embed=e)
    info = country_get_by_code_or_name(ctx.guild.id, code)
    if not info:
        return await ctx.send(embed=error_embed("Ошибка", "Данные страны не найдены."))
    sea = _fmt_bool(bool(info.get("sea_access"))) if info.get("sea_access") is not None else "—"
    lic_txt = f"<@&{int(info['license_role_id'])}>" if info.get("license_role_id") else "—"
    e = disnake.Embed(
        title=f"Страна пользователя {member.display_name}",
        description="\n".join([
            f"{info.get('flag') or ''} {info['name']} ({info['code']})",
            f"• Правитель: {info.get('ruler') or '—'}",
            f"• Континент: {info.get('continent') or '—'}",
            f"• Территория: {format_number(info.get('territory_km2') or 0)} км²",
            f"• Население: {format_number(info.get('population') or 0)}",
            f"• Выход в море: {sea}",
            f"• Лицензия: {lic_txt}",
        ]),
        color=disnake.Color.blurple()
    )
    e.set_author(name=ctx.guild.name, icon_url=getattr(ctx.guild.icon, "url", None))
    await ctx.send(embed=e)
# ============================================


def setup_shop_tables():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS export_deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price INTEGER NOT NULL,           -- сумма продажи БЕЗ доставки (то, что получает продавец)
            delivery INTEGER NOT NULL,        -- 5% от суммы продажи
            total_paid INTEGER NOT NULL,      -- price + delivery (списать с покупателя)
            status TEXT NOT NULL,             -- 'pending' | 'accepted' | 'rejected' | 'expired'
            created_at INTEGER NOT NULL,      -- unix time
            decided_at INTEGER                -- unix time
        )
    """)

    c.execute("PRAGMA table_info(items)")
    cols = {row[1] for row in c.fetchall()}

    def addcol(name, sql):
        if name not in cols:
            c.execute(f"ALTER TABLE items ADD COLUMN {sql}")

    addcol("name_lower", "name_lower TEXT")
    addcol("sell_price", "sell_price INTEGER")
    addcol("buy_price_type", "buy_price_type TEXT DEFAULT 'currency'")
    addcol("cost_items", "cost_items TEXT")
    addcol("is_listed", "is_listed INTEGER DEFAULT 1")
    addcol("stock_total", "stock_total INTEGER")
    addcol("restock_per_day", "restock_per_day INTEGER DEFAULT 0")
    addcol("per_user_daily_limit", "per_user_daily_limit INTEGER DEFAULT 0")
    addcol("roles_required_buy", "roles_required_buy TEXT")
    addcol("roles_required_sell", "roles_required_sell TEXT")
    addcol("roles_granted_on_buy", "roles_granted_on_buy TEXT")
    addcol("roles_removed_on_buy", "roles_removed_on_buy TEXT")
    addcol("disallow_sell", "disallow_sell INTEGER DEFAULT 0")
    addcol("license_role_id", "license_role_id INTEGER")  # <<< НОВОЕ

    c.execute("""
        CREATE TABLE IF NOT EXISTS item_shop_state (
            guild_id INTEGER,
            item_id INTEGER,
            current_stock INTEGER,
            last_restock_ymd TEXT,
            PRIMARY KEY (guild_id, item_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS item_user_daily (
            guild_id INTEGER,
            item_id INTEGER,
            user_id INTEGER,
            ymd TEXT,
            used INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, item_id, user_id, ymd)
        )
    """)

    c.execute("UPDATE items SET name_lower = lower(name) WHERE name_lower IS NULL")

    conn.commit()
    conn.close()


@bot.listen("on_ready")
async def _shop_on_ready():
    setup_shop_tables()
    print("Таблицы магазина готовы.")


def _item_row_to_dict(row) -> Optional[dict]:
    if not row:
        return None
    return {
        "id": row[0],
        "guild_id": row[1],
        "name": row[2],
        "name_lower": row[3],
        "price": int(row[4] or 0),
        "sell_price": None if row[5] is None else int(row[5]),
        "description": row[6] or "",
        "buy_price_type": row[7] or "currency",
        "cost_items": json.loads(row[8]) if row[8] else [],
        "is_listed": int(row[9] or 0),
        "stock_total": None if row[10] is None else int(row[10]),
        "restock_per_day": int(row[11] or 0),
        "per_user_daily_limit": int(row[12] or 0),
        "roles_required_buy": parse_roles_field(row[13]),
        "roles_required_sell": parse_roles_field(row[14]),
        "roles_granted_on_buy": parse_roles_field(row[15]),
        "roles_removed_on_buy": parse_roles_field(row[16]),
        "disallow_sell": int(row[17] or 0),
        "license_role_id": None if row[18] is None else int(row[18]),
    }

ROLE_ID_FINDER = re.compile(r"\d+")

def parse_roles_field(value: Optional[str]) -> list[int]:
    if not value:
        return []
    s = str(value).strip()

    # Попробуем JSON
    if s.startswith("[") and s.endswith("]"):
        try:
            data = json.loads(s)
            ids = []
            for x in data if isinstance(data, list) else []:
                try:
                    ids.append(int(x))
                except Exception:
                    pass
            return sorted(set(ids))
        except Exception:
            pass

    # CSV/упоминания/произвольная строка: достаём все числа
    ids = []
    for m in ROLE_ID_FINDER.finditer(s):
        try:
            ids.append(int(m.group(0)))
        except Exception:
            pass
    return sorted(set(ids))

def ensure_item_normalized(item: dict) -> dict:
    # Копия, чтобы не портить оригинал
    item = dict(item)

    # Тип цены
    bpt = (item.get("buy_price_type") or "currency").lower()
    if bpt == "coins":
        bpt = "currency"
    if bpt not in ("currency", "items"):
        bpt = "currency"
    item["buy_price_type"] = bpt

    # Числовые поля
    def _to_int(val, default=0):
        try:
            return int(val)
        except Exception:
            return default

    item["price"] = _to_int(item.get("price"), 0)

    sp = item.get("sell_price")
    item["sell_price"] = None if sp in (None, "") else _to_int(sp, None)

    st = item.get("stock_total", None)
    if st in ("", None):
        item["stock_total"] = None
    else:
        item["stock_total"] = _to_int(st, None)

    item["restock_per_day"] = _to_int(item.get("restock_per_day"), 0)
    item["per_user_daily_limit"] = _to_int(item.get("per_user_daily_limit"), 0)
    item["is_listed"] = _to_int(item.get("is_listed"), 0)
    item["disallow_sell"] = _to_int(item.get("disallow_sell"), 0)

    # Роли -> list[int]
    for k in ("roles_required_buy", "roles_required_sell", "roles_granted_on_buy", "roles_removed_on_buy"):
        item[k] = parse_roles_field(item.get(k))

    # cost_items -> list[{"item_id": int, "qty": int}]
    ci = item.get("cost_items")
    if isinstance(ci, str):
        try:
            ci = json.loads(ci) if ci.strip() else []
        except Exception:
            ci = []
    elif ci is None:
        ci = []
    elif isinstance(ci, dict):
        ci = [ci]

    norm_ci = []
    for e in ci:
        if isinstance(e, str):
            try:
                e = json.loads(e)
            except Exception:
                continue
        if not isinstance(e, dict):
            continue
        iid = e.get("item_id", e.get("id"))
        qty = e.get("qty", e.get("quantity", 1))
        try:
            iid = int(iid)
            qty = int(qty)
        except Exception:
            continue
        if iid > 0 and qty > 0:
            norm_ci.append({"item_id": iid, "qty": qty})
    item["cost_items"] = norm_ci

    return item

def get_item_by_name(guild_id: int, name: str) -> Optional[dict]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute(f"""
        SELECT
            id, guild_id, name, name_lower, price, sell_price, description,
            buy_price_type, cost_items, is_listed, stock_total, restock_per_day,
            per_user_daily_limit, roles_required_buy, roles_required_sell,
            roles_granted_on_buy, roles_removed_on_buy, disallow_sell, license_role_id
        FROM items
        WHERE guild_id = ? AND name_lower = ?
    """, (guild_id, (name or "").strip().lower()))
    row = c.fetchone()
    conn.close()
    return _item_row_to_dict(row)

def suggest_items(guild_id: int, query: str, limit: int = 5) -> list[str]:
    """Простые подсказки по подстроке (регистронезависимо)."""
    q = f"%{(query or '').strip().lower()}%"
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT name FROM items
        WHERE guild_id = ? AND name_lower LIKE ?
        ORDER BY name LIMIT ?
    """, (guild_id, q, limit))
    result = [r[0] for r in c.fetchall()]
    conn.close()
    return result

def list_items_db(guild_id: int) -> list[dict]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT
            id, guild_id, name, name_lower, price, sell_price, description,
            buy_price_type, cost_items, is_listed, stock_total, restock_per_day,
            per_user_daily_limit, roles_required_buy, roles_required_sell,
            roles_granted_on_buy, roles_removed_on_buy, disallow_sell, license_role_id
        FROM items
        WHERE guild_id = ?
        ORDER BY name_lower
    """, (guild_id,))
    rows = c.fetchall()
    conn.close()
    return [_item_row_to_dict(r) for r in rows]

def get_user_item_qty(guild_id: int, user_id: int, item_id: int) -> int:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT quantity FROM inventories
        WHERE guild_id = ? AND user_id = ? AND item_id = ?
    """, (guild_id, user_id, item_id))
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 0

def add_items_to_user(guild_id: int, user_id: int, item_id: int, amount: int):
    if amount == 0:
        return
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        INSERT INTO inventories (guild_id, user_id, item_id, quantity)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET
            quantity = inventories.quantity + excluded.quantity
    """, (guild_id, user_id, item_id, amount))
    conn.commit()
    conn.close()

def remove_items_from_user(guild_id: int, user_id: int, item_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT quantity FROM inventories
        WHERE guild_id = ? AND user_id = ? AND item_id = ?
    """, (guild_id, user_id, item_id))
    row = c.fetchone()
    if not row or row[0] < amount:
        conn.close()
        return False
    new_q = row[0] - amount
    if new_q == 0:
        c.execute("DELETE FROM inventories WHERE guild_id = ? AND user_id = ? AND item_id = ?",
                  (guild_id, user_id, item_id))
    else:
        c.execute("""
            UPDATE inventories
            SET quantity = ?
            WHERE guild_id = ? AND user_id = ? AND item_id = ?
        """, (new_q, guild_id, user_id, item_id))
    conn.commit()
    conn.close()
    return True

# общий список колонок как в get_item_by_name / list_items_db
ITEMS_COLUMNS = (
    "id, guild_id, name, name_lower, price, sell_price, description, "
    "buy_price_type, cost_items, is_listed, stock_total, restock_per_day, "
    "per_user_daily_limit, roles_required_buy, roles_required_sell, "
    "roles_granted_on_buy, roles_removed_on_buy, disallow_sell, license_role_id"
)

def search_items_by_name_or_id(guild_id: int, query: str) -> list[dict]:
    """
    Ищет и ВОЗВРАЩАЕТ НОРМАЛИЗОВАННЫЕ предметы (как _item_row_to_dict).
    """
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()

    # 1) точное совпадение по ID
    q = (query or "").strip()
    if q.isdigit():
        c.execute(f"SELECT {ITEMS_COLUMNS} FROM items WHERE guild_id = ? AND id = ?", (guild_id, int(q)))
        row = c.fetchone()
        conn.close()
        return [_item_row_to_dict(row)] if row else []

    # 2) поиск по имени (LIKE по name_lower)
    like = f"%{q.lower()}%"
    c.execute(f"SELECT {ITEMS_COLUMNS} FROM items WHERE guild_id = ? AND name_lower LIKE ? LIMIT 10", (guild_id, like))
    rows = c.fetchall()
    conn.close()
    return [_item_row_to_dict(r) for r in rows]

def db_reset_user_inventory(guild_id: int, user_id: int) -> tuple[int, int]:
    """
    Полностью очищает инвентарь пользователя на сервере.
    Возвращает кортеж: (кол-во разных позиций, общее кол-во предметов).
    """
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    try:
        # Считаем, чтобы вернуть статистику
        c.execute("""
            SELECT COUNT(*), COALESCE(SUM(quantity), 0)
            FROM inventories
            WHERE guild_id = ? AND user_id = ?
        """, (guild_id, user_id))
        row = c.fetchone()
        distinct_items = int(row[0] or 0)
        total_qty = int(row[1] or 0)

        # Удаляем
        c.execute("DELETE FROM inventories WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        conn.commit()
        return distinct_items, total_qty
    finally:
        conn.close()

def db_get_user_inventory_stats(guild_id: int, user_id: int) -> tuple[int, int]:
    """
    Возвращает (кол-во разных позиций, общее кол-во предметов) в инвентаре пользователя.
    """
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*), COALESCE(SUM(quantity), 0)
        FROM inventories
        WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))
    row = c.fetchone()
    conn.close()
    return int(row[0] or 0), int(row[1] or 0)

EXPORT_DELIVERY_RATE = 0.05  # 5%

def db_create_export_deal(
    guild_id: int,
    seller_id: int,
    buyer_id: int,
    item_id: int,
    quantity: int,
    price: int,
    delivery: int,
    total_paid: int
) -> int:
    """
    Создаёт запись экспортной сделки в статусе 'pending'. Возвращает id записи.
    """
    # Валидация числовых значений
    price = safe_int(price, name="Цена", min_v=0)
    delivery = safe_int(delivery, name="Доставка", min_v=0)
    total_paid = safe_int(total_paid, name="Итого", min_v=0)
    quantity = safe_int(quantity, name="Кол-во", min_v=1)

    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    created_at = int(datetime.utcnow().timestamp())  # секунды — точно в пределах int64
    c.execute("""
        INSERT INTO export_deals (
            guild_id, seller_id, buyer_id, item_id, quantity, price, delivery, total_paid, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (guild_id, seller_id, buyer_id, item_id, quantity, price, delivery, total_paid, created_at))
    deal_id = c.lastrowid or 0
    conn.commit()
    conn.close()
    return int(deal_id)

def db_update_export_status(deal_id: int, status: str):
    """
    Обновляет статус ('accepted'|'rejected'|'expired') и фиксирует время решения.
    """
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    decided_at = int(datetime.utcnow().timestamp())
    c.execute("UPDATE export_deals SET status = ?, decided_at = ? WHERE id = ?", (status, decided_at, deal_id))
    conn.commit()
    conn.close()

def format_price(n: int) -> str:
    return f"{format_number(n)} {MONEY_EMOJI}"

def effective_sell_price(item: dict) -> int:
    if item.get("sell_price") is not None:
        return int(item["sell_price"])
    return max(0, int(round(item["price"] * DEFAULT_SELL_PERCENT)))


def ymd_utc() -> str:
    return datetime.utcnow().strftime("%Y%m%d")

def ensure_item_state(guild_id: int, item: dict):
    """Создаёт/обновляет состояние склада (автопополнение по дню)."""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT current_stock, last_restock_ymd FROM item_shop_state WHERE guild_id = ? AND item_id = ?",
              (guild_id, item["id"]))
    row = c.fetchone()
    today = ymd_utc()
    if row is None:
        start_stock = item["stock_total"] if item["stock_total"] is not None else None
        c.execute("INSERT INTO item_shop_state (guild_id, item_id, current_stock, last_restock_ymd) VALUES (?, ?, ?, ?)",
                  (guild_id, item["id"], start_stock, today))
    else:
        cur, last = row[0], row[1]
        if item["stock_total"] is not None and last != today:
            cur_val = int(cur) if cur is not None else 0
            replenished = min(item["stock_total"], cur_val + int(item["restock_per_day"] or 0))
            c.execute("UPDATE item_shop_state SET current_stock = ?, last_restock_ymd = ? WHERE guild_id = ? AND item_id = ?",
                      (replenished, today, guild_id, item["id"]))
    conn.commit()
    conn.close()

def get_current_stock(guild_id: int, item_id: int) -> Optional[int]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT current_stock FROM item_shop_state WHERE guild_id = ? AND item_id = ?", (guild_id, item_id))
    row = c.fetchone()
    conn.close()
    if row is None:
        return None
    return None if row[0] is None else int(row[0])

def change_stock(guild_id: int, item_id: int, delta: int):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        UPDATE item_shop_state
        SET current_stock = CASE
            WHEN current_stock IS NULL THEN NULL
            ELSE current_stock + ?
        END
        WHERE guild_id = ? AND item_id = ?
    """, (delta, guild_id, item_id))
    conn.commit()
    conn.close()

def get_user_daily_used(guild_id: int, item_id: int, user_id: int) -> int:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    day = ymd_utc()
    c.execute("SELECT used FROM item_user_daily WHERE guild_id = ? AND item_id = ? AND user_id = ? AND ymd = ?",
              (guild_id, item_id, user_id, day))
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 0

def add_user_daily_used(guild_id: int, item_id: int, user_id: int, amount: int):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    day = ymd_utc()
    c.execute("""
        INSERT INTO item_user_daily (guild_id, item_id, user_id, ymd, used)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, item_id, user_id, ymd) DO UPDATE SET
            used = item_user_daily.used + excluded.used
    """, (guild_id, item_id, user_id, day, amount))
    conn.commit()
    conn.close()

def csv_from_ids(ids) -> str:
    """
    Безопасно преобразует список/строку ID ролей в CSV.
    Поддерживает:
      - None -> ""
      - список чисел/строк -> "1,2,3"
      - строку "1,2,3" -> "1,2,3"
    Отбрасывает нечисловые токены.
    """
    if not ids:
        return ""
    # Если пришла строка из БД, превратим её в список
    if isinstance(ids, str):
        ids = [p for p in ids.split(",") if p.strip()]
    norm = []
    for x in ids:
        s = str(x).strip()
        if s.isdigit():
            norm.append(int(s))
    if not norm:
        return ""
    return ",".join(str(x) for x in sorted(set(norm)))

def has_any_role(user: disnake.Member, role_ids: list[int | str]) -> bool:
    if not role_ids:
        return True
    want = {int(x) for x in role_ids if str(x).isdigit()}
    have = {r.id for r in user.roles}
    return not want.isdisjoint(have)  # есть пересечение => ок
# ===== РАЗРЕШЕНИЯ И РЕЗОЛВ РОЛЕЙ =====

async def ensure_role_manage_allowed(ctx: commands.Context) -> bool:
    """
    Унифицированная проверка прав:
    - Если у вас есть флаг ALLOWED_ROLE_MANAGE и ensure_allowed_ctx — используем его.
    - Иначе — проверяем стандартное право Manage Roles.
    """
    try:
        # Если у вас реализован ensure_allowed_ctx и флаг ALLOWED_ROLE_MANAGE — используйте его.
        return await ensure_allowed_ctx(ctx, ALLOWED_ROLE_MANAGE)  # type: ignore
    except NameError:
        return ctx.author.guild_permissions.manage_roles

def resolve_role_by_input(guild: disnake.Guild, raw: str) -> Optional[disnake.Role]:
    if not raw:
        return None
    s = raw.strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits:
        try:
            r = guild.get_role(int(digits))
            if r:
                return r
        except Exception:
            pass
    s_low = s.lower()
    exact = [r for r in guild.roles if r.name.lower() == s_low]
    if exact:
        return sorted(exact, key=lambda r: r.position, reverse=True)[0]
    partial = [r for r in guild.roles if s_low in r.name.lower()]
    if partial:
        return sorted(partial, key=lambda r: r.position, reverse=True)[0]
    return None

def _owner_or_higher(member: disnake.Member) -> bool:
    return member.guild is not None and member.id == member.guild.owner_id

def _can_actor_manage_role(actor: disnake.Member, role: disnake.Role) -> tuple[bool, str]:
    if role.is_default():
        return False, "Нельзя изменять роль @everyone."
    if role.managed:
        return False, "Этой ролью управляет интеграция/бот, её нельзя менять."
    if _owner_or_higher(actor):
        return True, ""
    if role.position >= actor.top_role.position:
        return False, "Нельзя управлять ролью, которая находится на уровне или выше вашей верхней роли."
    return True, ""

def _can_actor_manage_member(actor: disnake.Member, target: disnake.Member) -> tuple[bool, str]:
    if _owner_or_higher(actor):
        return True, ""
    if target.id == actor.id:
        return True, ""
    if target.top_role.position >= actor.top_role.position:
        return False, "Нельзя изменять роли участнику, который имеет роль на уровне или выше вашей верхней роли."
    return True, ""

def _bot_can_apply(guild: disnake.Guild, role: disnake.Role, target: disnake.Member) -> tuple[bool, str]:
    me = guild.me
    if not me:
        return False, "Бот не найден на сервере."
    if not me.guild_permissions.manage_roles:
        return False, "У бота отсутствует право «Управлять ролями»."
    if role.position >= me.top_role.position:
        return False, "Роль выше или на одном уровне с верхней ролью бота."
    if target.top_role.position >= me.top_role.position and not _owner_or_higher(target):
        return False, "Верхняя роль участника выше или на одном уровне с верхней ролью бота."
    return True, ""

def build_role_change_embed(
    guild: disnake.Guild,
    action: str,  # "add" | "remove"
    target: disnake.Member,
    role: disnake.Role,
    actor: disnake.Member
) -> disnake.Embed:
    titles = {
        "add": ("Выдача роли", disnake.Color.green()),
        "remove": ("Снятие роли", disnake.Color.red()),
    }
    title, color = titles.get(action, ("Действие с ролью", disnake.Color.blurple()))
    e = disnake.Embed(title=title, color=color)
    e.set_author(name=target.display_name, icon_url=target.display_avatar.url)
    e.add_field(name="Роль", value=role.mention, inline=False)
    e.add_field(name="Пользователь", value=target.mention, inline=False)
    e.add_field(name="Администратор", value=actor.mention, inline=False)
    server_icon = getattr(guild.icon, "url", None)
    e.set_footer(text=f"{guild.name} • {datetime.now().strftime('%d.%m.%Y %H:%M')}", icon_url=server_icon)
    return e


def error_embed(title: str, description: str) -> disnake.Embed:
    return disnake.Embed(title=title, description=description, color=disnake.Color.red())

def format_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d}д")
    if h: parts.append(f"{h}ч")
    if m: parts.append(f"{m}м")
    if s or not parts: parts.append(f"{s}с")
    return " ".join(parts)

def format_number(n: int) -> str:
    return f"{n:,}".replace(",", " ")

def parse_role_ids_from_text(guild: disnake.Guild, text: str) -> list[int]:
    """Парсит строку с ролями: упоминания, ID, имена (лучше упоминания/ID). Разделители — запятая/пробел/новая строка.
       'skip' или пустая строка -> []"""
    if not text or text.strip().lower() == "skip":
        return []
    raw = [p.strip() for p in text.replace("\n", " ").replace(",", " ").split(" ") if p.strip()]
    ids = set()
    for token in raw:
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            try:
                rid = int(digits)
                if guild.get_role(rid):
                    ids.add(rid)
                    continue
            except ValueError:
                pass
        role = disnake.utils.get(guild.roles, name=token)
        if role:
            ids.add(role.id)
    return sorted(ids)

def license_block_embed(item: dict, role: Optional[disnake.Role]) -> disnake.Embed:
    mention = role.mention if role else (f"<@&{int(item['license_role_id'])}>" if item.get('license_role_id') else "—")
    return disnake.Embed(
        title="Покупка недоступна",
        description=(
            f"Для покупки предмета «{item.get('name', 'Без названия')}» требуется лицензия {mention}.\n"
            f"Для получения лицензии обращайтесь к её владельцу."
        ),
        color=disnake.Color.orange()
    )

def user_has_item_license(member: disnake.Member, item: dict) -> bool:
    lic_id = item.get("license_role_id")
    if not lic_id:
        return True
    try:
        lic_id = int(lic_id)
    except Exception:
        return True  # некорректная настройка, не блокируем
    return any(r.id == lic_id for r in member.roles)

class ShopView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, items: list[dict]):
        super().__init__(timeout=SHOP_VIEW_TIMEOUT)
        self.ctx = ctx
        self.items = list(items)
        self.page = 0
        self.max_page = max(0, (len(self.items) - 1) // SHOP_ITEMS_PER_PAGE)
        self.author_id = ctx.author.id

        self._sort_modes: list[tuple[str, str]] = [
            ("price_asc", "Цена ↑"),
            ("price_desc", "Цена ↓"),
            ("name", "Название"),
            ("id", "ID"),
        ]
        self._sort_idx = 0
        self._apply_sort()
        self._sync_buttons_state()
        self._update_sort_label()

    def _current_sort_label(self) -> str:
        return self._sort_modes[self._sort_idx][1]

    def _is_currency(self, it: dict) -> bool:
        return (it.get("buy_price_type") or "currency") == "currency"

    def _price_val(self, it: dict) -> int:
        try:
            return int(it.get("price") or 0)
        except Exception:
            return 0

    def _apply_sort(self):
        mode = self._sort_modes[self._sort_idx][0]
        if mode == "price_asc":
            self.items.sort(key=lambda it: (not self._is_currency(it), self._price_val(it), (it.get("name") or "").casefold(), int(it.get("id") or 0)))
        elif mode == "price_desc":
            self.items.sort(key=lambda it: (not self._is_currency(it), -self._price_val(it), (it.get("name") or "").casefold(), int(it.get("id") or 0)))
        elif mode == "name":
            self.items.sort(key=lambda it: ((it.get("name") or "").casefold(), int(it.get("id") or 0)))
        elif mode == "id":
            self.items.sort(key=lambda it: int(it.get("id") or 0))
        self.max_page = max(0, (len(self.items) - 1) // SHOP_ITEMS_PER_PAGE)

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Эта панель доступна только инициатору.", ephemeral=True)
            return False
        return True

    def _sync_buttons_state(self):
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                if child.custom_id == "shop_prev":
                    child.disabled = self.page <= 0
                elif child.custom_id == "shop_next":
                    child.disabled = self.page >= self.max_page

    def _update_sort_label(self):
        for child in self.children:
            if isinstance(child, disnake.ui.Button) and child.custom_id == "shop_sort":
                child.label = f"Сортировка: {self._current_sort_label()}"
                break

    def _page_slice(self) -> list[dict]:
        start = self.page * SHOP_ITEMS_PER_PAGE
        end = start + SHOP_ITEMS_PER_PAGE
        return self.items[start:end]

    def _build_embed(self) -> disnake.Embed:
        embed = disnake.Embed(
            title="🛒 Магазин предметов",
            color=disnake.Color.blurple()
        )

        header_lines = [
            "🔸 Покупка: !buy [кол-во] <название>",
            "🔸 Инфо о предмете: !item-info <название>",
            ""
        ]

        page_items = self._page_slice()

        all_items = list_items_db(self.ctx.guild.id)
        id2name = {i["id"]: i["name"] for i in all_items}

        lines = []

        if not page_items:
            lines.append("Пока нет предметов в магазине.")
        else:
            start_idx = self.page * SHOP_ITEMS_PER_PAGE

            for idx, it in enumerate(page_items):
                name = it.get("name", "Без названия")

                # Описание — на следующей строке после цены/последнего ресурса
                desc = (it.get("description") or "").strip() or "Без описания."
                if len(desc) > 300:
                    desc = desc[:297] + "..."

                # Заголовок предмета: крупным жирным
                title_line = f"**__{name}__**"

                # Формируем блок строк для одного предмета
                block = []

                if (it.get("buy_price_type") or "currency") == "currency":
                    price_str = format_price(it.get("price", 0))
                    block.append(f"{title_line} — {price_str}")
                    # Описание на следующей строке
                    block.append(desc)
                else:
                    block.append(f"{title_line} — Цена (в ресурсах):")
                    cost_items = it.get("cost_items") or []
                    if not cost_items:
                        block.append("   • ❌ Требования не заданы.")
                    else:
                        for r in cost_items:
                            try:
                                item_id = int(r.get("item_id"))
                                qty = int(r.get("qty"))
                            except Exception:
                                continue
                            res_name = id2name.get(item_id, f"ID {item_id}")
                            block.append(f"   • {res_name} — {qty} шт.")
                    # Описание после списка требований
                    block.append(desc)

                # Добавляем блок в общие строки, с пустой строкой-отступом между предметами
                lines.extend(block)
                if idx < len(page_items) - 1:
                    lines.append("")

        embed.description = "\n".join(header_lines + lines).rstrip()

        embed.set_footer(text=f"Страница {self.page + 1} / {self.max_page + 1} • Сортировка: {self._current_sort_label()}")
        
        return embed


    @disnake.ui.button(label="Назад", style=disnake.ButtonStyle.secondary, custom_id="shop_prev", row=0)
    async def prev_page(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.page > 0:
            self.page -= 1
        self._sync_buttons_state()
        await inter.response.edit_message(embed=self._build_embed(), view=self)

    @disnake.ui.button(label="Сортировка", style=disnake.ButtonStyle.primary, custom_id="shop_sort", row=0)
    async def sort_toggle(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        self._sort_idx = (self._sort_idx + 1) % len(self._sort_modes)
        self._apply_sort()
        self.page = 0
        self._sync_buttons_state()
        self._update_sort_label()
        await inter.response.edit_message(embed=self._build_embed(), view=self)

    @disnake.ui.button(label="Вперед", style=disnake.ButtonStyle.primary, custom_id="shop_next", row=0)
    async def next_page(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.page < self.max_page:
            self.page += 1
        self._sync_buttons_state()
        await inter.response.edit_message(embed=self._build_embed(), view=self)

    async def on_timeout(self):
        self.stop()
        try:
            for child in self.children:
                if isinstance(child, disnake.ui.Button):
                    child.disabled = True
            if hasattr(self, "message") and self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


@bot.command(name="shop", aliases=["Shop", "SHOP", "Магазин", "магазин", "МАГАЗИН"])
async def shop_cmd(ctx: commands.Context, page: int = 1):
    """Открыть меню магазина."""
    if not await ensure_allowed_ctx(ctx, ALLOWED_SHOP):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    all_items = list_items_db(ctx.guild.id)
    items = [it for it in all_items if it["is_listed"]]
    view = ShopView(ctx, items)
    if page > 0:
        view.page = min(max(0, page - 1), view.max_page)
        view._sync_buttons_state()
    embed = view._build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


# ЗАМЕНИТЬ ЭТОТ КЛАСС
@dataclass
class ItemDraft:
    # ID предмета, который редактируется. None, если создаётся новый.
    editing_item_id: Optional[int] = None

    name: str = ""
    description: str = ""
    sell_price_raw: str = "skip"
    disallow_sell: int = 0

    buy_price_type: str = "currency"
    price_currency: int = 0
    cost_items: list[dict] = field(default_factory=list)

    is_listed: int = 1
    stock_total_raw: str = "skip"
    restock_per_day: int = 0
    per_user_daily_limit: int = 0

    roles_required_buy: list[int] = field(default_factory=list)
    roles_required_sell: list[int] = field(default_factory=list)
    roles_granted_on_buy: list[int] = field(default_factory=list)
    roles_removed_on_buy: list[int] = field(default_factory=list)
    license_role_id: Optional[int] = None   # <<< НОВОЕ


# Предполагается, что у тебя есть эти функции для работы с БД
# Если их нет, используй примеры ниже как шаблон
def search_items_by_name_or_id(guild_id: int, query: str) -> list[dict]:
    """
    Ищет предметы в БД по имени (частичное совпадение) или точному ID.
    Это ПРИМЕР, адаптируй его под свою структуру БД.
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Сначала пробуем найти по ID, если query - это число
    if query.isdigit():
        c.execute("SELECT * FROM items WHERE guild_id = ? AND id = ?", (guild_id, int(query)))
        item = c.fetchone()
        if item:
            conn.close()
            return [dict(item)] # Возвращаем в виде списка из одного элемента

    # Если по ID не нашли или query не число, ищем по имени
    search_query = f"%{query.lower()}%"
    c.execute("SELECT * FROM items WHERE guild_id = ? AND name_lower LIKE ? LIMIT 10", (guild_id, search_query))
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return items

async def resolve_item_by_user_input(
    ctx: commands.Context,
    query: str,
    timeout: int = 60,
    attempts: int = 3
) -> tuple[dict | None, str | None]:
    bot = ctx.bot
    results = search_items_by_name_or_id(ctx.guild.id, query)

    if not results:
        return None, "Предмет с таким названием или ID не найден."

    # ВАЖНО: нормализуем все результаты
    results = [ensure_item_normalized(it) for it in results]

    if len(results) == 1:
        return results[0], None

    description = "Найдено несколько предметов. Введите номер нужного вам предмета в чат.\n\n"
    for i, item in enumerate(results, 1):
        description += f"**{i}.** {item['name']} (ID: {item['id']})\n"
    
    choice_embed = disnake.Embed(
        title="Выберите предмет",
        description=description,
        color=disnake.Color.orange()
    ).set_footer(text=f"У вас есть {timeout} секунд на ответ.")

    prompt_message = await ctx.channel.send(embed=choice_embed)

    def check(m: disnake.Message):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    for attempt in range(attempts):
        try:
            msg = await bot.wait_for("message", check=check, timeout=timeout / attempts)
            with contextlib.suppress(disnake.HTTPException):
                await msg.delete()

            if msg.content.isdigit() and 1 <= int(msg.content) <= len(results):
                selected_item = results[int(msg.content) - 1]
                with contextlib.suppress(disnake.HTTPException):
                    await prompt_message.delete()
                return selected_item, None
            else:
                await ctx.channel.send(f"Неверный ввод. Пожалуйста, введите число от 1 до {len(results)}.", delete_after=10)
        
        except asyncio.TimeoutError:
            with contextlib.suppress(disnake.HTTPException):
                await prompt_message.delete()
            return None, "Время на выбор истекло."

    with contextlib.suppress(disnake.HTTPException):
        await prompt_message.delete()
    return None, "Вы исчерпали все попытки выбора."

# ЗАМЕНИТЬ ВЕСЬ БЛОК ОТ class BasicInfoModal ДО КОНЦА class CreateItemWizard

# ЗАМЕНИТЬ ВЕСЬ БЛОК ОТ class BasicInfoModal ДО КОНЦА class CreateItemWizard

class BasicInfoModal(disnake.ui.Modal):
    def __init__(self, view_ref, draft: ItemDraft):
        components = [
            disnake.ui.TextInput(
                label="Название предмета",
                custom_id="name",
                style=disnake.TextInputStyle.short,
                max_length=64,
                required=True,
                value=draft.name
            ),
            disnake.ui.TextInput(
                label="Цена продажи (!sell) — число или 'skip'",
                custom_id="sell_price",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 100 или skip",
                value=draft.sell_price_raw
            ),
            disnake.ui.TextInput(
                label="Описание предмета",
                custom_id="desc",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=False,
                value=draft.description
            ),
        ]
        title = "1️⃣ 📝 Основы предмета"
        if draft.editing_item_id:
            title = f"📝 Редактирование: Основы (ID: {draft.editing_item_id})"
        super().__init__(title=title, components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        name = inter.text_values.get("name", "").strip()
        sell_raw = inter.text_values.get("sell_price", "").strip().lower()
        desc = inter.text_values.get("desc", "").strip()

        if not name:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Название не может быть пустым."), ephemeral=True)

        exists = get_item_by_name(inter.guild.id, name)
        # Если предмет с таким именем существует, И это НЕ тот предмет, который мы редактируем
        if exists and exists['id'] != self.view_ref.draft.editing_item_id:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Предмет с таким именем уже существует."), ephemeral=True)

        disallow_sell = 0
        if sell_raw == "skip":
            disallow_sell = 1
        else:
            try:
                safe_int(sell_raw, name="Цена продажи", min_v=0)
            except ValueError as e:
                return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)

        self.view_ref.draft.name = name
        self.view_ref.draft.description = desc
        self.view_ref.draft.sell_price_raw = sell_raw
        self.view_ref.draft.disallow_sell = disallow_sell

        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class CurrencyPriceModal(disnake.ui.Modal):
    def __init__(self, view_ref, draft: ItemDraft):
        components = [
            disnake.ui.TextInput(
                label="Цена в валюте",
                custom_id="price",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 150",
                value=str(draft.price_currency) if draft.price_currency > 0 else ""
            )
        ]
        super().__init__(title="2️⃣ 💳 Цена покупки — валюта", components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        raw = inter.text_values.get("price", "").strip()
        try:
            price_val = safe_int(raw, name="Цена", min_v=1)
        except ValueError as e:
            return await inter.response.send_message(
                embed=error_embed("Ошибка", str(e)),
                ephemeral=True
            )
        self.view_ref.draft.buy_price_type = "currency"
        self.view_ref.draft.price_currency = price_val
        # Вместо .clear() (падает, если cost_items = None/строка) — просто переустанавливаем
        self.view_ref.draft.cost_items = []
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class AddCostItemByNameModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        components = [
            disnake.ui.TextInput(
                label="Предмет (название или ID)",
                custom_id="iname",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: Железо или 15"
            ),
            disnake.ui.TextInput(
                label="Количество",
                custom_id="qty",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 3"
            ),
        ]
        super().__init__(title="Добавить требуемый предмет", components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        iname = inter.text_values.get("iname", "").strip()
        qty_raw = inter.text_values.get("qty", "").strip()

        try:
            qty_val = safe_int(qty_raw, name="Количество", min_v=1)
        except ValueError as e:
            return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)

        await inter.response.send_message("Открыл выбор предмета в чате. Следуйте инструкции и введите номер в ответ.", ephemeral=True)

        async def _resolve_and_update():
            item, err = await resolve_item_by_user_input(self.view_ref.ctx, iname, timeout=60, attempts=3)
            if err or not item:
                with contextlib.suppress(Exception):
                    await self.view_ref.ctx.send(embed=error_embed("Выбор предмета", err or "Не удалось определить предмет."))
                return
            qty = qty_val

            # Проверяем, не является ли добавляемый предмет тем же, что мы редактируем
            if self.view_ref.draft.editing_item_id and item["id"] == self.view_ref.draft.editing_item_id:
                 with contextlib.suppress(Exception):
                    await self.view_ref.ctx.send(embed=error_embed("Неверная стоимость", "Нельзя использовать редактируемый предмет как цену для самого себя."))
                 return

            if item["name_lower"] == (self.view_ref.draft.name or "").lower():
                with contextlib.suppress(Exception):
                    await self.view_ref.ctx.send(embed=error_embed("Неверная стоимость", "Нельзя использовать текущий создаваемый предмет как цену."))
                return

            found = False
            for r in self.view_ref.draft.cost_items:
                if r["item_id"] == item["id"]:
                    r["qty"] = qty
                    found = True
                    break
            if not found:
                self.view_ref.draft.cost_items.append({"item_id": item["id"], "qty": qty})

            try:
                if self.view_ref.message:
                    await self.view_ref.message.edit(embed=self.view_ref.build_embed(), view=self.view_ref)
            except Exception:
                pass

            with contextlib.suppress(Exception):
                await self.view_ref.ctx.send(f"Добавлено/обновлено требование: {item['name']} {qty} шт.")

        asyncio.create_task(_resolve_and_update())


class ShopSettingsModal(disnake.ui.Modal):
    def __init__(self, view_ref, draft: ItemDraft):
        components = [
            disnake.ui.TextInput(
                label="Продается в магазине? (да/нет)",
                custom_id="listed",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="да | нет",
                value="да" if draft.is_listed else "нет"
            ),
            disnake.ui.TextInput(
                label="Общее количество (число или 'skip')",
                custom_id="stock",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 100 или skip",
                value=draft.stock_total_raw
            ),
            disnake.ui.TextInput(
                label="Автопополнение в день (число)",
                custom_id="restock",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 5",
                value=str(draft.restock_per_day)
            ),
            disnake.ui.TextInput(
                label="Лимит на пользователя в день (0 = без лим.)",
                custom_id="limit",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 2 или 0",
                value=str(draft.per_user_daily_limit)
            ),
        ]
        super().__init__(title="3️⃣ 🏪 Настройки магазина", components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        listed_raw = inter.text_values["listed"].strip().lower()
        stock_raw = inter.text_values["stock"].strip().lower()
        restock_raw = inter.text_values["restock"].strip()
        limit_raw = inter.text_values["limit"].strip()

        if listed_raw not in ("да", "нет"):
            return await inter.response.send_message(embed=error_embed("Ошибка", "Поле «Продается?» должно быть 'да' или 'нет'."), ephemeral=True)
        is_listed = 1 if listed_raw == "да" else 0

        if stock_raw != "skip":
            try:
                safe_int(stock_raw, name="Общее количество", min_v=1)
            except ValueError as e:
                return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)

        try:
            restock_val = safe_int(restock_raw, name="Автопополнение", min_v=0)
        except ValueError as e:
            return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)

        try:
            limit_val = safe_int(limit_raw, name="Лимит в день", min_v=0)
        except ValueError as e:
            return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)

        self.view_ref.draft.is_listed = is_listed
        self.view_ref.draft.stock_total_raw = stock_raw
        self.view_ref.draft.restock_per_day = restock_val
        self.view_ref.draft.per_user_daily_limit = limit_val

        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class RolesModal(disnake.ui.Modal):
    def __init__(self, view_ref, draft: ItemDraft):
        def ids_to_text(ids: list[int]) -> str:
            return " ".join(str(i) for i in ids)

        components = [
            disnake.ui.TextInput(
                label="Роли для покупки — ID/упоминания или 'skip'",
                custom_id="buy_req",
                style=disnake.TextInputStyle.paragraph,
                required=False,
                value=ids_to_text(draft.roles_required_buy)
            ),
            disnake.ui.TextInput(
                label="Роли для продажи — ID/упоминания или 'skip'",
                custom_id="sell_req",
                style=disnake.TextInputStyle.paragraph,
                required=False,
                value=ids_to_text(draft.roles_required_sell)
            ),
            disnake.ui.TextInput(
                label="Выдать роли при покупке — ID/упом. или 'skip'",
                custom_id="grant",
                style=disnake.TextInputStyle.paragraph,
                required=False,
                value=ids_to_text(draft.roles_granted_on_buy)
            ),
            disnake.ui.TextInput(
                label="Снять роли при покупке — ID/упом. или 'skip'",
                custom_id="remove",
                style=disnake.TextInputStyle.paragraph,
                required=False,
                value=ids_to_text(draft.roles_removed_on_buy)
            ),
        ]
        super().__init__(title="4️⃣ 🛡️ Права (роли)", components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        # Парсим ID ролей из введенного текста
        buy_ids = parse_role_ids_from_text(inter.guild, inter.text_values.get("buy_req", ""))
        sell_ids = parse_role_ids_from_text(inter.guild, inter.text_values.get("sell_req", ""))
        grant_ids = parse_role_ids_from_text(inter.guild, inter.text_values.get("grant", ""))
        remove_ids = parse_role_ids_from_text(inter.guild, inter.text_values.get("remove", ""))

        # ================== НОВАЯ ПРОВЕРКА ПРАВ ==================
        # Получаем самую высокую роль пользователя, который вызвал команду
        author_top_role = inter.user.top_role
        
        # Собираем все роли, которыми пользователь пытается управлять (выдача/снятие)
        # Используем set для удаления дубликатов
        managed_role_ids = set(grant_ids + remove_ids)
        
        problematic_roles = []
        for role_id in managed_role_ids:
            # Получаем объект роли по её ID
            role = inter.guild.get_role(role_id)
            # Проверяем, существует ли роль и находится ли её позиция ВЫШЕ или НА ТОМ ЖЕ УРОВНЕ,
            # что и самая высокая роль пользователя.
            if role and role.position >= author_top_role.position:
                problematic_roles.append(role.mention)
        
        # Если найдены роли, которые пользователь не имеет права назначать
        if problematic_roles:
            error_message = (
                f"Вы не можете управлять ролями, которые находятся на одном уровне "
                f"или выше вашей самой высокой роли ({author_top_role.mention}).\n\n"
                f"**Проблемные роли:** {', '.join(problematic_roles)}"
            )
            # Отправляем сообщение об ошибке и прекращаем выполнение
            await inter.response.send_message(
                embed=error_embed("Ошибка прав", error_message), 
                ephemeral=True
            )
            return
        # ================= КОНЕЦ ПРОВЕРКИ ПРАВ ==================

        # Если все проверки пройдены, сохраняем ID ролей в черновик
        self.view_ref.draft.roles_required_buy = buy_ids
        self.view_ref.draft.roles_required_sell = sell_ids
        self.view_ref.draft.roles_granted_on_buy = grant_ids
        self.view_ref.draft.roles_removed_on_buy = remove_ids

        # Обновляем главное сообщение с новыми данными
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class CreateItemWizard(disnake.ui.View):
    def __init__(self, ctx: commands.Context, item_to_edit: Optional[dict] = None):
        super().__init__(timeout=600)  # Увеличим таймаут для редактирования
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.draft = ItemDraft()
        self.message: Optional[disnake.Message] = None

        if item_to_edit:
            # Общие поля
            self.draft.editing_item_id = int(item_to_edit.get("id")) if item_to_edit.get("id") is not None else None
            self.draft.name = item_to_edit.get("name") or ""
            self.draft.description = item_to_edit.get("description") or ""
            self.draft.license_role_id = item_to_edit.get("license_role_id")
            
            # Продажа (!sell)
            self.draft.disallow_sell = int(item_to_edit.get("disallow_sell") or 0)
            sell_price = item_to_edit.get("sell_price")
            if self.draft.disallow_sell:
                self.draft.sell_price_raw = "skip"
            elif sell_price is None:
                self.draft.sell_price_raw = "skip"
            else:
                try:
                    self.draft.sell_price_raw = str(int(sell_price))
                except (TypeError, ValueError):
                    self.draft.sell_price_raw = "skip"

            # Покупка (!buy)
            self.draft.buy_price_type = (item_to_edit.get("buy_price_type") or "currency")
            try:
                self.draft.price_currency = int(item_to_edit.get("price") or 0)
            except (TypeError, ValueError):
                self.draft.price_currency = 0

            # Нормализация cost_items (может прийти JSON-строкой/NULL/списком)
            raw_cost = item_to_edit.get("cost_items")
            if isinstance(raw_cost, str) and raw_cost.strip():
                try:
                    parsed = json.loads(raw_cost)
                    self.draft.cost_items = parsed if isinstance(parsed, list) else []
                except Exception:
                    self.draft.cost_items = []
            elif isinstance(raw_cost, list):
                self.draft.cost_items = raw_cost
            else:
                self.draft.cost_items = []

            # Настройки магазина
            try:
                self.draft.is_listed = 1 if int(item_to_edit.get("is_listed") or 0) else 0
            except (TypeError, ValueError):
                self.draft.is_listed = 0

            stock = item_to_edit.get("stock_total")
            if stock in (None, ""):
                self.draft.stock_total_raw = "skip"
            else:
                try:
                    self.draft.stock_total_raw = str(int(stock))
                except (TypeError, ValueError):
                    self.draft.stock_total_raw = "skip"

            try:
                self.draft.restock_per_day = int(item_to_edit.get("restock_per_day") or 0)
            except (TypeError, ValueError):
                self.draft.restock_per_day = 0
            try:
                self.draft.per_user_daily_limit = int(item_to_edit.get("per_user_daily_limit") or 0)
            except (TypeError, ValueError):
                self.draft.per_user_daily_limit = 0

            # Роли: CSV/список -> list[int]
            def parse_roles(val):
                if not val:
                    return []
                if isinstance(val, list):
                    return [int(x) for x in val if str(x).strip().isdigit()]
                if isinstance(val, str):
                    out = []
                    for tok in val.split(","):
                        tok = tok.strip()
                        if tok.isdigit():
                            out.append(int(tok))
                    return out
                return []

            self.draft.roles_required_buy   = parse_roles(item_to_edit.get("roles_required_buy"))
            self.draft.roles_required_sell  = parse_roles(item_to_edit.get("roles_required_sell"))
            self.draft.roles_granted_on_buy = parse_roles(item_to_edit.get("roles_granted_on_buy"))
            self.draft.roles_removed_on_buy = parse_roles(item_to_edit.get("roles_removed_on_buy"))

    def build_embed(self) -> disnake.Embed:
        is_editing = self.draft.editing_item_id is not None
        
        st1 = bool(self.draft.name)
        st2 = (self.draft.buy_price_type == "currency" and self.draft.price_currency > 0) or \
              (self.draft.buy_price_type == "items" and len(self.draft.cost_items) > 0)
        st3 = True
        st4 = True

        def chip(ok: bool) -> str:
            return "✅" if ok else "▫️"

        progress_line = f"1️⃣ {chip(st1)}  •  2️⃣ {chip(st2)}  •  3️⃣ {chip(st3)}  •  4️⃣ {chip(st4)}"
        
        title = "⚙️ Мастер редактирования предмета" if is_editing else "⚙️ Мастер создания предмета"
        if is_editing:
            title += f" (ID: {self.draft.editing_item_id})"

        e = disnake.Embed(
            title=title,
            description=(
                "╭────────────────────────────╮\n"
                f"   Прогресс: {progress_line}\n"
                "╰────────────────────────────╯"
            ),
            color=disnake.Color.blurple()
        )
        e.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)

        if self.draft.disallow_sell:
            sell_info = "🔒 Запрещена"
        elif self.draft.sell_price_raw != "skip":
            sell_info = f"🏷️ Фикс.: {format_number(int(self.draft.sell_price_raw))} {MONEY_EMOJI}"
        else:
            sell_info = "ℹ️ По умолчанию (% от цены)"

        if self.draft.buy_price_type == "currency":
            cost_desc = f"💳 Валюта: **{format_number(self.draft.price_currency)} {MONEY_EMOJI}**" if self.draft.price_currency > 0 else "💳 Валюта: —"
        else:
            if not self.draft.cost_items:
                cost_desc = "🧱 Предметы: — не выбрано"
            else:
                all_items = list_items_db(self.ctx.guild.id)
                id2name = {i["id"]: i["name"] for i in all_items}
                parts = []
                for r in self.draft.cost_items:
                    nm = id2name.get(r['item_id'], 'ID ' + str(r['item_id']))
                    parts.append(f"🧱 {nm} × {r['qty']}")
                cost_desc = "\n".join(parts)

        listed = "🟢 Да" if self.draft.is_listed else "🔴 Нет"
        stock_text = self.draft.stock_total_raw
        stock_text = "∞ (без огранич.)" if stock_text == "skip" else stock_text

        e.add_field(
            name="1️⃣ 📝 Основы",
            value=(
                f"• Название: **{self.draft.name or '—'}**\n"
                f"• Описание: {self.draft.description or '—'}\n"
                f"• Продажа системе: {sell_info}"
            ),
            inline=False
        )

        e.add_field(
            name="2️⃣ 🛒 Покупка (!buy)",
            value=(
                f"• Тип цены: {'💳 Валюта' if self.draft.buy_price_type=='currency' else '🧱 Предметы'}\n"
                f"• {cost_desc}"
            ),
            inline=False
        )

        e.add_field(
            name="3️⃣ 🏪 Магазин",
            value=(
                f"• В продаже: {listed}\n"
                f"• Общее количество: **{stock_text}**\n"
                f"• Автопополнение/день: **{self.draft.restock_per_day}**\n"
                f"• Лимит/день на пользователя: **{self.draft.per_user_daily_limit or 'без лимита'}**"
            ),
            inline=False
        )

        def roles_str(ids):
            return ", ".join(f"<@&{r}>" for r in ids) if ids else "—"

        e.add_field(
            name="4️⃣ 🛡️ Права",
            value=(
                f"• Для покупки (!buy): {roles_str(self.draft.roles_required_buy)}\n"
                f"• Для продажи (!sell): {roles_str(self.draft.roles_required_sell)}\n"
                f"• Выдать роли при покупке: {roles_str(self.draft.roles_granted_on_buy)}\n"
                f"• Снять роли при покупке: {roles_str(self.draft.roles_removed_on_buy)}"
            ),
            inline=False
        )
        lic_txt = f"<@&{self.draft.license_role_id}>" if self.draft.license_role_id else "—"
        e.add_field(
            name="🔖 Лицензия",
            value=f"Лицензия: {lic_txt}",
            inline=False
        )
        e.add_field(
            name="ℹ️ Подсказки",
            value=(
                "• Нажмите кнопки ниже, чтобы изменить шаги.\n"
                "• Выберите тип цены в селекте, затем задайте стоимость.\n"
                "• Готово? Нажмите «💾 Сохранить»."
            ),
            inline=False
        )
        e.set_footer(text="Универсальный мастер: аккуратно заполняйте по шагам ✨")
        return e

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Эта панель доступна только создателю.", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="📝 О предмете", style=disnake.ButtonStyle.primary, custom_id="step_basic", row=0)
    async def _open_basic(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(BasicInfoModal(self, self.draft))

    @disnake.ui.button(label="💳 Цена покупки", style=disnake.ButtonStyle.primary, custom_id="step_price", row=0)
    async def _open_price(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.draft.buy_price_type == "currency":
            await inter.response.send_modal(CurrencyPriceModal(self, self.draft))
        else:
            await inter.response.send_message(
                "Выбран тип цены «Предметы». Нажмите «➕ Добавить требуемый предмет», чтобы задать стоимость.",
                ephemeral=True
            )

    @disnake.ui.button(label="🏪 Магазин", style=disnake.ButtonStyle.primary, custom_id="step_shop", row=0)
    async def _open_shop(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(ShopSettingsModal(self, self.draft))

    @disnake.ui.button(label="🛡️ Права", style=disnake.ButtonStyle.primary, custom_id="step_roles", row=0)
    async def _open_roles(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(RolesModal(self, self.draft))

    @disnake.ui.button(label="Лицензия", style=disnake.ButtonStyle.secondary, custom_id="step_license", row=3)
    async def _open_license(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        async def on_pick(role_id: int, i: disnake.MessageInteraction):
            self.draft.license_role_id = role_id
            if self.message:
                with contextlib.suppress(Exception):
                    await self.message.edit(embed=self.build_embed(), view=self)

        emb = build_license_pick_embed(
            invoker=inter.user,
            title="Выбор роли лицензии для предмета",
            current_role_id=self.draft.license_role_id
        )

        picker = LicenseRolePickView(self.ctx, on_pick=on_pick, current_role_id=self.draft.license_role_id)
        try:
            await inter.response.send_message(embed=emb, view=picker, ephemeral=True)
        except Exception:
            await inter.followup.send(embed=emb, view=picker, ephemeral=True)

        with contextlib.suppress(Exception):
            picker.message = await inter.original_message()

    @disnake.ui.button(label="💾 Сохранить", style=disnake.ButtonStyle.success, custom_id="save_item", row=0)
    async def _save_item(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        # --- Валидация ---
        if not self.draft.name:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Заполните «Название» на шаге 1."), ephemeral=True)
        if self.draft.buy_price_type == "currency":
            if self.draft.price_currency <= 0:
                return await inter.response.send_message(embed=error_embed("Ошибка", "Укажите положительную цену в валюте (шаг 2)."), ephemeral=True)
        else:
            if not self.draft.cost_items:
                return await inter.response.send_message(embed=error_embed("Ошибка", "Добавьте хотя бы один предмет-стоимость (шаг 2)."), ephemeral=True)

        exists = get_item_by_name(inter.guild.id, self.draft.name)
        if exists and exists['id'] != self.draft.editing_item_id:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Предмет с таким именем уже существует."), ephemeral=True)

        # --- Подготовка данных для БД + строгая валидация чисел ---
        MAX_SQL_INT = 9_223_372_036_854_775_807
        MIN_SQL_INT = -9_223_372_036_854_775_808

        def safe_int(v, *, name: str = "value", min_v: int = 0, max_v: int = MAX_SQL_INT) -> int:
            if v is None:
                raise ValueError(f"{name}: не задано.")
            # используем глобальную функцию safe_int, поддерживающую суффиксы
            return globals()["safe_int"](v, name=name, min_v=min_v, max_v=max_v)

        def safe_optional_int(v, *, name: str = "value", min_v: int = 0, max_v: int = MAX_SQL_INT):
            if v is None:
                return None
            return safe_int(v, name=name, min_v=min_v, max_v=max_v)

        try:
            guild_id_val = safe_int(inter.guild.id, name="Guild ID", min_v=0)

            price_raw = self.draft.price_currency if self.draft.buy_price_type == "currency" else 0
            price_val = safe_int(price_raw, name="Цена", min_v=0)

            sell_price_val = None
            if self.draft.disallow_sell == 0 and self.draft.sell_price_raw != "skip":
                sell_price_val = safe_int(self.draft.sell_price_raw, name="Цена продажи", min_v=0)

            stock_total_val = None if self.draft.stock_total_raw == "skip" else safe_int(self.draft.stock_total_raw, name="Склад (всего)", min_v=0)

            # Доп. числовые поля
            restock_per_day_val = safe_optional_int(self.draft.restock_per_day, name="Пополнение в день", min_v=0)
            per_user_daily_limit_val = safe_optional_int(self.draft.per_user_daily_limit, name="Лимит на пользователя в день", min_v=0)

            is_listed_val = safe_int(1 if self.draft.is_listed else 0, name="Публикация", min_v=0, max_v=1)
            disallow_sell_val = safe_int(self.draft.disallow_sell, name="Запрет продажи", min_v=0, max_v=1)
            license_role_id_val = safe_optional_int(self.draft.license_role_id, name="Лицензия (роль)", min_v=0)

            editing_item_id_val = None
            if self.draft.editing_item_id:
                editing_item_id_val = safe_int(self.draft.editing_item_id, name="ID предмета", min_v=1)
        except ValueError as ve:
            return await inter.response.send_message(embed=error_embed("Некорректные данные", str(ve)), ephemeral=True)
        except OverflowError:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Одно из числовых значений слишком велико для хранения в базе."), ephemeral=True)

        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        try:
            # --- Редактирование существующего ---
            if editing_item_id_val:
                c.execute("""
                    UPDATE items SET
                        name = ?, name_lower = ?, price = ?, sell_price = ?, description = ?,
                        buy_price_type = ?, cost_items = ?, is_listed = ?, stock_total = ?, 
                        restock_per_day = ?, per_user_daily_limit = ?, roles_required_buy = ?, 
                        roles_required_sell = ?, roles_granted_on_buy = ?, roles_removed_on_buy = ?, 
                        disallow_sell = ?, license_role_id = ?
                    WHERE id = ? AND guild_id = ?
                """, (
                    self.draft.name, self.draft.name.lower(), price_val, sell_price_val, self.draft.description,
                    self.draft.buy_price_type, json.dumps(self.draft.cost_items) if self.draft.cost_items else None,
                    is_listed_val, stock_total_val, restock_per_day_val, per_user_daily_limit_val,
                    csv_from_ids(self.draft.roles_required_buy) or None,
                    csv_from_ids(self.draft.roles_required_sell) or None,
                    csv_from_ids(self.draft.roles_granted_on_buy) or None,
                    csv_from_ids(self.draft.roles_removed_on_buy) or None,
                    disallow_sell_val, license_role_id_val,
                    editing_item_id_val, guild_id_val
                ))
                conn.commit()
                # Сбросим состояние склада, чтобы оно пересоздалось с новыми параметрами
                c.execute("DELETE FROM item_shop_state WHERE guild_id = ? AND item_id = ?", (guild_id_val, editing_item_id_val))
                conn.commit()
                
            # --- Создание нового ---
            else:
                c.execute("""
                    INSERT INTO items (
                        guild_id, name, name_lower, price, sell_price, description,
                        buy_price_type, cost_items, is_listed, stock_total, restock_per_day,
                        per_user_daily_limit, roles_required_buy, roles_required_sell,
                        roles_granted_on_buy, roles_removed_on_buy, disallow_sell, license_role_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    guild_id_val, self.draft.name, self.draft.name.lower(), price_val, sell_price_val, self.draft.description,
                    self.draft.buy_price_type, json.dumps(self.draft.cost_items) if self.draft.cost_items else None,
                    is_listed_val, stock_total_val, restock_per_day_val, per_user_daily_limit_val,
                    csv_from_ids(self.draft.roles_required_buy) or None,
                    csv_from_ids(self.draft.roles_required_sell) or None,
                    csv_from_ids(self.draft.roles_granted_on_buy) or None,
                    csv_from_ids(self.draft.roles_removed_on_buy) or None,
                    disallow_sell_val, license_role_id_val
                ))
                conn.commit()
                item_id = c.lastrowid
                if item_id:
                    c.execute("""
                        INSERT OR IGNORE INTO item_shop_state (guild_id, item_id, current_stock, last_restock_ymd)
                        VALUES (?, ?, ?, ?)
                    """, (guild_id_val, item_id, stock_total_val, ymd_utc()))
                    conn.commit()

        except sqlite3.IntegrityError as e:
            conn.close()
            print(f"Ошибка сохранения предмета: {e}")
            return await inter.response.send_message(embed=error_embed("Ошибка", "Предмет с таким именем уже существует (ошибка базы данных)."), ephemeral=True)
        finally:
            conn.close()

        # --- Логирование ---
        is_editing = self.draft.editing_item_id is not None
        
        try:
            # Если редактировали существующий предмет
            if is_editing:
                await send_shop_item_action_log(
                    guild=inter.guild,
                    actor=inter.user,
                    action="update",
                    item_name=self.draft.name
                )
            # Если создавали новый
            else:
                await send_shop_item_action_log(
                    guild=inter.guild,
                    actor=inter.user,
                    action="create",
                    item_name=self.draft.name
                )
        except Exception as e:
            # Опционально: можно добавить логирование самой ошибки, чтобы понимать, почему не сработал лог
            print(f"Failed to send shop item action log: {e}")
            
        done = disnake.Embed(
            title="✅ Предмет обновлён" if is_editing else "✅ Предмет создан",
            description=(
                "╭────────────────────────────╮\n"
                f"   «{self.draft.name}» успешно сохранён!\n"
                "╰────────────────────────────╯"
            ),
            color=disnake.Color.green()
        )
        done.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)
        await inter.response.edit_message(embed=done, view=None)


    @disnake.ui.string_select(
        custom_id="price_type_select",
        placeholder="Выберите тип цены • 💳 Валюта / 🧱 Предметы",
        row=1,
        options=[
            disnake.SelectOption(label="💳 Валюта", value="currency", description="Оплата деньгами"),
            disnake.SelectOption(label="🧱 Предметы", value="items", description="Оплата другими предметами"),
        ]
    )
    async def _price_type_select(self, select: disnake.ui.StringSelect, inter: disnake.MessageInteraction):
        val = select.values[0]
        self.draft.buy_price_type = val
        if val == "currency":
            await inter.response.send_modal(CurrencyPriceModal(self, self.draft))
        else:
            await inter.response.edit_message(embed=self.build_embed(), view=self)

    @disnake.ui.button(label="➕ Добавить требуемый предмет", style=disnake.ButtonStyle.secondary, custom_id="add_cost_item", row=2)
    async def _add_cost_item(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.draft.buy_price_type != "items":
            return await inter.response.send_message(embed=error_embed("Ошибка", "Сначала выберите тип цены «Предметы»."), ephemeral=True)
        await inter.response.send_modal(AddCostItemByNameModal(self))

    @disnake.ui.button(label="🧹 Очистить список требований", style=disnake.ButtonStyle.secondary, custom_id="clear_cost_items", row=2)
    async def _clear_cost_items(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.draft.cost_items.clear()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        try:
            for child in self.children:
                if isinstance(child, (disnake.ui.Button, disnake.ui.SelectBase)):
                    child.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# Если стандартная help включена — отключим
try:
    bot.remove_command("help")
except Exception:
    pass

HELP_VIEW_TIMEOUT = 180  # секунд

HELP_CATEGORIES_BASE: dict[str, dict] = {
    "items": {
        "title": "📦 Категория: Предметы",
        "color": disnake.Color.blurple(),
        "hint": "Команды магазина, инвентаря и работы с предметами.",
        "commands": [
            ("!shop", "магазин"),
            ("!buy", "купить предмета"),
            ("!inv", "посмотреть инвентарь"),
            ("!use", "использовать предмет из инвентаря"),
            ("!iteminfo", "информация о предмете"),
            ("!trade", "продать предмет пользователю"),
        ],
    },
    "economy": {
        "title": "💰 Категория: Экономика",
        "color": disnake.Color.gold(),
        "hint": "Баланс, переводы, работа и сбор доходов.",
        "commands": [
            ("!balance", "посмотреть баланс"),
            ("!pay", "передать деньги"),
            ("!work", "работать"),
            ("!worldbank", "меню Всемирного банка"),
            ("!collect", "собрать доход"),
            ("!income-list", "список доходных ролей"),
        ],
    },
}

# Карта админ-команд -> имя флага ALLOWED_* вашей системы
# При необходимости поправьте имена флагов под ваш проект.
ADMIN_COMMANDS_WITH_FLAGS: list[tuple[str, str, str]] = [
    ("!add-role", "выдать роль", "ALLOWED_ADD_ROLE"),
    ("!take-role", "забрать роль", "ALLOWED_TAKE_ROLE"),
    ("!create-item", "создать предмет", "ALLOWED_CREATE_ITEM"),
    ("!give-item", "выдать предмет", "ALLOWED_GIVE_ITEM"),
    ("!take-item", "забрать предмет", "ALLOWED_TAKE_ITEM"),
    ("!set-work", "настройка работы", "ALLOWED_SET_WORK"),
    ("!add-money", "выдать деньги", "ALLOWED_ADD_MONEY"),
    ("!remove-money", "забрать деньги", "ALLOWED_REMOVE_MONEY"),
    ("!reset-money", "обнулить баланс", "ALLOWED_RESET_MONEY"),
    ("!add-money-role", "выдать деньги", "ALLOWED_ADD_MONEY_ROLE"),
    ("!remove-money-role", "забрать деньги", "ALLOWED_REMOVE_MONEY_ROLE"),
    ("!reset-money-role", "обнулить баланс", "ALLOWED_RESET_MONEY_ROLE"),
    ("!role-income", "добавить доходные роли", "ALLOWED_ROLE_INCOME"),
    ("!edit-item", "изменить предмет", "ALLOWED_EDIT_ITEM"),
    ("!delete-item", "удалить предмет", "ALLOWED_DELETE_ITEM"),
    ("!reset-inventory", "очистить инвентарь", "ALLOWED_RESET_INVENTORY"),
    ("!apanel", "панель администрации (изменено)", "ALLOWED_APANEL"),
]


async def _ensure_allowed_silent(ctx: commands.Context, allowed_flag) -> bool:
    """
    Унифицированная «тихая» проверка доступа:
    - если ensure_allowed_ctx поддерживает silent=True — используем его;
    - иначе предполагаем, что ensure_allowed_ctx возвращает bool и не шумит.
    """
    try:
        # если в ensure_allowed_ctx есть silent — используем
        return await ensure_allowed_ctx(ctx, allowed_flag, silent=True)  # type: ignore
    except TypeError:
        # совместимость, если параметра silent нет
        return await ensure_allowed_ctx(ctx, allowed_flag)


async def get_admin_commands_for(ctx: commands.Context) -> list[tuple[str, str]]:
    """
    Вернёт только те админ-команды, к которым есть доступ по вашей системе разрешений.
    Отсутствующие флаги в globals() — считаем недоступными.
    """
    available: list[tuple[str, str]] = []
    for cmd, desc, flag_name in ADMIN_COMMANDS_WITH_FLAGS:
        allowed_obj = globals().get(flag_name, None)
        if allowed_obj is None:
            # Флаг не определён — считаем команду недоступной
            continue
        try:
            ok = await _ensure_allowed_silent(ctx, allowed_obj)
        except Exception:
            ok = False
        if ok:
            available.append((cmd, desc))
    return available


def build_help_embed(
    ctx: commands.Context,
    category_key: str,
    *,
    admin_commands: list[tuple[str, str]] | None = None,
    admin_locked: bool = False,  # оставлено для совместимости сигнатур, не используется
) -> disnake.Embed:
    # Общие категории
    if category_key in ("items", "economy"):
        base = HELP_CATEGORIES_BASE[category_key]
        e = disnake.Embed(title=base["title"], description=base.get("hint", ""), color=base["color"])
        e.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        lines = [f"• `{c}` — {d}" for c, d in base["commands"]]
        e.add_field(name="Список команд", value="\n".join(lines) if lines else "—", inline=False)
        e.add_field(
            name="ℹ️ Подсказки",
            value="• Выберите категорию в меню ниже.\n• Вводите команды без угловых скобок.",
            inline=False
        )
        e.set_footer(text=f"{ctx.guild.name if ctx.guild else 'ЛС'} • Выберите категорию")
        return e

    # Администрация — показываем всем, без проверок
    admin_commands = admin_commands or ALL_ADMIN_COMMANDS
    e = disnake.Embed(
        title="🛠️ Категория: Администрация",
        description="Команды модерации, экономики и предметов для администраторов.",
        color=disnake.Color.green()
    )
    e.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    lines = [f"• `{c}` — {d}" for c, d in admin_commands]
    e.add_field(name="Список команд", value="\n".join(lines) if lines else "—", inline=False)
    e.add_field(
        name="ℹ️ Подсказки",
        value="• Выберите категорию в меню ниже.\n• Некоторые команды могут требовать права при выполнении.",
        inline=False
    )
    e.set_footer(text=f"{ctx.guild.name if ctx.guild else 'ЛС'} • Административные команды")
    return e


class HelpCategorySelect(disnake.ui.StringSelect):
    def __init__(self, parent_view: "HelpView", options: list[disnake.SelectOption]):
        super().__init__(
            custom_id="help_category_select",
            placeholder="Выберите категорию команд",
            options=options,
            row=0
        )
        self.parent_view = parent_view

    async def callback(self, inter: disnake.MessageInteraction):
        self.parent_view.category = self.values[0]
        await inter.response.edit_message(
            embed=self.parent_view._embed_for_current(),
            view=self.parent_view
        )


class HelpView(disnake.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        *,
        default_category: str,
        admin_commands: list[tuple[str, str]],
    ):
        super().__init__(timeout=HELP_VIEW_TIMEOUT)
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.message: Optional[disnake.Message] = None

        self.admin_commands = admin_commands
        self.category = default_category

        # Всегда показываем «Администрация»
        opts: list[disnake.SelectOption] = [
            disnake.SelectOption(label="📦 Предметы", value="items", description="Магазин, инвентарь, предметы"),
            disnake.SelectOption(label="💰 Экономика", value="economy", description="Баланс, переводы, доходы"),
            disnake.SelectOption(label="🛠️ Администрация", value="admin", description="Модерация, экономика, предметы"),
        ]
        self.add_item(HelpCategorySelect(self, opts))

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Эта панель доступна только инициатору.", ephemeral=True)
            return False
        return True

    def _embed_for_current(self) -> disnake.Embed:
        if self.category == "admin":
            return build_help_embed(
                self.ctx,
                "admin",
                admin_commands=self.admin_commands,
                admin_locked=False  # игнорируется
            )
        return build_help_embed(self.ctx, self.category)

    async def on_timeout(self):
        try:
            for child in self.children:
                if isinstance(child, (disnake.ui.Button, disnake.ui.SelectBase)):
                    child.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


@bot.command(name="ping", aliases=["пинг"])
async def ping_cmd(ctx: commands.Context):
    """
    Проверка задержки бота:
      !ping
    Показывает WS-пинг (heartbeat) и REST-пинг (время на отправку сообщения).
    """
    import time as _time

    # Измеряем REST-пинг: время между началом отправки и получением объекта сообщения
    start = _time.perf_counter()
    msg = await ctx.send("🛰️ Измеряю задержку…")
    rest_ms = (_time.perf_counter() - start) * 1000.0

    # WS-пинг из bot.latency (секунды) -> мс
    ws_ms = bot.latency * 1000.0

    embed = disnake.Embed(
        title="🏓 Pong!",
        color=disnake.Color.green(),
        description=(
            f"• WS-пинг: **{ws_ms:.0f} мс**\n"
            f"• REST-пинг: **{rest_ms:.0f} мс**"
        )
    )

    # Обновляем сообщение на красивый embed
    await msg.edit(content=None, embed=embed)


ALL_ADMIN_COMMANDS: list[tuple[str, str]] = [
    (cmd, desc) for cmd, desc, _ in ADMIN_COMMANDS_WITH_FLAGS
]


@bot.command(name="help", aliases=["помощь"])
async def help_cmd(ctx: commands.Context, category: str = None):
    """
    Интерактивное меню помощи без проверки прав.
    Пример:
      !help               — открыть меню
      !help администрация — открыть админку
    """
    # Нормализуем желаемую категорию
    key_map = {
        "предметы": "items", "items": "items", "item": "items", "магазин": "items",
        "экономика": "economy", "eco": "economy", "economy": "economy",
        "админ": "admin", "админка": "admin", "администрация": "admin", "admin": "admin",
    }
    default_key = key_map.get((category or "").strip().lower(), "items")

    view = HelpView(
        ctx,
        default_category=default_key,
        admin_commands=ALL_ADMIN_COMMANDS
    )
    embed = view._embed_for_current()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


@bot.command(name="create-item", aliases=["Create-item", "CREATE-ITEM"])
async def create_item_cmd(ctx: commands.Context):
    """Запустить мастер создания предмета."""
    if not await ensure_allowed_ctx(ctx, ALLOWED_CREATE_ITEM):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    view = CreateItemWizard(ctx)
    embed = view.build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


def _parse_amount_and_name(raw: str) -> tuple[int, str] | tuple[None, None]:
    """
    Парсит строку вида:
      - "3 Меч" или "Меч 3" -> (3, "Меч")
      - "Меч"                -> (1, "Меч")

    Поддерживает числовые суффиксы ("15к", "2млн" и т.д.).
    """
    s = (raw or "").strip()
    if not s:
        return None, None
    parts = s.split()
    if not parts:
        return None, None

    if any(ch.isdigit() for ch in parts[0]):
        amt = safe_int(parts[0], name="Количество", min_v=1)
        name = " ".join(parts[1:]).strip()
        return (amt, name) if name else (None, None)

    if len(parts) > 1 and any(ch.isdigit() for ch in parts[-1]):
        amt = safe_int(parts[-1], name="Количество", min_v=1)
        name = " ".join(parts[:-1]).strip()
        return (amt, name) if name else (None, None)

    return 1, s


# ДОБАВИТЬ ЭТОТ КОД
@bot.command(name="edit-item", aliases=["Edit-item", "EDIT-ITEM"])
async def edit_item_cmd(ctx: commands.Context, *, item_name: str):
    """Запустить мастер редактирования предмета."""
    if not await ensure_allowed_ctx(ctx, ALLOWED_CREATE_ITEM): # Используем то же разрешение, что и для создания
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    if not item_name:
        return await ctx.send(embed=error_embed("Ошибка", "Укажите название или ID предмета для редактирования.\nПример: `!edit-item Золотая монета`"))
        
    # Ищем предмет с помощью умного резолвера
    item, err = await resolve_item_by_user_input(ctx, item_name)
    
    if err or not item:
        await ctx.send(embed=error_embed("Не удалось найти предмет", err or f"Предмет «{item_name}» не найден."))
        return
        
    # Запускаем тот же мастер, но передаем ему найденный предмет
    view = CreateItemWizard(ctx, item_to_edit=item)
    embed = view.build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

# ====================== DELETE ITEM ======================
@bot.command(name="delete-item", aliases=["Delete-item", "DELETE-ITEM"])
async def delete_item_cmd(ctx: commands.Context, *, item_query: str = ""):
    """
    Удалить предмет из магазина со всеми связанными записями.
    Использование: !delete-item <название|ID>
    """
    # Разумно ограничить только админам/модам — используем то же правило, что и для !create-item:
    if not await ensure_allowed_ctx(ctx, ALLOWED_DELETE_ITEM):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    if not item_query.strip():
        return await ctx.send(embed=error_embed("Ошибка", "Укажите название или ID предмета.\nПример: `!delete-item Золотая монета`"))

    # Резолвим предмет через ваш умный резолвер
    item, err = await resolve_item_by_user_input(ctx, item_query, timeout=60, attempts=3)
    if err or not item:
        return await ctx.send(embed=error_embed("Не удалось найти предмет", err or f"Предмет «{item_query}» не найден."))

    guild_id = ctx.guild.id
    item_id = int(item["id"])
    item_name = item["name"]

    # Подсчёт зависимостей (инвентари, ссылки в других предметах и пр.) — чтобы предупредить перед удалением
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()

    # Сколько всего экземпляров предмета у пользователей и у скольких пользователей он есть
    c.execute("SELECT COALESCE(SUM(quantity), 0) FROM inventories WHERE guild_id = ? AND item_id = ?", (guild_id, item_id))
    total_qty = int(c.fetchone()[0] or 0)
    c.execute("SELECT COUNT(*) FROM inventories WHERE guild_id = ? AND item_id = ? AND quantity > 0", (guild_id, item_id))
    holders = int(c.fetchone()[0] or 0)

    # Сколько ссылок на этот предмет в стоимостях других предметов
    c.execute("SELECT id, name, cost_items FROM items WHERE guild_id = ? AND id != ?", (guild_id, item_id))
    rows = c.fetchall()
    ref_count = 0
    for iid, iname, rcost in rows:
        if rcost:
            try:
                arr = json.loads(rcost)
                for r in arr or []:
                    if str(r.get("item_id")) == str(item_id):
                        ref_count += 1
            except Exception:
                pass

    conn.close()

    # Подтверждение удаления
    warn_lines = [
        f"Вы уверены, что хотите удалить предмет «{item_name}» (ID: {item_id})?",
        f"- В инвентарях у пользователей: {total_qty} шт. (у {holders} пользователей)",
        f"- Ссылок в стоимостях других предметов: {ref_count}",
        "",
        "Для подтверждения введите: удалить",
        "Для отмены — что угодно другое или подождите."
    ]
    confirm_embed = disnake.Embed(
        title="Подтверждение удаления предмета",
        description="\n".join(warn_lines),
        color=disnake.Color.red()
    )
    prompt_msg = await ctx.send(embed=confirm_embed)

    def check(m: disnake.Message):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        msg = await ctx.bot.wait_for("message", check=check, timeout=30.0)
        try:
            await msg.delete()
        except Exception:
            pass
        if msg.content.strip().lower() != "удалить":
            with contextlib.suppress(Exception):
                await prompt_msg.delete()
            return await ctx.send("Удаление отменено.", delete_after=10)
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            await prompt_msg.delete()
        return await ctx.send("Время на подтверждение истекло. Удаление отменено.", delete_after=10)

    # Удаляем предмет и связанные данные
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    cleaned_refs = 0
    try:
        # Чистим ссылки в других предметах (cost_items), чтобы не оставались «битые» ссылки
        c.execute("SELECT id, cost_items FROM items WHERE guild_id = ? AND id != ?", (guild_id, item_id))
        for other_id, rcost in c.fetchall():
            changed = False
            if rcost:
                try:
                    arr = json.loads(rcost)
                    new_arr = [r for r in (arr or []) if str(r.get("item_id")) != str(item_id)]
                    if len(new_arr) != len(arr):
                        changed = True
                        cleaned_refs += (len(arr) - len(new_arr))
                        # Если оплата предметами, но список пуст — можно оставить пустой JSON или NULL
                        # В остальном коде пустота обрабатывается как []
                        new_val = json.dumps(new_arr) if new_arr else None
                        c.execute("UPDATE items SET cost_items = ? WHERE guild_id = ? AND id = ?", (new_val, guild_id, other_id))
                except Exception:
                    pass

        # Удаляем записи инвентарей
        c.execute("DELETE FROM inventories WHERE guild_id = ? AND item_id = ?", (guild_id, item_id))
        # Удаляем состояние склада и дневные лимиты
        c.execute("DELETE FROM item_shop_state WHERE guild_id = ? AND item_id = ?", (guild_id, item_id))
        c.execute("DELETE FROM item_user_daily WHERE guild_id = ? AND item_id = ?", (guild_id, item_id))
        # Удаляем сам предмет
        c.execute("DELETE FROM items WHERE guild_id = ? AND id = ?", (guild_id, item_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return await ctx.send(embed=error_embed("Ошибка удаления", f"Не удалось удалить предмет: {e}"))
    finally:
        conn.close()

    # Логи (если у вас есть send_shop_item_action_log)
    try:
        await send_shop_item_action_log(
            guild=ctx.guild,
            actor=ctx.author,
            action="delete",
            item_name=item_name
        )
    except Exception as e:
        print(f"Failed to send shop item action log: {e}")

    done_embed = disnake.Embed(
        title="✅ Предмет удалён",
        description=(
            f"«{item_name}» (ID: {item_id}) успешно удалён.\n"
            f"• Очищено у пользователей: {total_qty} шт. (у {holders} пользователей)\n"
            f"• Удалено ссылок в стоимостях: {cleaned_refs}"
        ),
        color=disnake.Color.green()
    )
    await ctx.send(embed=done_embed)
# ====================== /DELETE ITEM ======================

# ====================== ITEM LIST (все предметы) ======================
@bot.command(name="item-list")
async def item_list_cmd(ctx: commands.Context, page: int = 1):
    """
    Список всех предметов (включая скрытые).
    Интерфейс и навигация — как у !shop.
    """
    # Если хотите сделать общедоступной — замените на ALLOWED_SHOP
    if not await ensure_allowed_ctx(ctx, ALLOWED_CREATE_ITEM):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    all_items = list_items_db(ctx.guild.id)  # берём все, без фильтра is_listed
    view = ShopView(ctx, all_items)
    if page > 0:
        view.page = min(max(0, page - 1), view.max_page)
        view._sync_buttons_state()
    embed = view._build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg
# ====================== /ITEM LIST ======================

@bot.command(name="buy", aliases=["Buy", "BUY", "Купить", "купить", "КУПИТЬ"])
async def buy_cmd(ctx: commands.Context, *, raw: str):
    if not await ensure_allowed_ctx(ctx, ALLOWED_BUY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    try:
        amount, name = _parse_amount_and_name(raw)
    except ValueError as e:
        return await ctx.send(embed=error_embed("Неверное количество", str(e)))
    if amount is None or not name:
        return await ctx.send(embed=usage_embed("buy"))
    if amount <= 0:
        return await ctx.send(embed=error_embed("Неверное количество", "Количество должно быть положительным."))

    item, err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if err:
        return await ctx.send(embed=error_embed("Выбор предмета", err))

    # ВАЖНО: нормализация
    item = ensure_item_normalized(item)

    if not item["is_listed"]:
        return await ctx.send(embed=error_embed("Покупка недоступна", "Этот предмет не продаётся в магазине."))

    # Проверка ролей (исправлен отступ)
    req = item.get("roles_required_buy") or []
    if req and not has_any_role(ctx.author, req):
        return await ctx.send(embed=error_embed(
            "Недостаточно прав",
            "Для покупки требуется иметь одну из ролей: " + render_roles_for_embed(ctx.guild, req)
        ))

    # ——— НОВОЕ: проверка лицензии предмета ———
    lic_id = item.get("license_role_id")
    if lic_id is not None:
        try:
            lic_id = int(lic_id)
        except Exception:
            lic_id = None
    if lic_id:
        has_license = any(r.id == lic_id for r in ctx.author.roles)
        if not has_license:
            lic_role = ctx.guild.get_role(lic_id)
            mention = lic_role.mention if lic_role else f"<@&{lic_id}>"
            emb = disnake.Embed(
                title="Покупка недоступна",
                description=(
                    f"Для покупки предмета «{item.get('name', 'Без названия')}» требуется лицензия {mention}.\n"
                    f"Для получения лицензии обращайтесь к её владельцу."
                ),
                color=disnake.Color.orange()
            )
            return await ctx.send(embed=emb)
    # ——— конец проверки лицензии ———

    ensure_item_state(ctx.guild.id, item)
    stock = get_current_stock(ctx.guild.id, item["id"])
    if stock is not None and stock < amount:
        return await ctx.send(embed=error_embed("Недостаточно на складе", f"Доступно только {stock} шт."))

    if item["per_user_daily_limit"] > 0:
        used = get_user_daily_used(ctx.guild.id, item["id"], ctx.author.id)
        remain = item["per_user_daily_limit"] - used
        if remain <= 0 or amount > remain:
            return await ctx.send(embed=error_embed("Превышен дневной лимит", f"Доступно к покупке сегодня: {max(remain,0)} шт."))

    total_cost_money = 0
    need_items = []

    if item["buy_price_type"] == "currency":
        total_cost_money = item["price"] * amount
        bal = get_balance(ctx.guild.id, ctx.author.id)
        if bal < total_cost_money:
            return await ctx.send(embed=error_embed("Недостаточно средств", f"Нужно {format_price(total_cost_money)}, у вас {format_number(bal)} {MONEY_EMOJI}."))
    else:
        # cost_items гарантированно list[dict] после ensure_item_normalized
        for r in item["cost_items"]:
            need_items.append({"item_id": int(r["item_id"]), "qty": int(r["qty"]) * amount})
        lacking = []
        all_items_map = {it["id"]: it for it in list_items_db(ctx.guild.id)}
        for r in need_items:
            have = get_user_item_qty(ctx.guild.id, ctx.author.id, r["item_id"])
            if have < r["qty"]:
                lacking.append(f"{all_items_map.get(r['item_id'], {'name': 'ID '+str(r['item_id'])})['name']} {r['qty']} шт. ( у вас {have} шт. )")
        if lacking:
            return await ctx.send(embed=error_embed(":no_entry_sign: Нехватка предметов:", "**Нехватает:**\n- " + "\n- ".join(lacking)))

    if total_cost_money > 0:
        update_balance(ctx.guild.id, ctx.author.id, -total_cost_money)
    if need_items:
        for r in need_items:
            ok = remove_items_from_user(ctx.guild.id, ctx.author.id, r["item_id"], r["qty"])
            if not ok:
                return await ctx.send(embed=error_embed("Ошибка", "Не удалось списать требуемые предметы. Попробуйте снова."))

    add_items_to_user(ctx.guild.id, ctx.author.id, item["id"], amount)

    if stock is not None:
        change_stock(ctx.guild.id, item["id"], -amount)
    if item["per_user_daily_limit"] > 0:
        add_user_daily_used(ctx.guild.id, item["id"], ctx.author.id, amount)

    if item["roles_removed_on_buy"]:
        roles_to_remove = [ctx.guild.get_role(r) for r in item["roles_removed_on_buy"] if ctx.guild.get_role(r)]
        if roles_to_remove:
            with contextlib.suppress(Exception):
                await ctx.author.remove_roles(*roles_to_remove, reason=f"Покупка предмета: {item['name']}")
    if item["roles_granted_on_buy"]:
        roles_to_add = [ctx.guild.get_role(r) for r in item["roles_granted_on_buy"] if ctx.guild.get_role(r)]
        if roles_to_add:
            with contextlib.suppress(Exception):
                await ctx.author.add_roles(*roles_to_add, reason=f"Покупка предмета: {item['name']}")

    new_bal = get_balance(ctx.guild.id, ctx.author.id)
    desc = f"**Вы купили:** {amount} шт. *{item['name']}*!"
    if total_cost_money > 0:
        desc += f"\n**Списано:** {format_price(total_cost_money)}."
    elif need_items:
        # Вывести списанные предметы в столбик
        id2name = {it["id"]: it["name"] for it in list_items_db(ctx.guild.id)}
        lines = []
        for r in need_items:
            nm = id2name.get(r["item_id"], f"ID {r['item_id']}")
            lines.append(f"*- {nm} {r['qty']} шт.*")
        desc += "\n**Оплачено предметами:**\n" + "\n".join(lines)

    await ctx.send(embed=disnake.Embed(title=":shopping_bags: Покупка успешна", description=desc, color=disnake.Color.green()))

@bot.command(name="sell", aliases=["Sell", "SELL"])
async def sell_cmd(ctx: commands.Context, *, raw: str):
    """
    Продать предмет системе: !sell [кол-во] <название|ID>
    Если у предмета «skip» — продажа запрещена.
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_SELL):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    try:
        amount, name = _parse_amount_and_name(raw)
    except ValueError as e:
        return await ctx.send(embed=error_embed("Неверное количество", str(e)))
    if amount is None or not name:
        return await ctx.send(embed=usage_embed("sell"))
    if amount <= 0:
        return await ctx.send(embed=error_embed("Неверное количество", "Количество должно быть положительным."))

    item, err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if err:
        return await ctx.send(embed=error_embed("Выбор предмета", err))

    if not has_any_role(ctx.author, item["roles_required_sell"]):
        return await ctx.send(embed=error_embed(":closed_lock_with_key: Нет доступа", "У вас нет требуемых ролей для продажи этого предмета."))

    if item["disallow_sell"]:
        return await ctx.send(embed=error_embed("Продажа запрещена", "Этот предмет нельзя продать системе."))

    have = get_user_item_qty(ctx.guild.id, ctx.author.id, item["id"])
    if have < amount:
        return await ctx.send(embed=error_embed("Недостаточно предметов", f"У вас только {have}× «{item['name']}»."))
    if not remove_items_from_user(ctx.guild.id, ctx.author.id, item["id"], amount):
        return await ctx.send(embed=error_embed("Ошибка", "Не удалось списать предметы. Попробуйте снова."))

    sell_each = item["sell_price"] if item["sell_price"] is not None else effective_sell_price(item)
    total = sell_each * amount
    update_balance(ctx.guild.id, ctx.author.id, total)
    new_bal = get_balance(ctx.guild.id, ctx.author.id)

    embed = disnake.Embed(
        title="Продажа успешна",
        description=(f"Вы продали {amount}× «{item['name']}» за {format_price(total)} "
                     f"(по {format_price(sell_each)} за шт.).\nБаланс: {format_number(new_bal)} {MONEY_EMOJI}"),
        color=disnake.Color.green()
    )
    await ctx.send(embed=embed)


def render_roles_for_embed(guild: disnake.Guild, ids: list[int | str]) -> str:
    if not ids:
        return "—"
    parts = []
    for rid in ids:
        try:
            rid = int(rid)
        except Exception:
            continue
        role = guild.get_role(rid)
        parts.append(role.mention if role else f"неизвестная роль ({rid})")
    return ", ".join(parts)


@bot.command(name="item-info", aliases=["iteminfo", "ii", "ItemInfo", "ITEMINFO", "Iteminfo", "Item-info"])
async def item_info_cmd(ctx: commands.Context, *, name: str):
    if not await ensure_allowed_ctx(ctx, ALLOWED_ITEM_INFO):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    if not name or not name.strip():
        return await ctx.send(embed=usage_embed("item-info"))

    item, err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if err:
        return await ctx.send(embed=error_embed("Выбор предмета", err))

    # ВАЖНО: нормализация
    item = ensure_item_normalized(item)

    ensure_item_state(ctx.guild.id, item)
    stock_now = get_current_stock(ctx.guild.id, item["id"])
    user_qty = get_user_item_qty(ctx.guild.id, ctx.author.id, item["id"])
    balance = get_balance(ctx.guild.id, ctx.author.id)

    all_items = list_items_db(ctx.guild.id)
    id2name = {i["id"]: i["name"] for i in all_items}

    embed = disnake.Embed(
        title=f"📦 {item['name']}",
        color=disnake.Color.from_rgb(88, 101, 242),
        description=(item["description"] or "Без описания.").strip()[:600]
    )
    embed.set_author(name=ctx.guild.name, icon_url=getattr(ctx.guild.icon, "url", None))
    embed.set_thumbnail(url=ctx.author.display_avatar.url)

    if (item.get("buy_price_type") or "currency") == "currency":
        embed.add_field(name="💳 Цена покупки", value=f"**{format_price(item['price'])}**", inline=True)
    else:
        if item["cost_items"]:
            cost_lines = []
            for r in item["cost_items"]:
                try:
                    rid = int(r["item_id"])
                    qty = int(r["qty"])
                except Exception:
                    continue
                cost_lines.append(f"• {id2name.get(rid, f'ID {rid}')} × {qty}")
            embed.add_field(name="🔁 Цена (обмен предметами)", value="\n".join(cost_lines), inline=False)
        else:
            embed.add_field(name="🔁 Цена (обмен предметами)", value="— не задано", inline=True)

    if item["disallow_sell"]:
        embed.add_field(name="🛑 Продажа системе", value="Запрещена", inline=True)
    else:
        embed.add_field(name="🏷️ Цена продажи", value=f"**{format_price(effective_sell_price(item))}**", inline=True)

    listed = "Да" if item["is_listed"] else "Нет"
    stock_total = item["stock_total"]
    restock = item["restock_per_day"] or 0
    if stock_total is None:
        stock_text = "∞ (без ограничений)"
    else:
        cur = "?" if stock_now is None else str(stock_now)
        stock_text = f"{cur} из {stock_total}"
        if restock:
            stock_text += f" • +{restock}/день"
    embed.add_field(
        name="📦 Наличие / листинг",
        value=f"В продаже: **{listed}**\nСклад: **{stock_text}**",
        inline=False
    )

    per_user = item["per_user_daily_limit"]
    embed.add_field(
        name="⏱️ Лимиты",
        value=f"На пользователя в день: **{per_user if per_user else 'без лимита'}**",
        inline=True
    )

    # Форматируем роли так же, как в мастере: просто упоминания
    def fmt_roles(ids: list[int]) -> str:
        return ", ".join(f"<@&{r}>" for r in ids) if ids else "—"

    embed.add_field(
        name="🔐 Доступ",
        value=f"Покупка: {fmt_roles(item['roles_required_buy'])}\nПродажа: {fmt_roles(item['roles_required_sell'])}",
        inline=False
    )

    grants = fmt_roles(item["roles_granted_on_buy"])
    removes = fmt_roles(item["roles_removed_on_buy"])
    if grants != "—" or removes != "—":
        embed.add_field(name="🎁 При покупке", value=f"Выдаёт роли: {grants}\nСнимает роли: {removes}", inline=False)

    embed.add_field(
        name="👤 Ваши данные",
        value=f"Баланс: **{format_number(balance)} {MONEY_EMOJI}**\nВ инвентаре: **{user_qty} шт.**",
        inline=False
    )
    
    lic_val = "—"
    try:
        # item тут — нормализованный dict, но license может отсутствовать; достанем сырцом
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("SELECT license_role_id FROM items WHERE guild_id=? AND id=?", (ctx.guild.id, item["id"]))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            lic_val = f"<@&{int(row[0])}>"
    except:
        pass
    embed.add_field(name="🔖 Лицензия", value=lic_val, inline=True)

    embed.set_footer(text=f"ID: {item['id']} • Купите: !buy [кол-во] {item['name']}")
    await ctx.send(embed=embed)


INV_ITEMS_PER_PAGE = 5
INV_VIEW_TIMEOUT = 120

def list_user_inventory_db(guild_id: int, user_id: int) -> list[dict]:
    """
    Возвращает список предметов пользователя:
    [{ item_id, name, description, quantity }]
    """
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT i.id, i.name, i.description, inv.quantity
        FROM inventories AS inv
        JOIN items AS i
          ON i.id = inv.item_id AND i.guild_id = inv.guild_id
        WHERE inv.guild_id = ? AND inv.user_id = ?
        ORDER BY i.name_lower
    """, (guild_id, user_id))
    rows = c.fetchall()
    conn.close()
    return [
        {
            "item_id": r[0],
            "name": r[1],
            "description": r[2] or "",
            "quantity": int(r[3]),
        } for r in rows
    ]


class InventoryView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, items: list[dict], owner: Optional[disnake.Member] = None):
        super().__init__(timeout=INV_VIEW_TIMEOUT)
        self.ctx = ctx
        self.items = items
        self.page = 0
        self.max_page = max(0, (len(items) - 1) // INV_ITEMS_PER_PAGE)
        self.author_id = ctx.author.id           # кто управляет пагинацией — инициатор
        self.owner = owner or ctx.author         # чей инвентарь показываем
        self._sync_buttons_state()

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Эта панель доступна только инициатору.", ephemeral=True)
            return False
        return True

    def _sync_buttons_state(self):
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                if child.custom_id == "inv_prev":
                    child.disabled = self.page <= 0
                elif child.custom_id == "inv_next":
                    child.disabled = self.page >= self.max_page

    def _page_slice(self) -> list[dict]:
        start = self.page * INV_ITEMS_PER_PAGE
        end = start + INV_ITEMS_PER_PAGE
        return self.items[start:end]

    def _build_embed(self) -> disnake.Embed:
        embed = disnake.Embed(
            title="🎒 Инвентарь",
            color=disnake.Color.green()
        )
        
        # В шапке — владелец инвентаря
        embed.set_author(
            name=self.owner.display_name,
            icon_url=self.owner.display_avatar.url
        )
        
        header_lines = [
            "🔸 Используйте предмет: !use <название|ID> [кол-во]",
            ""
        ]
        
        page_items = self._page_slice()
        lines = []
        
        if not page_items:
            lines.append("Инвентарь пуст.")
        else:
            for idx, it in enumerate(page_items):
                # Название — крупным жирным
                lines.append(f"**__{it['name']}__** — {it['quantity']} шт.")
                desc = (it['description'] or "").strip() or "Без описания."
                if len(desc) > 200:
                    desc = desc[:197] + "..."
                lines.append(desc)
                
                # Отступ в одну пустую строку между разными предметами
                if idx < len(page_items) - 1:
                    lines.append("")

        embed.description = "\n".join(header_lines + lines)
        embed.set_footer(text=f"Страница {self.page + 1} / {self.max_page + 1}")
        
        return embed


    @disnake.ui.button(label="Назад", style=disnake.ButtonStyle.secondary, custom_id="inv_prev")
    async def prev_page(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.page > 0:
            self.page -= 1
        self._sync_buttons_state()
        await inter.response.edit_message(embed=self._build_embed(), view=self)

    @disnake.ui.button(label="Вперед", style=disnake.ButtonStyle.primary, custom_id="inv_next")
    async def next_page(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.page < self.max_page:
            self.page += 1
        self._sync_buttons_state()
        await inter.response.edit_message(embed=self._build_embed(), view=self)

    async def on_timeout(self):
        self.stop()
        try:
            for child in self.children:
                if isinstance(child, disnake.ui.Button):
                    child.disabled = True
            if hasattr(self, "message") and self.message:
                await self.message.edit(view=self)
        except Exception:
            pass
        
        
class InventoryPermissionView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, requester: disnake.Member, owner: disnake.Member):
        super().__init__(timeout=INV_PERMISSION_TIMEOUT)
        self.ctx = ctx
        self.requester = requester
        self.owner = owner
        self.message: Optional[disnake.Message] = None

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("Только владелец инвентаря может выбрать.", ephemeral=True)
            return False
        return True

    def _disable_buttons(self):
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                child.disabled = True

    @disnake.ui.button(label="Разрешить", style=disnake.ButtonStyle.success, custom_id="inv_allow")
    async def allow(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer()
        # Отправляем инвентарь владельца — запрашивающему
        items = list_user_inventory_db(self.ctx.guild.id, self.owner.id)
        inv_view = InventoryView(self.ctx, items, owner=self.owner)
        embed = inv_view._build_embed()
        msg = await self.ctx.send(content=self.requester.mention, embed=embed, view=inv_view)
        inv_view.message = msg

        # Обновляем сообщение-запрос: показываем, что доступ предоставлен
        self._disable_buttons()
        result_embed = disnake.Embed(
            title="Просмотр инвентаря",
            description=f"✅ {self.owner.mention} предоставил доступ {self.requester.mention}.",
            color=disnake.Color.green()
        )
        result_embed.set_author(name=self.requester.display_name, icon_url=self.requester.display_avatar.url)
        await inter.edit_original_message(embed=result_embed, view=self)

    @disnake.ui.button(label="Запретить", style=disnake.ButtonStyle.danger, custom_id="inv_deny")
    async def deny(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Уведомляем запрашивающего об отказе
        deny_embed = disnake.Embed(
            title="Просмотр инвентаря",
            description=f"⛔ {self.owner.mention} отклонил запрос на просмотр инвентаря.",
            color=disnake.Color.red()
        )
        deny_embed.set_author(name=self.owner.display_name, icon_url=self.owner.display_avatar.url)
        await self.ctx.send(content=self.requester.mention, embed=deny_embed)

        # Обновляем сообщение-запрос
        self._disable_buttons()
        result_embed = disnake.Embed(
            title="Просмотр инвентаря",
            description=f"🚫 Доступ не предоставлен.",
            color=disnake.Color.red()
        )
        result_embed.set_author(name=self.requester.display_name, icon_url=self.requester.display_avatar.url)
        await inter.response.edit_message(embed=result_embed, view=self)

    async def on_timeout(self):
        try:
            self._disable_buttons()
            if self.message:
                timeout_embed = disnake.Embed(
                    title="Просмотр инвентаря",
                    description="⌛ Запрос истек. Вы можете отправить новый запрос командой `!inv @пользователь`.",
                    color=disnake.Color.dark_gray()
                )
                timeout_embed.set_author(name=self.requester.display_name, icon_url=self.requester.display_avatar.url)
                await self.message.edit(embed=timeout_embed, view=self)
        except Exception:
            pass
        
class ExportDealView(disnake.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        deal_id: int,
        seller: disnake.Member,
        buyer: disnake.Member,
        item: dict,
        quantity: int,
        price: int,
        delivery: int,
        expires_at_unix: int
    ):
        super().__init__(timeout=300)  # 5 минут
        self.ctx = ctx
        self.deal_id = deal_id
        self.seller = seller
        self.buyer = buyer
        self.item = item
        self.quantity = quantity
        self.price = price
        self.delivery = delivery
        self.total = price + delivery
        self.expires_at_unix = expires_at_unix
        self.message: Optional[disnake.Message] = None

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        # Нажимать может только покупатель
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("Кнопки доступны только указанному покупателю.", ephemeral=True)
            return False
        return True

    def _disable_all(self):
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                child.disabled = True

    def _build_result_embed(self, success: bool) -> disnake.Embed:
        color = disnake.Color.green() if success else disnake.Color.red()
        e = disnake.Embed(title="Экспорт", color=color)
        e.set_author(name=self.seller.display_name, icon_url=self.seller.display_avatar.url)

        # Блок 1
        e.add_field(
            name="\u200b",
            inline=False,
            value=(
                f">>> Товар: {self.item['name']}\n"
                f"Количество предмета: {self.quantity}\n"
                f"Статус сделки: {'Успешно' if success else 'Неуспешно'}"
            )
        )

        # Блок 2
        e.add_field(
            name="\u200b",
            inline=False,
            value=(
                f">>> Сумма сделки - {format_price(self.price)}\n"
                f"Доставка: {format_price(self.delivery)}"
            )
        )

        # Блок 3
        e.add_field(
            name="\u200b",
            inline=False,
            value=(
                f">>> Экспортер: {self.seller.mention}\n"
                f"Покупатель: {self.buyer.mention}"
            )
        )

        server_icon = getattr(self.ctx.guild.icon, "url", None)
        e.set_footer(text=f"{self.ctx.guild.name} • {datetime.now().strftime('%d.%m.%Y %H:%M')}", icon_url=server_icon)
        return e

    async def _finish_as(self, inter: disnake.MessageInteraction, status: str, success: bool, info_ephemeral: Optional[str] = None):
        try:
            db_update_export_status(self.deal_id, status)
        except Exception:
            pass

        self._disable_all()
        with contextlib.suppress(Exception):
            await inter.edit_original_message(view=self)

        # Итоговое сообщение в чат (по ТЗ: отправляем "красивое" вне зависимости от успеха)
        result_embed = self._build_result_embed(success)
        await self.ctx.send(embed=result_embed)

        # Небольшое эпемеральное уведомление нажимавшему
        if info_ephemeral:
            with contextlib.suppress(Exception):
                await inter.followup.send(info_ephemeral, ephemeral=True)

        self.stop()

    @disnake.ui.button(label="Принять", style=disnake.ButtonStyle.secondary, custom_id="export_accept")
    async def accept(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer()

        # Повторные проверки (пока шло ожидание):
        # 1) Наличие предметов у продавца
        have = get_user_item_qty(self.ctx.guild.id, self.seller.id, self.item["id"])
        if have < self.quantity:
            return await self._finish_as(inter, "rejected", False, info_ephemeral="У продавца больше нет нужного количества товара.")

        # 2) Деньги у покупателя
        buyer_bal = get_balance(self.ctx.guild.id, self.buyer.id)
        if buyer_bal < self.total:
            return await self._finish_as(inter, "rejected", False, info_ephemeral="Недостаточно средств для оплаты сделки.")

        # Проводим транзакцию шагами с доп. проверками
        # Списание предметов у продавца
        if not remove_items_from_user(self.ctx.guild.id, self.seller.id, self.item["id"], self.quantity):
            return await self._finish_as(inter, "rejected", False, info_ephemeral="Не удалось списать товар у продавца.")

        # Списание денег у покупателя
        update_balance(self.ctx.guild.id, self.buyer.id, -self.total)
        # Начисление денег продавцу (только сумма сделки без доставки)
        update_balance(self.ctx.guild.id, self.seller.id, self.price)
        # Выдача товара покупателю
        add_items_to_user(self.ctx.guild.id, self.buyer.id, self.item["id"], self.quantity)

        # Обновляем статус и финалим
        await self._finish_as(inter, "accepted", True, info_ephemeral="Сделка успешно проведена.")

    @disnake.ui.button(label="Отклонить", style=disnake.ButtonStyle.secondary, custom_id="export_reject")
    async def reject(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer()
        await self._finish_as(inter, "rejected", False, info_ephemeral="Вы отклонили предложение.")

    async def on_timeout(self):
        try:
            db_update_export_status(self.deal_id, "expired")
        except Exception:
            pass
        self._disable_all()
        with contextlib.suppress(Exception):
            if self.message:
                await self.message.edit(view=self)
        # Итоговое сообщение об истечении времени
        try:
            result_embed = self._build_result_embed(False)
            await self.ctx.send(embed=result_embed)
        except Exception:
            pass
        
def _extract_user_id_from_mention(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.match(r"<@!?(?P<id>\d+)>$", s.strip())
    if m:
        return int(m.group("id"))
    if s.isdigit():
        # Это может быть и страница, и ID. Разрулим в команде.
        return int(s)
    return None


def _parse_export_tail(raw: str) -> tuple[Optional[str], Optional[int], Optional[int], Optional[str]]:
    """
    Парсит '<Название предмета> <Кол-во> <Цена>'.
    Возвращает: (name, qty, price, error)
    """
    if not raw:
        return None, None, None, "Укажите: <Название предмета> <Кол-во> <Цена>."
    parts = [p.strip() for p in raw.split() if p.strip()]
    if len(parts) < 3:
        return None, None, None, "Недостаточно аргументов. Пример: !export @user Железо 10 5000"
    
    HUMAN_LIMIT_PRICE = 1_000_000_000_000_000  # настройте под свою экономику
    HUMAN_LIMIT_QTY = 1_000_000_000

    try:
        qty = safe_int(parts[-2], name="Кол-во", min_v=1, max_v=HUMAN_LIMIT_QTY)
        price = safe_int(parts[-1], name="Цена", min_v=1, max_v=HUMAN_LIMIT_PRICE)
    except ValueError as e:
        return None, None, None, str(e)

    name = " ".join(parts[:-2]).strip()
    if not name:
        return None, None, None, "Название предмета не распознано."
    return name, qty, price, None


@bot.command(name="export", aliases=["Export", "EXPORT", "экспорт", "Экспорт", "ЭКСПОРТ"])
async def export_cmd(ctx: commands.Context, member: disnake.Member, *, raw: str):
    """
    Продажа предметов из инвентаря одного пользователя другому:
      !export @покупатель <Название предмета> <Кол-во> <Цена>
    Цена — сумма продажи БЕЗ доставки (доставка 5% оплачивается покупателем сверх цены).
    """
    # Если у вас есть система прав — проверим её (как в остальных командах)
    if not await ensure_allowed_ctx(ctx, ALLOWED_EXPORT):  # type: ignore
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    seller = ctx.author
    buyer = member

    if buyer.id == seller.id:
        return await ctx.send(embed=error_embed("Неверный получатель", "Нельзя экспортировать самому себе."))

    # Парсим "<название> <qty> <price>"
    name, qty, price, err = _parse_export_tail(raw)
    if err:
        return await ctx.send(embed=error_embed("Неверные аргументы", err))

    # Определяем предмет
    item, choose_err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if choose_err or not item:
        return await ctx.send(embed=error_embed("Выбор предмета", choose_err or "Предмет не найден."))

    # Предварительные проверки
    # 1) Продавец: наличие нужного количества
    have = get_user_item_qty(ctx.guild.id, seller.id, item["id"])
    if have < qty:
        return await ctx.send(embed=error_embed("Недостаточно предметов", f"У вас только {have} шт. «{item['name']}»."))
    # 2) Покупатель: хватает ли денег с учётом доставки
    delivery = (price * 5 + 50) // 100  # 5% c округлением
    total = price + delivery
    buyer_balance = get_balance(ctx.guild.id, buyer.id)
    if buyer_balance < total:
        nice = disnake.Embed(
            title="Недостаточно средств",
            description=(
                f"Для оплаты требуется: **{format_price(total)}**\n"
                f"— Сумма сделки: **{format_price(price)}**\n"
                f"— Доставка (5%): **{format_price(delivery)}**"
            ),
            color=disnake.Color.red()
        )
        nice.set_author(name=buyer.display_name, icon_url=buyer.display_avatar.url)
        return await ctx.send(embed=nice)

    # Создаём запись в БД (pending)
    deal_id = db_create_export_deal(
        guild_id=ctx.guild.id,
        seller_id=seller.id,
        buyer_id=buyer.id,
        item_id=item["id"],
        quantity=qty,
        price=price,
        delivery=delivery,
        total_paid=total
    )

    # Формируем Embed запроса
    per_unit = max(1, int(round(price / qty)))  # показываем целое за шт.
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    expires_unix = int(expires_at.timestamp())

    offer = disnake.Embed(title="Запрос на экспорт", color=disnake.Color.blurple())
    offer.set_author(name=seller.display_name, icon_url=seller.display_avatar.url)

    # Подзаголовок и детали
    small = f"_Предложение об экспорте успешно отправлено стране — {buyer.mention}_"
    offer.description = (
        f"{small}\n\n"
        f">>> Детали сделки:\n"
        f"Страна экспортер: {seller.mention}\n"
        f"Страна импортер: {buyer.mention}."
    )

    # Блок 1 (>>>)
    offer.add_field(
        name="\u200b",
        inline=False,
        value=(
            f">>> Страна {seller.mention} экспортирует в страну {buyer.mention}:\n"
            f"{qty} шт. {item['name']}\n"
            f"Оплата: {format_price(price)} ({format_price(per_unit)} за 1 шт)\n"
            f"Доставка: {format_price(delivery)}."
        )
    )

    # Блок 2 (>>> + таймер)
    offer.add_field(
        name="\u200b",
        inline=False,
        value=">>> На решение предоставлено 5 минут."
    )

    server_icon = getattr(ctx.guild.icon, "url", None)
    offer.set_footer(text=f"{ctx.guild.name} • {datetime.now().strftime('%d.%m.%Y %H:%M')}", icon_url=server_icon)

    # Кнопки
    view = ExportDealView(
        ctx=ctx,
        deal_id=deal_id,
        seller=seller,
        buyer=buyer,
        item=item,
        quantity=qty,
        price=price,
        delivery=delivery,
        expires_at_unix=expires_unix
    )
    msg = await ctx.send(content=buyer.mention, embed=offer, view=view)
    view.message = msg

@bot.command(name="inv", aliases=["inventory", "инв", "инвентарь", "Inv", "Инвентарь", "Инв", "Inventory", "INV", "INVENTORY", "ИНВ", "ИНВЕНТАРЬ"])
async def inv_cmd(ctx: commands.Context, arg: Optional[str] = None, page: int = 1):
    """Открыть меню инвентаря или запросить чужой инвентарь: !inv [@пользователь|страница]."""
    if not await ensure_allowed_ctx(ctx, ALLOWED_INV):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    # Если аргумент не указан — показываем свой инвентарь (как раньше, с поддержкой page)
    if arg is None:
        items = list_user_inventory_db(ctx.guild.id, ctx.author.id)
        view = InventoryView(ctx, items, owner=ctx.author)
        if page > 0:
            view.page = min(max(0, page - 1), view.max_page)
            view._sync_buttons_state()
        embed = view._build_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        return

    # Есть аргумент — пытаемся распарсить как упоминание/ID участника
    raw_id = _extract_user_id_from_mention(arg)
    target_member: Optional[disnake.Member] = None

    if raw_id is not None:
        # Это может быть ID участника ИЛИ номер страницы.
        # Сначала попробуем как участника.
        target_member = ctx.guild.get_member(raw_id)
        if target_member is None:
            try:
                target_member = await ctx.guild.fetch_member(raw_id)
            except Exception:
                target_member = None

    if target_member:
        # Если запрос к себе — просто открыть как обычно
        if target_member.id == ctx.author.id:
            items = list_user_inventory_db(ctx.guild.id, ctx.author.id)
            view = InventoryView(ctx, items, owner=ctx.author)
            embed = view._build_embed()
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
            return

        # Отправляем владельцу запрос на разрешение
        req_embed = disnake.Embed(
            title="Просмотр инвентаря",
            description=f"Пользователь {ctx.author.mention} желает просмотреть ваш инвентарь.",
            color=disnake.Color.blurple()
        )
        req_embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        perm_view = InventoryPermissionView(ctx, requester=ctx.author, owner=target_member)
        req_msg = await ctx.send(content=target_member.mention, embed=req_embed, view=perm_view)
        perm_view.message = req_msg
        return

    # Если это не участник — возможно, это номер страницы
    if arg.isdigit():
        page_num = int(arg)
        if page_num <= 0:
            return await ctx.send("Номер страницы должен быть положительным числом.")

        items = list_user_inventory_db(ctx.guild.id, ctx.author.id)
        view = InventoryView(ctx, items, owner=ctx.author)
        view.page = min(max(0, page_num - 1), view.max_page)
        view._sync_buttons_state()
        embed = view._build_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        return

    # Иначе — нераспознанный аргумент
    await ctx.send("Укажите корректное упоминание пользователя (`@ник`) или номер страницы.")


def _parse_name_then_optional_amount(raw: str) -> tuple[Optional[str], Optional[int]]:
    """
    Парсит строку: '<название|ID> [кол-во]'.
    Если последний токен — число (поддерживаются суффиксы), это количество,
    иначе количество=1.
    """
    s = (raw or "").strip()
    if not s:
        return None, None
    parts = s.split()
    if not parts:
        return None, None
    if len(parts) > 1 and any(ch.isdigit() for ch in parts[-1]):
        amt = safe_int(parts[-1], name="Количество", min_v=1)
        name = " ".join(parts[:-1]).strip()
        return (name if name else None), amt
    return s, 1


@bot.command(name="reset-inventory", aliases=["reset-inv", "inv-reset"])
async def reset_inventory_cmd(ctx: commands.Context, member: disnake.Member):
    """
    Обнулить инвентарь пользователя с подтверждением:
      !reset-inventory @пользователь
    """
    # Права: при необходимости замените на свой ALLOWED_* флаг
    if not await ensure_allowed_ctx(ctx, ALLOWED_DELETE_ITEM):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    # Статистика до удаления
    distinct_items, total_qty = db_get_user_inventory_stats(ctx.guild.id, member.id)
    if distinct_items == 0:
        return await ctx.send(
            embed=disnake.Embed(
                title="ℹ️ Инвентарь уже пуст",
                description=f"У {member.mention} нет предметов для удаления.",
                color=disnake.Color.orange()
            ),
            delete_after=10
        )

    # Подтверждение
    warn_lines = [
        f"Вы уверены, что хотите полностью очистить инвентарь {member.mention}?",
        f"- Позиции: {format_number(distinct_items)}",
        f"- Предметов всего: {format_number(total_qty)}",
        "",
        "Для подтверждения введите: удалить",
        "Для отмены — введите любой другой текст или подождите."
    ]
    confirm_embed = disnake.Embed(
        title="Подтверждение обнуления инвентаря",
        description="\n".join(warn_lines),
        color=disnake.Color.red()
    )
    prompt_msg = await ctx.send(embed=confirm_embed)

    def check(m: disnake.Message):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        msg = await ctx.bot.wait_for("message", check=check, timeout=30.0)
        with contextlib.suppress(Exception):
            await msg.delete()
        if msg.content.strip().lower() not in ("удалить", "delete"):
            with contextlib.suppress(Exception):
                await prompt_msg.delete()
            return await ctx.send("Обнуление отменено.", delete_after=10)
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            await prompt_msg.delete()
        return await ctx.send("Время на подтверждение истекло. Обнуление отменено.", delete_after=10)

    # Выполняем сброс
    with contextlib.suppress(Exception):
        await prompt_msg.delete()

    removed_distinct, removed_total = db_reset_user_inventory(ctx.guild.id, member.id)

    # Ответ в чат
    done_embed = disnake.Embed(
        title="✅ Инвентарь обнулён",
        description=(
            f"Пользователь: {member.mention}\n"
            f"Удалено позиций: **{format_number(removed_distinct)}**\n"
            f"Удалено предметов всего: **{format_number(removed_total)}**"
        ),
        color=disnake.Color.green()
    )
    done_embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=done_embed)

    # Логирование (апанель-стиль)
    await send_inventory_action_log(ctx.guild, ctx.author, member, removed_distinct, removed_total)


@bot.command(name="use", aliases=["Use", "USE", "использовать", "Использовать", "ИСПОЛЬЗОВАТЬ"])
async def use_cmd(ctx: commands.Context, *, raw: str):
    """
    Использовать предмет из инвентаря:
      !use <название|ID> [кол-во]
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_USE):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    try:
        name, amount = _parse_name_then_optional_amount(raw)
    except ValueError as e:
        return await ctx.send(embed=error_embed("Неверное количество", str(e)))
    if not name:
        return await ctx.send(embed=usage_embed("use"))
    if amount <= 0:
        return await ctx.send(embed=disnake.Embed(
            title="Неверное количество",
            description="Количество должно быть положительным.",
            color=disnake.Color.red()
        ))

    item, err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if err:
        return await ctx.send(embed=error_embed("Выбор предмета", err))

    have = get_user_item_qty(ctx.guild.id, ctx.author.id, item["id"])
    if have <= 0:
        return await ctx.send(embed=disnake.Embed(
            title="Нет предмета",
            description=f"У вас нет «{item['name']}» в инвентаре.",
            color=disnake.Color.red()
        ))
    if have < amount:
        return await ctx.send(embed=disnake.Embed(
            title="Недостаточно предметов",
            description=f"У вас только {have} шт. «{item['name']}».",
            color=disnake.Color.red()
        ))

    ok = remove_items_from_user(ctx.guild.id, ctx.author.id, item["id"], amount)
    if not ok:
        return await ctx.send(embed=disnake.Embed(
            title="Ошибка",
            description="Не удалось списать предметы. Попробуйте ещё раз.",
            color=disnake.Color.red()
        ))

    embed = disnake.Embed(
        title="✅ Предмет использован",
        description=f"**Вы использовали:** {item['name']}  {amount} шт. ",
        color=disnake.Color.green()
    )
    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command(name="give-item", aliases=["Give-item", "GIVE-ITEM", "Give-Item"])
async def give_item_cmd(ctx: commands.Context, member: disnake.Member, *, raw: str):
    """
    Выдать предмет пользователю:
      !give-item @user <название|ID> [кол-во]
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_GIVE_ITEM):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    try:
        name, amount = _parse_name_then_optional_amount(raw)
    except ValueError as e:
        return await ctx.send(embed=error_embed("Неверное количество", str(e)))
    if not name:
        return await ctx.send(embed=usage_embed("give-item"))
    if amount <= 0:
        return await ctx.send(embed=disnake.Embed(
            title="Неверное количество",
            description="Количество должно быть положительным.",
            color=disnake.Color.red()
        ))

    item, err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if err:
        return await ctx.send(embed=error_embed("Выбор предмета", err))

    add_items_to_user(ctx.guild.id, member.id, item["id"], amount)
    embed = disnake.Embed(
        title="Выдача предмета",
        description=f"**{item['name']}** в количестве {amount} шт. добавлен в инвентарь пользователю {member.mention}.",
        color=disnake.Color.green()
    )
    await ctx.send(embed=embed)


@bot.command(name="take-item", aliases=["Take-item", "TAKE-ITEM", "Take-Item"])
async def take_item_cmd(ctx: commands.Context, member: disnake.Member, *, raw: str):
    """
    Забрать предмет у пользователя:
      !take-item @user <название|ID> [кол-во]
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_TAKE_ITEM):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    try:
        name, amount = _parse_name_then_optional_amount(raw)
    except ValueError as e:
        return await ctx.send(embed=error_embed("Неверное количество", str(e)))
    if not name:
        return await ctx.send(embed=usage_embed("take-item"))
    if amount <= 0:
        return await ctx.send(embed=disnake.Embed(
            title="Неверное количество",
            description="Количество должно быть положительным.",
            color=disnake.Color.red()
        ))

    item, err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if err:
        return await ctx.send(embed=error_embed("Выбор предмета", err))

    have = get_user_item_qty(ctx.guild.id, member.id, item["id"])
    if have < amount:
        return await ctx.send(embed=disnake.Embed(
            title="Недостаточно предметов у пользователя",
            description=f"У {member.mention} только {have} шт. **{item['name']}**.",
            color=disnake.Color.red()
        ))

    ok = remove_items_from_user(ctx.guild.id, member.id, item["id"], amount)
    if not ok:
        return await ctx.send(embed=disnake.Embed(
            title="Ошибка",
            description="Не удалось списать предметы. Попробуйте ещё раз.",
            color=disnake.Color.red()
        ))

    embed = disnake.Embed(
        title="Изъятие предмета",
        description=f"Забрано {amount} шт. «{item['name']}» у {member.mention}.",
        color=disnake.Color.orange()
    )
    await ctx.send(embed=embed)


DEFAULT_MIN_INCOME = 10
DEFAULT_MAX_INCOME = 50
DEFAULT_COOLDOWN = 3600

def get_work_settings(guild_id: int) -> tuple[int, int, int]:
    """
    Возвращает (min_income, max_income, cooldown_seconds).
    Если настроек нет — создает с дефолтами.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT min_income, max_income, cooldown_seconds FROM work_settings WHERE guild_id = ?", (guild_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute(
            "INSERT INTO work_settings (guild_id, min_income, max_income, cooldown_seconds) VALUES (?, ?, ?, ?)",
            (guild_id, DEFAULT_MIN_INCOME, DEFAULT_MAX_INCOME, DEFAULT_COOLDOWN)
        )
        conn.commit()
        result = (DEFAULT_MIN_INCOME, DEFAULT_MAX_INCOME, DEFAULT_COOLDOWN)
    else:
        result = (int(row[0]), int(row[1]), int(row[2]))
    conn.close()
    return result

def set_work_settings(guild_id: int, min_income: int, max_income: int, cooldown_seconds: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO work_settings (guild_id, min_income, max_income, cooldown_seconds)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            min_income = excluded.min_income,
            max_income = excluded.max_income,
            cooldown_seconds = excluded.cooldown_seconds
    """, (guild_id, min_income, max_income, cooldown_seconds))
    conn.commit()
    conn.close()

def get_last_work_ts(guild_id: int, user_id: int) -> Optional[int]:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT last_ts FROM work_cooldowns WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
    row = cursor.fetchone()
    conn.close()
    if row:
        return int(row[0])
    return None

def set_last_work_ts(guild_id: int, user_id: int, ts: int):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO work_cooldowns (guild_id, user_id, last_ts)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET last_ts = excluded.last_ts
    """, (guild_id, user_id, ts))
    conn.commit()
    conn.close()


from datetime import datetime

def _ri_items_to_str(guild: disnake.Guild, items: list[dict]) -> str:
    if not items:
        return "—"
    id2name = items_id_to_name_map(guild)
    parts = []
    for it in items:
        iid = int(it["item_id"])
        qty = int(it["qty"])
        nm = id2name.get(iid, f"ID {iid}")
        parts.append(f"{nm} × {qty}")
    return ", ".join(parts) if parts else "—"

def _ri_params_to_lines(guild: disnake.Guild, ri: dict) -> list[str]:
    # ri: {'role_id', 'income_type', 'money_amount', 'items', 'cooldown_seconds', ...}
    if not ri:
        return ["—"]
    lines = []
    typ = "💰 Деньги" if ri["income_type"] == "money" else "📦 Предметы"
    lines.append(f"Тип: {typ}")
    if ri["income_type"] == "money":
        lines.append(f"Сумма за сбор: {format_number(int(ri['money_amount'] or 0))} {MONEY_EMOJI}")
    else:
        lines.append(f"Предметы: {_ri_items_to_str(guild, ri.get('items') or [])}")
    lines.append(f"Кулдаун: {format_seconds(int(ri['cooldown_seconds'] or 0))}")
    return lines

def _ri_diff_lines(guild: disnake.Guild, before: Optional[dict], after: Optional[dict]) -> list[str]:
    # Возвращает список строк, описывающих изменения между before и after.
    # Сравниваем: income_type, money_amount, items, cooldown_seconds
    if not before and after:
        # Полное описание после
        return _ri_params_to_lines(guild, after)
    if before and not after:
        # Полное описание до
        return _ri_params_to_lines(guild, before)

    lines = []
    if not before or not after:
        return lines

    # Тип
    if (before.get("income_type") != after.get("income_type")):
        b = "💰 Деньги" if before.get("income_type") == "money" else "📦 Предметы"
        a = "💰 Деньги" if after.get("income_type") == "money" else "📦 Предметы"
        lines.append(f"Тип: {b} → {a}")

    # Сумма (имеет смысл для money)
    if int(before.get("money_amount") or 0) != int(after.get("money_amount") or 0):
        lines.append(f"Сумма: {format_number(int(before.get('money_amount') or 0))} → {format_number(int(after.get('money_amount') or 0))}")

    # Предметы (строковое представление)
    b_items = _ri_items_to_str(guild, before.get("items") or [])
    a_items = _ri_items_to_str(guild, after.get("items") or [])
    if b_items != a_items:
        lines.append(f"Предметы: {b_items} → {a_items}")

    # Кулдаун
    if int(before.get("cooldown_seconds") or 0) != int(after.get("cooldown_seconds") or 0):
        lines.append(f"Кулдаун: {format_seconds(int(before.get('cooldown_seconds') or 0))} → {format_seconds(int(after.get('cooldown_seconds') or 0))}")

    # Если не нашли явных различий (например, поля совпали, но меняли тип на тот же)
    if not lines:
        lines.append("Изменённые параметры: — (без видимых изменений значений)")

    return lines

async def send_role_income_log(
    guild: disnake.Guild,
    actor: disnake.Member,
    action: str,  # 'create' | 'update' | 'delete'
    role_id: int,
    before: Optional[dict],
    after: Optional[dict]
):
    """
    Шлёт лог в настроенный канал.
    """
    try:
        channel_id = db_get_role_income_log_channel(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id) or bot.get_channel(channel_id)  # bot должен быть доступен в области видимости
        if not channel:
            return

        title_map = {
            "create": "Создание доходной роли",
            "update": "Изменение доходной роли",
            "delete": "Удаление доходной роли",
        }
        color_map = {
            "create": disnake.Color.green(),
            "update": disnake.Color.blue(),
            "delete": disnake.Color.red(),
        }

        e = disnake.Embed(
            title=title_map.get(action, "Лог доходной роли"),
            color=color_map.get(action, disnake.Color.light_grey())
        )
        e.set_author(name=actor.display_name, icon_url=actor.display_avatar.url)

        # Роль
        role_mention = f"<@&{role_id}>"
        e.add_field(name="Роль", value=role_mention, inline=False)

        # Основная часть: параметры или изменения
        if action == "create":
            lines = _ri_params_to_lines(guild, after or {})
            body = "\n".join(lines)
            e.add_field(name="Параметры доходной роли", value=body or "—", inline=False)
            e.add_field(name="Пользователь", value=f"{actor.mention} добавил(а) доходную роль", inline=False)
        elif action == "update":
            lines = _ri_diff_lines(guild, before, after)
            body = "\n".join(lines)
            e.add_field(name="Изменённые параметры", value=body or "—", inline=False)
            e.add_field(name="Пользователь", value=f"{actor.mention} внёс(ла) изменения", inline=False)
        elif action == "delete":
            # Покажем, что удалили и что было
            lines = _ri_params_to_lines(guild, before or {})
            body = "\n".join(lines)
            e.add_field(name="Удалённая доходная роль", value=body or "—", inline=False)
            e.add_field(name="Пользователь", value=f"{actor.mention} удалил(а) доходную роль", inline=False)

        server_icon = getattr(guild.icon, "url", None)
        footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        e.set_footer(text=f"{guild.name} • {footer_time}", icon_url=server_icon)

        await channel.send(embed=e)
    except Exception:
        # Логи не должны падать с ошибкой на основной поток
        pass


async def send_shop_item_action_log(
    guild: disnake.Guild,
    actor: disnake.Member,
    action: str,  # 'create' | 'update' | 'delete'
    item_name: str
):
    """
    Отправляет лог действий с предметами магазина в канал, выбранный через !logmenu.
    Верхняя часть: аватарка и НИК актёра (display_name).
    """
    try:
        # Определение канала по вашей системе (аналогично send_money_action_log)
        channel_id = db_get_role_income_log_channel(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id) or bot.get_channel(channel_id)
        if not channel:
            return

        titles = {
            "create": (":tools: Создание предмета", disnake.Color.green()),
            "update": (":tools: Изменение предмета", disnake.Color.orange()),
            "delete": (":tools: Удаление предмета", disnake.Color.red()),
        }
        title, color = titles.get(action, ("Действие с предметом", disnake.Color.blurple()))

        e = disnake.Embed(title=title, color=color)

        # Шапка — ник (display_name) и аватарка актёра
        display_name = getattr(actor, "display_name", str(actor))
        e.set_author(name=display_name, icon_url=actor.display_avatar.url)

        # Предмет
        e.add_field(name="Предмет", value=f"`{item_name}`", inline=False)

        # Исполнитель
        e.add_field(name="Выполнил действие:", value=actor.mention, inline=False)

        # Подсказка по инфо-команде (кроме удаления)
        if action != "delete":
            e.add_field(name="Информация о предмете", value=f"!iteminfo {item_name}", inline=False)

        # Футер с иконкой сервера и временем
        server_icon = getattr(guild.icon, "url", None)
        footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        e.set_footer(text=f"{guild.name} • {footer_time}", icon_url=server_icon)

        await channel.send(embed=e)
    except Exception:
        # Не прерываем основную логику из-за проблем с логами
        pass


# ========= Логи денежных действий (команды денег) =========

from datetime import datetime
from typing import Optional, Union

async def send_money_action_log(
    guild: disnake.Guild,
    actor: disnake.Member,
    action: str,  # 'add' | 'remove' | 'reset'
    target: Union[disnake.Member, disnake.Role],
    amount: Optional[int]
):
    """
    Отправляет лог выполнения денежных команд в канал, выбранный через !logmenu.
    Верхняя часть: аватарка и РОЛЬ актёра (display_name).
    """
    try:
        channel_id = db_get_role_income_log_channel(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id) or bot.get_channel(channel_id)
        if not channel:
            return

        titles = {
            "add": ("Выдача средств", disnake.Color.green()),
            "remove": ("Списание средств", disnake.Color.orange()),
            "reset": ("Обнуление средств", disnake.Color.red()),
        }
        title, color = titles.get(action, ("Операция со средствами", disnake.Color.blurple()))

        e = disnake.Embed(title=title, color=color)

        # В шапке показываем НИК пользователя (display_name) рядом с аватаркой.
        display_name = getattr(actor, "display_name", str(actor))
        e.set_author(name=display_name, icon_url=actor.display_avatar.url)

        # Цель: пользователь или роль (в массовых командах)
        target_val = target.mention if hasattr(target, "mention") else str(target)
        e.add_field(name="Пользователь, в отношении которого выполнено действие", value=target_val, inline=False)

        # Исполнитель
        e.add_field(name="Пользователь, который выполнил команду", value=actor.mention, inline=False)

        # Сумма / Обнуление
        if action == "reset":
            e.add_field(name="Сумма", value="Обнуление", inline=False)
        else:
            e.add_field(
                name="Сумма",
                value=(f"{format_number(int(amount or 0))} {MONEY_EMOJI}"),
                inline=False
            )

        # Футер
        server_icon = getattr(guild.icon, "url", None)
        footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        e.set_footer(text=f"{guild.name} • {footer_time}", icon_url=server_icon)

        await channel.send(embed=e)
    except Exception:
        # Не ломаем основной поток из-за проблем с логами
        pass


async def send_inventory_action_log(
    guild: disnake.Guild,
    actor: disnake.Member,
    target: disnake.Member,
    distinct_items: int,
    total_qty: int
):
    """
    Логирует обнуление инвентаря в канал логов (используется тот же канал, что и для апанели).
    """
    try:
        channel_id = db_get_role_income_log_channel(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id) or bot.get_channel(channel_id)
        if not channel:
            return

        title = "Обнуление инвентаря"
        color = disnake.Color.red()

        e = disnake.Embed(title=title, color=color)
        # Шапка — ник и аватар исполнителя (как в apanel-логах)
        display_name = getattr(actor, "display_name", str(actor))
        e.set_author(name=display_name, icon_url=actor.display_avatar.url)

        # Поля
        e.add_field(name="Кому обнулили", value=target.mention, inline=False)
        e.add_field(name="Исполнитель", value=actor.mention, inline=False)
        e.add_field(
            name="Итог",
            value=f"Удалено позиций: {format_number(distinct_items)}\nУдалено предметов всего: {format_number(total_qty)}",
            inline=False
        )

        # Футер с названием сервера и временем
        server_icon = getattr(guild.icon, "url", None)
        footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        e.set_footer(text=f"{guild.name} • {footer_time}", icon_url=server_icon)

        await channel.send(embed=e)
    except Exception:
        # Не ломаем основной поток
        pass


async def send_role_change_log(
    guild: disnake.Guild,
    action: str,  # "add" | "remove"
    target: disnake.Member,
    role: disnake.Role,
    actor: disnake.Member
):
    """
    Логирует выдачу/снятие роли в канал логов (используется db_get_role_income_log_channel).
    Оформление — как в сообщении в чат.
    """
    try:
        channel_id = db_get_role_income_log_channel(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id) or bot.get_channel(channel_id)
        if not channel:
            return
        embed = build_role_change_embed(guild, action, target, role, actor)
        await channel.send(embed=embed)
    except Exception:
        pass


async def send_admin_action_log(
    guild: disnake.Guild,
    actor: disnake.Member,
    action: str,           # 'reset_inventories' | 'reset_balances' | 'reset_worldbank' | 'clear_shop' | 'clear_role_incomes'
    details: str
):
    """
    Отправляет лог действий админ-панели в канал логов (guild_logs.role_income_log_channel_id).
    Оформление:
      - Администратор: @mention
      - Параметры — в столбик (каждый «Ключ: Значение» отдельным полем)
      - Футер: <название сервера> • <время>
    """
    try:
        channel_id = db_get_role_income_log_channel(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id) or bot.get_channel(channel_id)
        if not channel:
            return

        titles = {
            "reset_inventories": ("Сброшены инвентари", disnake.Color.orange()),
            "reset_balances": ("Сброшены балансы пользователей", disnake.Color.orange()),
            "reset_worldbank": ("Сброшен бюджет Всемирного банка", disnake.Color.red()),
            "clear_shop": ("Очищен магазин предметов", disnake.Color.red()),
            "clear_role_incomes": ("Очищены доходные роли", disnake.Color.red()),
        }
        title, color = titles.get(action, ("Действие админ-панели", disnake.Color.blurple()))
        e = disnake.Embed(title=title, color=color)

        # Шапка — ник и аватар инициатора
        e.set_author(name=getattr(actor, "display_name", str(actor)), icon_url=actor.display_avatar.url)

        # Администратор (упоминание)
        e.add_field(name="Администратор", value=actor.mention, inline=False)

        # Разбор «деталей» на пары «ключ: значение» и вывод «в столбик»
        # Ищем все подстроки вида "Ключ: Значение" (разделители блоков — ; • перевод строки)
        # Пример: "Удалено предметов: 10; состояний склада: 5; дневных записей: 3"
        pairs = []
        if details:
            for key, val in re.findall(r"([^:;\n•]+?):\s*([^;•\n]+)", details):
                k = key.strip().strip(".").capitalize()
                v = val.strip().strip(".")
                if k and v:
                    pairs.append((k, v))

        if pairs:
            for k, v in pairs:
                e.add_field(name=k, value=v, inline=False)
        else:
            # Если пар «ключ: значение» не нашли — показываем весь текст одним блоком
            e.add_field(name="Детали", value=(details or "—"), inline=False)

        # Футер — сервер + время
        server_icon = getattr(guild.icon, "url", None)
        footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        e.set_footer(text=f"{guild.name} • {footer_time}", icon_url=server_icon)

        await channel.send(embed=e)
    except Exception:
        # Не ломаем основной поток из-за проблем с логами
        pass


# ======= Доходные роли: функции БД/утилиты =======
def db_get_role_incomes(guild_id: int) -> list[dict]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT role_id, income_type, money_amount, items_json, cooldown_seconds, created_by, created_ts
        FROM role_incomes
        WHERE guild_id = ?
        ORDER BY role_id
    """, (guild_id,))
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        items = []
        if r[1] == "items" and r[3]:
            try:
                parsed = json.loads(r[3])
                if isinstance(parsed, list):
                    items = [{"item_id": int(x["item_id"]), "qty": int(x["qty"])} for x in parsed]
            except Exception:
                items = []
        result.append({
            "role_id": int(r[0]),
            "income_type": r[1],
            "money_amount": int(r[2] or 0),
            "items": items,
            "cooldown_seconds": int(r[4] or 0),
            "created_by": int(r[5]) if r[5] is not None else None,
            "created_ts": int(r[6]) if r[6] is not None else None,
        })
    return result

def db_get_role_income(guild_id: int, role_id: int) -> Optional[dict]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT income_type, money_amount, items_json, cooldown_seconds, created_by, created_ts
        FROM role_incomes
        WHERE guild_id = ? AND role_id = ?
    """, (guild_id, role_id))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    items = []
    if row[0] == "items" and row[2]:
        try:
            parsed = json.loads(row[2])
            if isinstance(parsed, list):
                items = [{"item_id": int(x["item_id"]), "qty": int(x["qty"])} for x in parsed]
        except Exception:
            items = []
    return {
        "role_id": role_id,
        "income_type": row[0],
        "money_amount": int(row[1] or 0),
        "items": items,
        "cooldown_seconds": int(row[3] or 0),
        "created_by": int(row[4]) if row[4] is not None else None,
        "created_ts": int(row[5]) if row[5] is not None else None,
    }

def db_upsert_role_income(
    guild_id: int,
    role_id: int,
    income_type: str,
    money_amount: int,
    items: list[dict],
    cooldown_seconds: int,
    created_by: Optional[int] = None
):
    import time as _time
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    items_json = json.dumps(items) if items else None
    created_ts = int(_time.time()) if created_by else None

    # сохраняем created_by/created_ts только если они ещё не установлены (COALESCE)
    c.execute(f"""
        INSERT INTO role_incomes (guild_id, role_id, income_type, money_amount, items_json, cooldown_seconds, created_by, created_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, role_id) DO UPDATE SET
            income_type = excluded.income_type,
            money_amount = excluded.money_amount,
            items_json = excluded.items_json,
            cooldown_seconds = excluded.cooldown_seconds,
            created_by = COALESCE(role_incomes.created_by, excluded.created_by),
            created_ts = COALESCE(role_incomes.created_ts, excluded.created_ts)
    """, (guild_id, role_id, income_type, int(money_amount or 0), items_json, int(cooldown_seconds or 0), created_by, created_ts))
    conn.commit()
    conn.close()

def db_delete_role_income(guild_id: int, role_id: int):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("DELETE FROM role_incomes WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
    c.execute("DELETE FROM role_income_cooldowns WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
    conn.commit()
    conn.close()

def db_get_role_income_log_channel(guild_id: int) -> Optional[int]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT role_income_log_channel_id FROM guild_logs WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return int(row[0]) if row[0] is not None else None

def db_set_role_income_log_channel(guild_id: int, channel_id: Optional[int]):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        INSERT INTO guild_logs (guild_id, role_income_log_channel_id)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            role_income_log_channel_id = excluded.role_income_log_channel_id
    """, (guild_id, channel_id))
    conn.commit()
    conn.close()

def db_get_ri_last_ts(guild_id: int, role_id: int, user_id: int) -> Optional[int]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT last_ts FROM role_income_cooldowns
        WHERE guild_id = ? AND role_id = ? AND user_id = ?
    """, (guild_id, role_id, user_id))
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else None

def db_set_ri_last_ts(guild_id: int, role_id: int, user_id: int, ts: int):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        INSERT INTO role_income_cooldowns (guild_id, role_id, user_id, last_ts)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, role_id, user_id) DO UPDATE SET
            last_ts = excluded.last_ts
    """, (guild_id, role_id, user_id, ts))
    conn.commit()
    conn.close()

def items_id_to_name_map(guild: disnake.Guild) -> dict[int, str]:
    return {it["id"]: it["name"] for it in list_items_db(guild.id)}

def parse_duration_to_seconds(text: str) -> Optional[int]:
    """
    Поддерживает:
      - чистые секунды: "3600"
      - суффиксы: "1h 30m 15s", "90m", "2d"
      - формат времени: "HH:MM:SS" или "MM:SS"
    Возвращает секунды либо None (ошибка).
    """
    s = (text or "").strip().lower()
    if not s:
        return None

    if ":" in s:
        parts = s.split(":")
        if len(parts) == 3:
            h, m, sec = parts
        elif len(parts) == 2:
            h, m, sec = "0", parts[0], parts[1]
        else:
            return None
        if not (h.isdigit() and m.isdigit() and sec.isdigit()):
            return None
        h, m, sec = int(h), int(m), int(sec)
        if m >= 60 or sec >= 60 or h < 0 or m < 0 or sec < 0:
            return None
        return h * 3600 + m * 60 + sec

    if s.isdigit():
        v = int(s)
        return v if v >= 0 else None

    total = 0
    for num, unit in re.findall(r"(\d+)\s*([dhms])", s):
        n = int(num)
        if n < 0:
            return None
        if unit == "d":
            total += n * 86400
        elif unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        elif unit == "s":
            total += n
    if total == 0:
        return None
    return total

# ===== Вью и модалки для настройки доходных ролей =====

def _fmt_income_line(guild: disnake.Guild, ri: dict) -> str:
    role_mention = f"<@&{ri['role_id']}>"
    cd = format_seconds(ri['cooldown_seconds'])
    if ri["income_type"] == "money":
        return f"{role_mention} • Тип: 💰 Деньги • Доход: {format_number(ri['money_amount'])} {MONEY_EMOJI} • Кулдаун: {cd}"
    else:
        id2name = items_id_to_name_map(guild)
        if not ri["items"]:
            items_desc = "—"
        else:
            parts = []
            for x in ri["items"]:
                nm = id2name.get(x["item_id"], f"ID {x['item_id']}")
                parts.append(f"{nm} × {x['qty']}")
            items_desc = ", ".join(parts)
        return f"{role_mention} • Тип: 📦 Предметы • Доход: {items_desc} • Кулдаун: {cd}"

def build_role_income_embed(guild: disnake.Guild, invoker: disnake.Member) -> disnake.Embed:
    MAX_FIELD_VALUE = 1024
    MAX_FIELDS = 25

    def chunk_lines_to_fields(lines: list[str]) -> list[str]:
        """
        Склеивает строки в блоки <= 1024 символов. Если одна строка слишком длинная — обрезает её.
        Возвращает список строк — это будущие значения полей.
        """
        fields = []
        buf = ""

        for ln in lines:
            # Гарантируем, что одна строка не превышает лимита поля (с запасом под перенос строки)
            if len(ln) > MAX_FIELD_VALUE - 1:
                ln = ln[:MAX_FIELD_VALUE - 2] + "…"

            # Плюс перенос строки
            candidate = (ln + "\n")

            if len(buf) + len(candidate) > MAX_FIELD_VALUE:
                # зафиксировать предыдущий буфер
                if buf:
                    fields.append(buf.rstrip("\n"))
                # начать новый буфер с текущей строки
                buf = candidate
            else:
                buf += candidate

        if buf:
            fields.append(buf.rstrip("\n"))

        # Ограничим по количеству полей
        if len(fields) > MAX_FIELDS:
            fields = fields[:MAX_FIELDS]
            # Поставим троеточие в конец последнего поля
            if len(fields[-1]) >= MAX_FIELD_VALUE - 1:
                fields[-1] = fields[-1][:MAX_FIELD_VALUE - 2] + "…"
            else:
                fields[-1] += "\n…"

        # Если вдруг список пуст — вернём одно поле с «—»
        if not fields:
            fields = ["—"]

        return fields

    data = db_get_role_incomes(guild.id)
    e = disnake.Embed(
        title="Настройка доходных ролей",
        color=disnake.Color.from_rgb(88, 101, 242),
        description="Ниже список добавленных доходных ролей и их параметры."
    )
    e.set_author(name=invoker.display_name, icon_url=invoker.display_avatar.url)

    if not data:
        e.add_field(name="Доходные роли", value="Список пуст. Нажмите «Добавить доходную роль».", inline=False)
    else:
        lines = [_fmt_income_line(guild, ri) for ri in data]
        field_values = chunk_lines_to_fields(lines)

        for idx, val in enumerate(field_values):
            name = "Доходные роли" if idx == 0 else f"Доходные роли (продолжение {idx})"
            e.add_field(name=name, value=val, inline=False)

    e.set_footer(text=guild.name, icon_url=getattr(guild.icon, "url", None))
    return e

class RIMoneyModal(disnake.ui.Modal):
    def __init__(self, view_ref, mode: str, role_id: int, money_amount: int = 0, cooldown_seconds: int = 86400):
        # mode: 'add' | 'edit'
        components = [
            disnake.ui.TextInput(
                label="Сумма за один !collect (целое > 0)",
                custom_id="ri_money",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 250",
                value=str(money_amount) if money_amount > 0 else ""
            ),
            disnake.ui.TextInput(
                label="Кулдаун (пример: 3600, 1h 30m, 00:45:00)",
                custom_id="ri_cd",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 1h 30m",
                value=str(cooldown_seconds) if cooldown_seconds else ""
            ),
        ]
        super().__init__(title=("Добавить" if mode == "add" else "Изменить") + " • Деньги", components=components)
        self.view_ref = view_ref
        self.role_id = role_id
        self.mode = mode

    async def callback(self, inter: disnake.ModalInteraction):
        money_raw = (inter.text_values.get("ri_money") or "").replace(" ", "")
        cd_raw = (inter.text_values.get("ri_cd") or "").strip()
        try:
            money_val = safe_int(money_raw, name="Сумма", min_v=1)
        except ValueError as e:
            return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)
        cd = parse_duration_to_seconds(cd_raw)
        if cd is None or cd <= 0:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Введите валидный кулдаун (> 0)."), ephemeral=True)

        # ДОБАВЛЕНО: снимем состояние "до"
        before = db_get_role_income(inter.guild.id, self.role_id)

        db_upsert_role_income(
            inter.guild.id,
            self.role_id,
            "money",
            money_val,
            [],
            cd,
            created_by=(inter.user.id if self.mode == "add" else None)
        )

        # ДОБАВЛЕНО: снимем состояние "после" и отправим лог
        after = db_get_role_income(inter.guild.id, self.role_id)
        action = "create" if before is None else "update"
        await send_role_income_log(inter.guild, inter.user, action, self.role_id, before, after)

        await inter.response.edit_message(embed=build_role_income_embed(inter.guild, self.view_ref.ctx.author), view=self.view_ref)
        await inter.followup.send("Сохранено.", ephemeral=True)

class RIItemsModal(disnake.ui.Modal):
    def __init__(self, view_ref, mode: str, role_id: int, items_prefill: Optional[list[dict]] = None, cooldown_seconds: int = 86400):
        example = "Пример строк:\n15 2\n27 5\n(где 15 и 27 — ID предметов из магазина)"
        pre_text = ""
        if items_prefill:
            pre_text = "\n".join(f"{it['item_id']} {it['qty']}" for it in items_prefill)
        components = [
            disnake.ui.TextInput(
                label="Предметы (ID и количество, по строкам)",
                custom_id="ri_items",
                style=disnake.TextInputStyle.paragraph,
                required=True,
                placeholder=example,
                value=pre_text[:950]
            ),
            disnake.ui.TextInput(
                label="Кулдаун (пример: 3600, 1h 30m, 00:45:00)",
                custom_id="ri_cd2",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 12h",
                value=str(cooldown_seconds) if cooldown_seconds else ""
            ),
        ]
        super().__init__(title=("Добавить" if mode == "add" else "Изменить") + " • Предметы", components=components)
        self.view_ref = view_ref
        self.role_id = role_id
        self.mode = mode

    async def callback(self, inter: disnake.ModalInteraction):
        raw = (inter.text_values.get("ri_items") or "").strip()
        cd_raw = (inter.text_values.get("ri_cd2") or "").strip()
        if not raw:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Укажите хотя бы один предмет."), ephemeral=True)
        items_list = []
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        all_items = list_items_db(inter.guild.id)
        valid_ids = {int(it["id"]) for it in all_items}
        for ln in lines:
            parts = ln.replace("×", " ").replace("x", " ").split()
            if len(parts) < 2 or not parts[0].isdigit():
                return await inter.response.send_message(embed=error_embed("Ошибка", f"Неверная строка: «{ln}». Используйте «ID количество»."), ephemeral=True)
            iid = int(parts[0])
            try:
                qty = safe_int(parts[1], name="Количество", min_v=1)
            except ValueError as e:
                return await inter.response.send_message(embed=error_embed("Ошибка", f"ID {iid}: {e}"), ephemeral=True)
            if iid not in valid_ids:
                return await inter.response.send_message(embed=error_embed("Ошибка", f"Предмет с ID {iid} не найден в магазине."), ephemeral=True)
            items_list.append({"item_id": iid, "qty": qty})
        if not items_list:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Список предметов пуст."), ephemeral=True)
        cd = parse_duration_to_seconds(cd_raw)
        if cd is None or cd <= 0:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Введите валидный кулдаун (> 0)."), ephemeral=True)

        # ДОБАВЛЕНО: снимем состояние "до"
        before = db_get_role_income(inter.guild.id, self.role_id)

        db_upsert_role_income(
            inter.guild.id,
            self.role_id,
            "items",
            0,
            items_list,
            cd,
            created_by=(inter.user.id if self.mode == "add" else None)
        )

        # ДОБАВЛЕНО: снимем состояние "после" и отправим лог
        after = db_get_role_income(inter.guild.id, self.role_id)
        action = "create" if before is None else "update"
        await send_role_income_log(inter.guild, inter.user, action, self.role_id, before, after)

        await inter.response.edit_message(embed=build_role_income_embed(inter.guild, self.view_ref.ctx.author), view=self.view_ref)
        await inter.followup.send("Сохранено.", ephemeral=True)

class RISelect(disnake.ui.StringSelect):
    def __init__(self, options: list[disnake.SelectOption], placeholder: str, custom_id: str, min_values: int = 1, max_values: int = 1):
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            options=options[:25],  # Discord ограничение
            min_values=min_values,
            max_values=max_values
        )

class RoleIncomeView(disnake.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.message: Optional[disnake.Message] = None

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if not is_user_allowed_for(ALLOWED_ROLE_INCOME, inter.user):
            await inter.response.send_message("Недостаточно прав для управления доходными ролями.", ephemeral=True)
            return False
        return True

    def _roles_not_configured_options(self) -> list[disnake.SelectOption]:
        configured = {ri["role_id"] for ri in db_get_role_incomes(self.ctx.guild.id)}
        opts = []
        for r in sorted(self.ctx.guild.roles, key=lambda x: x.position, reverse=True):
            if r.is_default() or r.id in configured:
                continue
            label = r.name[:95]
            opts.append(disnake.SelectOption(label=label, value=str(r.id)))
            if len(opts) >= 25:
                break
        return opts

    def _roles_configured_options(self) -> list[disnake.SelectOption]:
        opts = []
        for ri in db_get_role_incomes(self.ctx.guild.id):
            role = self.ctx.guild.get_role(ri["role_id"])
            if not role:
                continue
            label = role.name[:95]
            opts.append(disnake.SelectOption(label=label, value=str(role.id), description=("💰" if ri["income_type"]=="money" else "📦")))
            if len(opts) >= 25:
                break
        return opts

    async def _refresh_main(self, inter: disnake.MessageInteraction):
        try:
            if self.message:
                await self.message.edit(embed=build_role_income_embed(self.ctx.guild, self.ctx.author), view=self)
        except Exception:
            pass

    @disnake.ui.button(label="Добавить доходную роль", style=disnake.ButtonStyle.success, custom_id="ri_add", row=0)
    async def _btn_add(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Множество уже сконфигурированных ролей, чтобы не дать добавить повторно
        configured = {ri["role_id"] for ri in db_get_role_incomes(inter.guild.id)}

        view = disnake.ui.View(timeout=120)

        # 1) Выбор роли из всех ролей сервера (с поиском)
        role_select = disnake.ui.RoleSelect(
            custom_id="ri_add_pick_role",
            placeholder="Выберите роль (можно искать)",
            min_values=1,
            max_values=1
        )

        # 2) Выбор типа дохода — как раньше
        type_select = RISelect(
            [
                disnake.SelectOption(label="Деньги", value="money", emoji="💰"),
                disnake.SelectOption(label="Предметы магазина", value="items", emoji="📦"),
            ],
            "Тип дохода",
            "ri_add_pick_type"
        )

        proceed_btn = disnake.ui.Button(label="Ввести параметры", style=disnake.ButtonStyle.primary, custom_id="ri_add_continue")

        chosen = {"role_id": None, "type": None}

        async def on_role_pick(i: disnake.MessageInteraction):
            # RoleSelect.values в disnake — список объектов дискорд-ролей
            picked = role_select.values[0] if role_select.values else None
            if not picked:
                return await i.response.send_message("Не удалось определить роль.", ephemeral=True)

            if picked.is_default():
                return await i.response.send_message("Нельзя выбрать @everyone.", ephemeral=True)

            if picked.id in configured:
                return await i.response.send_message("Эта роль уже настроена как доходная. Выберите другую.", ephemeral=True)

            chosen["role_id"] = int(picked.id)
            await i.response.defer()  # просто отмечаем выбор, без сообщения

        async def on_type_pick(i: disnake.MessageInteraction):
            chosen["type"] = type_select.values[0]
            await i.response.defer()

        async def on_proceed(i: disnake.MessageInteraction):
            if not chosen["role_id"] or not chosen["type"]:
                return await i.response.send_message("Сначала выберите роль и тип дохода.", ephemeral=True)
            if chosen["type"] == "money":
                await i.response.send_modal(RIMoneyModal(self, "add", chosen["role_id"]))
            else:
                await i.response.send_modal(RIItemsModal(self, "add", chosen["role_id"]))

        role_select.callback = on_role_pick
        type_select.callback = on_type_pick
        proceed_btn.callback = on_proceed

        view.add_item(role_select)
        view.add_item(type_select)
        view.add_item(proceed_btn)

        try:
            await inter.response.send_message("Мастер добавления доходной роли", ephemeral=True, view=view)
        except Exception:
            await inter.followup.send("Мастер добавления доходной роли", ephemeral=True, view=view)

    @disnake.ui.button(label="Изменить доходную роль", style=disnake.ButtonStyle.primary, custom_id="ri_edit", row=0)
    async def _btn_edit(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Для изменения роль должна быть в БД
        configured = {ri["role_id"] for ri in db_get_role_incomes(inter.guild.id)}
        if not configured:
            return await inter.response.send_message("Нет добавленных доходных ролей для изменения.", ephemeral=True)

        view = disnake.ui.View(timeout=120)

        role_select = disnake.ui.RoleSelect(
            custom_id="ri_edit_pick_role",
            placeholder="Выберите доходную роль (можно искать)",
            min_values=1,
            max_values=1
        )
        type_select = RISelect(
            [
                disnake.SelectOption(label="Деньги", value="money", emoji="💰"),
                disnake.SelectOption(label="Предметы магазина", value="items", emoji="📦"),
            ],
            "Новый тип дохода",
            "ri_edit_pick_type"
        )
        proceed_btn = disnake.ui.Button(label="Изменить параметры", style=disnake.ButtonStyle.primary, custom_id="ri_edit_continue")

        chosen = {"role_id": None, "type": None}

        async def on_role_pick(i: disnake.MessageInteraction):
            picked = role_select.values[0] if role_select.values else None
            if not picked:
                return await i.response.send_message("Не удалось определить роль.", ephemeral=True)

            rid = int(picked.id)
            if rid not in configured:
                return await i.response.send_message("У выбранной роли пока нет настроенного дохода.", ephemeral=True)

            chosen["role_id"] = rid
            await i.response.defer()

        async def on_type_pick(i: disnake.MessageInteraction):
            chosen["type"] = type_select.values[0]
            await i.response.defer()

        async def on_proceed(i: disnake.MessageInteraction):
            if not chosen["role_id"] or not chosen["type"]:
                return await i.response.send_message("Сначала выберите роль и новый тип дохода.", ephemeral=True)
            current = db_get_role_income(i.guild.id, chosen["role_id"]) or {}
            if chosen["type"] == "money":
                await i.response.send_modal(RIMoneyModal(
                    self, "edit", chosen["role_id"],
                    money_amount=current.get("money_amount", 0),
                    cooldown_seconds=current.get("cooldown_seconds", 86400)
                ))
            else:
                await i.response.send_modal(RIItemsModal(
                    self, "edit", chosen["role_id"],
                    items_prefill=current.get("items") or [],
                    cooldown_seconds=current.get("cooldown_seconds", 86400)
                ))

        role_select.callback = on_role_pick
        type_select.callback = on_type_pick
        proceed_btn.callback = on_proceed

        view.add_item(role_select)
        view.add_item(type_select)
        view.add_item(proceed_btn)

        try:
            await inter.response.send_message("Мастер изменения доходной роли", ephemeral=True, view=view)
        except Exception:
            await inter.followup.send("Мастер изменения доходной роли", ephemeral=True, view=view)

    @disnake.ui.button(label="Удалить доходную роль", style=disnake.ButtonStyle.danger, custom_id="ri_del", row=0)
    async def _btn_del(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        configured = {ri["role_id"] for ri in db_get_role_incomes(inter.guild.id)}
        if not configured:
            return await inter.response.send_message("Нет добавленных доходных ролей для удаления.", ephemeral=True)

        view = disnake.ui.View(timeout=120)

        role_select = disnake.ui.RoleSelect(
            custom_id="ri_del_pick_role",
            placeholder="Выберите доходную роль для удаления (можно искать)",
            min_values=1,
            max_values=1
        )
        confirm_btn = disnake.ui.Button(label="Удалить", style=disnake.ButtonStyle.danger, custom_id="ri_del_confirm")
        cancel_btn  = disnake.ui.Button(label="Отмена",  style=disnake.ButtonStyle.secondary, custom_id="ri_del_cancel")

        chosen = {"role_id": None}

        async def on_role_pick(i: disnake.MessageInteraction):
            picked = role_select.values[0] if role_select.values else None
            if not picked:
                return await i.response.send_message("Не удалось определить роль.", ephemeral=True)
            rid = int(picked.id)
            if rid not in configured:
                return await i.response.send_message("У выбранной роли нет настроенного дохода.", ephemeral=True)
            chosen["role_id"] = rid
            await i.response.defer()

        async def on_confirm(i: disnake.MessageInteraction):
            if not chosen["role_id"]:
                return await i.response.send_message("Сначала выберите роль.", ephemeral=True)

            # Для лога - снимем состояние "до"
            before = db_get_role_income(i.guild.id, chosen["role_id"])

            db_delete_role_income(i.guild.id, chosen["role_id"])
            await i.response.edit_message(content="Доходная роль удалена.", view=None)
            await self._refresh_main(i)

            # Лог
            await send_role_income_log(i.guild, i.user, "delete", chosen["role_id"], before, None)

        async def on_cancel(i: disnake.MessageInteraction):
            await i.response.edit_message(content="Удаление отменено.", view=None)

        role_select.callback = on_role_pick
        confirm_btn.callback = on_confirm
        cancel_btn.callback = on_cancel

        view.add_item(role_select)
        view.add_item(confirm_btn)
        view.add_item(cancel_btn)

        try:
            await inter.response.send_message("Подтвердите удаление доходной роли", ephemeral=True, view=view)
        except Exception:
            await inter.followup.send("Подтвердите удаление доходной роли", ephemeral=True, view=view)

    async def on_timeout(self):
        try:
            for c in self.children:
                if isinstance(c, (disnake.ui.Button, disnake.ui.SelectBase)):
                    c.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# >>> ВСТАВИТЬ В РАЗДЕЛ С UI (View) КЛАССАМИ

def _apanel_is_admin(member: disnake.Member) -> bool:
    return bool(member.guild_permissions.administrator)

class AdminConfirmView(disnake.ui.View):
    """
    Небольшая вьюшка подтверждения действия.
    По нажатию Confirm вызывает переданный колбэк-экшн.
    """
    def __init__(self, ctx: commands.Context, action_code: str, on_confirm):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.action_code = action_code
        self.on_confirm = on_confirm

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.ctx.author.id:
            await inter.response.send_message("Подтверждать может только инициатор.", ephemeral=True)
            return False
        if not _apanel_is_admin(inter.user):
            await inter.response.send_message("Требуются права администратора.", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="Подтвердить", style=disnake.ButtonStyle.danger, custom_id="ap_confirm")
    async def _confirm(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer(ephemeral=True)
        try:
            msg = await self.on_confirm(inter)
            await inter.followup.send(msg or "Готово.", ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"Ошибка: {e}", ephemeral=True)
        finally:
            self.stop()

    @disnake.ui.button(label="Отмена", style=disnake.ButtonStyle.secondary, custom_id="ap_cancel")
    async def _cancel(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.edit_message(content="Действие отменено.", view=None)
        self.stop()

class AdminPanelView(disnake.ui.View):
    """
    Основная панель с кнопками админ-действий.
    """
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.message: Optional[disnake.Message] = None

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.ctx.author.id:
            await inter.response.send_message("Эта панель доступна только инициатору.", ephemeral=True)
            return False
        if not _apanel_is_admin(inter.user):
            await inter.response.send_message("Требуются права администратора.", ephemeral=True)
            return False
        return True

    async def _ask_confirm(self, inter: disnake.MessageInteraction, action_code: str, prompt: str, on_confirm_callable):
        view = AdminConfirmView(self.ctx, action_code, on_confirm_callable)
        try:
            await inter.response.send_message(prompt, ephemeral=True, view=view)
        except Exception:
            await inter.followup.send(prompt, ephemeral=True, view=view)

    # --- КНОПКИ ---

    @disnake.ui.button(label="Сбросить инвентари", style=disnake.ButtonStyle.danger, custom_id="ap_reset_inv", row=0)
    async def _btn_reset_inv(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        async def do_confirm(_i: disnake.MessageInteraction):
            deleted, users = admin_reset_inventories(_i.guild.id)
            details = f"Удалено {deleted} записей инвентаря у {users} пользователей."
            await send_admin_action_log(_i.guild, _i.user, "reset_inventories", details)
            return f"✅ Инвентари сброшены. {details}"
        await self._ask_confirm(inter, "reset_inventories", "Подтвердите сброс всех инвентарей (операция необратима).", do_confirm)

    @disnake.ui.button(label="Сбросить балансы", style=disnake.ButtonStyle.danger, custom_id="ap_reset_bal", row=0)
    async def _btn_reset_bal(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        async def do_confirm(_i: disnake.MessageInteraction):
            affected, total, sum_before = admin_reset_balances(_i.guild.id)
            details = f"Обнулены балансы у {affected} записей (всего строк: {total}). Сумма до обнуления: {format_number(sum_before)} {MONEY_EMOJI}"
            await send_admin_action_log(_i.guild, _i.user, "reset_balances", details)
            return f"✅ Балансы сброшены. {details}"
        await self._ask_confirm(inter, "reset_balances", "Подтвердите сброс баланса у всех пользователей (установится 0).", do_confirm)

    @disnake.ui.button(label="Сбросить бюджет Всемирного банка", style=disnake.ButtonStyle.danger, custom_id="ap_reset_wb", row=1)
    async def _btn_reset_wb(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        async def do_confirm(_i: disnake.MessageInteraction):
            before, after = admin_reset_worldbank(_i.guild.id)
            details = f"Бюджет: {format_number(before)} → {format_number(after)} {MONEY_EMOJI}"
            await send_admin_action_log(_i.guild, _i.user, "reset_worldbank", details)
            return f"✅ Бюджет Всемирного банка сброшен. {details}"
        await self._ask_confirm(inter, "reset_worldbank", "Подтвердите сброс бюджета Всемирного банка до 0.", do_confirm)

    @disnake.ui.button(label="Очистить магазин", style=disnake.ButtonStyle.danger, custom_id="ap_clear_shop", row=1)
    async def _btn_clear_shop(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        async def do_confirm(_i: disnake.MessageInteraction):
            stats = admin_clear_shop(_i.guild.id)
            details = (
                f"Удалено предметов: {stats['items']}; "
                f"записей инвентаря по предметам: {stats['inv_rows']}; "
                f"состояний склада: {stats['shop_state']}; "
                f"дневных записей: {stats['user_daily']}."
            )
            await send_admin_action_log(_i.guild, _i.user, "clear_shop", details)
            return f"✅ Магазин очищен. {details}"
        await self._ask_confirm(inter, "clear_shop", "Подтвердите полную очистку магазина (предметы, состояния, дневные лимиты и инвентари по этим предметам).", do_confirm)

    @disnake.ui.button(label="Очистить доходные роли", style=disnake.ButtonStyle.danger, custom_id="ap_clear_ri", row=2)
    async def _btn_clear_ri(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        async def do_confirm(_i: disnake.MessageInteraction):
            roles_deleted, cds_deleted = admin_clear_role_incomes(_i.guild.id)
            details = f"Удалено записей доходных ролей: {roles_deleted}; кулдаунов: {cds_deleted}."
            await send_admin_action_log(_i.guild, _i.user, "clear_role_incomes", details)
            return f"✅ Доходные роли очищены. {details}"
        await self._ask_confirm(inter, "clear_role_incomes", "Подтвердите очистку всех доходных ролей и их кулдаунов.", do_confirm)

    async def on_timeout(self):
        try:
            for c in self.children:
                if isinstance(c, (disnake.ui.Button, disnake.ui.SelectBase)):
                    c.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


@bot.event
async def on_ready():
    setup_database()
    print(f'Бот {bot.user} готов к работе!')
    print(f'Подключен к {len(bot.guilds)} серверам.')
    
@bot.command(name="balance", aliases=["bal", "Bal", "Баланс", "Бал", "баланс", "бал", "BAL", "BALANCE", "БАЛАНС", "БАЛ", "Balance"])
async def balance_prefix(ctx: commands.Context, user: disnake.Member = None):
    if not await ensure_allowed_ctx(ctx, ALLOWED_BALANCE):
        return
    target_user = user or ctx.author
    balance = get_balance(ctx.guild.id, target_user.id)
    embed = disnake.Embed(
        title=f":moneybag: Баланс {target_user.display_name}",
        description=f"**На счету:**\n{format_number(balance)} {MONEY_EMOJI}",
        color=disnake.Color.gold()
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)
    await ctx.send(embed=embed)

# ====== НОВАЯ РЕАЛИЗАЦИЯ !pay С УЧЕТОМ КОМИССИИ ВСЕМИРНОГО БАНКА ======
@bot.command(name="pay", aliases=["Pay", "PAY", "Перевод", "перевод", "ПЕРЕВОД"])
async def pay_prefix(ctx: commands.Context, recipient: disnake.Member, amount_raw: str):
    """
    Перевод денег между пользователями с комиссией Всемирного банка.
      !pay @получатель <сумма>
    Получатель получает сумму за вычетом комиссии. Комиссия зачисляется в бюджет Всемирного банка (!worldbank).
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_PAY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    if recipient == ctx.author:
        await ctx.send("Вы не можете переводить деньги самому себе!")
        return
    try:
        amount = safe_int(amount_raw, name="Сумма", min_v=1)
    except ValueError as e:
        await ctx.send(embed=error_embed("Ошибка", str(e)))
        return

    sender_balance = get_balance(ctx.guild.id, ctx.author.id)
    if sender_balance < amount:
        await ctx.send(f"У вас недостаточно средств! Ваш баланс: {format_number(sender_balance)} {MONEY_EMOJI}")
        return

    # Комиссия Всемирного банка
    commission_percent, _bank_bal = get_worldbank(ctx.guild.id)
    commission = math.floor(amount * commission_percent / 100)
    received = max(0, amount - commission)

    # Транзакции
    update_balance(ctx.guild.id, ctx.author.id, -amount)
    if received > 0:
        update_balance(ctx.guild.id, recipient.id, received)
    if commission > 0:
        change_worldbank_balance(ctx.guild.id, commission)

    sender_balance_after = get_balance(ctx.guild.id, ctx.author.id)
    recipient_balance_after = get_balance(ctx.guild.id, recipient.id)

    # Красивый эмбед
    embed = disnake.Embed(
        title="Перевод выполнен!",
        color=disnake.Color.green()
    )
    embed.set_thumbnail(url=recipient.display_avatar.url)  # аватарка получателя в правом верхнем углу

    embed.add_field(name="От", value=f"{ctx.author.mention}", inline=True)
    embed.add_field(name="Кому", value=f"{recipient.mention}", inline=True)
    embed.add_field(
        name="Комиссия",
        value=f"{format_number(commission)} {MONEY_EMOJI} ({commission_percent}%)",
        inline=False
    )
    embed.add_field(
        name="Получено",
        value=f"{format_number(received)} {MONEY_EMOJI}",
        inline=True
    )
    embed.add_field(
        name="Баланс отправителя",
        value=f"{format_number(sender_balance_after)} {MONEY_EMOJI}",
        inline=True
    )
    embed.add_field(
        name="Баланс получателя",
        value=f"{format_number(recipient_balance_after)} {MONEY_EMOJI}",
        inline=False
    )

    server_icon = getattr(ctx.guild.icon, "url", None)
    footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    embed.set_footer(text=f"{ctx.guild.name} • {footer_time}", icon_url=server_icon)

    await ctx.send(embed=embed)


# ====== Вспомогательная функция: эмбед для денежных действий ======
def build_money_action_embed(
    ctx: commands.Context,
    *,
    action: str,  # 'add' | 'remove' | 'reset'
    is_role: bool,
    target_mention: str,
    amount: Optional[int],
    new_balance: Optional[int],  # только для пользователя; для роли None
) -> disnake.Embed:
    titles = {
        "add": ("Выдача средств", disnake.Color.green(), "Выдал"),
        "remove": ("Списание средств", disnake.Color.orange(), "Снял"),
        "reset": ("Обнуление средств", disnake.Color.red(), "Обнулил"),
    }
    title, color, verb = titles.get(action, ("Операция со средствами", disnake.Color.blurple(), "Изменил"))

    e = disnake.Embed(
        title=title,
        color=color
    )
    e.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

    who_line = f"{'Роль' if is_role else 'Пользователь'}: {target_mention}"
    by_line = f"{verb}: {ctx.author.mention}"
    sum_line = f"Сумма: {format_number(amount)} {MONEY_EMOJI}" if (amount is not None and amount > 0) else "Сумма: —"
    if is_role:
        new_line = "Новый баланс: — (массовая операция)"
    else:
        new_line = f"Новый баланс: {format_number(new_balance or 0)} {MONEY_EMOJI}"

    # Убираем дублирование названия в описании — оставляем только строки с данными
    e.description = "\n".join([who_line, by_line, sum_line, new_line])
    return e

# Константа: макс. количество совпадений, при котором предлагаем выбрать
MAX_MATCHES_FOR_PROMPT = 5

def resolve_roles_by_input(guild: disnake.Guild, query: str) -> list[disnake.Role]:
    """
    Попытки распознать роль по вводу:
    1) упоминание <@&id> или просто id
    2) точное совпадение имени (без учёта регистра)
    3) частичное совпадение (substring)
    Возвращает список ролей (может быть пустым).
    """
    query = (query or "").strip()
    if not query:
        return []

    # 1) упоминание или id
    m = re.match(r"<@&(d+)>$", query)
    if m:
        r = guild.get_role(int(m.group(1)))
        if r:
            return [r]
    if query.isdigit():
        r = guild.get_role(int(query))
        if r:
            return [r]

    # 2) точное совпадение имени (без учёта регистра)
    for role in guild.roles:
        if role.name.lower() == query.lower():
            return [role]

    # 3) частичное совпадение
    matches = [role for role in guild.roles if query.lower() in role.name.lower()]
    return matches  # возможно пустой список


async def ask_role_choice(ctx: commands.Context, roles: list[disnake.Role], prompt: str = "Найдено несколько ролей. Выберите номер:") -> disnake.Role | None:
    """
    Просит пользователя ввести номер роли в чат (вариант без реакций).
    Возвращает выбранную роль или None при отмене/таймауте/ошибке.
    """
    if not roles:
        return None

    # Сформируем аккуратное перечисление ролей — не более MAX_MATCHES_FOR_PROMPT элементов.
    lines = []
    for i, r in enumerate(roles[:MAX_MATCHES_FOR_PROMPT], start=1):  # Ограничиваем количество отображаемых ролей
        lines.append(f"{i}. {r.mention} — {r.name} (id: {r.id})")

    text = prompt + "\n\n" + "\n".join(lines)
    text += f"\n\nНапишите номер роли (1-{len(roles)}) или 'отмена'."

    embed = disnake.Embed(title="Выбор роли", description=text, color=0x3498DB)
    
    # Обрежем описание если оно выйдет за пределы (4096)
    if len(embed.description) > 4096:
        embed.description = embed.description[:4093] + "..."
    
    await ctx.send(embed=embed)

    def check(m: disnake.Message):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await ctx.bot.wait_for("message", check=check, timeout=30)
    except asyncio.TimeoutError:
        await ctx.send(embed=error_embed("Время выбора истекло", "Пожалуйста, повторите команду позже."))
        return None

    content = (msg.content or "").strip().lower()
    if content in ("отмена", "cancel"):
        await ctx.send(embed=error_embed("Операция отменена", "Выбор роли отменён."))
        return None

    if not content.isdigit():
        await ctx.send(embed=error_embed("Неверный формат", "Ожидался номер роли. Попробуйте ещё раз."))
        return None

    idx = int(content)
    if idx < 1 or idx > len(roles):
        await ctx.send(embed=error_embed("Неверный номер", f"Номер должен быть в диапазоне от 1 до {len(roles)}."))
        return None

    return roles[idx - 1]


@bot.command(name="add-role", aliases=["addrole", "giverole", "give-role"])
async def add_role_cmd(ctx: commands.Context, member: disnake.Member, *, role_query: str):
    """
    Выдать роль пользователю:
    !add-role @пользователь <@роль | название роли>
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_ROLE_COMMANDS):
        return
    if not ctx.guild:
        return await ctx.send(embed=error_embed("Ошибка", "Команда доступна только на сервере."))

    roles = resolve_roles_by_input(ctx.guild, role_query)
    if not roles:
        return await ctx.send(embed=error_embed("Роль не найдена", f"Не удалось определить роль по вводу: {role_query!r}"))

    # Если слишком много совпадений — просим уточнить ввод
    if len(roles) > MAX_MATCHES_FOR_PROMPT:
        return await ctx.send(embed=error_embed(
            "Слишком много совпадений",
            f"Найдено {len(roles)} ролей, подходящих под запрос. Укажите название точнее (например, часть имени покороче или упомяните роль)."
        ))

    # Неоднозначность: попросим выбрать
    role = roles[0] if len(roles) == 1 else (await ask_role_choice(ctx, roles, prompt="Найдено несколько ролей, подходящих по запросу. Выберите номер роли:"))
    if not role:
        return  # пользователь отменил или истёк таймаут

    if role in member.roles:
        return await ctx.send(embed=error_embed("Невозможно выдать роль", f"{member.mention} уже имеет роль {role.mention}."))

    ok, msg = _can_actor_manage_role(ctx.author, role)
    if not ok:
        return await ctx.send(embed=error_embed("Отказано", msg))

    ok, msg = _bot_can_apply(ctx.guild, role, member)
    if not ok:
        return await ctx.send(embed=error_embed("Бот не может выполнить действие", msg))

    try:
        await member.add_roles(role, reason=f"{ctx.author} выдал роль")
    except disnake.Forbidden:
        return await ctx.send(embed=error_embed("Ошибка", "Discord запретил операцию (Forbidden). Проверьте права и порядок ролей."))
    except disnake.HTTPException as e:
        return await ctx.send(embed=error_embed("Ошибка", f"Не удалось выдать роль: {e}"))

    embed = build_role_change_embed(ctx.guild, "add", member, role, ctx.author)
    await ctx.send(embed=embed)
    await send_role_change_log(ctx.guild, "add", member, role, ctx.author)


@bot.command(name="take-role", aliases=["takerole", "removerole", "remove-role"])
async def take_role_cmd(ctx: commands.Context, member: disnake.Member, *, role_query: str):
    """
    Снять роль с пользователя:
    !take-role @пользователь <@роль | название роли>
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_ROLE_COMMANDS):
        return
    if not ctx.guild:
        return await ctx.send(embed=error_embed("Ошибка", "Команда доступна только на сервере."))

    roles = resolve_roles_by_input(ctx.guild, role_query)
    if not roles:
        return await ctx.send(embed=error_embed("Роль не найдена", f"Не удалось определить роль по вводу: {role_query!r}"))

    # Если слишком много совпадений — просим уточнить ввод
    if len(roles) > MAX_MATCHES_FOR_PROMPT:
        return await ctx.send(embed=error_embed(
            "Слишком много совпадений",
            f"Найдено {len(roles)} ролей, подходящих под запрос. Уточните название роли."
        ))

    if len(roles) == 1:
        role = roles[0]
    else:
        chosen = await ask_role_choice(ctx, roles, prompt="Найдено несколько ролей, подходящих по запросу. Выберите номер роли:")
        if not chosen:
            return
        role = chosen

    if role not in member.roles:
        return await ctx.send(embed=error_embed("Нечего снимать", f"У {member.mention} нет роли {role.mention}."))

    ok, msg = _can_actor_manage_role(ctx.author, role)
    if not ok:
        return await ctx.send(embed=error_embed("Отказано", msg))

    ok, msg = _bot_can_apply(ctx.guild, role, member)
    if not ok:
        return await ctx.send(embed=error_embed("Бот не может выполнить действие", msg))

    try:
        await member.remove_roles(role, reason=f"{ctx.author} снял роль")
    except disnake.Forbidden:
        return await ctx.send(embed=error_embed("Ошибка", "Discord запретил операцию (Forbidden). Проверьте права и порядок ролей."))
    except disnake.HTTPException as e:
        return await ctx.send(embed=error_embed("Ошибка", f"Не удалось снять роль: {e}"))

    embed = build_role_change_embed(ctx.guild, "remove", member, role, ctx.author)
    await ctx.send(embed=embed)
    await send_role_change_log(ctx.guild, "remove", member, role, ctx.author)


# ================= Команды: управление деньгами (пользователь) =================

@bot.command(name="add-money", aliases=["Add-money", "ADD-MONEY"])
async def add_money_cmd(ctx: commands.Context, member: disnake.Member, amount_raw: str):
    """
    Выдать деньги пользователю:
      !add-money @пользователь <сумма>
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_ADD_MONEY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    try:
        amount = safe_int(amount_raw, name="Сумма", min_v=1)
    except ValueError as e:
        return await ctx.send(embed=error_embed("Ошибка", str(e)))
    update_balance(ctx.guild.id, member.id, amount)
    new_bal = get_balance(ctx.guild.id, member.id)
    embed = build_money_action_embed(
        ctx, action="add", is_role=False, target_mention=member.mention, amount=amount, new_balance=new_bal
    )
    await ctx.send(embed=embed)

    # ДОБАВЛЕНО: лог в канал логов
    await send_money_action_log(ctx.guild, ctx.author, "add", member, amount)

@bot.command(name="remove-money", aliases=["Remove-money", "REMOVE-MONEY", "Remove-Money"])
async def remove_money_cmd(ctx: commands.Context, member: disnake.Member, amount_raw: str):
    """
    Списать деньги у пользователя:
      !remove-money @пользователь <сумма>
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_REMOVE_MONEY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    try:
        amount = safe_int(amount_raw, name="Сумма", min_v=1)
    except ValueError as e:
        return await ctx.send(embed=error_embed("Ошибка", str(e)))

    current = get_balance(ctx.guild.id, member.id)
    if amount > current:
        return await ctx.send(embed=error_embed(
            "Недостаточно средств для списания",
            f"У {member.mention} на счету только {format_number(current)} {MONEY_EMOJI}. "
            f"Нельзя списать {format_number(amount)}."
        ))

    update_balance(ctx.guild.id, member.id, -amount)
    new_bal = get_balance(ctx.guild.id, member.id)
    embed = build_money_action_embed(
        ctx, action="remove", is_role=False, target_mention=member.mention, amount=amount, new_balance=new_bal
    )
    await ctx.send(embed=embed)

    # ДОБАВЛЕНО: лог в канал логов
    await send_money_action_log(ctx.guild, ctx.author, "remove", member, amount)

@bot.command(name="reset-money", aliases=["Reset-money", "RESET-MONEY", "Reset-Money"])
async def reset_money_cmd(ctx: commands.Context, member: disnake.Member):
    """
    Обнулить баланс пользователя:
      !reset-money @пользователь
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_RESET_MONEY):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    set_balance(ctx.guild.id, member.id, 0)
    embed = build_money_action_embed(
        ctx, action="reset", is_role=False, target_mention=member.mention, amount=None, new_balance=0
    )
    await ctx.send(embed=embed)

    # ДОБАВЛЕНО: лог в канал логов
    await send_money_action_log(ctx.guild, ctx.author, "reset", member, None)


# ================= Команды: управление деньгами (роль) =================

@bot.command(name="add-money-role")
async def add_money_role_cmd(ctx: commands.Context, role: disnake.Role, amount_raw: str):
    """
    Выдать деньги всем пользователям с ролью:
      !add-money-role @роль <сумма>
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_ADD_MONEY_ROLE):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    try:
        amount = safe_int(amount_raw, name="Сумма", min_v=1)
    except ValueError as e:
        return await ctx.send(embed=error_embed("Ошибка", str(e)))

    members = [m for m in role.members if m.guild.id == ctx.guild.id]
    for m in members:
        update_balance(ctx.guild.id, m.id, amount)

    embed = build_money_action_embed(
        ctx, action="add", is_role=True, target_mention=role.mention, amount=amount, new_balance=None
    )
    await ctx.send(embed=embed)

    # ДОБАВЛЕНО: лог в канал логов (цель — роль)
    await send_money_action_log(ctx.guild, ctx.author, "add", role, amount)

@bot.command(name="remove-money-role")
async def remove_money_role_cmd(ctx: commands.Context, role: disnake.Role, amount_raw: str):
    """
    Снять деньги у всех пользователей с ролью:
      !remove-money-role @роль <сумма>
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_REMOVE_MONEY_ROLE):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    try:
        amount = safe_int(amount_raw, name="Сумма", min_v=1)
    except ValueError as e:
        return await ctx.send(embed=error_embed("Ошибка", str(e)))

    members = [m for m in role.members if m.guild.id == ctx.guild.id]
    for m in members:
        update_balance(ctx.guild.id, m.id, -amount)

    embed = build_money_action_embed(
        ctx, action="remove", is_role=True, target_mention=role.mention, amount=amount, new_balance=None
    )
    await ctx.send(embed=embed)

    # ДОБАВЛЕНО: лог в канал логов (цель — роль)
    await send_money_action_log(ctx.guild, ctx.author, "remove", role, amount)

@bot.command(name="reset-money-role")
async def reset_money_role_cmd(ctx: commands.Context, role: disnake.Role):
    """
    Обнулить баланс у всех пользователей с ролью:
      !reset-money-role @роль
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_RESET_MONEY_ROLE):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    members = [m for m in role.members if m.guild.id == ctx.guild.id]
    for m in members:
        set_balance(ctx.guild.id, m.id, 0)

    embed = build_money_action_embed(
        ctx, action="reset", is_role=True, target_mention=role.mention, amount=None, new_balance=None
    )
    await ctx.send(embed=embed)

    # ДОБАВЛЕНО: лог в канал логов (цель — роль)
    await send_money_action_log(ctx.guild, ctx.author, "reset", role, None)


# ========================== Команда !worldbank ==========================

def _wb_is_manager(member: disnake.Member) -> bool:
    return is_user_allowed_for(ALLOWED_WORLDBANK_MANAGE, member)

def build_worldbank_embed(guild: disnake.Guild, invoker: disnake.Member) -> disnake.Embed:
    percent, bank = get_worldbank(guild.id)
    e = disnake.Embed(
        title="Всемирный банк",
        color=disnake.Color.from_rgb(88, 101, 242)
    )
    e.set_author(name=invoker.display_name, icon_url=invoker.display_avatar.url)

    # Президент(ы)
    pres_role = guild.get_role(PRESIDENT_ROLE_ID)
    if pres_role:
        pres_members = [m.mention for m in pres_role.members]
        pres_value = "\n".join(pres_members) if pres_members else "—"
    else:
        pres_value = "— (роль не найдена)"

    e.add_field(name="Президент", value=pres_value, inline=False)
    e.add_field(name="Комиссионная ставка", value=f"{percent}%", inline=False)
    e.add_field(name="Бюджет банка", value=f"{format_number(bank)} {MONEY_EMOJI}", inline=False)

    return e

class WBPercentModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        super().__init__(
            title="Изменить ставку комиссии",
            components=[
                disnake.ui.TextInput(
                    label="Введите процент (1–10)",
                    custom_id="wb_percent",
                    style=disnake.TextInputStyle.short,
                    required=True,
                    placeholder="например: 5",
                    max_length=3
                )
            ]
        )
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        if not _wb_is_manager(inter.user):
            return await inter.response.send_message("Недостаточно прав.", ephemeral=True)
        raw = (inter.text_values.get("wb_percent") or "")
        try:
            val = safe_int(raw, name="Процент", min_v=1, max_v=10)
        except ValueError as e:
            return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)
        set_commission_percent(inter.guild.id, val)
        await inter.response.edit_message(embed=build_worldbank_embed(inter.guild, self.view_ref.ctx.author), view=self.view_ref)
        await inter.followup.send(f"Ставка комиссии обновлена: {val}%.", ephemeral=True)

class WBWithdrawModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        super().__init__(
            title="Снять с казны",
            components=[
                disnake.ui.TextInput(
                    label="Сумма для снятия (целое, > 0)",
                    custom_id="wb_withdraw",
                    style=disnake.TextInputStyle.short,
                    required=True,
                    placeholder="например: 1000",
                    max_length=16
                )
            ]
        )
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        if not _wb_is_manager(inter.user):
            return await inter.response.send_message("Недостаточно прав.", ephemeral=True)
        raw = inter.text_values.get("wb_withdraw") or ""
        try:
            amount = safe_int(raw, name="Сумма", min_v=1)
        except ValueError as e:
            return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)
        bank_bal = get_worldbank_balance(inter.guild.id)
        if amount > bank_bal:
            return await inter.response.send_message(embed=error_embed("Недостаточно средств в казне", f"В банке только {format_number(bank_bal)} {MONEY_EMOJI}."), ephemeral=True)
        ok = change_worldbank_balance(inter.guild.id, -amount)
        if not ok:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Не удалось списать с казны."), ephemeral=True)
        update_balance(inter.guild.id, inter.user.id, amount)
        await inter.response.edit_message(embed=build_worldbank_embed(inter.guild, self.view_ref.ctx.author), view=self.view_ref)
        await inter.followup.send(f"Снято с казны: {format_number(amount)} {MONEY_EMOJI}. Средства зачислены на ваш баланс.", ephemeral=True)

class WBDepositModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        super().__init__(
            title="Пополнить бюджет",
            components=[
                disnake.ui.TextInput(
                    label="Сумма пополнения (целое, > 0)",
                    custom_id="wb_deposit",
                    style=disnake.TextInputStyle.short,
                    required=True,
                    placeholder="например: 500",
                    max_length=16
                )
            ]
        )
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        # Пополнять может любой желающий — но можно ограничить так же, как и управление:
        if not _wb_is_manager(inter.user):
            return await inter.response.send_message("Недостаточно прав.", ephemeral=True)
        raw = inter.text_values.get("wb_deposit") or ""
        try:
            amount = safe_int(raw, name="Сумма", min_v=1)
        except ValueError as e:
            return await inter.response.send_message(embed=error_embed("Ошибка", str(e)), ephemeral=True)
        user_bal = get_balance(inter.guild.id, inter.user.id)
        if amount > user_bal:
            return await inter.response.send_message(embed=error_embed("Недостаточно средств", f"Ваш баланс: {format_number(user_bal)} {MONEY_EMOJI}"), ephemeral=True)
        update_balance(inter.guild.id, inter.user.id, -amount)
        change_worldbank_balance(inter.guild.id, amount)
        await inter.response.edit_message(embed=build_worldbank_embed(inter.guild, self.view_ref.ctx.author), view=self.view_ref)
        await inter.followup.send(f"Казна пополнена на {format_number(amount)} {MONEY_EMOJI}. Спасибо!", ephemeral=True)

class WorldBankView(disnake.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.message: Optional[disnake.Message] = None

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        # Любой может смотреть. Управление проверяется в модалках.
        return True

    @disnake.ui.button(label="Изменить ставку комиссии", style=disnake.ButtonStyle.primary, custom_id="wb_rate", row=0)
    async def _change_rate(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not _wb_is_manager(inter.user):
            return await inter.response.send_message("Недостаточно прав для изменения ставки.", ephemeral=True)
        await inter.response.send_modal(WBPercentModal(self))

    @disnake.ui.button(label="Снять с казны", style=disnake.ButtonStyle.danger, custom_id="wb_withdraw", row=0)
    async def _withdraw(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not _wb_is_manager(inter.user):
            return await inter.response.send_message("Недостаточно прав для снятия средств.", ephemeral=True)
        await inter.response.send_modal(WBWithdrawModal(self))

    @disnake.ui.button(label="Пополнить бюджет", style=disnake.ButtonStyle.success, custom_id="wb_deposit", row=0)
    async def _deposit(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not _wb_is_manager(inter.user):
            return await inter.response.send_message("Недостаточно прав для пополнения казны.", ephemeral=True)
        await inter.response.send_modal(WBDepositModal(self))

    async def on_timeout(self):
        try:
            for c in self.children:
                if isinstance(c, (disnake.ui.Button, disnake.ui.SelectBase)):
                    c.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

@bot.command(name="worldbank", aliases=["Worldbank", "WORLDBANK"])
async def worldbank_cmd(ctx: commands.Context):
    """
    Всемирный банк:
      !worldbank
    Показывает текущую комиссию перевода, бюджет банка и список Президентов (по роли).
    Управление: кнопки изменить ставку, снять с казны, пополнить бюджет.
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_WORLDBANK):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    # Обеспечим наличие строки WB
    get_worldbank(ctx.guild.id)

    view = WorldBankView(ctx)
    embed = build_worldbank_embed(ctx.guild, ctx.author)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


@bot.command(name="work", aliases=["Work", "WORK", "Работать", "работать", "РАБОТАТЬ"])
async def work_cmd(ctx: commands.Context):
    if not await ensure_allowed_ctx(ctx, ALLOWED_WORK):
        return
    min_income, max_income, cooldown = get_work_settings(ctx.guild.id)

    now = int(time.time())
    last_ts = get_last_work_ts(ctx.guild.id, ctx.author.id)
    if last_ts is not None:
        remaining = (last_ts + cooldown) - now
        if remaining > 0:
            next_ts = last_ts + cooldown
            embed = disnake.Embed(
                title="🕒 Работа недоступна",
                color=disnake.Color.orange()
            )
            embed.add_field(
                name="🗓️ Следующая работа",
                value="Доступна через <t:" + str(next_ts) + ":R>",
                inline=False
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            server_icon = getattr(ctx.guild.icon, "url", None)
            footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
            embed.set_footer(text=f"{ctx.guild.name} • {footer_time}", icon_url=server_icon)
            await ctx.send(embed=embed)
            return

    if max_income < min_income:
        min_income, max_income = max_income, min_income
    earn = random.randint(min_income, max_income)

    if earn - min_income >= 5:
        base = random.randint(min_income, max(min_income, int(earn * 0.6)))
        bonus = max(0, earn - base)
    else:
        base = earn
        bonus = 0

    update_balance(ctx.guild.id, ctx.author.id, earn)
    set_last_work_ts(ctx.guild.id, ctx.author.id, now)
    new_balance = get_balance(ctx.guild.id, ctx.author.id)
    next_ts = now + cooldown

    embed = disnake.Embed(
        title=f"🧑‍💻 Работа выполнена!",
        color=disnake.Color.green()
    )
    embed.add_field(
        name=f"{ctx.author.display_name} заработал:",
        value=f"\u200b",
        inline=False
    )
    embed.add_field(
        name=f"💹 Общий заработок",
        value=f"• + {format_number(earn)} {MONEY_EMOJI}",
        inline=False
    )
    detalization_lines = [
        f"• Зарплата: {format_number(base)}  {MONEY_EMOJI}"
    ]
    if bonus > 0:
        detalization_lines.append(f"• Премия: {format_number(bonus)} {MONEY_EMOJI}")

    embed.add_field(
        name="🧾 Детализация",
        value="\n".join(detalization_lines),
        inline=False
    )
    embed.add_field(
        name="💰 Ваш баланс:",
        value=f"• {format_number(new_balance)} {MONEY_EMOJI}",
        inline=False
    )
    embed.add_field(
        name="🗓️ Следующая работа",
        value="Доступна через <t:" + str(next_ts) + ":R>",
        inline=False
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    server_icon = getattr(ctx.guild.icon, "url", None)
    footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    embed.set_footer(text=f"{ctx.guild.name} • {footer_time}", icon_url=server_icon)

    await ctx.send(embed=embed)


SET_WORK_VIEW_TIMEOUT = 240

def parse_duration_to_seconds(text: str) -> Optional[int]:
    """
    Поддерживает:
      - чистые секунды: "3600"
      - суффиксы: "1h 30m 15s", "90m", "2d"
      - формат времени: "HH:MM:SS" или "MM:SS"
    Возвращает секунды либо None (ошибка).
    """
    s = (text or "").strip().lower()
    if not s:
        return None

    if ":" in s:
        parts = s.split(":")
        if len(parts) == 3:
            h, m, sec = parts
        elif len(parts) == 2:
            h, m, sec = "0", parts[0], parts[1]
        else:
            return None
        if not (h.isdigit() and m.isdigit() and sec.isdigit()):
            return None
        h, m, sec = int(h), int(m), int(sec)
        if m >= 60 or sec >= 60 or h < 0 or m < 0 or sec < 0:
            return None
        return h * 3600 + m * 60 + sec

    if s.isdigit():
        v = int(s)
        return v if v >= 0 else None

    total = 0
    for num, unit in re.findall(r"(\d+)\s*([dhms])", s):
        n = int(num)
        if n < 0:
            return None
        if unit == "d":
            total += n * 86400
        elif unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        elif unit == "s":
            total += n
    if total == 0:
        return None
    return total

class _NumModal(disnake.ui.Modal):
    """Базовая модалка для ввода числа."""
    def __init__(self, *, title: str, label: str, placeholder: str, cid: str, view_ref, min0=True):
        super().__init__(title=title, components=[
            disnake.ui.TextInput(
                label=label,
                custom_id=cid,
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder=placeholder,
                max_length=16
            )
        ])
        self.view_ref = view_ref
        self._cid = cid
        self._min0 = min0

    async def callback(self, inter: disnake.ModalInteraction):
        raw = (inter.text_values.get(self._cid) or "").strip().replace(" ", "")
        try:
            val = safe_int(raw, name="Значение", min_v=(0 if self._min0 else 1))
        except ValueError as e:
            return await inter.response.send_message(embed=error_embed("Неверный ввод", str(e)), ephemeral=True)
        ok, msg = self.view_ref.apply_numeric(self._cid, val)
        if not ok:
            return await inter.response.send_message(embed=error_embed("Ошибка", msg or "Проверьте значения."), ephemeral=True)
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class _CooldownModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        super().__init__(
            title="⏱️ Введите кулдаун",
            components=[
                disnake.ui.TextInput(
                    label="Кулдаун",
                    custom_id="cooldown_human",
                    style=disnake.TextInputStyle.short,
                    required=True,
                    placeholder="пример: 3600 или 1h 30m или 00:45:00",
                    max_length=32
                )
            ]
        )
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        raw = (inter.text_values.get("cooldown_human") or "").strip()
        sec = parse_duration_to_seconds(raw)
        if sec is None:
            return await inter.response.send_message(
                embed=error_embed("Неверный формат", "Используйте секунды, '1h 30m', '45m', 'HH:MM:SS' или 'MM:SS'."),
                ephemeral=True
            )
        ok, msg = self.view_ref.apply_cooldown(sec)
        if not ok:
            return await inter.response.send_message(embed=error_embed("Ошибка", msg or "Проверьте значения."), ephemeral=True)
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class WorkSettingsView(disnake.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=SET_WORK_VIEW_TIMEOUT)
        self.ctx = ctx
        self.author_id = ctx.author.id

        cur_min, cur_max, cur_cd = get_work_settings(ctx.guild.id)

        self.min_income = cur_min
        self.max_income = cur_max
        self.cooldown = cur_cd

        self._orig = (cur_min, cur_max, cur_cd)
        self.message: Optional[disnake.Message] = None

    def _changed_chip(self) -> str:
        return " ✎" if (self.min_income, self.max_income, self.cooldown) != self._orig else ""

    def build_embed(self) -> disnake.Embed:
        header = (
            "╭────────────────────────────────╮\n"
            "   ⚙️  Настройки заработка — ᗯᴏʀᴋ\n"
            "╰────────────────────────────────╯"
        )
        e = disnake.Embed(
            title="💼 Панель настройки !work" + self._changed_chip(),
            description=header,
            color=disnake.Color.from_rgb(88, 101, 242)
        )

        e.add_field(
            name="💰 Доход",
            value=(
                f"• Минимум: **{format_number(self.min_income)} {MONEY_EMOJI}**\n"
                f"• Максимум: **{format_number(self.max_income)} {MONEY_EMOJI}**"
            ),
            inline=True
        )
        e.add_field(
            name="⏱️ Кулдаун",
            value=f"• **{format_seconds(self.cooldown)}**",
            inline=True
        )

        try:
            lo, hi = sorted((self.min_income, self.max_income))
        except Exception:
            lo, hi = self.min_income, self.max_income
        preview = random.randint(min(lo, hi), max(lo, hi)) if hi >= lo else lo
        e.add_field(
            name="🔎 Превью начисления (случайный пример)",
            value=f"• Пример следующей выплаты: **{format_number(preview)} {MONEY_EMOJI}**",
            inline=False
        )

        e.add_field(
            name="ℹ️ Подсказки",
            value=(
                "• Нажмите «Изменить минимум/максимум», чтобы ввести число.\n"
                "• «Изменить кулдаун» — введите секунды или формат вроде 1h 30m / 00:45:00.\n"
                "• Пресеты помогают быстро выбрать популярные значения.\n"
                "• «Сброс к дефолту» — подставит значения по умолчанию (не сохранит автоматически).\n"
                "• Нажмите «💾 Сохранить», чтобы применить изменения на сервере."
            ),
            inline=False
        )

        e.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)
        server_icon = getattr(self.ctx.guild.icon, "url", None)
        e.set_footer(text=self.ctx.guild.name, icon_url=server_icon)
        return e

    def apply_numeric(self, cid: str, value: int) -> tuple[bool, Optional[str]]:
        if value < 0:
            return False, "Значение не может быть отрицательным."
        if cid == "min_income":
            self.min_income = value
            if self.max_income < self.min_income:
                self.max_income = self.min_income
            return True, None
        if cid == "max_income":
            self.max_income = value
            if self.max_income < self.min_income:
                self.min_income = self.max_income
            return True, None
        return False, "Неизвестное поле."

    def apply_cooldown(self, seconds: int) -> tuple[bool, Optional[str]]:
        if seconds < 0:
            return False, "Кулдаун не может быть отрицательным."
        self.cooldown = seconds
        return True, None

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Эта панель доступна только инициатору.", ephemeral=True)
            return False
        # Проверка актуального допуска по настройке команды set-work
        if not is_user_allowed_for(ALLOWED_SET_WORK, inter.user):
            await inter.response.send_message("Доступ к настройке работы ограничен.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        try:
            for c in self.children:
                if isinstance(c, (disnake.ui.Button, disnake.ui.SelectBase)):
                    c.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    # ---- controls ----
    @disnake.ui.button(label="🧮 Изменить минимум", style=disnake.ButtonStyle.secondary, custom_id="ws_min", row=0)
    async def _edit_min(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(_NumModal(
            title="🧮 Минимальная граница заработка",
            label="Введите число (≥ 0)",
            placeholder=str(self.min_income),
            cid="min_income",
            view_ref=self,
            min0=True
        ))

    @disnake.ui.button(label="📈 Изменить максимум", style=disnake.ButtonStyle.secondary, custom_id="ws_max", row=0)
    async def _edit_max(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(_NumModal(
            title="📈 Максимальная граница заработка",
            label="Введите число (≥ 0)",
            placeholder=str(self.max_income),
            cid="max_income",
            view_ref=self,
            min0=True
        ))

    @disnake.ui.button(label="⏱️ Изменить кулдаун", style=disnake.ButtonStyle.primary, custom_id="ws_cd", row=0)
    async def _edit_cd(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(_CooldownModal(self))

    @disnake.ui.string_select(
        custom_id="ws_cd_presets",
        placeholder="⚡ Быстрые пресеты кулдауна",
        row=1,
        options=[
            disnake.SelectOption(label="15 минут", value="900", emoji="🟢"),
            disnake.SelectOption(label="30 минут", value="1800", emoji="🟢"),
            disnake.SelectOption(label="1 час", value="3600", emoji="🟡"),
            disnake.SelectOption(label="2 часа", value="7200", emoji="🟡"),
            disnake.SelectOption(label="6 часов", value="21600", emoji="🟠"),
            disnake.SelectOption(label="12 часов", value="43200", emoji="🟠"),
            disnake.SelectOption(label="24 часа", value="86400", emoji="🔴"),
        ]
    )
    async def _cd_presets(self, select: disnake.ui.StringSelect, inter: disnake.MessageInteraction):
        try:
            sec = int(select.values[0])
        except Exception:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Не удалось применить пресет."), ephemeral=True)
        self.cooldown = max(0, sec)
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    @disnake.ui.button(label="♻️ Сброс к дефолту", style=disnake.ButtonStyle.danger, custom_id="ws_reset", row=2)
    async def _reset_defaults(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.min_income = DEFAULT_MIN_INCOME
        self.max_income = DEFAULT_MAX_INCOME
        self.cooldown = DEFAULT_COOLDOWN
        await inter.response.edit_message(embed=self.build_embed(), view=self)
        await inter.followup.send("Черновик сброшен к значениям по умолчанию. Нажмите «Сохранить», чтобы применить.", ephemeral=True)

    @disnake.ui.button(label="💾 Сохранить", style=disnake.ButtonStyle.success, custom_id="ws_save", row=2)
    async def _save(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.min_income < 0 or self.max_income < 0 or self.cooldown < 0:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Значения не могут быть отрицательными."), ephemeral=True)
        if self.min_income > self.max_income:
            self.min_income, self.max_income = self.max_income, self.min_income

        set_work_settings(inter.guild.id, self.min_income, self.max_income, self.cooldown)
        self._orig = (self.min_income, self.max_income, self.cooldown)

        done = disnake.Embed(
            title="✅ Настройки работы сохранены",
            description=(
                "╭────────────────────────────╮\n"
                f"  • Мин.: {format_number(self.min_income)} {MONEY_EMOJI}\n"
                f"  • Макс.: {format_number(self.max_income)} {MONEY_EMOJI}\n"
                f"  • Кулдаун: {format_seconds(self.cooldown)}\n"
                "╰────────────────────────────╯"
            ),
            color=disnake.Color.green()
        )
        done.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)

        try:
            for c in self.children:
                if isinstance(c, (disnake.ui.Button, disnake.ui.SelectBase)):
                    c.disabled = True
        except Exception:
            pass

        if self.message:
            await inter.response.edit_message(embed=done, view=self)
        else:
            await inter.response.send_message(embed=done, ephemeral=True)

    @disnake.ui.button(label="🚪 Закрыть", style=disnake.ButtonStyle.secondary, custom_id="ws_close", row=2)
    async def _close(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.stop()
        try:
            for c in self.children:
                if isinstance(c, (disnake.ui.Button, disnake.ui.SelectBase)):
                    c.disabled = True
            if self.message:
                await inter.response.edit_message(embed=self.build_embed(), view=self)
        except Exception:
            with contextlib.suppress(Exception):
                await inter.response.defer()

@bot.command(name="set-work")
async def set_work_cmd(ctx: commands.Context):
    """
    Открывает интерактивную панель настроек !work.
    Доступ контролируется списком ALLOWED_SET_WORK.
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_SET_WORK):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    view = WorkSettingsView(ctx)
    embed = view.build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

# ====================== Команда !role-income (панель) ======================

@bot.command(name="role-income", aliases=["Role-income", "ROLE-INCOME", "Role-Income", "roleincome", "Roleincome", "ROLEINCOME"])
async def role_income_cmd(ctx: commands.Context):
    """
    Панель управления доходными ролями:
      !role-income
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_ROLE_INCOME):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    view = RoleIncomeView(ctx)
    embed = build_role_income_embed(ctx.guild, ctx.author)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

# ====================== Команда !income-list (список доходов ролей) ======================

INCOME_LIST_PAGE_SIZE = 5  # Сколько записей показывать на странице
PAGE_SIZE = 10  # добавьте вверху файла

def _build_income_list_embed(guild: disnake.Guild, data: list[dict], page: int, per_page: int) -> disnake.Embed:
    from datetime import datetime
    total = len(data)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    chunk = data[start:end]

    e = disnake.Embed(
        title=f"Список доходов с ролей (страница {page + 1}/{total_pages})",
        color=disnake.Color.from_rgb(88, 101, 242)
    )

    if not chunk:
        e.description = "Список пуст."
    else:
        id2name = items_id_to_name_map(guild)
        for ri in chunk:
            # ИСПОЛЬЗУЕМ НЕВИДИМЫЙ СИМВОЛ ДЛЯ ЗАГОЛОВКА, ЧТОБЫ СОХРАНИТЬ ВНЕШНИЙ ВИД
            # Это "нулевой" пробел (zero-width space)
            field_name = "\u200b"

            # 1) Роль (ПЕРЕНЕСЕНО ВНУТРЬ VALUE)
            role_mention = f"<@&{ri['role_id']}>"
            first = f"**Роль: {role_mention}**"

            # 2) Сумма или Ресурсы
            if ri["income_type"] == "money":
                second = f"Сумма: {format_number(int(ri['money_amount'] or 0))}"
            else:
                if not ri["items"]:
                    second = "Ресурсы: —"
                else:
                    parts = []
                    for it in ri["items"]:
                        nm = id2name.get(int(it["item_id"]), f"ID {it['item_id']}")
                        qty = int(it["qty"])
                        parts.append(f"{nm} ({qty} шт.)")
                    second = "Ресурсы: " + " | ".join(parts)

            # 3) Интервал
            third = f"Интервал: {format_seconds(int(ri['cooldown_seconds'] or 0))}"

            # 4) Тип
            typ = "Cash" if ri["income_type"] == "money" else "Item"
            fourth = f"Тип: {typ}"

            # 5) Добавил
            added_by = f"<@{ri['created_by']}>" if ri.get("created_by") else "—"
            fifth = f"Добавил: {added_by}"
            
            # Собираем все строки в значение поля
            value = "\n".join([first, second, third, fourth, fifth])
            if len(value) > 1024:
                value = value[:1000] + "\n…"

            e.add_field(name=field_name, value=value, inline=False)

    # Футер: Всего доходов + время, как на скрине
    server_icon = getattr(guild.icon, "url", None)
    footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    e.set_footer(text=f"Всего доходов: {total} • {footer_time}", icon_url=server_icon)
    return e

class IncomeListView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, data: list[dict], per_page: int = INCOME_LIST_PAGE_SIZE):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.data = data
        self.per_page = per_page
        self.page = 0
        self.message: Optional[disnake.Message] = None

        # При инициализации корректно проставим состояние кнопок
        self._update_buttons_state()

    def _update_buttons_state(self):
        total = len(self.data)
        total_pages = max(1, (total + self.per_page - 1) // self.per_page)
        prev_btn = next((c for c in self.children if isinstance(c, disnake.ui.Button) and c.custom_id == "income_prev"), None)
        next_btn = next((c for c in self.children if isinstance(c, disnake.ui.Button) and c.custom_id == "income_next"), None)
        if prev_btn:
            prev_btn.disabled = (self.page <= 0 or total_pages <= 1)
        if next_btn:
            next_btn.disabled = (self.page >= total_pages - 1 or total_pages <= 1)

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        # Разрешаем листать только автору команды.
        if inter.user.id != self.ctx.author.id:
            await inter.response.send_message("Листать страницы может только автор команды.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> disnake.Embed:
        return _build_income_list_embed(self.ctx.guild, self.data, self.page, self.per_page)

    @disnake.ui.button(label="Назад", style=disnake.ButtonStyle.secondary, custom_id="income_prev")
    async def _prev(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.page = max(0, self.page - 1)
        self._update_buttons_state()
        try:
            await inter.response.edit_message(embed=self.build_embed(), view=self)
        except Exception:
            pass

    @disnake.ui.button(label="Вперед", style=disnake.ButtonStyle.primary, custom_id="income_next")
    async def _next(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        total = len(self.data)
        total_pages = max(1, (total + self.per_page - 1) // self.per_page)
        self.page = min(total_pages - 1, self.page + 1)
        self._update_buttons_state()
        try:
            await inter.response.edit_message(embed=self.build_embed(), view=self)
        except Exception:
            pass

    async def on_timeout(self):
        try:
            for c in self.children:
                if isinstance(c, disnake.ui.Button):
                    c.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

@bot.command(name="income-list", aliases=["Income-list", "INCOME-LIST", "Income-List", "incomelist", "INCOMELIST"])
async def income_list_cmd(ctx: commands.Context):
    """
    Список доходов с ролей с пагинацией:
      !income-list
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_INCOME_LIST):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    data = db_get_role_incomes(ctx.guild.id)
    view = IncomeListView(ctx, data, per_page=INCOME_LIST_PAGE_SIZE)
    embed = view.build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

def build_logmenu_embed(guild: disnake.Guild) -> disnake.Embed:
    e = disnake.Embed(
        title="Настройка логов доходных ролей",
        description="Выберите канал, куда бот будет отправлять логи создания/изменения/удаления доходных ролей.",
        color=disnake.Color.from_rgb(88, 101, 242)
    )
    ch_id = db_get_role_income_log_channel(guild.id)
    current = f"<#{ch_id}>" if ch_id else "— (не выбран)"
    e.add_field(name="Текущий канал логов", value=current, inline=False)
    server_icon = getattr(guild.icon, "url", None)
    footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    e.set_footer(text=f"{guild.name} • {footer_time}", icon_url=server_icon)
    return e

class LogMenuView(disnake.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.message: Optional[disnake.Message] = None

        # Компонент выбора канала (текстовые/новостные)
        self.channel_select = disnake.ui.ChannelSelect(
            channel_types=[disnake.ChannelType.text, disnake.ChannelType.news],
            placeholder="Выберите канал для логов",
            min_values=1, max_values=1,
            custom_id="ri_logs_pick_channel"
        )
        self.add_item(self.channel_select)

        # Кнопка отключения
        self.disable_btn = disnake.ui.Button(
            label="Отключить логи",
            style=disnake.ButtonStyle.danger,
            custom_id="ri_logs_disable"
        )
        self.add_item(self.disable_btn)

        async def on_channel_pick(i: disnake.MessageInteraction):
            # Разрешаем настраивать только автору и пользователям с правами на доходные роли
            if not is_user_allowed_for(ALLOWED_ROLE_INCOME, i.user):
                return await i.response.send_message("Недостаточно прав.", ephemeral=True)

            ch = self.channel_select.values[0]
            db_set_role_income_log_channel(i.guild.id, ch.id)
            try:
                await i.response.edit_message(embed=build_logmenu_embed(i.guild), view=self)
            except Exception:
                await i.response.send_message(f"Канал логов установлен: {ch.mention}", ephemeral=True)

        async def on_disable(i: disnake.MessageInteraction):
            if not is_user_allowed_for(ALLOWED_ROLE_INCOME, i.user):
                return await i.response.send_message("Недостаточно прав.", ephemeral=True)

            db_set_role_income_log_channel(i.guild.id, None)
            try:
                await i.response.edit_message(embed=build_logmenu_embed(i.guild), view=self)
            except Exception:
                await i.response.send_message("Логи отключены.", ephemeral=True)

        self.channel_select.callback = on_channel_pick
        self.disable_btn.callback = on_disable

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        # Базовая защита от чужих кликов
        if inter.user.id != self.ctx.author.id and not is_user_allowed_for(ALLOWED_ROLE_INCOME, inter.user):
            await inter.response.send_message("Недостаточно прав для изменения настроек логов.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        try:
            for c in self.children:
                if isinstance(c, (disnake.ui.Button, disnake.ui.SelectBase)):
                    c.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

@bot.command(name="logmenu", aliases=["Logmenu", "LOGMENU"])
async def logmenu_cmd(ctx: commands.Context):
    """
    Настройка логов доходных ролей:
      !logmenu
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_LOG_MENU):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    view = LogMenuView(ctx)
    embed = build_logmenu_embed(ctx.guild)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

# --- Вспомогательные функции (вставьте рядом с другими утилитами файла) ---

BAR_LEN = 20

def _make_bar(pct: int, length: int = BAR_LEN) -> str:
    """Текстовая полоска прогресса для наглядности."""
    pct = max(0, min(100, int(pct)))
    filled = max(0, min(length, round(pct * length / 100)))
    return f"[{'█' * filled}{'░' * (length - filled)}]"

def _mix_color_for(pct_for: int) -> disnake.Color:
    """Цвет от красного (0% ЗА) к зелёному (100% ЗА)."""
    pct_for = max(0, min(100, int(pct_for)))
    r = int(255 * (100 - pct_for) / 100)
    g = int(255 * pct_for / 100)
    b = 60
    return disnake.Color.from_rgb(r, g, b)

@dataclass
class Candidate:
    name: str
    age: int
    ideology: str
    party: str


def _server_icon_and_name(embed: disnake.Embed, guild: disnake.Guild, bot_user: disnake.ClientUser | None):
    """Оформляет верхнюю часть эмбеда как в референдуме: мини-иконка + имя сервера."""
    icon_url = None
    if guild and guild.icon:
        icon_url = guild.icon.url
    elif bot_user:
        icon_url = bot_user.display_avatar.url

    if icon_url:
        embed.set_author(name=guild.name if guild else "Server", icon_url=icon_url)
        embed.set_thumbnail(url=icon_url)
    else:
        embed.set_author(name=guild.name if guild else "Server")


def _dirichlet_like_normalized(n: int) -> list[int]:
    """Случайное разбиение 100% между n кандидатами c «сбалансированным» видом."""
    if n <= 0:
        return []
    # Сэмплируем веса из гаммы (эквивалент Дирихле), затем нормируем
    alpha = 3.2
    ws = [random.gammavariate(alpha, 1.0) for _ in range(n)]
    s = sum(ws)
    if s <= 0:
        # фолбэк - равные доли
        base = 100 // n
        arr = [base] * n
        arr[0] += 100 - base * n
        return arr
    floats = [w / s * 100 for w in ws]
    # Переведём в int так, чтобы сумма была ровно 100
    ints = [int(round(x)) for x in floats]
    diff = 100 - sum(ints)
    # Подправим (распределим отклонение по единицам)
    i = 0
    while diff != 0 and i < n * 3:
        idx = i % n
        if diff > 0:
            ints[idx] += 1
            diff -= 1
        else:
            if ints[idx] > 0:
                ints[idx] -= 1
                diff += 1
        i += 1
    # гарантируем неотрицательность
    for i in range(n):
        if ints[i] < 0:
            ints[i] = 0
    # на всякий случай снова поправим сумму
    s2 = sum(ints)
    if s2 != 100 and n > 0:
        ints[0] += (100 - s2)
    return ints


# ===========================
# Выборы: модалки и вьюшки
# ===========================

class CandidateModal(disnake.ui.Modal):
    """Модалка анкеты кандидата."""
    def __init__(self, view_ref):
        components = [
            disnake.ui.TextInput(
                label="Имя кандидата",
                custom_id="name",
                style=disnake.TextInputStyle.short,
                max_length=64,
                required=True
            ),
            disnake.ui.TextInput(
                label="Возраст кандидата",
                custom_id="age",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 35"
            ),
            disnake.ui.TextInput(
                label="Политическая идеология кандидата",
                custom_id="ideology",
                style=disnake.TextInputStyle.paragraph,
                max_length=200,
                required=True
            ),
            disnake.ui.TextInput(
                label="Политическая партия кандидата",
                custom_id="party",
                style=disnake.TextInputStyle.short,
                max_length=100,
                required=True
            ),
        ]
        super().__init__(title="Анкета кандидата", components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        name = inter.text_values.get("name", "").strip()
        age_raw = inter.text_values.get("age", "").strip()
        ideology = inter.text_values.get("ideology", "").strip()
        party = inter.text_values.get("party", "").strip()

        try:
            age = safe_int(age_raw, name="Возраст", min_v=1, max_v=120)
        except ValueError as e:
            return await inter.response.send_message(
                embed=error_embed("Ошибка", str(e)),
                ephemeral=True
            )

        cand = Candidate(name=name, age=age, ideology=ideology, party=party)
        self.view_ref.candidates.append(cand)
        self.view_ref._sync_buttons_state()

        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class _DeleteCandidateSelect(disnake.ui.StringSelect):
    """Временный селект для удаления кандидата."""
    def __init__(self, parent_view):
        options = []
        for idx, c in enumerate(parent_view.candidates):
            label = c.name[:25] if c.name else f"Кандидат {idx+1}"
            desc = f"{c.party or 'без партии'} • {c.age} лет"
            options.append(disnake.SelectOption(label=label, value=str(idx), description=desc))
        super().__init__(
            placeholder="Выберите кандидата для удаления",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="elections_del_select"
        )
        self.parent_view = parent_view

    async def callback(self, inter: disnake.MessageInteraction):
        try:
            idx = int(self.values[0])
        except Exception:
            return await inter.response.send_message("Некорректный выбор.", ephemeral=True)

        if 0 <= idx < len(self.parent_view.candidates):
            removed = self.parent_view.candidates.pop(idx)
            self.parent_view._sync_buttons_state()
            # Обновим основное сообщение
            try:
                if self.parent_view.message:
                    await self.parent_view.message.edit(embed=self.parent_view.build_embed(), view=self.parent_view)
            except Exception:
                pass
            await inter.response.edit_message(content=f"Удалён: {removed.name}", view=None)
        else:
            await inter.response.send_message("Кандидат не найден.", ephemeral=True)


class _DeleteCandidateEphemeralView(disnake.ui.View):
    """Временная ephemeral-вьюшка с селектом удаления."""
    def __init__(self, parent_view):
        super().__init__(timeout=60)
        self.add_item(_DeleteCandidateSelect(parent_view))


class ElectionsApplicationView(disnake.ui.View):
    """Панель заявки на выборы: добавление/удаление кандидатов и запуск выборов."""
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.candidates: list[Candidate] = []
        self.message: disnake.Message | None = None
        self._sync_buttons_state()

    def build_embed(self) -> disnake.Embed:
        e = disnake.Embed(
            title="Заявка на выборы",
            color=disnake.Color.blurple()
        )
        _server_icon_and_name(e, self.ctx.guild, self.ctx.bot.user)

        if not self.candidates:
            e.description = "Список кандидатов пуст. Нажмите «Добавить кандидата»."
        else:
            blocks = []
            for i, c in enumerate(self.candidates, start=1):
                block = [
                    f"**{i}. {c.name}**",
                    f"- Возраст: {c.age}",
                    f"- Политическая идеология: {c.ideology}",
                    f"- Политическая партия: {c.party}",
                ]
                blocks.append("\n".join(block))
            e.description = "\n\n".join(blocks)

        e.set_footer(text="Добавляйте кандидатов, затем нажмите «Провести выборы».")
        return e

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Эта панель доступна только инициатору.", ephemeral=True)
            return False
        return True

    def _sync_buttons_state(self):
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                if child.custom_id == "elections_start":
                    # Минимум 2 кандидата для смысла выборов
                    child.disabled = len(self.candidates) < 2
                elif child.custom_id == "elections_del":
                    child.disabled = len(self.candidates) == 0

    @disnake.ui.button(label="Добавить кандидата", style=disnake.ButtonStyle.success, custom_id="elections_add", row=0)
    async def _add_candidate(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(CandidateModal(self))

    @disnake.ui.button(label="Удалить кандидата", style=disnake.ButtonStyle.danger, custom_id="elections_del", row=0)
    async def _del_candidate(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not self.candidates:
            return await inter.response.send_message("Пока некого удалять.", ephemeral=True)
        view = _DeleteCandidateEphemeralView(self)
        await inter.response.send_message("Выберите кандидата для удаления:", view=view, ephemeral=True)

    @disnake.ui.button(label="Провести выборы", style=disnake.ButtonStyle.primary, custom_id="elections_start", row=0)
    async def _start_elections(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if len(self.candidates) < 2:
            return await inter.response.send_message(embed=error_embed("Недостаточно кандидатов", "Добавьте минимум двух кандидатов."), ephemeral=True)

        # Подготовим результаты первого тура
        result_view = ElectionsResultsView(self.ctx, self.candidates, round_index=1)
        embed = result_view.build_embed()

        await inter.response.defer()
        with contextlib.suppress(Exception):
            await inter.message.delete()

        msg = await self.ctx.channel.send(embed=embed, view=result_view)
        result_view.message = msg

    async def on_timeout(self):
        try:
            for child in self.children:
                if isinstance(child, (disnake.ui.Button, disnake.ui.SelectBase)):
                    child.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class ElectionsResultsView(disnake.ui.View):
    """Панель показа результатов выборов с пагинацией и кнопкой тура/итогов."""
    def __init__(self, ctx: commands.Context, candidates: list[Candidate], round_index: int = 1):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.candidates = list(candidates)
        self.round_index = int(round_index)
        self.page = 0
        self.message: disnake.Message | None = None

        # Случайная явка (как в референдуме — чаще средняя/высокая)
        self.turnout = int(round(random.betavariate(4, 3) * 100))
        self.turnout = max(0, min(100, self.turnout))

        # Проценты по кандидатам
        if len(self.candidates) == 2 and self.round_index >= 2:
            # Для 2 тура — гарантируем определённого победителя (не 50/50)
            p = random.betavariate(3.2, 3.2)
            if abs(p - 0.5) < 0.01:
                p += 0.02 if random.random() < 0.5 else -0.02
            p = max(0.0, min(1.0, p))
            a = int(round(p * 100))
            b = 100 - a
            self.pcts = [a, b]
        else:
            self.pcts = _dirichlet_like_normalized(len(self.candidates))

        # Индекс лидера
        self.winner_idx = max(range(len(self.pcts)), key=lambda i: self.pcts[i]) if self.candidates else 0

        # Правило завершения тура/перехода к следующему:
        # - В 1-м туре второй тур назначается, если победитель < 50% ИЛИ явка < 50%.
        # - Во 2-м туре итоги доступны всегда (has_majority = True).
        base_majority = any(p >= 50 for p in self.pcts)
        if self.round_index >= 2:
            self.has_majority = True
        else:
            self.has_majority = base_majority and self.turnout >= 50

        self._sync_buttons_state()

    def _current_candidate(self) -> tuple[Candidate, int]:
        cand = self.candidates[self.page]
        pct = int(self.pcts[self.page])
        return cand, pct

    def _action_label(self) -> str:
        return "Итоги выборов" if self.has_majority else "Следующий тур"

    def _sync_buttons_state(self):
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                if child.custom_id == "results_prev":
                    child.disabled = self.page <= 0
                elif child.custom_id == "results_next":
                    child.disabled = self.page >= len(self.candidates) - 1
                elif child.custom_id == "results_action":
                    child.label = self._action_label()

    def build_embed(self) -> disnake.Embed:
        cand, pct = self._current_candidate()
        color = _mix_color_for(pct)

        e = disnake.Embed(
            title="Выборы",
            color=color
        )
        _server_icon_and_name(e, self.ctx.guild, self.ctx.bot.user)

        # Оформление блока кандидата
        lines = [
            f"**{cand.name}**",
            f"- Возраст: {cand.age}",
            f"- Политическая идеология: {cand.ideology}",
            f"- Политическая партия: {cand.party}",
            "",
            "__Результаты выборов:__",
            f"Явка: {self.turnout}% {_make_bar(self.turnout)}",
            f"Проголосовали за кандидата: {pct}% {_make_bar(pct)}",
        ]
        e.description = "\n".join(lines)
        e.set_footer(text=f"Кандидат {self.page + 1} / {len(self.candidates)} • Тур {self.round_index}")
        return e

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Эта панель доступна только инициатору.", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="Назад", style=disnake.ButtonStyle.secondary, custom_id="results_prev", row=0)
    async def _prev(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.page > 0:
            self.page -= 1
        self._sync_buttons_state()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    @disnake.ui.button(label="Следующее действие", style=disnake.ButtonStyle.blurple, custom_id="results_action", row=0)
    async def _action(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.has_majority:
            # Итоги выборов — показываем победителя отдельным эмбед-сообщением
            winner = self.candidates[self.winner_idx]
            pct = int(self.pcts[self.winner_idx])

            em = disnake.Embed(
                title="Победитель выборов:",
                color=disnake.Color.green()
            )
            _server_icon_and_name(em, inter.guild, inter.client.user)
            em.description = "\n".join([
                f"**{winner.name}**",
                f"- Возраст: {winner.age}",
                f"- Политическая идеология: {winner.ideology}",
                f"- Политическая партия: {winner.party}",
                "",
                "__Результаты выборов:__",
                f"Явка: {self.turnout}% {_make_bar(self.turnout)}",
                f"Проголосовали за кандидата: {pct}% {_make_bar(pct)}",
            ])
            em.set_footer(text=f"Тур {self.round_index} • Победитель по итогам голосования")
            await inter.response.send_message(embed=em)
        else:
            # Следующий тур: ТОП-2 кандидата
            if len(self.candidates) < 2:
                return await inter.response.send_message("Недостаточно кандидатов для второго тура.", ephemeral=True)

            order = sorted(range(len(self.pcts)), key=lambda i: self.pcts[i], reverse=True)
            top2_idx = order[:2]
            next_candidates = [self.candidates[i] for i in top2_idx]

            next_view = ElectionsResultsView(self.ctx, next_candidates, round_index=self.round_index + 1)
            embed = next_view.build_embed()
            next_view.message = self.message

            await inter.response.edit_message(embed=embed, view=next_view)

    @disnake.ui.button(label="Вперед", style=disnake.ButtonStyle.primary, custom_id="results_next", row=0)
    async def _next(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.page < len(self.candidates) - 1:
            self.page += 1
        self._sync_buttons_state()
        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        try:
            for child in self.children:
                if isinstance(child, (disnake.ui.Button, disnake.ui.SelectBase)):
                    child.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# ===========================
# Команда выборов (префиксная)
# ===========================
@bot.command(name="elections", aliases=["выборы", "Выборы", "ВЫБОРЫ"])
async def elections_cmd(ctx: commands.Context):
    """Создать заявку на выборы, добавить кандидатов и провести выборы."""
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    view = ElectionsApplicationView(ctx)
    embed = view.build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

# --- Команда референдума (префиксная), стиль и структура как у остальных команд ---

@bot.command(name="referendum", aliases=["референдум", "Референдум", "РЕФЕРЕНДУМ"])
async def referendum_cmd(ctx: commands.Context):
    """Показать случайные результаты референдума (сбалансированные проценты)."""
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    guild = ctx.guild

    # Явка: чаще средняя/высокая, но всегда в диапазоне 0..100
    turnout = int(round(random.betavariate(4, 3) * 100))
    turnout = max(0, min(100, turnout))

    # Проценты ЗА/ПРОТИВ: симметричное beta-распределение вокруг 50%,
    # реже уходящее в крайности — «более сбалансировано».
    p_for = random.betavariate(3.2, 3.2)
    for_pct = max(0, min(100, int(round(p_for * 100))))
    against_pct = 100 - for_pct  # гарантируем сумму 100%

    color = _mix_color_for(for_pct)

    embed = disnake.Embed(
        title=":scroll: Референдум",
        color=color,
    )

    # Верхняя часть: мини-иконка (аватарка) и название сервера
    icon_url = None
    if guild and guild.icon:
        icon_url = guild.icon.url
    else:
        # Фолбэк — иконка бота
        if ctx.bot.user:
            icon_url = ctx.bot.user.display_avatar.url

    if icon_url:
        embed.set_author(name=guild.name if guild else "Server", icon_url=icon_url)
        embed.set_thumbnail(url=icon_url)
    else:
        embed.set_author(name=guild.name if guild else "Server")

    # Контент
    embed.description = (
        f":busts_in_silhouette: Явка: {turnout}%\n"
        f":ballot_box_with_check: Голоса ЗА: {for_pct}% {_make_bar(for_pct)}\n"
        f":x: Голоса против: {against_pct}% {_make_bar(against_pct)}"
    )
    embed.set_footer(text="Результаты сгенерированы случайно для демонстрации")

    await ctx.send(embed=embed)

class LeaderboardView(disnake.ui.View):
    def __init__(self, ctx, *, page_size: int = 10, timeout: float | None = 120):
        # В disnake.ui.View допустим только timeout
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.author_id = ctx.author.id

        # Нормализуем page_size
        try:
            ps = int(page_size)
        except (TypeError, ValueError):
            ps = 10
        self.page_size = max(1, ps)  # защита от 0 и отрицательных

        self.page = 1
        self.total = get_balances_count(self.guild.id)
        # ceil без импорта math
        self.total_pages = max(1, ((self.total + self.page_size - 1) // self.page_size)) if self.total else 1
        self.message: disnake.Message | None = None

    async def _resolve_name(self, user_id: int) -> str:
        # Ник без пинга: берем display_name в гильдии, иначе глобальное имя/ID
        member = self.guild.get_member(user_id)
        if member:
            return member.display_name
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except Exception:
                user = None
        return user.name if user else f"ID {user_id}"

    async def make_embed(self) -> disnake.Embed:
        offset = (self.page - 1) * self.page_size
        rows = get_top_balances(self.guild.id, self.page_size, offset)

        if not rows:
            description = "Пока нет данных по балансу на этом сервере."
        else:
            lines = []
            for i, (user_id, balance) in enumerate(rows, start=offset + 1):
                name = await self._resolve_name(user_id)
                lines.append(f"{i}. {name} → {format_number(balance)} {MONEY_EMOJI}")
            description = "\n".join(lines)

        embed = disnake.Embed(
            title=f"🏆 Топ игроков {self.guild.name}",
            description=description,
            color=disnake.Color.gold(),
        )
        if self.guild.icon:
            embed.set_thumbnail(url=self.guild.icon.url)
        embed.set_footer(text=f"Страница {self.page}/{self.total_pages}")
        # Переключим доступность кнопок под текущую страницу
        self._sync_buttons_state()
        return embed

    def _sync_buttons_state(self):
        back_btn = next((c for c in self.children if isinstance(c, disnake.ui.Button) and c.custom_id == "lb_back"), None)
        fwd_btn = next((c for c in self.children if isinstance(c, disnake.ui.Button) and c.custom_id == "lb_forward"), None)
        if back_btn:
            back_btn.disabled = self.page <= 1
        if fwd_btn:
            fwd_btn.disabled = self.page >= self.total_pages or self.total_pages == 1

    async def _ensure_author(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.author_id:
            try:
                await inter.response.send_message("Только автор команды может листать страницы.", ephemeral=True)
            except disnake.HTTPException:
                pass
            return False
        return True

    @disnake.ui.button(label="Назад", emoji="⬅️", style=disnake.ButtonStyle.secondary, custom_id="lb_back")
    async def back(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not await self._ensure_author(inter):
            return
        if self.page > 1:
            self.page -= 1
        embed = await self.make_embed()
        await inter.response.edit_message(embed=embed, view=self)

    @disnake.ui.button(label="Вперед", emoji="➡️", style=disnake.ButtonStyle.secondary, custom_id="lb_forward")
    async def forward(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        if not await self._ensure_author(inter):
            return
        if self.page < self.total_pages:
            self.page += 1
        embed = await self.make_embed()
        await inter.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        # По таймауту отключаем кнопки
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

# >>> ВСТАВИТЬ В РАЗДЕЛ КОМАНД

@bot.command(name="apanel")
async def admin_panel_cmd(ctx: commands.Context):
    """
    Админ-панель: показывает эмбед с кнопками опасных действий.
    Доступ только администраторам.
    """
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    if not _apanel_is_admin(ctx.author):
        return await ctx.send(embed=error_embed("Недостаточно прав", "Эта команда доступна только администраторам."))

    # Красивый эмбед
    e = disnake.Embed(
        title="Админ панель",
        color=disnake.Color.from_rgb(88, 101, 242),
        description=(
            "Опасные операции. Будьте осторожны — перед выполнением потребуется подтверждение.\n"
            "• Сбросить инвентари — удаляет все записи инвентаря пользователей.\n"
            "• Сбросить балансы — выставляет балансы всем пользователям в 0.\n"
            "• Сбросить бюджет Всемирного банка — обнуляет казну банка (комиссия не меняется).\n"
            "• Очистить магазин — удаляет все предметы, состояния, дневные лимиты и инвентари по этим предметам.\n"
            "• Очистить доходные роли — удаляет все доходные роли и кулдауны."
        )
    )
    e.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    e.set_footer(text=ctx.guild.name, icon_url=getattr(ctx.guild.icon, "url", None))

    view = AdminPanelView(ctx)
    msg = await ctx.send(embed=e, view=view)
    view.message = msg

@bot.command(name="leaderboard", aliases=["lb", "top", "Top", "Lb", "Leaderboard", "LB", "TOP"])
async def leaderboard_prefix(ctx: commands.Context):

    # Используем ту же систему допуска, что и для баланса
    if not await ensure_allowed_ctx(ctx, ALLOWED_BALANCE):
        return

    view = LeaderboardView(ctx, page_size=PAGE_SIZE)
    embed = await view.make_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

BUMP_REMINDER_BOT_ID = 478321260481478677
# ДОБАВИТЬ рядом с BUMP_REMINDER_BOT_ID
SERVER_MONITORING_BOT_ID = 315926021457051650
SUPPORTED_BUMP_BOT_IDS = {BUMP_REMINDER_BOT_ID, SERVER_MONITORING_BOT_ID}

def setup_bump_tables():
    """Создаём таблицы для настроек и логов наград за бамп."""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bump_reward_settings (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            amount INTEGER NOT NULL DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bump_reward_awards (
            guild_id INTEGER NOT NULL,
            message_id INTEGER PRIMARY KEY,
            awarded_user_id INTEGER NOT NULL,
            awarded_ts INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def db_get_bump_settings(guild_id: int) -> tuple[int, int]:
    """Возвращает (enabled, amount)."""
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("SELECT enabled, amount FROM bump_reward_settings WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    if not row:
        # создадим дефолт
        c.execute("INSERT OR IGNORE INTO bump_reward_settings (guild_id, enabled, amount) VALUES (?, ?, ?)", (guild_id, 0, 0))
        conn.commit()
        conn.close()
        return 0, 0
    conn.close()
    return int(row[0]), int(row[1])

def db_set_bump_enabled(guild_id: int, enabled: bool):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        INSERT INTO bump_reward_settings (guild_id, enabled, amount)
        VALUES (?, ?, COALESCE((SELECT amount FROM bump_reward_settings WHERE guild_id = ?), 0))
        ON CONFLICT(guild_id) DO UPDATE SET enabled = excluded.enabled
    """, (guild_id, 1 if enabled else 0, guild_id))
    conn.commit()
    conn.close()

def db_set_bump_amount(guild_id: int, amount: int):
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        INSERT INTO bump_reward_settings (guild_id, enabled, amount)
        VALUES (?, COALESCE((SELECT enabled FROM bump_reward_settings WHERE guild_id = ?), 0), ?)
        ON CONFLICT(guild_id) DO UPDATE SET amount = excluded.amount
    """, (guild_id, guild_id, int(amount)))
    conn.commit()
    conn.close()

def db_mark_bump_awarded(guild_id: int, message_id: int, user_id: int) -> bool:
    """
    Пишем лог выдачи по message_id. Если такая запись уже есть — вернём False (не выдавать повторно).
    """
    import time as _time
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO bump_reward_awards (guild_id, message_id, awarded_user_id, awarded_ts)
            VALUES (?, ?, ?, ?)
        """, (guild_id, message_id, user_id, int(_time.time())))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def _build_bump_settings_embed(guild: disnake.Guild, invoker: disnake.Member) -> disnake.Embed:
    enabled, amount = db_get_bump_settings(guild.id)
    e = disnake.Embed(
        title="Настройка награды за бамп",
        color=disnake.Color.from_rgb(88, 101, 242),
        description=(
            f"Статус: {'🟢 Включено' if enabled else '🔴 Выключено'}\n"
            f"Сумма награды: {format_number(amount)} {MONEY_EMOJI}"
        )
    )
    e.set_author(name=invoker.display_name, icon_url=invoker.display_avatar.url)
    e.set_footer(text=guild.name, icon_url=getattr(guild.icon, 'url', None))
    return e

class BumpRewardAmountModal(disnake.ui.Modal):
    def __init__(self, view_ref: "BumpRewardView"):
        components = [
            disnake.ui.TextInput(
                label="Сумма награды за бамп",
                custom_id="amount",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="Например: 500",
                value=str(db_get_bump_settings(view_ref.ctx.guild.id)[1] or "")
            )
        ]
        super().__init__(title="Изменить сумму награды", components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        raw = inter.text_values.get("amount", "").strip()
        try:
            amount = safe_int(raw, name="Сумма", min_v=0)
        except ValueError as e:
            return await inter.response.send_message(
                embed=error_embed("Ошибка", str(e)),
                ephemeral=True
            )
        db_set_bump_amount(inter.guild.id, amount)
        await inter.response.edit_message(embed=_build_bump_settings_embed(inter.guild, inter.user), view=self.view_ref)

class BumpRewardView(disnake.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.author_id = ctx.author.id
        # динамически обновим подписи
        self._sync_toggle_label()

    def _sync_toggle_label(self):
        enabled, _ = db_get_bump_settings(self.ctx.guild.id)
        for child in self.children:
            if isinstance(child, disnake.ui.Button) and child.custom_id == "bump_toggle":
                child.label = "Выключить" if enabled else "Включить"
                child.style = disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        # ограничим управление только инициатору и людям с правом управления сервером
        if inter.user.id != self.author_id and not inter.user.guild_permissions.manage_guild:
            await inter.response.send_message("Только инициатор и пользователи с правом «Управлять сервером» могут менять настройки.", ephemeral=True)
            return False
        return True

    @disnake.ui.button(label="Включить", style=disnake.ButtonStyle.success, custom_id="bump_toggle", row=0)
    async def _toggle(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        enabled, amount = db_get_bump_settings(inter.guild.id)
        db_set_bump_enabled(inter.guild.id, not bool(enabled))
        self._sync_toggle_label()
        await inter.response.edit_message(embed=_build_bump_settings_embed(inter.guild, inter.user), view=self)

    @disnake.ui.button(label="Награда", style=disnake.ButtonStyle.primary, custom_id="bump_amount", row=0)
    async def _amount(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(BumpRewardAmountModal(self))

    async def on_timeout(self):
        try:
            for c in self.children:
                if isinstance(c, (disnake.ui.Button, disnake.ui.SelectBase)):
                    c.disabled = True
            # Попробуем обновить сообщение (если оно ещё доступно)
            # self.message может быть присвоено снаружи
            if hasattr(self, "message") and self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

@bot.command(name="set-money-bump")
@commands.has_permissions(manage_guild=True)
async def set_money_bump_cmd(ctx: commands.Context):
    """
    Открывает панель настройки награды за бамп:
    - Включить/Выключить
    - Награда (ввести сумму)
    """
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    view = BumpRewardView(ctx)
    embed = _build_bump_settings_embed(ctx.guild, ctx.author)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

@bot.listen("on_ready")
async def _bump_on_ready():
    setup_bump_tables()
    print("Таблицы Bump Reward готовы.")

def _extract_text_from_embeds(embeds: list[disnake.Embed]) -> str:
    """Собираем текст из эмбедов: title/description/fields."""
    parts = []
    for em in embeds or []:
        if em.title: parts.append(str(em.title))
        if em.description: parts.append(str(em.description))
        for f in em.fields:
            parts.append(f"{f.name}\n{f.value}")
        # Некоторые боты кладут полезное в footer.text
        if em.footer and em.footer.text:
            parts.append(str(em.footer.text))
    return "\n".join(parts)

# ЗАМЕНИТЬ целиком функцию на эту (совместима с прежней логикой)
def _try_extract_user_from_bump_message(message: disnake.Message) -> disnake.Member | None:
    """
    Пытаемся понять, кто бампнул сервер, по сообщению от поддерживаемых ботов.
    Стратегии:
      1) Явные упоминания в тексте/эмбеде (<@id>)
      2) em.author.name ~ ник/дисплей-нейм участника
      3) user_id из icon_url (для некоторых эмбедов)
      4) Fallback для Server Monitoring: "Server bumped by <...>" — пытаемся вытащить mention или ник
    """
    guild = message.guild
    if not guild:
        return None

    combined_text = (message.content or "") + "\n" + _extract_text_from_embeds(message.embeds or [])

    # 1) Явные упоминания в самом сообщении
    if message.mentions:
        m = message.mentions[0]
        return guild.get_member(m.id) if hasattr(m, "id") else None

    # 2) Парсим упоминания вида <@id> внутри текста/эмбедов
    m = re.search(r"<@!?(\d+)>", combined_text)
    if m:
        uid = int(m.group(1))
        mem = guild.get_member(uid)
        if mem:
            return mem

    # 3) Эвристика по em.author.name
    if message.embeds:
        em = message.embeds[0]
        if em.author and em.author.name:
            name = em.author.name.strip()
            for member in guild.members:
                if member.name == name or member.display_name == name:
                    return member
            name_low = name.casefold()
            candidates = [m for m in guild.members if (m.name or "").casefold() == name_low or (m.display_name or "").casefold() == name_low]
            if len(candidates) == 1:
                return candidates[0]
        # 3.1 user_id из icon_url
        try:
            icon_url = getattr(em.author, "icon_url", None) or getattr(em.author, "icon", None)
            icon_url = str(icon_url) if icon_url else ""
            m2 = re.search(r"/avatars/(\d+)/", icon_url)
            if m2:
                uid = int(m2.group(1))
                mem = guild.get_member(uid)
                if mem:
                    return mem
        except Exception:
            pass

    # 4) Fallback для Server Monitoring: "Server bumped by ..."
    #    Сначала смотрим, есть ли вообще триггерная фраза (на всякий случай)
    if message.author.id == SERVER_MONITORING_BOT_ID and re.search(r"server\s+bumped\s+by\s+", combined_text, flags=re.I):
        # Пытаемся выцепить либо <@id>, либо @ник после фразы
        m = re.search(r"server\s+bumped\s+by\s+(<@!?\d+>|@?[^\s\n]+)", combined_text, flags=re.I)
        if m:
            token = m.group(1).strip()
            # Если это mention — уже обработали бы выше, но на всякий случай:
            m_id = re.search(r"<@!?(\d+)>", token)
            if m_id:
                uid = int(m_id.group(1))
                mem = guild.get_member(uid)
                if mem:
                    return mem
            # Иначе пробуем как ник
            name = token.lstrip("@").strip()
            if name:
                # Сначала точное совпадение
                for member in guild.members:
                    if member.name == name or member.display_name == name:
                        return member
                # Потом регистронезависимое
                name_low = name.casefold()
                candidates = [memb for memb in guild.members if (memb.name or "").casefold() == name_low or (memb.display_name or "").casefold() == name_low]
                if len(candidates) == 1:
                    return candidates[0]

    return None

# ЗАМЕНИТЬ целиком функцию
def _is_probably_success_bump_message(message: disnake.Message) -> bool:
    """
    Проверяет, что сообщение — успех бампа для поддерживаемых ботов.

    Bump Reminder:
      - "Запущенная команда: /bump" ИЛИ присутствует "Время реакции"
    Server Monitoring:
      - содержит "Server bumped by"
    """
    text = (message.content or "") + "\n" + _extract_text_from_embeds(message.embeds or [])
    tl = text.lower()

    if message.author.id == BUMP_REMINDER_BOT_ID:
        return ("запущенная команда" in tl and "/bump" in tl) or ("время реакции" in tl)

    if message.author.id == SERVER_MONITORING_BOT_ID:
        return "server bumped by" in tl

    return False

def _build_award_embed(guild: disnake.Guild, member: disnake.Member, amount: int) -> disnake.Embed:
    e = disnake.Embed(
        title="Награда начислена:",
        color=disnake.Color.green(),
        description=f"{member.mention}\nСумма награды: {format_number(amount)} {MONEY_EMOJI}"
    )
    e.set_author(name=member.display_name, icon_url=member.display_avatar.url)
    e.set_footer(text=guild.name, icon_url=getattr(guild.icon, "url", None))
    return e

@bot.listen("on_message")
async def bump_reward_listener(message: disnake.Message):
    """
    Слушаем сообщения от Bump Reminder и начисляем награду, если:
      - включена настройка
      - сумма > 0
      - это сообщение похоже на успешный бамп
      - ещё не награждали по данному message.id
    """
    try:
        if not message.guild:
            return
        if message.author.id not in SUPPORTED_BUMP_BOT_IDS:
            return
        enabled, amount = db_get_bump_settings(message.guild.id)
        if not enabled or amount <= 0:
            return
        if not message.embeds:
            return
        if not _is_probably_success_bump_message(message):
            return

        member = _try_extract_user_from_bump_message(message)
        if not member:
            # Не удалось однозначно определить — не начисляем, чтобы не ошибиться.
            return

        # Идемпотентность по message_id
        if not db_mark_bump_awarded(message.guild.id, message.id, member.id):
            return  # уже обработано

        # Начисление
        update_balance(message.guild.id, member.id, amount)

        # Сообщение о начислении
        await message.channel.send(embed=_build_award_embed(message.guild, member, amount))

    except Exception as e:
        # Не ломаем основной поток бота
        # print(f"[bump_reward_listener] error: {e}")
        pass
# ========== /BUMP REWARD INTEGRATION ==========

# ====================== Команда !collect (сбор дохода с ролей) ======================

@bot.command(name="collect", aliases=["Collect", "COLLECT", "Доход", "доход", "ДОХОД"])
async def collect_cmd(ctx: commands.Context):
    """
    Собрать доход с доходных ролей:
      !collect
    """
    if not await ensure_allowed_ctx(ctx, ALLOWED_COLLECT):
        return
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    member: disnake.Member = ctx.author
    now = int(time.time())

    incomes = db_get_role_incomes(ctx.guild.id)
    if not incomes:
        return await ctx.send(embed=error_embed("Нет доходных ролей", "На сервере ещё не настроены доходные роли."))

    member_role_ids = {r.id for r in member.roles}
    eligible = [ri for ri in incomes if ri["role_id"] in member_role_ids]

    if not eligible:
        return await ctx.send(embed=error_embed("Нет подходящих ролей", "У вас нет ролей, дающих доход."))

    ready: list[dict] = []
    cooling: list[tuple[dict, int]] = []  # (ri, remaining_sec)

    for ri in eligible:
        last = db_get_ri_last_ts(ctx.guild.id, ri["role_id"], member.id)
        cd = int(ri["cooldown_seconds"] or 0)
        if not last or last + cd <= now:
            ready.append(ri)
        else:
            remaining = (last + cd) - now
            cooling.append((ri, remaining))

    if not ready:
        # Показать эмбед с таймерами
        e = disnake.Embed(
            title=":bulb: Доступные роли:",
            color=disnake.Color.orange()
        )
        e.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        lines = []
        for ri, rem in sorted(cooling, key=lambda x: x[1]):
            lines.append(f"<@&{ri['role_id']}> через {format_seconds(rem)}")
        e.add_field(name=":clock1: Ожидайте доход:", value="\n".join(lines) if lines else "—", inline=False)
        server_icon = getattr(ctx.guild.icon, "url", None)
        footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        e.set_footer(text=f"{ctx.guild.name} • {footer_time}", icon_url=server_icon)
        return await ctx.send(embed=e)

    # Выдаём доход
    total_money = 0
    money_lines = []
    item_lines = []
    id2name = items_id_to_name_map(ctx.guild)

    for ri in ready:
        if ri["income_type"] == "money":
            amt = int(ri["money_amount"] or 0)
            if amt > 0:
                total_money += amt
                money_lines.append(f"<@&{ri['role_id']}> → {format_number(amt)} {MONEY_EMOJI} (cash)")
        else:
            # Предметы
            if not ri["items"]:
                continue
            sub_lines = []
            for it in ri["items"]:
                iid = int(it["item_id"])
                qty = int(it["qty"])
                if qty <= 0:
                    continue
                add_items_to_user(ctx.guild.id, member.id, iid, qty)
                sub_lines.append(f"{id2name.get(iid, f'ID {iid}')} {qty} (item)")
            if sub_lines:
                if len(sub_lines) == 1:
                    item_lines.append(f"<@&{ri['role_id']}> → {sub_lines[0]}")
                else:
                    item_lines.append(f"<@&{ri['role_id']}> →:\n" + "\n".join(f" {ln}" for ln in sub_lines))

        # зафиксировать кулдаун для этой роли
        db_set_ri_last_ts(ctx.guild.id, ri["role_id"], member.id, now)

    if total_money > 0:
        update_balance(ctx.guild.id, member.id, total_money)

    # Собираем эмбед результата
    e = disnake.Embed(
        title=":ballot_box_with_check: Доход с ролей получен!",
        color=disnake.Color.green()
    )
    e.set_author(name=member.display_name, icon_url=member.display_avatar.url)

    e.add_field(name=":moneybag: Денежный доход:", value="\n".join(money_lines) if money_lines else "—", inline=False)
    e.add_field(name=":pick: Доход ресурсов:", value="\n".join(item_lines) if item_lines else "—", inline=False)
    e.add_field(name=":bar_chart: Итоговый доход:",
    value=f"\n*{format_number(total_money)} {MONEY_EMOJI}*\n", inline=False)

    server_icon = getattr(ctx.guild.icon, "url", None)
    footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    e.set_footer(text=f"{ctx.guild.name} • {footer_time}", icon_url=server_icon)

    await ctx.send(embed=e)


@bot.event
async def on_command_error(ctx: commands.Context, error):
    # Подсказки по синтаксису: отсутствующие/неверные аргументы и т.п.
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument, commands.TooManyArguments, commands.UserInputError)):
        cmd_name = ctx.command.qualified_name if ctx.command else None
        if cmd_name:
            await ctx.send(embed=usage_embed(cmd_name))
            return

    if isinstance(error, commands.MissingPermissions):
        embed = disnake.Embed(
            title="Недостаточно прав",
            description="У вас нет прав для использования этой команды.",
            color=disnake.Color.red()
        )
        await ctx.send(embed=embed, delete_after=10)
        return

    if isinstance(error, commands.CheckFailure):
        cmd_name = ctx.command.qualified_name if ctx.command else "неизвестной команды"
        embed = disnake.Embed(
            title="Доступ запрещён",
            description=f"У вас нет доступа к использованию команды: `{cmd_name}`.",
            color=disnake.Color.red()
        )
        embed.set_footer(text="Обратитесь к администратору сервера для получения доступа.")
        await ctx.send(embed=embed, delete_after=12)
        return

    if isinstance(error, commands.CommandNotFound):
        return

    # Прочие ошибки — логируем в консоль
    print(f"Произошла ошибка в команде '{getattr(ctx.command, 'qualified_name', None)}': {error}")


if __name__ == "__main__":
    bot.run(TOKEN)
