"""
База данных TRECCC через Supabase (PostgreSQL).
"""
import time
from supabase import create_client, Client

SUPABASE_URL = "https://gcehuuwpirgswdlxlnsg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdjZWh1dXdwaXJnc3dkbHhsbnNnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE5MzM5ODUsImV4cCI6MjA4NzUwOTk4NX0.Yl9DJ8XkU1NRoCX_vtol5PjOYKhfiPvxuBplieN21uI"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─── СТАТУСЫ ─────────────────────────────────────────────────────────────────

STATUS_WAITING_PAYMENT = "waiting_payment"
STATUS_PAID            = "paid"
STATUS_SHIPPED         = "shipped"
STATUS_COMPLETED       = "completed"
STATUS_DISPUTED        = "disputed"
STATUS_REFUNDED        = "refunded"


# ─── ADS ──────────────────────────────────────────────────────────────────────

def save_ad(user_id: int, ad: dict):
    supabase.table("ads").upsert({
        "user_id":     user_id,
        "name":        ad.get("name", ""),
        "description": ad.get("desc", ""),
        "price":       float(ad.get("price", 0)),
        "country":     ad.get("country", ""),
        "delivery":    ad.get("delivery", ""),
        "media":       ad.get("media", []),
        "active":      True,
    }).execute()


def get_ad(user_id: int) -> dict:
    res = supabase.table("ads").select("*").eq("user_id", user_id).eq("active", True).execute()
    if res.data:
        row = res.data[0]
        row["desc"] = row.pop("description", "")
        return row
    return None


def delete_ad(user_id: int):
    supabase.table("ads").update({"active": False}).eq("user_id", user_id).execute()


def search_ads(query: str) -> list:
    res = supabase.table("ads").select("*").eq("active", True).or_(
        f"name.ilike.%{query}%,description.ilike.%{query}%"
    ).limit(20).execute()
    result = []
    for row in (res.data or []):
        row["desc"] = row.pop("description", "")
        result.append(row)
    return result


def get_all_ads() -> dict:
    res = supabase.table("ads").select("*").eq("active", True).execute()
    result = {}
    for row in (res.data or []):
        row["desc"] = row.pop("description", "")
        result[row["user_id"]] = row
    return result


# ─── DEALS ────────────────────────────────────────────────────────────────────

def create_deal(seller_id: int, buyer_id: int, ad: dict, invoice_id: int, invoice_url: str) -> str:
    deal_id    = "deal_" + str(int(time.time())) + "_" + str(seller_id) + "_" + str(buyer_id)
    base_price = float(ad["price"])
    commission = round(base_price * 0.05, 2)
    total      = round(base_price + commission, 2)
    supabase.table("deals").insert({
        "deal_id":      deal_id,
        "seller_id":    seller_id,
        "buyer_id":     buyer_id,
        "product_name": ad["name"],
        "base_price":   base_price,
        "commission":   commission,
        "total":        total,
        "invoice_id":   invoice_id,
        "invoice_url":  invoice_url,
        "status":       STATUS_WAITING_PAYMENT,
    }).execute()
    return deal_id


def get_deal(deal_id: str) -> dict:
    res = supabase.table("deals").select("*").eq("deal_id", deal_id).execute()
    return res.data[0] if res.data else None


def get_deal_by_invoice(invoice_id: int) -> dict:
    res = supabase.table("deals").select("*").eq("invoice_id", invoice_id).execute()
    return res.data[0] if res.data else None


def get_deals_by_seller(seller_id: int) -> list:
    res = supabase.table("deals").select("*").eq("seller_id", seller_id).order("created_at", desc=True).limit(10).execute()
    return res.data or []


def get_deals_by_buyer(buyer_id: int) -> list:
    res = supabase.table("deals").select("*").eq("buyer_id", buyer_id).order("created_at", desc=True).limit(10).execute()
    return res.data or []


def get_deals_by_status(status: str) -> list:
    res = supabase.table("deals").select("*").eq("status", status).execute()
    return res.data or []


def update_deal(deal_id: str, **kwargs):
    if kwargs:
        supabase.table("deals").update(kwargs).eq("deal_id", deal_id).execute()


def set_paid(deal_id: str):
    supabase.table("deals").update({"status": STATUS_PAID, "paid_at": "now()"}).eq("deal_id", deal_id).execute()


def set_shipped(deal_id: str, track: str):
    supabase.table("deals").update({
        "status": STATUS_SHIPPED, "track_number": track, "shipped_at": "now()"
    }).eq("deal_id", deal_id).execute()


def set_completed(deal_id: str):
    supabase.table("deals").update({"status": STATUS_COMPLETED, "completed_at": "now()"}).eq("deal_id", deal_id).execute()


def set_disputed(deal_id: str):
    supabase.table("deals").update({"status": STATUS_DISPUTED}).eq("deal_id", deal_id).execute()


def set_refunded(deal_id: str):
    supabase.table("deals").update({"status": STATUS_REFUNDED}).eq("deal_id", deal_id).execute()


def get_shipped_deals_older_than(seconds: int) -> list:
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    res = supabase.table("deals").select("*").eq("status", STATUS_SHIPPED).lt("shipped_at", cutoff).execute()
    return res.data or []


# ─── USERS ────────────────────────────────────────────────────────────────────

def get_or_create_user(user_id: int, username: str = "", full_name: str = "") -> dict:
    res = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if res.data:
        user = res.data[0]
        if username and user.get("username") != username:
            supabase.table("users").update({"username": username, "full_name": full_name}).eq("user_id", user_id).execute()
            user["username"] = username
            user["full_name"] = full_name
        return user
    new_user = {"user_id": user_id, "username": username, "full_name": full_name}
    supabase.table("users").insert(new_user).execute()
    return new_user


def get_user(user_id: int) -> dict:
    res = supabase.table("users").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None


def set_verified(user_id: int, verified: bool = True):
    supabase.table("users").update({"verified": verified}).eq("user_id", user_id).execute()


def set_agreed_terms(user_id: int):
    supabase.table("users").update({"agreed_terms": True}).eq("user_id", user_id).execute()


def has_agreed_terms(user_id: int) -> bool:
    res = supabase.table("users").select("agreed_terms").eq("user_id", user_id).execute()
    return bool(res.data and res.data[0].get("agreed_terms"))


def increment_deals(user_id: int, role: str):
    res = supabase.table("users").select("deals_seller,deals_buyer").eq("user_id", user_id).execute()
    if res.data:
        user  = res.data[0]
        field = "deals_seller" if role == "seller" else "deals_buyer"
        supabase.table("users").update({field: (user.get(field) or 0) + 1}).eq("user_id", user_id).execute()


def get_badge(user: dict) -> str:
    deals = user.get("deals_seller", 0) if user else 0
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
    return " \u2705" if user and user.get("verified") else ""


# ─── FAVORITES ────────────────────────────────────────────────────────────────

def add_favorite(user_id: int, seller_id: int) -> bool:
    try:
        supabase.table("favorites").insert({"user_id": user_id, "seller_id": seller_id}).execute()
        return True
    except Exception:
        return False


def remove_favorite(user_id: int, seller_id: int):
    supabase.table("favorites").delete().eq("user_id", user_id).eq("seller_id", seller_id).execute()


def get_favorites(user_id: int) -> list:
    res = supabase.table("favorites").select("seller_id").eq("user_id", user_id).execute()
    if not res.data:
        return []
    seller_ids = [r["seller_id"] for r in res.data]
    ads_res = supabase.table("ads").select("*").in_("user_id", seller_ids).eq("active", True).execute()
    result = []
    for row in (ads_res.data or []):
        row["desc"] = row.pop("description", "")
        result.append(row)
    return result


def is_favorite(user_id: int, seller_id: int) -> bool:
    res = supabase.table("favorites").select("id").eq("user_id", user_id).eq("seller_id", seller_id).execute()
    return bool(res.data)


# ─── REVIEWS ──────────────────────────────────────────────────────────────────

def add_review(deal_id: str, seller_id: int, buyer_id: int, rating: int, text: str = ""):
    try:
        supabase.table("reviews").upsert({
            "deal_id": deal_id, "seller_id": seller_id,
            "buyer_id": buyer_id, "rating": rating, "text": text,
        }, on_conflict="deal_id,buyer_id").execute()
    except Exception as e:
        print("[reviews] Ошибка:", e)


def get_seller_reviews(seller_id: int) -> list:
    res = supabase.table("reviews").select("*").eq("seller_id", seller_id).order("created_at", desc=True).limit(10).execute()
    return res.data or []


def get_seller_rating(seller_id: int) -> tuple:
    res = supabase.table("reviews").select("rating").eq("seller_id", seller_id).execute()
    data = res.data or []
    if not data:
        return 0.0, 0
    avg = round(sum(r["rating"] for r in data) / len(data), 1)
    return avg, len(data)


# ─── МИГРАЦИЯ ИЗ JSON ─────────────────────────────────────────────────────────

def migrate_from_json():
    import json, os
    base = os.path.dirname(os.path.abspath(__file__))

    ads_file = os.path.join(base, "ads_backup.json")
    if os.path.exists(ads_file):
        try:
            with open(ads_file, "r", encoding="utf-8") as f:
                old = json.load(f)
            for uid, ad in old.items():
                save_ad(int(uid), ad)
            print(f"[Supabase] Мигрировано {len(old)} объявлений")
        except Exception as e:
            print(f"[Supabase] Ошибка миграции ads: {e}")

    deals_file = os.path.join(base, "deals.json")
    if os.path.exists(deals_file):
        try:
            with open(deals_file, "r", encoding="utf-8") as f:
                old = json.load(f)
            for deal_id, d in old.items():
                try:
                    supabase.table("deals").upsert({
                        "deal_id":        deal_id,
                        "seller_id":      d.get("seller_id", 0),
                        "buyer_id":       d.get("buyer_id", 0),
                        "product_name":   d.get("product_name", ""),
                        "base_price":     d.get("base_price", 0),
                        "commission":     d.get("commission", 0),
                        "total":          d.get("total", 0),
                        "invoice_id":     d.get("invoice_id", 0),
                        "invoice_url":    d.get("invoice_url", ""),
                        "status":         d.get("status", "waiting_payment"),
                        "payment_method": d.get("payment_method", "usdt"),
                        "stars_amount":   d.get("stars_amount", 0),
                        "track_number":   d.get("track_number", "") or "",
                    }).execute()
                except Exception:
                    pass
            print(f"[Supabase] Мигрировано {len(old)} сделок")
        except Exception as e:
            print(f"[Supabase] Ошибка миграции deals: {e}")


# ─── INIT ─────────────────────────────────────────────────────────────────────

def init_db():
    try:
        supabase.table("users").select("user_id").limit(1).execute()
        print("[Supabase] Подключение успешно!")
    except Exception as e:
        print(f"[Supabase] Ошибка подключения: {e}")
        raise