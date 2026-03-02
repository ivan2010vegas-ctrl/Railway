"""
База данных TRECCC — SQLite.
Цена объявления в USD. Первое объявление бесплатно (free_ads_left).
"""
import sqlite3
import json
import traceback
from typing import Dict, List, Optional, Tuple

DATABASE_PATH = "treccc.db"


def get_conn():
    """Возвращает соединение с БД."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def execute_safe(cursor, query: str, params=None):
    """Безопасное выполнение запроса с выводом ошибок."""
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
    except Exception as e:
        print(f"❌ SQL Error: {e}")
        print(f"📝 Query: {query}")
        if params:
            print(f"📦 Params: {params}")
        traceback.print_exc()
        raise


def init_db():
    """Инициализация базы данных."""
    with get_conn() as conn:
        c = conn.cursor()

        # Таблица пользователей
        execute_safe(c, '''CREATE TABLE IF NOT EXISTS users (
            user_id        INTEGER PRIMARY KEY,
            username       TEXT DEFAULT '',
            full_name      TEXT DEFAULT '',
            agreed_terms   INTEGER DEFAULT 0,
            verified       INTEGER DEFAULT 0,
            deals_seller   INTEGER DEFAULT 0,
            deals_buyer    INTEGER DEFAULT 0,
            referrer_id    INTEGER DEFAULT NULL,
            referral_count INTEGER DEFAULT 0,
            free_ads_left  INTEGER DEFAULT 1
        )''')

        # Таблица объявлений
        execute_safe(c, '''CREATE TABLE IF NOT EXISTS ads (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            name         TEXT,
            description  TEXT,
            price_usd    REAL DEFAULT 0,
            country      TEXT,
            delivery     TEXT,
            media        TEXT DEFAULT '[]',
            status       TEXT DEFAULT 'pending',
            views        INTEGER DEFAULT 0,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Таблица отзывов
        execute_safe(c, '''CREATE TABLE IF NOT EXISTS reviews (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id  INTEGER,
            buyer_id   INTEGER,
            rating     INTEGER,
            text       TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Таблица жалоб
        execute_safe(c, '''CREATE TABLE IF NOT EXISTS reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER,
            seller_id   INTEGER,
            reason      TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Таблица избранного
        execute_safe(c, '''CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            ad_id   INTEGER,
            PRIMARY KEY (user_id, ad_id)
        )''')

        # Таблица верификации
        execute_safe(c, '''CREATE TABLE IF NOT EXISTS verifications (
            user_id    INTEGER PRIMARY KEY,
            status     TEXT DEFAULT 'pending',
            photo_id   TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Таблица реферальных бустов
        execute_safe(c, '''CREATE TABLE IF NOT EXISTS referral_boosts (
            user_id    INTEGER PRIMARY KEY,
            boosts_left INTEGER DEFAULT 0
        )''')

        conn.commit()

    # Миграция: добавляем колонки если их нет
    _migrate()


def _migrate():
    """Добавляет новые колонки в существующие таблицы, если их нет."""
    with get_conn() as conn:
        c = conn.cursor()
        
        # Проверяем существующие колонки в таблице users
        c.execute("PRAGMA table_info(users)")
        existing_columns_users = [col[1] for col in c.fetchall()]
        
        # Добавляем колонки в users, если их нет
        if 'free_ads_left' not in existing_columns_users:
            try:
                c.execute("ALTER TABLE users ADD COLUMN free_ads_left INTEGER DEFAULT 1")
                print("✅ Добавлена колонка free_ads_left в users")
            except Exception as e:
                print(f"ℹ️ {e}")
        
        if 'referral_count' not in existing_columns_users:
            try:
                c.execute("ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0")
                print("✅ Добавлена колонка referral_count в users")
            except Exception as e:
                print(f"ℹ️ {e}")
        
        # Проверяем существующие колонки в таблице ads
        c.execute("PRAGMA table_info(ads)")
        existing_columns_ads = [col[1] for col in c.fetchall()]
        
        # Добавляем колонки в ads, если их нет
        if 'price_usd' not in existing_columns_ads:
            try:
                c.execute("ALTER TABLE ads ADD COLUMN price_usd REAL DEFAULT 0")
                print("✅ Добавлена колонка price_usd в ads")
            except Exception as e:
                print(f"ℹ️ {e}")
        
        if 'status' not in existing_columns_ads:
            try:
                c.execute("ALTER TABLE ads ADD COLUMN status TEXT DEFAULT 'pending'")
                print("✅ Добавлена колонка status в ads")
            except Exception as e:
                print(f"ℹ️ {e}")
        
        if 'views' not in existing_columns_ads:
            try:
                c.execute("ALTER TABLE ads ADD COLUMN views INTEGER DEFAULT 0")
                print("✅ Добавлена колонка views в ads")
            except Exception as e:
                print(f"ℹ️ {e}")
        
        conn.commit()


# ── Пользователи ──────────────────────────────────────────────────────────────

def get_or_create_user(user_id: int, username: str, full_name: str,
                        referrer_id: Optional[int] = None) -> Dict:
    """Получает или создает пользователя."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        
        if row is None:
            # Создаем нового пользователя
            execute_safe(c,
                """INSERT INTO users
                   (user_id, username, full_name, referrer_id, free_ads_left)
                   VALUES (?,?,?,?,1)""",
                (user_id, username, full_name, referrer_id)
            )
            
            # Начисляем бонус рефереру
            if referrer_id and referrer_id != user_id:
                execute_safe(c,
                    "UPDATE users SET referral_count = referral_count + 1 WHERE user_id=?",
                    (referrer_id,)
                )
                # Проверяем нужно ли начислить буст
                check_and_give_ref_bonus(referrer_id)
            
            conn.commit()
            
            # Получаем созданного пользователя
            execute_safe(c, "SELECT * FROM users WHERE user_id=?", (user_id,))
            row = c.fetchone()
        else:
            # Обновляем существующего пользователя
            execute_safe(c,
                "UPDATE users SET username=?, full_name=? WHERE user_id=?",
                (username, full_name, user_id)
            )
            conn.commit()
    
    return dict(row)


def get_user(user_id: int) -> Optional[Dict]:
    """Получает пользователя по ID."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    return dict(row) if row else None


def get_all_users() -> List[int]:
    """Получает список всех пользователей."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT user_id FROM users")
        return [r[0] for r in c.fetchall()]


def has_agreed_terms(user_id: int) -> bool:
    """Проверяет, принял ли пользователь условия."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT agreed_terms FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    return row is not None and row[0] == 1


def set_agreed_terms(user_id: int):
    """Отмечает, что пользователь принял условия."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "UPDATE users SET agreed_terms=1 WHERE user_id=?", (user_id,))
        conn.commit()


def set_verified(user_id: int):
    """Верифицирует пользователя."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "UPDATE users SET verified=1 WHERE user_id=?", (user_id,))
        conn.commit()


def use_free_ad(user_id: int):
    """Тратит одно бесплатное объявление."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            "UPDATE users SET free_ads_left = MAX(0, free_ads_left - 1) WHERE user_id=?",
            (user_id,)
        )
        conn.commit()


def get_verified_mark(user: Dict) -> str:
    """Возвращает значок верификации."""
    return " ✅" if user and user.get("verified") else ""


def get_badge(user: Dict) -> str:
    """Возвращает бейдж пользователя на основе количества сделок."""
    if not user:
        return ""
    deals = user.get("deals_seller") or 0
    if deals >= 50:
        return "🏆 Топ продавец"
    if deals >= 20:
        return "🥇 Опытный"
    if deals >= 5:
        return "🥈 Активный"
    return "🆕 Новичок"


def increment_deals(user_id: int, role: str):
    """Увеличивает счетчик сделок."""
    field = "deals_seller" if role == "seller" else "deals_buyer"
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, f"UPDATE users SET {field} = {field} + 1 WHERE user_id=?", (user_id,))
        conn.commit()


# ── Объявления ────────────────────────────────────────────────────────────────

def save_ad(user_id: int, ad_data: Dict) -> int:
    """Сохраняет объявление и возвращает его id."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            """INSERT INTO ads
               (user_id, name, description, price_usd, country, delivery, media, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                user_id,
                ad_data.get("name", ""),
                ad_data.get("description", ""),
                ad_data.get("price_usd", 0),
                ad_data.get("country", ""),
                ad_data.get("delivery", ""),
                json.dumps(ad_data.get("media", []), ensure_ascii=False),
                "pending",
            )
        )
        conn.commit()
        return c.lastrowid


def get_ad(user_id: int, status: str = None) -> Optional[Dict]:
    """Возвращает последнее объявление пользователя (или с нужным статусом)."""
    with get_conn() as conn:
        c = conn.cursor()
        if status:
            execute_safe(c,
                "SELECT * FROM ads WHERE user_id=? AND status=? ORDER BY id DESC LIMIT 1",
                (user_id, status)
            )
        else:
            execute_safe(c,
                "SELECT * FROM ads WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (user_id,)
            )
        row = c.fetchone()
    
    if not row:
        return None
    
    d = dict(row)
    d["media"] = json.loads(d.get("media") or "[]")
    return d


def get_ad_by_id(ad_id: int) -> Optional[Dict]:
    """Возвращает объявление по его id."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT * FROM ads WHERE id=?", (ad_id,))
        row = c.fetchone()
    
    if not row:
        return None
    
    d = dict(row)
    d["media"] = json.loads(d.get("media") or "[]")
    return d


def get_user_ads(user_id: int) -> list:
    """Все объявления пользователя."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT * FROM ads WHERE user_id=? ORDER BY id DESC", (user_id,))
        rows = c.fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        d["media"] = json.loads(d.get("media") or "[]")
        result.append(d)
    return result


def delete_ad(user_id: int = None, ad_id: int = None):
    """Удаляет объявление."""
    with get_conn() as conn:
        c = conn.cursor()
        if ad_id:
            execute_safe(c, "DELETE FROM ads WHERE id=?", (ad_id,))
        elif user_id:
            execute_safe(c,
                "DELETE FROM ads WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (user_id,)
            )
        conn.commit()


def approve_ad(user_id: int = None, ad_id: int = None):
    """Одобряет объявление."""
    with get_conn() as conn:
        c = conn.cursor()
        if ad_id:
            execute_safe(c, "UPDATE ads SET status='approved' WHERE id=?", (ad_id,))
        elif user_id:
            execute_safe(c,
                """UPDATE ads SET status='approved' WHERE id=(
                    SELECT id FROM ads WHERE user_id=? AND status='pending'
                    ORDER BY id DESC LIMIT 1
                )""",
                (user_id,)
            )
        conn.commit()


def search_ads(query: str) -> List[Dict]:
    """Ищет объявления по тексту."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            "SELECT * FROM ads WHERE status='approved' AND (name LIKE ? OR description LIKE ?)",
            (f'%{query}%', f'%{query}%')
        )
        rows = c.fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        d["media"] = json.loads(d.get("media") or "[]")
        result.append(d)
    return result


def get_all_approved_ads() -> List[Dict]:
    """Все одобренные объявления."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT * FROM ads WHERE status='approved' ORDER BY id DESC")
        rows = c.fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        d["media"] = json.loads(d.get("media") or "[]")
        result.append(d)
    return result


# ── Отзывы ────────────────────────────────────────────────────────────────────

def add_review(seller_id: int, buyer_id: int, rating: int, text: str = ""):
    """Добавляет отзыв."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            "INSERT INTO reviews (seller_id, buyer_id, rating, text) VALUES (?,?,?,?)",
            (seller_id, buyer_id, rating, text)
        )
        conn.commit()


def get_seller_rating(seller_id: int) -> Tuple[float, int]:
    """Возвращает рейтинг продавца и количество отзывов."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT AVG(rating), COUNT(*) FROM reviews WHERE seller_id=?", (seller_id,))
        row = c.fetchone()
    
    avg = round(row[0], 1) if row and row[0] else 0.0
    cnt = row[1] if row else 0
    return avg, cnt


# ── Жалобы ────────────────────────────────────────────────────────────────────

def save_report(reporter_id: int, seller_id: int, reason: str):
    """Сохраняет жалобу."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            "INSERT INTO reports (reporter_id, seller_id, reason) VALUES (?,?,?)",
            (reporter_id, seller_id, reason)
        )
        conn.commit()


# ── Избранное ─────────────────────────────────────────────────────────────────

def add_favorite(user_id: int, ad_id: int) -> bool:
    """Добавляет объявление в избранное."""
    with get_conn() as conn:
        c = conn.cursor()
        try:
            execute_safe(c,
                "INSERT INTO favorites (user_id, ad_id) VALUES (?,?)",
                (user_id, ad_id)
            )
            conn.commit()
            return True
        except Exception:
            return False


def remove_favorite(user_id: int, ad_id: int):
    """Удаляет объявление из избранного."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            "DELETE FROM favorites WHERE user_id=? AND ad_id=?",
            (user_id, ad_id)
        )
        conn.commit()


def get_favorites(user_id: int) -> list:
    """Возвращает список избранных объявлений."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, """
            SELECT ads.* FROM ads
            JOIN favorites ON ads.id = favorites.ad_id
            WHERE favorites.user_id=? AND ads.status='approved'
            ORDER BY ads.id DESC
        """, (user_id,))
        rows = c.fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        d["media"] = json.loads(d.get("media") or "[]")
        result.append(d)
    return result


# ── Верификация ───────────────────────────────────────────────────────────────

def save_verification(user_id: int, photo_id: str):
    """Сохраняет заявку на верификацию."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            """INSERT OR REPLACE INTO verifications (user_id, photo_id, status)
               VALUES (?,?,'pending')""",
            (user_id, photo_id)
        )
        conn.commit()


def approve_verification(user_id: int):
    """Одобряет верификацию."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            "UPDATE verifications SET status='approved' WHERE user_id=?",
            (user_id,)
        )
        execute_safe(c,
            "UPDATE users SET verified=1 WHERE user_id=?",
            (user_id,)
        )
        conn.commit()


def get_verification(user_id: int) -> Optional[Dict]:
    """Получает статус верификации."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT * FROM verifications WHERE user_id=?", (user_id,))
        row = c.fetchone()
    return dict(row) if row else None


# ── Реферальные бонусы ────────────────────────────────────────────────────────

def add_referral_boost(user_id: int, amount: int = 1):
    """Добавляет бесплатные бусты."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            """INSERT INTO referral_boosts (user_id, boosts_left)
               VALUES (?,?)
               ON CONFLICT(user_id) DO UPDATE SET boosts_left = boosts_left + ?""",
            (user_id, amount, amount)
        )
        conn.commit()


def use_referral_boost(user_id: int) -> bool:
    """Использует один бесплатный буст."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT boosts_left FROM referral_boosts WHERE user_id=?", (user_id,))
        row = c.fetchone()
        
        if not row or row[0] < 1:
            return False
        
        execute_safe(c,
            "UPDATE referral_boosts SET boosts_left = boosts_left - 1 WHERE user_id=?",
            (user_id,)
        )
        conn.commit()
        return True


def get_referral_boosts(user_id: int) -> int:
    """Возвращает количество доступных бустов."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT boosts_left FROM referral_boosts WHERE user_id=?", (user_id,))
        row = c.fetchone()
    return row[0] if row else 0


# ── Счётчик просмотров объявления ─────────────────────────────────────────────

def increment_ad_views(ad_id: int):
    """Увеличивает счетчик просмотров."""
    with get_conn() as conn:
        c = conn.cursor()
        try:
            execute_safe(c, "UPDATE ads SET views = views + 1 WHERE id=?", (ad_id,))
            conn.commit()
        except Exception:
            pass  # колонка views может отсутствовать


# ── Топ продавцов ─────────────────────────────────────────────────────────────

def get_top_sellers(limit: int = 10) -> list:
    """Возвращает топ продавцов по рейтингу."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, """
            SELECT 
                u.user_id, 
                u.username, 
                u.full_name, 
                u.verified, 
                u.deals_seller,
                COALESCE(AVG(r.rating), 0) as avg_rating, 
                COUNT(r.id) as review_count
            FROM users u
            LEFT JOIN reviews r ON u.user_id = r.seller_id
            GROUP BY u.user_id
            ORDER BY avg_rating DESC, review_count DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
    
    result = []
    for row in rows:
        d = dict(row)
        # Округляем рейтинг
        d['avg_rating'] = round(d['avg_rating'], 1)
        result.append(d)
    return result


# ── Начисление реф бонуса ─────────────────────────────────────────────────────

def check_and_give_ref_bonus(referrer_id: int):
    """Проверяет достиг ли реферер порога и начисляет бонус."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c, "SELECT referral_count FROM users WHERE user_id=?", (referrer_id,))
        row = c.fetchone()
        
        if row and row[0] % 5 == 0 and row[0] > 0:
            # Каждые 5 рефералов — 1 бесплатный BOOST
            add_referral_boost(referrer_id, 1)
            return True
    
    return False


# ── Очистка старых данных ─────────────────────────────────────────────────────

def cleanup_old_pending_ads(days: int = 7):
    """Удаляет старые объявления со статусом 'pending'."""
    with get_conn() as conn:
        c = conn.cursor()
        execute_safe(c,
            "DELETE FROM ads WHERE status='pending' AND created_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        deleted = c.rowcount
        conn.commit()
        print(f"🧹 Удалено {deleted} старых объявлений")
        return deleted

