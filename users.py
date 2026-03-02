
"""
Профили пользователей: верификация, достижения, рейтинг.
"""
import json
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")


def _load() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def get_or_create(user_id: int, username: str = "", full_name: str = "") -> dict:
    users = _load()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "verified": False,
            "agreed_terms": False,
            "deals_as_seller": 0,
            "deals_as_buyer": 0,
            "joined_at": int(time.time()),
        }
        _save(users)
    else:
        # Обновляем username если изменился
        if username and users[uid].get("username") != username:
            users[uid]["username"] = username
            _save(users)
    return users[uid]


def get_user(user_id: int) -> dict:
    return _load().get(str(user_id))


def set_verified(user_id: int, verified: bool = True):
    users = _load()
    uid = str(user_id)
    if uid in users:
        users[uid]["verified"] = verified
        _save(users)


def set_agreed_terms(user_id: int):
    users = _load()
    uid = str(user_id)
    if uid in users:
        users[uid]["agreed_terms"] = True
        _save(users)


def increment_deals(user_id: int, role: str):
    """role = 'seller' или 'buyer'"""
    users = _load()
    uid = str(user_id)
    if uid in users:
        key = "deals_as_" + role
        users[uid][key] = users[uid].get(key, 0) + 1
        _save(users)


def get_badge(user: dict) -> str:
    """Возвращает значок уровня продавца."""
    deals = user.get("deals_as_seller", 0)
    if deals >= 50:
        return "\U0001f947 Золотой продавец"
    elif deals >= 10:
        return "\U0001f948 Серебряный продавец"
    elif deals >= 5:
        return "\U0001f949 Бронзовый продавец"
    elif deals >= 1:
        return "\u2b50 Продавец"
    return "\U0001f195 Новичок"


def get_verified_mark(user: dict) -> str:
    return " \u2705" if user.get("verified") else ""


def has_agreed_terms(user_id: int) -> bool:
    user = get_user(user_id)
