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
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from datetime import datetime
from typing import Union, Optional

# --- КОНФИГУРАЦИЯ ---
from config import TOKEN

# Определяем "намерения" (Intents) для бота.
intents = disnake.Intents.all()

# Создаем экземпляр бота.
bot = commands.Bot(command_prefix="!", intents=intents)

# Эмодзи денег — можно заменить на свой
MONEY_EMOJI = "💶"
# --- КОНФИГ ВЕРХОМ ФАЙЛА (рядом с MONEY_EMOJI) ---
MONEY_EMOJI = "💶"
CURRENCY = "€"  # символ валюты под скрин
SHOW_BALANCE_FIELD = True  # выключите, если нужно прям 1-в-1 как на скрине без поля "Баланс"

# --- БАЗА ДАННЫХ (SQLite) ---
DEFAULT_SELL_PERCENT = 0.5  # по умолчанию предметы продаются за 50% от цены
SHOP_ITEMS_PER_PAGE = 5     # предметов на страницу в меню !shop
SHOP_VIEW_TIMEOUT = 120     # время жизни кнопок пагинации (сек)


# Функция для получения пути к БД
def get_db_path():
    return os.path.join(os.path.dirname(__file__), 'economy.db')

# Функция для инициализации/миграции базы данных
def setup_database():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    # Таблица для балансов (без изменений)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            guild_id INTEGER,
            user_id INTEGER,
            balance INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    # Таблица для инвентаря (если у вас уже есть — оставьте как было)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventories (
            guild_id INTEGER,
            user_id INTEGER,
            item_id INTEGER,
            quantity INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, item_id)
        )
    """)

    # Таблица для разрешений (миграция под пер-командные правила)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permissions (
            guild_id INTEGER,
            target_id INTEGER,
            target_type TEXT,
            permission_type TEXT
        )
    """)

    # Добавляем столбец command_name при миграции, если его нет
    cursor.execute("PRAGMA table_info(permissions)")
    cols = [row[1] for row in cursor.fetchall()]
    if "command_name" not in cols:
        cursor.execute("ALTER TABLE permissions ADD COLUMN command_name TEXT DEFAULT '*'")

    # Уникальный индекс на (guild_id, target_id, command_name) для upsert по конкретной команде
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_permissions_unique
        ON permissions (guild_id, target_id, command_name)
    """)

    # Таблица настроек работы (на сервер)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_settings (
            guild_id INTEGER PRIMARY KEY,
            min_income INTEGER NOT NULL,
            max_income INTEGER NOT NULL,
            cooldown_seconds INTEGER NOT NULL
        )
    """)

    # Таблица кулдаунов работы (на пользователя)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_cooldowns (
            guild_id INTEGER,
            user_id INTEGER,
            last_ts INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    conn.commit()
    conn.close()


# --- Функции для работы с балансом (без изменений) ---

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


# --- Таблицы магазина и миграции под расширенные настройки ---

def setup_shop_tables():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()

    # Таблица предметов
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            name_lower TEXT NOT NULL,
            price INTEGER NOT NULL,           -- цена в валюте (если buy_price_type='currency')
            sell_price INTEGER,               -- ручная цена продажи (если None и selling разрешён — берём %)
            description TEXT DEFAULT '',
            -- новые поля
            buy_price_type TEXT DEFAULT 'currency',  -- 'currency' | 'items'
            cost_items TEXT,                  -- JSON: [{"item_id": int, "qty": int}, ...]
            is_listed INTEGER DEFAULT 1,      -- 1 - продаётся в магазине; 0 - нет
            stock_total INTEGER,              -- общий максимум (NULL = бесконечно)
            restock_per_day INTEGER DEFAULT 0,-- авто-пополнение в день
            per_user_daily_limit INTEGER DEFAULT 0, -- 0 = без лимита
            roles_required_buy TEXT,          -- CSV IDs ролей (или NULL)
            roles_required_sell TEXT,         -- CSV IDs
            roles_granted_on_buy TEXT,        -- CSV IDs
            roles_removed_on_buy TEXT,        -- CSV IDs
            disallow_sell INTEGER DEFAULT 0,  -- 1 = нельзя продавать системе (!sell)
            UNIQUE(guild_id, name_lower)
        )
    """)

    # Миграции существующей таблицы
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

    # Таблица текущего склада по предмету (для ограничений/автопополнения)
    c.execute("""
        CREATE TABLE IF NOT EXISTS item_shop_state (
            guild_id INTEGER,
            item_id INTEGER,
            current_stock INTEGER,
            last_restock_ymd TEXT,
            PRIMARY KEY (guild_id, item_id)
        )
    """)

    # Таблица дневных лимитов на пользователя
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

    # Заполнение name_lower для старых строк
    c.execute("UPDATE items SET name_lower = lower(name) WHERE name_lower IS NULL")

    conn.commit()
    conn.close()


# Отдельный listener, чтобы не менять ваш on_ready
@bot.listen("on_ready")
async def _shop_on_ready():
    setup_shop_tables()
    print("Таблицы магазина готовы.")


# --- Утилиты БД для магазина ---

def _item_row_to_dict(row) -> Optional[dict]:
    if not row:
        return None
    return {
        "id": row[0],
        "guild_id": row[1],
        "name": row[2],
        "name_lower": row[3],
        "price": int(row[4]),
        "sell_price": None if row[5] is None else int(row[5]),
        "description": row[6] or "",
        "buy_price_type": row[7] or "currency",
        "cost_items": json.loads(row[8]) if row[8] else [],
        "is_listed": int(row[9] or 0),
        "stock_total": None if row[10] is None else int(row[10]),
        "restock_per_day": int(row[11] or 0),
        "per_user_daily_limit": int(row[12] or 0),
        "roles_required_buy": [int(x) for x in (row[13] or "").split(",") if x.strip().isdigit()],
        "roles_required_sell": [int(x) for x in (row[14] or "").split(",") if x.strip().isdigit()],
        "roles_granted_on_buy": [int(x) for x in (row[15] or "").split(",") if x.strip().isdigit()],
        "roles_removed_on_buy": [int(x) for x in (row[16] or "").split(",") if x.strip().isdigit()],
        "disallow_sell": int(row[17] or 0)
    }

def get_item_by_name(guild_id: int, name: str) -> Optional[dict]:
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute("""
        SELECT
            id, guild_id, name, name_lower, price, sell_price, description,
            buy_price_type, cost_items, is_listed, stock_total, restock_per_day,
            per_user_daily_limit, roles_required_buy, roles_required_sell,
            roles_granted_on_buy, roles_removed_on_buy, disallow_sell
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
            roles_granted_on_buy, roles_removed_on_buy, disallow_sell
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
    # Проверим текущее количество
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

def format_price(n: int) -> str:
    return f"{format_number(n)} {MONEY_EMOJI}"

def effective_sell_price(item: dict) -> int:
    if item.get("sell_price") is not None:
        return int(item["sell_price"])
    return max(0, int(round(item["price"] * DEFAULT_SELL_PERCENT)))


# --- Доп. утилиты: склад/лимиты/роли/ошибки/формат ---

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

def csv_from_ids(ids: list[int]) -> str:
    return ",".join(str(x) for x in sorted(set(ids)))

def has_any_role(user: disnake.Member, role_ids: list[int]) -> bool:
    if not role_ids:
        return True
    user_ids = {r.id for r in user.roles}
    return any(rid in user_ids for rid in role_ids)

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
        # Упоминание <@&123>
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            try:
                rid = int(digits)
                if guild.get_role(rid):
                    ids.add(rid)
                    continue
            except ValueError:
                pass
        # Имя роли — попытка найти точное совпадение (не рекомендовано)
        role = disnake.utils.get(guild.roles, name=token)
        if role:
            ids.add(role.id)
    return sorted(ids)


# --- Пагинация магазина ---

class ShopView(disnake.ui.View):
    def __init__(self, ctx: commands.Context, items: list[dict]):
        super().__init__(timeout=SHOP_VIEW_TIMEOUT)
        self.ctx = ctx
        self.items = list(items)
        self.page = 0
        self.max_page = max(0, (len(self.items) - 1) // SHOP_ITEMS_PER_PAGE)
        self.author_id = ctx.author.id

        # Режимы сортировки
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
            # Не-валютные в конец, затем по цене, затем по имени и id для стабильности
            self.items.sort(key=lambda it: (not self._is_currency(it), self._price_val(it), (it.get("name") or "").casefold(), int(it.get("id") or 0)))
        elif mode == "price_desc":
            # Не-валютные в конец, затем по цене убыв., затем по имени и id
            self.items.sort(key=lambda it: (not self._is_currency(it), -self._price_val(it), (it.get("name") or "").casefold(), int(it.get("id") or 0)))
        elif mode == "name":
            self.items.sort(key=lambda it: ((it.get("name") or "").casefold(), int(it.get("id") or 0)))
        elif mode == "id":
            self.items.sort(key=lambda it: int(it.get("id") or 0))
        # Пересчёт страниц при изменении порядка (кол-во не меняется, но на всякий случай)
        self.max_page = max(0, (len(self.items) - 1) // SHOP_ITEMS_PER_PAGE)
        # Обнулить страницу при смене сортировки (сделаем это в обработчике)

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Эта панель доступна только инициатору.", ephemeral=True)
            return False
        return True

    def _sync_buttons_state(self):
        # Отключаем кнопки на краях
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                if child.custom_id == "shop_prev":
                    child.disabled = self.page <= 0
                elif child.custom_id == "shop_next":
                    child.disabled = self.page >= self.max_page

    def _update_sort_label(self):
        # Найти кнопку сортировки и обновить подпись
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

        header = [
            "🔸 Покупка: `!buy [кол-во] <название>`",
            "🔸 Инфо о предмете: `!item-info <название>`",
        ]

        page_items = self._page_slice()

        # Карта id -> имя для вывода стоимости ресурсами
        all_items = list_items_db(self.ctx.guild.id)
        id2name = {i["id"]: i["name"] for i in all_items}

        sections = []  # сюда будем класть законченные многострочные блоки по каждому предмету

        if not page_items:
            sections.append("Пока нет предметов в магазине.")
        else:
            start_idx = self.page * SHOP_ITEMS_PER_PAGE

            for i, it in enumerate(page_items, start=1):
                num = start_idx + i
                name = it.get("name", "Без названия")

                block = []  # строки одного предмета

                if it.get('buy_price_type') == 'currency':
                    price_str = format_price(it.get('price', 0))
                    block.append(f"**{name}** **—  {price_str}**")
                else:
                    block.append(f"**{name}** **— Цена ( В ресурсах ):**")
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
                            block.append(f"   • __{res_name} — {qty} шт.__")

                # Готовый многострочный блок предмета
                sections.append("\n".join(block))

        # Формирование описания эмбеда: шапка + пустая строка + блоки предметов через пустую строку
        parts = ["\n".join(header), "" if sections else "", "\n\n".join(sections)]
        embed.description = "\n".join([p for p in parts if p != ""]).rstrip()

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
        # Переключаем режим сортировки по кругу
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
        # По таймауту — выключить кнопки
        self.stop()
        try:
            for child in self.children:
                if isinstance(child, disnake.ui.Button):
                    child.disabled = True
            if hasattr(self, "message") and self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# --- КОМАНДЫ МАГАЗИНА ---

@bot.command(name="shop")
async def shop_cmd(ctx: commands.Context, page: int = 1):
    """Открыть меню магазина."""
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    all_items = list_items_db(ctx.guild.id)
    # Показываем только те, что продаются в магазине
    items = [it for it in all_items if it["is_listed"]]
    view = ShopView(ctx, items)
    if page > 0:
        view.page = min(max(0, page - 1), view.max_page)
        view._sync_buttons_state()
    embed = view._build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


# ==========================
# ===  МАСТЕР СОЗДАНИЯ   ===
# ==========================

@dataclass
class ItemDraft:
    name: str = ""
    description: str = ""
    sell_price_raw: str = "skip"   # "skip" | number
    disallow_sell: int = 0

    buy_price_type: str = "currency"  # 'currency' | 'items'
    price_currency: int = 0
    cost_items: list[dict] = field(default_factory=list)  # [{"item_id": int, "qty": int}]

    is_listed: int = 1
    stock_total_raw: str = "skip"  # "skip" | number
    restock_per_day: int = 0
    per_user_daily_limit: int = 0

    roles_required_buy: list[int] = field(default_factory=list)
    roles_required_sell: list[int] = field(default_factory=list)
    roles_granted_on_buy: list[int] = field(default_factory=list)
    roles_removed_on_buy: list[int] = field(default_factory=list)


# ==========================
# ===  ОБНОВЛЁННЫЙ UI   ===
# ==========================

class BasicInfoModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        components = [
            disnake.ui.TextInput(
                label="Название предмета",
                custom_id="name",
                style=disnake.TextInputStyle.short,
                max_length=64,
                required=True
            ),
            disnake.ui.TextInput(
                label="Цена продажи (!sell) — число или 'skip'",
                custom_id="sell_price",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 100 или skip"
            ),
            disnake.ui.TextInput(
                label="Описание предмета",
                custom_id="desc",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=False
            ),
        ]
        super().__init__(title="1️⃣ 📝 Основы предмета", components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        name = inter.text_values.get("name", "").strip()
        sell_raw = inter.text_values.get("sell_price", "").strip().lower()
        desc = inter.text_values.get("desc", "").strip()

        if not name:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Название не может быть пустым."), ephemeral=True)

        exists = get_item_by_name(inter.guild.id, name)
        if exists:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Предмет с таким именем уже существует."), ephemeral=True)

        disallow_sell = 0
        if sell_raw == "skip":
            disallow_sell = 1
        else:
            if not sell_raw.isdigit() or int(sell_raw) < 0:
                return await inter.response.send_message(embed=error_embed("Ошибка", "Цена продажи должна быть неотрицательным числом или 'skip'."), ephemeral=True)

        self.view_ref.draft.name = name
        self.view_ref.draft.description = desc
        self.view_ref.draft.sell_price_raw = sell_raw
        self.view_ref.draft.disallow_sell = disallow_sell

        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class CurrencyPriceModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        components = [
            disnake.ui.TextInput(
                label="Цена в валюте",
                custom_id="price",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 150"
            )
        ]
        super().__init__(title="2️⃣ 💳 Цена покупки — валюта", components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        raw = inter.text_values.get("price", "").strip()
        if not raw.isdigit() or int(raw) <= 0:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Цена должна быть положительным числом."), ephemeral=True)
        self.view_ref.draft.buy_price_type = "currency"
        self.view_ref.draft.price_currency = int(raw)
        self.view_ref.draft.cost_items.clear()
        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


# --- ФАЗЗИ ПОИСК И РЕЗОЛВЕР ПРЕДМЕТА ---

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

def _normalize(s: Optional[str]) -> str:
    if not s:
        return ""
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s.casefold()

def _score(query_n: str, name_n: str) -> float:
    if not query_n or not name_n:
        return 0.0
    ratio = SequenceMatcher(None, query_n, name_n).ratio()
    bonus = 0.0
    if query_n in name_n:
        bonus += 0.45
    if name_n.startswith(query_n):
        bonus += 0.25
    return min(1.0, ratio + bonus)

def fuzzy_candidates(items: list[dict], query: str, *, threshold: float = 0.55, limit: int = 50) -> list[tuple[dict, float]]:
    qn = _normalize(query)
    scored: list[tuple[dict, float]] = []
    for it in items:
        sn = _normalize(it.get("name") or "")
        sc = _score(qn, sn)
        if sc >= threshold:
            scored.append((it, sc))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]

def try_by_id(items: list[dict], token: str) -> Optional[dict]:
    token = (token or "").strip()
    if not token.isdigit():
        return None
    iid = int(token)
    for it in items:
        try:
            if int(it.get("id")) == iid:
                return it
        except Exception:
            continue
    return None

def _build_ambiguous_embed(query: str, matches: list[dict], page_size: int = 20) -> disnake.Embed:
    embed = disnake.Embed(
        title="Найдено несколько предметов",
        description=f"По запросу “{query}” найдено несколько совпадений.\nОтветьте цифрой из списка, чтобы выбрать нужный предмет.",
        color=disnake.Color.gold()
    )
    lines = []
    for idx, it in enumerate(matches[:page_size], start=1):
        nm = it.get("name", "Без названия")
        iid = it.get("id", "?")
        price_info = ""
        if it.get("buy_price_type") == "currency":
            price_info = f" — {format_price(it.get('price', 0))}"
        lines.append(f"{idx}. 📦 {nm} — ID: `{iid}`{price_info}")
    if len(matches) > page_size:
        lines.append(f"… и ещё {len(matches) - page_size} (уточните запрос).")
    embed.add_field(name="Варианты", value="\n".join(lines) if lines else "Пусто", inline=False)
    embed.set_footer(text="Введите номер (например: 1). Для отмены напишите: отмена")
    return embed

async def resolve_item_by_user_input(
    ctx: commands.Context,
    user_query: str,
    *,
    timeout: int = 60,
    attempts: int = 3,
) -> tuple[Optional[dict], Optional[str]]:
    """
    Универсальный резолвер предмета:
      - поддержка ID (число),
      - приблизительный поиск по названию,
      - если нескольких совпадений много — покажет эмбед и попросит выбрать номер.
    Возвращает (item, None) при успехе, (None, err_msg) при отмене/ошибке.
    """
    if not ctx.guild:
        return None, "Команда доступна только на сервере."
    all_items = list_items_db(ctx.guild.id)

    # 1) Пробуем по ID
    by_id = try_by_id(all_items, user_query)
    if by_id:
        return by_id, None

    # 2) Фаззи-кандидаты
    candidates = [it for it, _ in fuzzy_candidates(all_items, user_query)]
    if not candidates:
        return None, f"Не нашлось предметов, похожих на «{user_query}». Уточните запрос."

    # 3) Если один — отлично
    if len(candidates) == 1:
        return candidates[0], None

    # 4) Попросим выбрать
    embed = _build_ambiguous_embed(user_query, candidates)
    prompt = await ctx.send(embed=embed)

    def check(m: disnake.Message) -> bool:
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        left = attempts
        while left > 0:
            left -= 1
            try:
                reply: disnake.Message = await bot.wait_for("message", timeout=timeout, check=check)
            except asyncio.TimeoutError:
                return None, "Время ожидания ответа истекло."
            content = (reply.content or "").strip().lower()

            with contextlib.suppress(Exception):
                await reply.delete()

            if content in {"отмена", "cancel", "стоп", "нет"}:
                return None, "Отменено."

            if content.isdigit():
                idx = int(content)
                max_idx = min(20, len(candidates))
                if 1 <= idx <= max_idx:
                    return candidates[idx - 1], None

            if left > 0:
                await ctx.send(f"Введите число от 1 до {min(20, len(candidates))} или 'отмена'. Осталось попыток: {left}")
            else:
                return None, "Слишком много неверных попыток."
    finally:
        with contextlib.suppress(Exception):
            await prompt.delete()


class AddCostItemByNameModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        components = [
            disnake.ui.TextInput(
                label="Предмет (название или ID)",  # <= 45 символов
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

        # Быстрый ответ модалки, чтобы не истечь по времени
        if not qty_raw.isdigit() or int(qty_raw) <= 0:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Количество должно быть положительным числом."), ephemeral=True)

        await inter.response.send_message("Открыл выбор предмета в чате. Следуйте инструкции и введите номер в ответ.", ephemeral=True)

        async def _resolve_and_update():
            item, err = await resolve_item_by_user_input(self.view_ref.ctx, iname, timeout=60, attempts=3)
            if err or not item:
                with contextlib.suppress(Exception):
                    await self.view_ref.ctx.send(embed=error_embed("Выбор предмета", err or "Не удалось определить предмет."))
                return
            qty = int(qty_raw)

            # Запрет на использование самого создаваемого предмета как стоимости
            if item["name_lower"] == (self.view_ref.draft.name or "").lower():
                with contextlib.suppress(Exception):
                    await self.view_ref.ctx.send(embed=error_embed("Неверная стоимость", "Нельзя использовать текущий создаваемый предмет как цену."))
                return

            # Обновить/добавить
            found = False
            for r in self.view_ref.draft.cost_items:
                if r["item_id"] == item["id"]:
                    r["qty"] = qty
                    found = True
                    break
            if not found:
                self.view_ref.draft.cost_items.append({"item_id": item["id"], "qty": qty})

            # Обновим сообщение мастера
            try:
                if self.view_ref.message:
                    await self.view_ref.message.edit(embed=self.view_ref.build_embed(), view=self.view_ref)
            except Exception:
                pass

            with contextlib.suppress(Exception):
                await self.view_ref.ctx.send(f"Добавлено требование: {item['name']} × {qty}")

        asyncio.create_task(_resolve_and_update())


class ShopSettingsModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        components = [
            disnake.ui.TextInput(
                label="Продается в магазине? (да/нет)",
                custom_id="listed",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="да | нет"
            ),
            disnake.ui.TextInput(
                label="Общее количество (число или 'skip')",
                custom_id="stock",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 100 или skip"
            ),
            disnake.ui.TextInput(
                label="Автопополнение в день (число)",
                custom_id="restock",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 5"
            ),
            disnake.ui.TextInput(
                label="Лимит на пользователя в день (0 = без лим.)",
                custom_id="limit",
                style=disnake.TextInputStyle.short,
                required=True,
                placeholder="например: 2 или 0"
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

        if stock_raw != "skip" and (not stock_raw.isdigit() or int(stock_raw) <= 0):
            return await inter.response.send_message(embed=error_embed("Ошибка", "«Общее количество» должно быть положительным числом или 'skip'."), ephemeral=True)

        if not restock_raw.isdigit() or int(restock_raw) < 0:
            return await inter.response.send_message(embed=error_embed("Ошибка", "«Автопополнение» должно быть неотрицательным числом."), ephemeral=True)

        if not limit_raw.isdigit() or int(limit_raw) < 0:
            return await inter.response.send_message(embed=error_embed("Ошибка", "«Лимит в день» должен быть неотрицательным числом."), ephemeral=True)

        self.view_ref.draft.is_listed = is_listed
        self.view_ref.draft.stock_total_raw = stock_raw
        self.view_ref.draft.restock_per_day = int(restock_raw)
        self.view_ref.draft.per_user_daily_limit = int(limit_raw)

        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class RolesModal(disnake.ui.Modal):
    def __init__(self, view_ref):
        components = [
            disnake.ui.TextInput(
                label="Роли для покупки — ID/упоминания или 'skip'",
                custom_id="buy_req",
                style=disnake.TextInputStyle.paragraph,
                required=False
            ),
            disnake.ui.TextInput(
                label="Роли для продажи — ID/упоминания или 'skip'",
                custom_id="sell_req",
                style=disnake.TextInputStyle.paragraph,
                required=False
            ),
            disnake.ui.TextInput(
                label="Выдать роли при покупке — ID/упом. или 'skip'",
                custom_id="grant",
                style=disnake.TextInputStyle.paragraph,
                required=False
            ),
            disnake.ui.TextInput(
                label="Снять роли при покупке — ID/упом. или 'skip'",
                custom_id="remove",
                style=disnake.TextInputStyle.paragraph,
                required=False
            ),
        ]
        super().__init__(title="4️⃣ 🛡️ Права (роли)", components=components)
        self.view_ref = view_ref

    async def callback(self, inter: disnake.ModalInteraction):
        buy_ids = parse_role_ids_from_text(inter.guild, inter.text_values.get("buy_req", ""))
        sell_ids = parse_role_ids_from_text(inter.guild, inter.text_values.get("sell_req", ""))
        grant_ids = parse_role_ids_from_text(inter.guild, inter.text_values.get("grant", ""))
        remove_ids = parse_role_ids_from_text(inter.guild, inter.text_values.get("remove", ""))

        self.view_ref.draft.roles_required_buy = buy_ids
        self.view_ref.draft.roles_required_sell = sell_ids
        self.view_ref.draft.roles_granted_on_buy = grant_ids
        self.view_ref.draft.roles_removed_on_buy = remove_ids

        await inter.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class CreateItemWizard(disnake.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.draft = ItemDraft()
        self.message: Optional[disnake.Message] = None

    def build_embed(self) -> disnake.Embed:
        # Состояние шагов
        st1 = bool(self.draft.name)
        st2 = (self.draft.buy_price_type == "currency" and self.draft.price_currency > 0) or \
              (self.draft.buy_price_type == "items" and len(self.draft.cost_items) > 0)
        st3 = True  # настройки магазина заданы по умолчанию — считаем валидными
        st4 = True  # права опциональны

        # Красивые индикаторы прогресса
        def chip(ok: bool) -> str:
            return "✅" if ok else "▫️"

        progress_line = f"1️⃣ {chip(st1)}  •  2️⃣ {chip(st2)}  •  3️⃣ {chip(st3)}  •  4️⃣ {chip(st4)}"

        e = disnake.Embed(
            title="⚙️ Мастер создания предмета",
            description=(
                "╭────────────────────────────╮\n"
                f"   Прогресс: {progress_line}\n"
                "╰────────────────────────────╯"
            ),
            color=disnake.Color.blurple()
        )
        e.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)

        # Продажа системе
        if self.draft.disallow_sell:
            sell_info = "🔒 Запрещена"
        elif self.draft.sell_price_raw != "skip":
            sell_info = f"🏷️ Фикс.: {format_number(int(self.draft.sell_price_raw))} {MONEY_EMOJI}"
        else:
            sell_info = "ℹ️ По умолчанию"

        # Покупка (цена)
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

        # Магазин
        listed = "🟢 Да" if self.draft.is_listed else "🔴 Нет"
        stock_text = self.draft.stock_total_raw
        stock_text = "∞ (без огранич.)" if stock_text == "skip" else stock_text

        # Поле 1 — Основы
        e.add_field(
            name="1️⃣ 📝 Основы",
            value=(
                f"• Название: **{self.draft.name or '—'}**\n"
                f"• Описание: {self.draft.description or '—'}\n"
                f"• Продажа системе: {sell_info}"
            ),
            inline=False
        )

        # Поле 2 — Покупка
        e.add_field(
            name="2️⃣ 🛒 Покупка (!buy)",
            value=(
                f"• Тип цены: {'💳 Валюта' if self.draft.buy_price_type=='currency' else '🧱 Предметы'}\n"
                f"• {cost_desc}"
            ),
            inline=False
        )

        # Поле 3 — Магазин
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

        # Поле 4 — Права
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

        e.add_field(
            name="ℹ️ Подсказки",
            value=(
                "• Нажмите кнопки ниже, чтобы заполнить шаги.\n"
                "• Выберите тип цены в селекте, затем задайте стоимость.\n"
                "• Готово? Нажмите «💾 Сохранить»."
            ),
            inline=False
        )
        e.set_footer(text="Стильный мастер: аккуратно заполняйте по шагам ✨")
        return e

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        if inter.user.id != self.author_id:
            await inter.response.send_message("Эта панель доступна только создателю.", ephemeral=True)
            return False
        return True

    # Ряд 0 — 5 кнопок шагов (только меняем подписи/эмодзи, id и логика прежние)
    @disnake.ui.button(label="📝 О предмете", style=disnake.ButtonStyle.primary, custom_id="step_basic", row=0)
    async def _open_basic(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(BasicInfoModal(self))

    @disnake.ui.button(label="💳 Цена покупки", style=disnake.ButtonStyle.primary, custom_id="step_price", row=0)
    async def _open_price(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        if self.draft.buy_price_type == "currency":
            await inter.response.send_modal(CurrencyPriceModal(self))
        else:
            await inter.response.send_message(
                "Выбран тип цены «Предметы». Нажмите «➕ Добавить требуемый предмет», чтобы задать стоимость.",
                ephemeral=True
            )

    @disnake.ui.button(label="🏪 Магазин", style=disnake.ButtonStyle.primary, custom_id="step_shop", row=0)
    async def _open_shop(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(ShopSettingsModal(self))

    @disnake.ui.button(label="🛡️ Права", style=disnake.ButtonStyle.primary, custom_id="step_roles", row=0)
    async def _open_roles(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(RolesModal(self))

    @disnake.ui.button(label="💾 Сохранить", style=disnake.ButtonStyle.success, custom_id="save_item", row=0)
    async def _save_item(self, btn: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Валидация — без изменений
        if not self.draft.name:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Заполните «Название» на шаге 1."), ephemeral=True)
        if self.draft.buy_price_type == "currency":
            if self.draft.price_currency <= 0:
                return await inter.response.send_message(embed=error_embed("Ошибка", "Укажите положительную цену в валюте (шаг 2)."), ephemeral=True)
        else:
            if not self.draft.cost_items:
                return await inter.response.send_message(embed=error_embed("Ошибка", "Добавьте хотя бы один предмет-стоимость (шаг 2)."), ephemeral=True)

        if get_item_by_name(inter.guild.id, self.draft.name):
            return await inter.response.send_message(embed=error_embed("Ошибка", "Предмет с таким именем уже существует."), ephemeral=True)

        price = self.draft.price_currency if self.draft.buy_price_type == "currency" else 0
        sell_price_val = None
        if self.draft.disallow_sell == 0 and self.draft.sell_price_raw != "skip":
            sell_price_val = int(self.draft.sell_price_raw)

        stock_total_val = None if self.draft.stock_total_raw == "skip" else int(self.draft.stock_total_raw)

        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO items (
                    guild_id, name, name_lower, price, sell_price, description,
                    buy_price_type, cost_items, is_listed, stock_total, restock_per_day,
                    per_user_daily_limit, roles_required_buy, roles_required_sell,
                    roles_granted_on_buy, roles_removed_on_buy, disallow_sell
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inter.guild.id, self.draft.name, self.draft.name.lower(), price, sell_price_val, self.draft.description,
                self.draft.buy_price_type, json.dumps(self.draft.cost_items) if self.draft.cost_items else None,
                self.draft.is_listed, stock_total_val, self.draft.restock_per_day, self.draft.per_user_daily_limit,
                csv_from_ids(self.draft.roles_required_buy) or None,
                csv_from_ids(self.draft.roles_required_sell) or None,
                csv_from_ids(self.draft.roles_granted_on_buy) or None,
                csv_from_ids(self.draft.roles_removed_on_buy) or None,
                self.draft.disallow_sell
            ))
            conn.commit()
            # Инициализация склада — как было
            c.execute("SELECT id, stock_total FROM items WHERE guild_id = ? AND name_lower = ?", (inter.guild.id, self.draft.name.lower()))
            row = c.fetchone()
            if row:
                item_id, stock_total = int(row[0]), None if row[1] is None else int(row[1])
                c.execute("""
                    INSERT OR IGNORE INTO item_shop_state (guild_id, item_id, current_stock, last_restock_ymd)
                    VALUES (?, ?, ?, ?)
                """, (inter.guild.id, item_id, stock_total, ymd_utc()))
                conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return await inter.response.send_message(embed=error_embed("Ошибка", "Предмет с таким именем уже существует."), ephemeral=True)
        finally:
            conn.close()

        done = disnake.Embed(
            title="✅ Предмет создан",
            description=(
                "╭────────────────────────────╮\n"
                f"   «{self.draft.name}» успешно сохранён!\n"
                "╰────────────────────────────╯"
            ),
            color=disnake.Color.green()
        )
        done.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)
        await inter.response.edit_message(embed=done, view=None)

    # Ряд 1 — выбор типа цены с аккуратным плейсхолдером и эмодзи
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
            await inter.response.send_modal(CurrencyPriceModal(self))
        else:
            await inter.response.edit_message(embed=self.build_embed(), view=self)

    # Ряд 2 — кнопки управления стоимостью «предметами»
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


@bot.command(name="create-item")
@commands.has_permissions(administrator=True)
async def create_item_cmd(ctx: commands.Context):
    """Запустить мастер создания предмета."""
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    view = CreateItemWizard(ctx)
    embed = view.build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


def _parse_amount_and_name(raw: str) -> tuple[int, str] | tuple[None, None]:
    """
    Парсит строку вида:
      - "3 Меч" -> (3, "Меч")
      - "Меч"   -> (1, "Меч")
    """
    s = (raw or "").strip()
    if not s:
        return None, None
    parts = s.split(maxsplit=1)
    if parts[0].isdigit():
        amt = int(parts[0])
        name = parts[1].strip() if len(parts) > 1 else ""
        return amt, name
    else:
        return 1, s

# --- ПОКУПКА / ПРОДАЖА ---

@bot.command(name="buy")
async def buy_cmd(ctx: commands.Context, *, raw: str):
    """
    Купить предмет: !buy [кол-во] <название|ID>
    Можно валютой или другими предметами (если так настроено).
    """
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    amount, name = _parse_amount_and_name(raw)
    if amount is None or not name:
        return await ctx.send(embed=error_embed("Неверное использование", "Использование: `!buy [кол-во] <название|ID>`"))
    if amount <= 0:
        return await ctx.send(embed=error_embed("Неверное количество", "Количество должно быть положительным."))

    item, err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if err:
        return await ctx.send(embed=error_embed("Выбор предмета", err))

    # Проверка листинга
    if not item["is_listed"]:
        return await ctx.send(embed=error_embed("Покупка недоступна", "Этот предмет не продаётся в магазине."))

    # Проверка ролей для покупки
    if not has_any_role(ctx.author, item["roles_required_buy"]):
        return await ctx.send(embed=error_embed("Нет доступа", "У вас нет требуемых ролей для покупки этого предмета."))

    # Склад/лимиты
    ensure_item_state(ctx.guild.id, item)
    stock = get_current_stock(ctx.guild.id, item["id"])
    if stock is not None and stock < amount:
        return await ctx.send(embed=error_embed("Недостаточно на складе", f"Доступно только {stock} шт."))

    # Лимит на пользователя в день
    if item["per_user_daily_limit"] > 0:
        used = get_user_daily_used(ctx.guild.id, item["id"], ctx.author.id)
        remain = item["per_user_daily_limit"] - used
        if remain <= 0 or amount > remain:
            return await ctx.send(embed=error_embed("Превышен дневной лимит", f"Доступно к покупке сегодня: {max(remain,0)} шт."))

    total_cost_money = 0
    need_items = []  # [{"item_id":, "qty":}]

    if item["buy_price_type"] == "currency":
        total_cost_money = item["price"] * amount
        bal = get_balance(ctx.guild.id, ctx.author.id)
        if bal < total_cost_money:
            return await ctx.send(embed=error_embed("Недостаточно средств", f"Нужно {format_price(total_cost_money)}, у вас {format_number(bal)} {MONEY_EMOJI}."))
    else:
        # Предметы: умножаем требования на amount
        for r in item["cost_items"]:
            need_items.append({"item_id": int(r["item_id"]), "qty": int(r["qty"]) * amount})
        # Проверим наличие у пользователя
        lacking = []
        all_items_map = {it["id"]: it for it in list_items_db(ctx.guild.id)}
        for r in need_items:
            have = get_user_item_qty(ctx.guild.id, ctx.author.id, r["item_id"])
            if have < r["qty"]:
                lacking.append(f"{all_items_map.get(r['item_id'], {'name': 'ID '+str(r['item_id'])})['name']} × {r['qty']} (у вас {have})")
        if lacking:
            return await ctx.send(embed=error_embed("Не хватает предметов для обмена", "Недостает:\n- " + "\n- ".join(lacking)))

    # Списание оплаты
    if total_cost_money > 0:
        update_balance(ctx.guild.id, ctx.author.id, -total_cost_money)
    if need_items:
        for r in need_items:
            ok = remove_items_from_user(ctx.guild.id, ctx.author.id, r["item_id"], r["qty"])
            if not ok:
                return await ctx.send(embed=error_embed("Ошибка", "Не удалось списать требуемые предметы. Попробуйте снова."))

    # Выдача предмета
    add_items_to_user(ctx.guild.id, ctx.author.id, item["id"], amount)

    # Обновление склада/лимита
    if stock is not None:
        change_stock(ctx.guild.id, item["id"], -amount)
    if item["per_user_daily_limit"] > 0:
        add_user_daily_used(ctx.guild.id, item["id"], ctx.author.id, amount)

    # Роли при покупке
    # Снятие ролей
    if item["roles_removed_on_buy"]:
        roles_to_remove = [ctx.guild.get_role(r) for r in item["roles_removed_on_buy"] if ctx.guild.get_role(r)]
        if roles_to_remove:
            try:
                await ctx.author.remove_roles(*roles_to_remove, reason=f"Покупка предмета: {item['name']}")
            except Exception:
                pass
    # Выдача ролей
    if item["roles_granted_on_buy"]:
        roles_to_add = [ctx.guild.get_role(r) for r in item["roles_granted_on_buy"] if ctx.guild.get_role(r)]
        if roles_to_add:
            try:
                await ctx.author.add_roles(*roles_to_add, reason=f"Покупка предмета: {item['name']}")
            except Exception:
                pass

    new_bal = get_balance(ctx.guild.id, ctx.author.id)
    desc = f"Вы купили {amount}× «{item['name']}»."
    if total_cost_money > 0:
        desc += f"\nСписано: {format_price(total_cost_money)}. Баланс: {format_number(new_bal)} {MONEY_EMOJI}"
    elif need_items:
        desc += f"\nОплачено предметами."
    await ctx.send(embed=disnake.Embed(title="Покупка успешна", description=desc, color=disnake.Color.green()))


@bot.command(name="sell")
async def sell_cmd(ctx: commands.Context, *, raw: str):
    """
    Продать предмет системе: !sell [кол-во] <название|ID>
    Если у предмета «skip» — продажа запрещена.
    """
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    amount, name = _parse_amount_and_name(raw)
    if amount is None or not name:
        return await ctx.send(embed=error_embed("Неверное использование", "Использование: `!sell [кол-во] <название|ID>`"))
    if amount <= 0:
        return await ctx.send(embed=error_embed("Неверное количество", "Количество должно быть положительным."))

    item, err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if err:
        return await ctx.send(embed=error_embed("Выбор предмета", err))

    # Роли для продажи
    if not has_any_role(ctx.author, item["roles_required_sell"]):
        return await ctx.send(embed=error_embed("Нет доступа", "У вас нет требуемых ролей для продажи этого предмета."))

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


@bot.command(name="item-info", aliases=["iteminfo", "ii"])
async def item_info_cmd(ctx: commands.Context, *, name: str):
    """Информация о предмете: !iteminfo <название|ID>"""
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    item, err = await resolve_item_by_user_input(ctx, name, timeout=60, attempts=3)
    if err:
        return await ctx.send(embed=error_embed("Выбор предмета", err))

    # Актуализируем состояние склада и получим данные игрока
    ensure_item_state(ctx.guild.id, item)
    stock_now = get_current_stock(ctx.guild.id, item["id"])
    user_qty = get_user_item_qty(ctx.guild.id, ctx.author.id, item["id"])
    balance = get_balance(ctx.guild.id, ctx.author.id)

    # Карта ID -> имя для красивого вывода стоимости "предметами"
    all_items = list_items_db(ctx.guild.id)
    id2name = {i["id"]: i["name"] for i in all_items}

    # Базовый эмбед
    embed = disnake.Embed(
        title=f"📦 {item['name']}",
        color=disnake.Color.from_rgb(88, 101, 242),
        description=(item["description"] or "Без описания.").strip()[:600]
    )
    embed.set_author(name=ctx.guild.name, icon_url=getattr(ctx.guild.icon, "url", None))
    embed.set_thumbnail(url=ctx.author.display_avatar.url)

    # Цена покупки
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

    # Продажа системе
    if item["disallow_sell"]:
        embed.add_field(name="🛑 Продажа системе", value="Запрещена", inline=True)
    else:
        embed.add_field(name="🏷️ Цена продажи", value=f"**{format_price(effective_sell_price(item))}**", inline=True)

    # Наличие и листинг
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

    # Лимиты на покупку
    per_user = item["per_user_daily_limit"]
    embed.add_field(
        name="⏱️ Лимиты",
        value=f"На пользователя в день: **{per_user if per_user else 'без лимита'}**",
        inline=True
    )

    # Права и роли
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

    # Персональный блок игрока
    embed.add_field(
        name="👤 Ваши данные",
        value=f"Баланс: **{format_number(balance)} {MONEY_EMOJI}**\nВ инвентаре: **{user_qty} шт.**",
        inline=False
    )

    embed.set_footer(text=f"ID: {item['id']} • Купите: !buy [кол-во] {item['name']}")
    await ctx.send(embed=embed)


# ==========================
# ===     ИНВЕНТАРЬ      ===
# ==========================

INV_ITEMS_PER_PAGE = 5
INV_VIEW_TIMEOUT = 120  # сек для кнопок

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
    def __init__(self, ctx: commands.Context, items: list[dict]):
        super().__init__(timeout=INV_VIEW_TIMEOUT)
        self.ctx = ctx
        self.items = items
        self.page = 0
        self.max_page = max(0, (len(items) - 1) // INV_ITEMS_PER_PAGE)
        self.author_id = ctx.author.id
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
        embed.set_author(
            name=self.ctx.author.display_name,
            icon_url=self.ctx.author.display_avatar.url
        )
        header_lines = [
            "🔸 Используйте предмет: `!use <название|ID> [кол-во]`",
            ""
        ]
        page_items = self._page_slice()
        lines = []
        if not page_items:
            lines.append("Инвентарь пуст.")
        else:
            for it in page_items:
                lines.append(f"**{it['name']}** — **{it['quantity']} шт.**")
                desc = (it['description'] or "").strip() or "Без описания."
                if len(desc) > 200:
                    desc = desc[:197] + "..."
                lines.append(desc)

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


@bot.command(name="inv", aliases=["inventory", "инв"])
async def inv_cmd(ctx: commands.Context, page: int = 1):
    """Открыть меню инвентаря."""
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    items = list_user_inventory_db(ctx.guild.id, ctx.author.id)
    view = InventoryView(ctx, items)
    if page > 0:
        view.page = min(max(0, page - 1), view.max_page)
        view._sync_buttons_state()
    embed = view._build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


# ---- Команда использования предмета ----

def _parse_name_then_optional_amount(raw: str) -> tuple[Optional[str], Optional[int]]:
    """
    Парсит строку: '<название|ID> [кол-во]'.
    Если последний токен — число, это количество, иначе количество=1.
    """
    s = (raw or "").strip()
    if not s:
        return None, None
    name = s
    amount = 1
    if " " in s:
        left, right = s.rsplit(" ", 1)
        if right.isdigit():
            name = left.strip()
            amount = int(right)
    return (name if name else None), amount


@bot.command(name="use")
async def use_cmd(ctx: commands.Context, *, raw: str):
    """
    Использовать предмет из инвентаря:
      !use <название|ID> [кол-во]
    """
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    name, amount = _parse_name_then_optional_amount(raw)
    if not name:
        return await ctx.send(embed=disnake.Embed(
            title="Неверное использование",
            description="Использование: `!use <название|ID> [кол-во]`",
            color=disnake.Color.red()
        ))
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
        description=f"Вы использовали {amount} шт. «{item['name']}».",
        color=disnake.Color.green()
    )
    embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)


# ---- Админ-команды управления инвентарём ----

@bot.command(name="give-item")
@commands.has_permissions(administrator=True)
async def give_item_cmd(ctx: commands.Context, member: disnake.Member, *, raw: str):
    """
    Выдать предмет пользователю:
      !give-item @user <название|ID> [кол-во]
    """
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    name, amount = _parse_name_then_optional_amount(raw)
    if not name:
        return await ctx.send(embed=disnake.Embed(
            title="Неверное использование",
            description="Использование: `!give-item @пользователь <название|ID> [кол-во]`",
            color=disnake.Color.red()
        ))
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


@bot.command(name="take-item")
@commands.has_permissions(administrator=True)
async def take_item_cmd(ctx: commands.Context, member: disnake.Member, *, raw: str):
    """
    Забрать предмет у пользователя:
      !take-item @user <название|ID> [кол-во]
    """
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")

    name, amount = _parse_name_then_optional_amount(raw)
    if not name:
        return await ctx.send(embed=disnake.Embed(
            title="Неверное использование",
            description="Использование: `!take-item @пользователь <название|ID> [кол-во]`",
            color=disnake.Color.red()
        ))
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


# --- НОВЫЕ ФУНКЦИИ: для работы с разрешениями по КОМАНДАМ ---

def set_permission(guild_id: int, target_id: int, target_type: str, permission_type: str, command_name: str):
    """Добавляет или обновляет правило в БД для конкретной команды (или для всех — '*')."""
    command_name = command_name.lower()
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO permissions (guild_id, target_id, target_type, permission_type, command_name)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, target_id, command_name) DO UPDATE SET
            target_type = excluded.target_type,
            permission_type = excluded.permission_type
    """, (guild_id, target_id, target_type, permission_type, command_name))
    conn.commit()
    conn.close()

def remove_permission(guild_id: int, target_id: int, command_name: Optional[str] = None):
    """Удаляет правило: либо конкретной команды, либо все правила цели."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    if command_name is None:
        cursor.execute("DELETE FROM permissions WHERE guild_id = ? AND target_id = ?", (guild_id, target_id))
    else:
        cursor.execute("DELETE FROM permissions WHERE guild_id = ? AND target_id = ? AND command_name = ?",
                       (guild_id, target_id, command_name.lower()))
    conn.commit()
    conn.close()

def get_permissions_for_command(guild_id: int, command_name: str) -> dict:
    """Получает разрешения для конкретной команды с учетом глобальных ('*')."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT target_id, target_type, permission_type
        FROM permissions
        WHERE guild_id = ? AND (command_name = ? OR command_name = '*')
    """, (guild_id, command_name.lower()))

    perms = {
        'allow': {'users': set(), 'roles': set()},
        'deny': {'users': set(), 'roles': set()}
    }

    for target_id, target_type, permission_type in cursor.fetchall():
        if target_type == 'user':
            perms[permission_type]['users'].add(target_id)
        elif target_type == 'role':
            perms[permission_type]['roles'].add(target_id)

    conn.close()
    return perms

def get_all_permissions_grouped(guild_id: int) -> dict:
    """
    Возвращает все правила сервера, сгруппированные по command_name.
    Структура: { 'command_name': { 'allow': {'users': set(), 'roles': set()}, 'deny': {...} } }
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT target_id, target_type, permission_type, command_name
        FROM permissions WHERE guild_id = ?
        ORDER BY command_name
    """, (guild_id,))

    grouped = {}
    for target_id, target_type, permission_type, command_name in cursor.fetchall():
        if command_name not in grouped:
            grouped[command_name] = {
                'allow': {'users': set(), 'roles': set()},
                'deny': {'users': set(), 'roles': set()}
            }
        key = 'users' if target_type == 'user' else 'roles'
        grouped[command_name][permission_type][key].add(target_id)

    conn.close()
    return grouped


# --- Утилиты для парсинга названия команды ---

def normalize_command_name(raw: str, bot_obj: commands.Bot) -> Optional[str]:
    """
    Преобразует введенное имя в qualified_name команды или '*' для глобального правила.
    Возвращает None, если команда не найдена.
    """
    name = (raw or "").strip().lower()
    if name in ("*", "all", "все"):
        return "*"

    cmd = bot_obj.get_command(name)
    if cmd is None:
        return None
    return cmd.qualified_name.lower()


# --- Работа: настройки и кулдауны ---

DEFAULT_MIN_INCOME = 10
DEFAULT_MAX_INCOME = 50
DEFAULT_COOLDOWN = 3600  # 1 час

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


# --- ГЛОБАЛЬНАЯ ПРОВЕРКА РАЗРЕШЕНИЙ ---

@bot.check
async def has_command_permission(ctx: commands.Context):
    # Не проверяем личные сообщения
    if not ctx.guild:
        return True

    # Админы могут всё
    if ctx.author.guild_permissions.administrator:
        return True

    # Получаем правила для конкретной команды + глобальные
    command_name = ctx.command.qualified_name.lower()
    perms = get_permissions_for_command(ctx.guild.id, command_name)
    author_roles_ids = {role.id for role in ctx.author.roles}

    # 1) Deny имеет наивысший приоритет
    if ctx.author.id in perms['deny']['users']:
        return False
    if not perms['deny']['roles'].isdisjoint(author_roles_ids):
        return False

    # 2) Проверка allow
    has_any_allow_rules = bool(perms['allow']['users'] or perms['allow']['roles'])
    if not has_any_allow_rules:
        # Если allow-правил нет вообще (ни глобально, ни для команды) — разрешаем всем (кто не в deny)
        return True

    # Если allow-правила есть — доступ только тем, кто в allow
    if ctx.author.id in perms['allow']['users']:
        return True
    if not perms['allow']['roles'].isdisjoint(author_roles_ids):
        return True

    # Иначе — запрет
    return False


# --- КОМАНДЫ БОТА ---

@bot.event
async def on_ready():
    setup_database()
    print(f'Бот {bot.user} готов к работе!')
    print(f'Подключен к {len(bot.guilds)} серверам.')

# --- Команда Balance ---
@bot.command(name="balance", aliases=["bal"])
async def balance_prefix(ctx: commands.Context, user: disnake.Member = None):
    target_user = user or ctx.author
    balance = get_balance(ctx.guild.id, target_user.id)
    embed = disnake.Embed(
        title=f"Баланс {target_user.display_name}",
        description=f"На счету: **{format_number(balance)}** монет {MONEY_EMOJI}",
        color=disnake.Color.gold()
    )
    embed.set_thumbnail(url=target_user.display_avatar.url)
    await ctx.send(embed=embed)

# --- Команда Pay ---
@bot.command(name="pay")
async def pay_prefix(ctx: commands.Context, получатель: disnake.Member, сумма: int):
    if получатель.bot:
        await ctx.send("Вы не можете переводить деньги ботам!")
        return
    if получатель == ctx.author:
        await ctx.send("Вы не можете переводить деньги самому себе!")
        return
    if сумма <= 0:
        await ctx.send("Сумма перевода должна быть положительной!")
        return

    sender_balance = get_balance(ctx.guild.id, ctx.author.id)
    if sender_balance < сумма:
        await ctx.send(f"У вас недостаточно средств! Ваш баланс: {format_number(sender_balance)} {MONEY_EMOJI}")
        return

    update_balance(ctx.guild.id, ctx.author.id, -сумма)
    update_balance(ctx.guild.id, получатель.id, сумма)

    embed = disnake.Embed(
        title="Перевод выполнен",
        description=f"{ctx.author.mention} перевел **{format_number(сумма)}** монет {MONEY_EMOJI} пользователю {получатель.mention}!",
        color=disnake.Color.green()
    )
    await ctx.send(embed=embed)


# --- Новые команды: Работа ---

@bot.command(name="work")
async def work_cmd(ctx: commands.Context):
    # Настройки
    min_income, max_income, cooldown = get_work_settings(ctx.guild.id)

    # Проверка кулдауна
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
                # Важно: формируем строку без f-форматирования с ':R', чтобы исключить ошибки форматирования
                value="Доступна через <t:" + str(next_ts) + ":R>",
                inline=False
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            server_icon = getattr(ctx.guild.icon, "url", None)
            footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
            embed.set_footer(text=f"{ctx.guild.name} • {footer_time}", icon_url=server_icon)
            await ctx.send(embed=embed)
            return

    # Генерация заработка
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
        # Важно: формируем строку без f-форматирования с ':R', чтобы исключить ошибки форматирования
        value="Доступна через <t:" + str(next_ts) + ":R>",
        inline=False
    )
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    server_icon = getattr(ctx.guild.icon, "url", None)
    footer_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    embed.set_footer(text=f"{ctx.guild.name} • {footer_time}", icon_url=server_icon)

    await ctx.send(embed=embed)


# ==========================
# ===  UI: !set-work     ===
# ==========================
SET_WORK_VIEW_TIMEOUT = 240  # сек. жизни панели

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

    # 1) HH:MM:SS | MM:SS
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

    # 2) только цифры = секунды
    if s.isdigit():
        v = int(s)
        return v if v >= 0 else None

    # 3) токены с суффиксами
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
        if not raw.isdigit():
            return await inter.response.send_message(embed=error_embed("Неверный ввод", "Введите целое неотрицательное число."), ephemeral=True)
        val = int(raw)
        if not self._min0 and val <= 0:
            return await inter.response.send_message(embed=error_embed("Неверный ввод", "Значение должно быть положительным."), ephemeral=True)
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

        # Текущие значения из БД
        cur_min, cur_max, cur_cd = get_work_settings(ctx.guild.id)

        # Черновик (можно менять, пока не нажали Сохранить)
        self.min_income = cur_min
        self.max_income = cur_max
        self.cooldown = cur_cd

        # Оригинал (для сравнения)
        self._orig = (cur_min, cur_max, cur_cd)
        self.message: Optional[disnake.Message] = None

    # ---- helpers ----
    def _changed_chip(self) -> str:
        return " ✎" if (self.min_income, self.max_income, self.cooldown) != self._orig else ""

    def build_embed(self) -> disnake.Embed:
        # Красивая «рамка» и эмодзи
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

        # Основные параметры
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

        # Превью
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

        # Подсказки
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

    # ---- mutations with validation ----
    def apply_numeric(self, cid: str, value: int) -> tuple[bool, Optional[str]]:
        if value < 0:
            return False, "Значение не может быть отрицательным."
        if cid == "min_income":
            # если минимум > максимум — подвинем максимум вверх, чтобы сохранить инвариант
            self.min_income = value
            if self.max_income < self.min_income:
                self.max_income = self.min_income
            return True, None
        if cid == "max_income":
            self.max_income = value
            if self.max_income < self.min_income:
                # Если админ задал меньший максимум — подвинем минимум вниз
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
        # Дополнительно: проверка, что у инициатора всё ещё есть права админа
        if not inter.user.guild_permissions.administrator:
            await inter.response.send_message("Требуются права администратора.", ephemeral=True)
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
        # финальная валидация
        if self.min_income < 0 or self.max_income < 0 or self.cooldown < 0:
            return await inter.response.send_message(embed=error_embed("Ошибка", "Значения не могут быть отрицательными."), ephemeral=True)
        # Поддержим инвариант min <= max: если нарушен — аккуратно поменяем местами
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

        # Отключим элементы после сохранения
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
@commands.has_permissions(administrator=True)
async def set_work_cmd(ctx: commands.Context):
    """
    Открывает интерактивную панель настроек !work.
    Доступно только администраторам.
    """
    if not ctx.guild:
        return await ctx.send("Команда доступна только на сервере.")
    view = WorkSettingsView(ctx)
    embed = view.build_embed()
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


# --- НОВЫЕ КОМАНДЫ: Управление разрешениями ---

@bot.group(invoke_without_command=True, name="perms", aliases=["permissions"])
@commands.has_permissions(administrator=True)
async def perms(ctx: commands.Context):
    """Показывает справку по командам управления разрешениями."""
    embed = disnake.Embed(
        title="Управление разрешениями команд",
        description="Настрой, кто может использовать конкретные команды бота.",
        color=disnake.Color.orange()
    )
    prefix = bot.command_prefix
    embed.add_field(
        name=f"`{prefix}perms allow <@роль | @пользователь> \"Название команды|*\"`",
        value="Разрешить доступ к указанной команде (или всем командам, если *).",
        inline=False
    )
    embed.add_field(
        name=f"`{prefix}perms deny <@роль | @пользователь> \"Название команды|*\"`",
        value="Запретить доступ к указанной команде (или всем командам, если *).",
        inline=False
    )
    embed.add_field(
        name=f"`{prefix}perms remove <@роль | @пользователь> [\"Название команды|*\"]`",
        value="Удалить правило для команды. Без указания команды — удалить все правила для цели.",
        inline=False
    )
    embed.add_field(
        name=f"`{prefix}perms list`",
        value="Показать все текущие правила (по командам).",
        inline=False
    )
    embed.set_footer(text='Поддерживаются алиасы команд. Если имя с пробелами — возьмите его в кавычки.')
    await ctx.send(embed=embed)

@perms.command(name="allow")
@commands.has_permissions(administrator=True)
async def perms_allow(ctx: commands.Context, target: Union[disnake.Member, disnake.Role], *, command_name: str):
    normalized = normalize_command_name(command_name, bot)
    if normalized is None:
        return await ctx.send(embed=disnake.Embed(
            title="Команда не найдена",
            description=f"Не удалось найти команду по имени: `{command_name}`",
            color=disnake.Color.red()
        ))

    target_type = "user" if isinstance(target, disnake.Member) else "role"
    set_permission(ctx.guild.id, target.id, target_type, "allow", normalized)

    shown = "всем командам" if normalized == "*" else f"команде `{normalized}`"
    embed = disnake.Embed(
        title="Правило добавлено",
        description=f"✅ Разрешено для {target.mention} доступ к {shown}.",
        color=disnake.Color.green()
    )
    await ctx.send(embed=embed)

@perms.command(name="deny")
@commands.has_permissions(administrator=True)
async def perms_deny(ctx: commands.Context, target: Union[disnake.Member, disnake.Role], *, command_name: str):
    normalized = normalize_command_name(command_name, bot)
    if normalized is None:
        return await ctx.send(embed=disnake.Embed(
            title="Команда не найдена",
            description=f"Не удалось найти команду по имени: `{command_name}`",
            color=disnake.Color.red()
        ))

    target_type = "user" if isinstance(target, disnake.Member) else "role"
    set_permission(ctx.guild.id, target.id, target_type, "deny", normalized)

    shown = "всем командам" if normalized == "*" else f"команде `{normalized}`"
    embed = disnake.Embed(
        title="Правило добавлено",
        description=f"🚫 Запрещено для {target.mention} доступ к {shown}.",
        color=disnake.Color.red()
    )
    await ctx.send(embed=embed)

@perms.command(name="remove")
@commands.has_permissions(administrator=True)
async def perms_remove(ctx: commands.Context, target: Union[disnake.Member, disnake.Role], *, command_name: Optional[str] = None):
    if command_name:
        normalized = normalize_command_name(command_name, bot)
        if normalized is None:
            return await ctx.send(embed=disnake.Embed(
                title="Команда не найдена",
                description=f"Не удалось найти команду по имени: `{command_name}`",
                color=disnake.Color.red()
            ))
        remove_permission(ctx.guild.id, target.id, normalized)
        shown = "всем командам" if normalized == "*" else f"команде `{normalized}`"
        embed = disnake.Embed(
            title="Правило удалено",
            description=f"🗑️ Удалено правило для {target.mention} по {shown}.",
            color=disnake.Color.orange()
        )
    else:
        remove_permission(ctx.guild.id, target.id, None)
        embed = disnake.Embed(
            title="Правила удалены",
            description=f"🗑️ Удалены все правила для {target.mention}.",
            color=disnake.Color.orange()
        )
    await ctx.send(embed=embed)

@perms.command(name="list")
@commands.has_permissions(administrator=True)
async def perms_list(ctx: commands.Context):
    grouped = get_all_permissions_grouped(ctx.guild.id)
    if not grouped:
        return await ctx.send(embed=disnake.Embed(
            title="Правила отсутствуют",
            description="Пока не настроено ни одного правила разрешений.",
            color=disnake.Color.blurple()
        ))

    embed = disnake.Embed(title="Текущие разрешения на команды", color=disnake.Color.blue())
    command_names = sorted(grouped.keys(), key=lambda x: (x != "*", x))

    for cmd_name in command_names:
        data = grouped[cmd_name]
        allowed_mentions = [f"<@&{rid}>" for rid in sorted(data['allow']['roles'])] + \
                           [f"<@{uid}>" for uid in sorted(data['allow']['users'])]
        denied_mentions = [f"<@&{rid}>" for rid in sorted(data['deny']['roles'])] + \
                          [f"<@{uid}>" for uid in sorted(data['deny']['users'])]

        allowed_text = "\n".join(allowed_mentions) if allowed_mentions else "Нет"
        denied_text = "\n".join(denied_mentions) if denied_mentions else "Нет"

        title = "Глобальные правила (*)" if cmd_name == "*" else f"Команда: {cmd_name}"
        embed.add_field(name=f"{title}\n✅ Allow", value=allowed_text, inline=True)
        embed.add_field(name="🚫 Deny", value=denied_text, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

    await ctx.send(embed=embed)


# --- ОБРАБОТЧИКИ ОШИБОК ---

@bot.event
async def on_command_error(ctx: commands.Context, error):
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

    print(f"Произошла ошибка в команде '{getattr(ctx.command, 'qualified_name', None)}': {error}")


# Запуск бота
if __name__ == "__main__":
    bot.run(TOKEN)