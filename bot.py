"""
TRECCC — маркетплейс объявлений ЕАЭС.
- Публикация: 1 бесплатно, далее 10 Stars
- Цена в USD + эквивалент в валютах ЕАЭС
- BOOST: Выделение / Закреп / История
"""
import re
import asyncio
import sys
from typing import List, Tuple

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    LabeledPrice,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
)
from telegram.constants import ParseMode

from config import TOKEN, CHANNEL_PUBLIC, ADMIN_ID
from send_to_admin import send_ad_to_admin
import database as db

db.init_db()

# ── ЭТАПЫ ────────────────────────────────────────────────────────────────────
NAME, DESC, PRICE, COUNTRY, DELIVERY, MEDIA = range(6)
REVIEW_RATING, REVIEW_TEXT = range(20, 22)
VERIFY_PHOTO = 30
BROADCAST_TEXT, BROADCAST_MEDIA, BROADCAST_CONFIRM = range(10, 13)

# ── КОНСТАНТЫ ─────────────────────────────────────────────────────────────────
# Публикация объявлений — БЕСПЛАТНО

BOOST_HIGHLIGHT_STARS = 75    # 🔥 Выделение
BOOST_PIN_STARS       = 200   # 📌 Закреп на 24ч
BOOST_STORY_STARS     = 350   # 📢 Повтор через 24ч
BOOST_ALL_STARS       = int((BOOST_HIGHLIGHT_STARS + BOOST_PIN_STARS + BOOST_STORY_STARS) * 0.8)  # ⚡ Всё со скидкой 20%
VERIFY_STARS          = 300   # ✅ Верификация продавца
REF_BONUS_THRESHOLD   = 5     # Рефералов для бесплатного BOOST

EAEU_RATES = {
    "🇷🇺 RUB": 92.5,
    "🇧🇾 BYN": 3.28,
    "🇰🇿 KZT": 455.0,
    "🇦🇲 AMD": 388.0,
    "🇰🇬 KGS": 87.5,
}

TERMS_TEXT = (
    "📄 ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ TRECCC\n\n"
    "Используя платформу, вы соглашаетесь:\n\n"
    "1. Продавать только легальные товары\n"
    "2. Предоставлять достоверную информацию о товаре\n"
    "3. Отвечать покупателям в течение 24 часов\n"
    "4. Не обманывать покупателей\n"
    "5. Все споры решаются через администрацию\n\n"
    "Администрация вправе заблокировать аккаунт за нарушения."
)

# ── КЛАВИАТУРЫ ────────────────────────────────────────────────────────────────
MAIN_KBD = ReplyKeyboardMarkup(
    [
        ["📦 Создать объявление", "👤 Мой профиль"],
        ["🤍 Избранное",         "📋 Мои объявления"],
        ["💥 BOOST — ПРОДАЙ БЫСТРЕЕ! 💥"],
        ["👥 Рефералы",          "❓ Как это работает?"],
        ["✅ Верификация",        "🏆 Топ продавцов"],
    ],
    resize_keyboard=True,
)

COUNTRY_KBD = ReplyKeyboardMarkup(
    [
        ["🇷🇺 Россия",     "🇧🇾 Беларусь"],
        ["🇰🇿 Казахстан",  "🇦🇲 Армения"],
        ["🇰🇬 Кыргызстан", "🌍 Другая страна ЕАЭС"],
    ],
    one_time_keyboard=True, resize_keyboard=True,
)

DELIVERY_KBD = ReplyKeyboardMarkup(
    [["✅ Да, возможна", "❌ Нет, самовывоз"]],
    one_time_keyboard=True, resize_keyboard=True,
)

FINISH_KBD = ReplyKeyboardMarkup(
    [["✅ Закончить"], ["❌ Отменить объявление"]],
    resize_keyboard=True,
)


# ── ВСПОМОГАТЕЛЬНЫЕ ──────────────────────────────────────────────────────────
def seller_contact_url(seller: dict, seller_id: int) -> str:
    """Прямая ссылка на чат с продавцом."""
    username = seller.get("username", "") if seller else ""
    if username:
        return f"https://t.me/{username}"
    return f"tg://user?id={seller_id}"


def ulink(username: str, full_name: str) -> str:
    return "@" + username if username else (full_name or "Пользователь")


def stars_rating_str(rating: float, count: int) -> str:
    if count == 0:
        return "нет отзывов"
    filled = int(round(rating))
    return "⭐" * filled + "☆" * (5 - filled) + f" {rating:.1f} ({count})"


def price_in_eaeu(usd: float) -> str:
    parts = []
    for flag_code, rate in EAEU_RATES.items():
        amount = usd * rate
        parts.append(
            f"{flag_code}: {amount:,.0f}" if amount >= 1000
            else f"{flag_code}: {amount:.2f}"
        )
    return "\n".join(parts)


def build_ad_text(ad: dict, seller: dict, boosted: bool = False) -> str:
    """Формирует текст объявления для канала. boosted=True — особое оформление."""
    p = ad.get("price_usd", 0)
    eaeu = price_in_eaeu(p)
    vmark = db.get_verified_mark(seller) if seller else ""
    badge = db.get_badge(seller) if seller else ""
    slink = ulink(
        seller.get("username", "") if seller else "",
        seller.get("full_name", "") if seller else "?"
    )
    rating, rcnt = db.get_seller_rating(ad["user_id"])
    desc_line = f"📝 {ad['description']}\n\n" if ad.get("description") else ""

    if boosted:
        header = (
            "🔥🔥🔥 ВИП ОБЪЯВЛЕНИЕ 🔥🔥🔥\n"
            "★━━━━━━━━━━━━━━━━★\n"
        )
        footer = "\n★━━━━━━━━━━━━━━━━★"
    else:
        header = ""
        footer = ""

    return (
        header +
        f"📦 {ad['name'].upper()}\n"
        f"📍 {ad['country']}  🚚 {ad['delivery']}\n\n"
        + desc_line +
        f"💵 Цена: ${p:.2f}\n"
        f"📊 Эквивалент:\n{eaeu}\n\n"
        f"👤 {slink}{vmark} {badge}\n"
        f"⭐ {stars_rating_str(rating, rcnt)}\n\n"
        "📲 Напишите продавцу для покупки"
        + footer
    )


# ── АНТИ-СКАМ v2 (КАПИТАЛЬНАЯ ВЕРСИЯ) ────────────────────────────────────────

import re
from typing import Tuple, List

# ── ЗАПРЕЩЁННЫЕ СЛОВА (расширенный словарь) ───────────────────────────────────
BANNED_WORDS: List[str] = [
    # Наркотики (рус)
    "наркотик", "наркота", "нарки", "спайс", "соль", "скорость", "меф", "мефедрон",
    "кокаин", "кокс", "героин", "амфетамин", "лсд", "марки", "гашиш", "марихуана",
    "шишки", "бошки", "план", "гарик", "фен", "мет", "кристаллы", "трава", "ганджа",
    "анаша", "опиум", "морфин", "фентанил", "экстази", "эйфоретик", "диссоциатив",
    "закладка", "закл", "клад", "прайс лист", "прайслист", "моно", "микс",
    "соль для ванн", "удобрение", "реагент", "реагенты",
    # Наркотики (латиница)
    "drug", "weed", "cocaine", "heroin", "meth", "lsd", "mdma", "ecstasy",
    "amphetamine", "fentanyl", "ketamine", "crystal", "crack", "hash",
    "marijuana", "cannabis", "hemp", "narcotic", "stash",
    # Эскорт / 18+
    "порно", "porno", "porn", "проститутк", "проститут", "эскорт", "шлюх",
    "интим услуг", "интим-услуг", "вирт", "минет", "куни", "bdsm", "бдсм",
    "вебка", "webcam", "onlyfans", "только для взрослых", "досуг",
    "индивидуалк", "анкета девушк", "приятный досуг",
    # Оружие и боеприпасы
    "оружие", "пистолет", "автомат", "граната", "патроны", "weapon", "gun",
    "rifle", "ствол", "глушитель", "взрывчат", "тротил", "гексоген",
    "самопал", "обрез", "нож боевой", "кастет", "баллистик",
    "пневматик", "травматик", "газовый пистолет", "арбалет боевой",
    # Скам / мошенничество / тёмные услуги
    "скам", "лохотрон", "кидалово", "мошенник", "scam", "fraud", "fake",
    "залив", "обнал", "обналичивание", "кардинг", "carding", "пробив",
    "взлом", "взломать", "хакер", "слив базы", "слив бд", "база данных продам",
    "darknet", "даркнет", "гидра", "hydra", "onion", "tor браузер",
    "левые документы", "поддельные документы", "фальшивые документы",
    "купить паспорт", "купить права", "левая симкарт",
    # Финансовые махинации
    "перевод на карту", "qiwi кошелек", "обход блокировки", "иксы",
    "арбитраж трафика", "памп", "дамп", "pump", "dump",
    "airdrop", "presale", "слив сигналов", "договорняк",
    "слив матчей", "договорной матч", "инсайд",
    # Азартные игры / казино
    "казино", "слоты", "vavada", "1xbet", "ставки онлайн", "букмекер",
    "игровые автоматы", "рулетка онлайн",
    # Обходы фильтров (типичные паттерны)
    "схема заработка", "темка", "ворк", "дроп", "абуз", "абузить",
    "серая схема", "чёрная схема", "нелегальный заработок",
    "быстрые деньги", "без вложений x", "лёгкий заработок",
    # Мат (расширен)
    "хуй", "пизда", "блядь", "сука", "петух", "гандон", "уебок",
    "ебать", "пидор", "мразь", "еблан", "шалава", "залупа",
    "ёбаный", "ёб твою", "иди нахуй", "иди нафуй",
]

# ── ТАБЛИЦА ЗАМЕН: leetspeak + Unicode-спуфинг ────────────────────────────────
_LEET: dict = {
    # Цифры
    "0": "о", "1": "и", "3": "з", "4": "ч", "5": "с",
    "6": "б", "7": "т", "8": "в", "9": "д",
    # Спецсимволы
    "@": "а", "$": "с", "!": "и", "|": "и", "(": "с",
    # Латиница → кириллица (визуально похожие)
    "a": "а", "e": "е", "o": "о", "p": "р", "c": "с",
    "x": "х", "k": "к", "m": "м", "h": "н", "b": "в",
    "t": "т", "y": "у",
}

# ── ПОДОЗРИТЕЛЬНЫЕ ПАТТЕРНЫ (регулярные выражения) ────────────────────────────
_SUSPICIOUS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Номера карт (12–19 цифр)
    (re.compile(r"\d[\s\-]*\d[\s\-]*\d[\s\-]*\d[\s\-]*\d[\s\-]*\d[\s\-]*"
                r"\d[\s\-]*\d[\s\-]*\d[\s\-]*\d[\s\-]*\d[\s\-]*\d"), "Подозрение на номер карты"),
    # Номер телефона (RU/BY/KZ/AM/KG)
    (re.compile(r"(?:\+?[78]|(?:\+?374)|(?:\+?375)|(?:\+?7|8))"
                r"[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"), "Номер телефона"),
    # Ссылки Telegram
    (re.compile(r"t(?:elegram)?\.me\s*/\s*\+?[\w_]+", re.I), "Ссылка Telegram"),
    # @username (5+ символов)
    (re.compile(r"@[a-zа-яё0-9_]{4,}", re.I), "Контакт @username"),
    # Внешние ссылки
    (re.compile(r"https?://[^\s]+", re.I), "Внешняя ссылка"),
    (re.compile(r"(?:whatsapp|viber|wa\.me|vk\.com|bit\.ly|tinyurl|t\.co)/[\w\.]+", re.I), "Мессенджер/сокращатель"),
    # IBAN / SWIFT / крипто-адреса
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b"), "IBAN"),
    (re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b"), "Bitcoin адрес"),
    (re.compile(r"\b0x[a-fA-F0-9]{40}\b"), "Ethereum адрес"),
    # Упоминание .onion
    (re.compile(r"[a-z2-7]{16,}\.onion", re.I), "Onion-ссылка"),
    # Кодовые слова доставки наркотиков
    (re.compile(r"клад\s*\w{0,10}\s*\d", re.I), "Закладка"),
    (re.compile(r"прайс\s*[лl]ист", re.I), "Прайслист (подозрение)"),
]

# ── ФЛАГИ ПОВЫШЕННОГО РИСКА (совпадение сразу двух → блок) ───────────────────
_RISK_WORDS: List[str] = [
    "купить", "продам", "есть товар", "отправка", "доставка",
    "проверенный", "надёжный", "гарантия", "без кидалова",
]

_HIGH_RISK_COMBOS: List[Tuple[str, str]] = [
    # (слово_риска, слово_из_banned_context)
    ("купить", "соль"),
    ("продам", "соль"),
    ("купить", "кристалл"),
    ("доставка", "закладка"),
    ("гарантия", "качество товар"),
    ("надёжный", "поставщик"),
]


def _normalize(text: str) -> Tuple[str, str]:
    """
    Возвращает (text_leet_normalized, text_clean_no_separators).
    text_leet_normalized — строчный текст с заменой leet-символов.
    text_clean — только буквы/цифры (ловит п.и.з.д.а, х_у_й и т.д.).
    """
    t = text.lower()
    for sym, repl in _LEET.items():
        t = t.replace(sym, repl)
    clean = re.sub(r"[^а-яёa-z0-9]", "", t)
    return t, clean


def _contains_word(clean_text: str, word: str) -> bool:
    """Проверяет вхождение слова в очищенный текст (без разделителей)."""
    word_clean = re.sub(r"[^а-яёa-z0-9]", "", word.lower())
    return word_clean in clean_text


def anti_scam(text: str) -> Tuple[bool, str]:
    """
    Проверяет текст на запрещённый контент.
    Возвращает (True, причина) если найдено нарушение, иначе (False, "").
    """
    if not text or not text.strip():
        return False, ""

    normalized, clean = _normalize(text)

    # 1. Регулярные паттерны (номера карт, телефоны, ссылки, крипто и т.д.)
    for pattern, reason in _SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            return True, reason
        if pattern.search(normalized):
            return True, reason

    # 2. Запрещённые слова (проверяем в clean — ловит обходы через точки/дефисы)
    for word in BANNED_WORDS:
        if _contains_word(clean, word):
            return True, f"Запрещённое слово: «{word}»"

    # 3. Комбинированные риск-паттерны (например: "куплю" + "соль")
    for risk_word, banned_ctx in _HIGH_RISK_COMBOS:
        if _contains_word(clean, risk_word) and _contains_word(clean, banned_ctx):
            return True, f"Подозрительная комбинация: «{risk_word}» + «{banned_ctx}»"

    # 4. Слишком много заглавных букв — признак спама (>60% при длине >10 символов)
    letters = [c for c in text if c.isalpha()]
    if len(letters) > 10:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.65:
            return True, "Слишком много заглавных букв (спам)"

    # 5. Повторяющиеся символы (ааааа, !!!!!!) — спам-паттерн
    if re.search(r"(.)\1{5,}", text):
        return True, "Спам-символы (повторение)"

    # 6. Чрезмерное количество эмодзи (>10) — признак спама
    emoji_count = len(re.findall(
        r"[\U0001F300-\U0001FFFF\U00002600-\U000027BF]", text
    ))
    if emoji_count > 10:
        return True, "Слишком много эмодзи (спам)"

    return False, ""


def anti_scam_price(price: float) -> Tuple[bool, str]:
    """Дополнительная проверка цены на подозрительные значения."""
    if price <= 0:
        return True, "Цена должна быть больше нуля"
    if price > 100_000:
        return True, "Цена превышает допустимый максимум ($100 000)"
    # Подозрительно круглые суммы с пометкой "бесплатно"
    return False, ""

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referrer_id = None
    if args:
        if args[0].startswith("ref"):
            try:
                referrer_id = int(args[0][3:])
            except ValueError:
                pass
        elif args[0].startswith("contact_"):
            # Пользователь перешёл по ссылке "Написать продавцу"
            try:
                seller_id = int(args[0][8:])
                seller = db.get_user(seller_id)
                if seller and seller.get("username"):
                    # Уведомляем продавца
                    try:
                        buyer = update.effective_user
                        buyer_link = f"@{buyer.username}" if buyer.username else buyer.full_name
                        await context.bot.send_message(
                            seller_id,
                            f"👀 НОВЫЙ ПОКУПАТЕЛЬ!\n\n"
                            f"Пользователь {buyer_link} хочет купить ваш товар.\n"
                            f"Он написал вам в личные сообщения!"
                        )
                    except Exception:
                        pass
                    await update.message.reply_text(
                        "💬 Связь с продавцом:\n@" + seller["username"],
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(
                                "💬 Открыть чат",
                                url=f"https://t.me/{seller['username']}"
                            )
                        ]])
                    )
                else:
                    await update.message.reply_text(
                        "⚠️ У продавца нет username. Напишите ему через поиск по ID."
                    )
                return
            except (ValueError, TypeError):
                pass

    profile = db.get_or_create_user(
        user.id, user.username or "", user.full_name or "", referrer_id
    )
    badge = db.get_badge(profile)
    vmark = db.get_verified_mark(profile)
    rating, rcnt = db.get_seller_rating(user.id)

    await update.message.reply_text(
        f"🛒 Добро пожаловать в TRECCC{vmark}\n"
        "━━━━━━━━━━━━━━━━\n"
        "Первый безопасный маркетплейс для стран ЕАЭС\n"
        "🇷🇺 🇧🇾 🇰🇿 🇦🇲 🇰🇬\n\n"
        f"💼 Статус: {badge or '🆕 Новичок'}\n"
        f"⭐ Рейтинг: {stars_rating_str(rating, rcnt)}\n"
        f"📦 Объявлений: {profile.get('deals_seller', 0)}\n"
        "Выберите действие:",
        reply_markup=MAIN_KBD,
    )


# ── ПРОФИЛЬ ───────────────────────────────────────────────────────────────────
async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    profile = db.get_user(user.id)
    if not profile:
        await update.message.reply_text("Профиль не найден. Нажмите /start")
        return
    badge = db.get_badge(profile)
    vmark = db.get_verified_mark(profile)
    rating, rcnt = db.get_seller_rating(user.id)
    ref_link = f"https://t.me/{context.bot.username}?start=ref{user.id}"

    await update.message.reply_text(
        f"👤 МОЙ ПРОФИЛЬ\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Имя: {user.full_name}{vmark}\n"
        f"Статус: {badge or '🆕 Новичок'}\n"
        f"⭐ Рейтинг: {stars_rating_str(rating, rcnt)}\n"
        f"📦 Объявлений: {profile.get('deals_seller', 0)}\n"
        f"👥 Рефералов: {profile.get('referral_count', 0)}\n\n"
        f"🔗 Реферальная ссылка:\n{ref_link}",
        reply_markup=MAIN_KBD,
    )


# ── МОИ ОБЪЯВЛЕНИЯ ────────────────────────────────────────────────────────────
async def my_ads_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ads = db.get_user_ads(user_id)
    if not ads:
        await update.message.reply_text(
            "📋 У вас нет объявлений.\n\nСоздать: /new",
            reply_markup=MAIN_KBD,
        )
        return

    await update.message.reply_text(
        f"📋 МОИ ОБЪЯВЛЕНИЯ — {len(ads)} шт.",
        reply_markup=MAIN_KBD,
    )

    status_map = {"pending": "⏳ На модерации", "approved": "✅ Опубликовано", "rejected": "❌ Отклонено"}
    for ad in ads:
        p = ad.get("price_usd", 0)
        status = status_map.get(ad.get("status", ""), "❓")
        ad_id = ad.get("id", 0)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💥 BOOST", callback_data=f"boost_menu_{user_id}"),
             InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_ad_{ad_id}")],
        ])
        media = ad.get("media", [])
        text = (
            f"📦 {ad['name'].upper()}\n"
            f"💵 ${p:.2f} | 📍 {ad['country']}\n"
            f"📊 {status}"
        )
        if media and media[0]["type"] == "photo":
            await update.message.reply_photo(
                photo=media[0]["file_id"], caption=text, reply_markup=kb
            )
        else:
            await update.message.reply_text(text, reply_markup=kb)


# ── РЕФЕРАЛЫ ─────────────────────────────────────────────────────────────────
# referrals_cmd — перенесена выше


# ── КАК ЭТО РАБОТАЕТ ─────────────────────────────────────────────────────────
async def how_it_works(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Оплата и Stars", callback_data="how_payment")],
        [InlineKeyboardButton("🚚 Доставка в ЕАЭС", callback_data="how_delivery")],
        [InlineKeyboardButton("💥 Что такое BOOST?", callback_data="how_boost")],
    ])
    await update.message.reply_text(
        "🛒 КАК РАБОТАЕТ TRECCC\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "TRECCC — маркетплейс объявлений для стран\n"
        "🇷🇺 Россия  🇧🇾 Беларусь  🇰🇿 Казахстан  🇦🇲 Армения  🇰🇬 Кыргызстан\n\n"
        "Здесь продавцы и покупатели находят друг друга\n"
        "и договариваются НАПРЯМУЮ — без посредников.\n\n"
        "📋 ПОШАГОВО:\n\n"
        "1️⃣ Продавец создаёт объявление (/new)\n"
        "   Указывает товар, фото, цену в USD\n\n"
        "2️⃣ Модерация (обычно 5–30 минут)\n"
        "   Проверяем что всё по правилам\n\n"
        "3️⃣ Объявление выходит в канале\n"
        "   Тысячи покупателей видят ваш товар\n\n"
        "4️⃣ Покупатель нажимает «Написать продавцу»\n"
        "   Общение напрямую в Telegram\n\n"
        "5️⃣ Договариваетесь об условиях и доставке\n"
        "   Цена, способ отправки — всё между вами\n\n"
        "6️⃣ Оплата — любым удобным способом\n"
        "   Наличные, перевод, Stars — решаете сами\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🎁 Создание объявлений — БЕСПЛАТНО!\n\n"
        "📦 Трекинг посылок: /track <номер>",
        reply_markup=kb,
    )


# ── BOOST МЕНЮ ────────────────────────────────────────────────────────────────
async def boost_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ad = db.get_ad(user_id)

    if not ad or ad.get("status") != "approved":
        await update.message.reply_text(
            "💥 BOOST\n\n"
            "⚠️ У вас нет опубликованного объявления.\n"
            "Сначала создайте и опубликуйте объявление: /new",
            reply_markup=MAIN_KBD,
        )
        return

    await _send_boost_menu(update.message, user_id, ad)


async def _send_boost_menu(message, user_id: int, ad: dict):
    p = ad.get("price_usd", 0)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🔥 Выделение — {BOOST_HIGHLIGHT_STARS} ⭐",
            callback_data=f"boost_buy_highlight_{user_id}"
        )],
        [InlineKeyboardButton(
            f"📌 Закреп 24ч — {BOOST_PIN_STARS} ⭐",
            callback_data=f"boost_buy_pin_{user_id}"
        )],
        [InlineKeyboardButton(
            f"📢 Повтор через 24ч — {BOOST_STORY_STARS} ⭐",
            callback_data=f"boost_buy_story_{user_id}"
        )],
        [InlineKeyboardButton(
            f"⚡ ВСЁ СРАЗУ — {BOOST_ALL_STARS} ⭐  (скидка 20%)",
            callback_data=f"boost_buy_all_{user_id}"
        )],
    ])
    await message.reply_text(
        "💥 BOOST — УСКОРЬ ПРОДАЖУ\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"Ваш товар: {ad['name'].upper()}\n"
        f"💵 ${p:.2f}\n\n"
        f"🔥 ВЫДЕЛЕНИЕ — {BOOST_HIGHLIGHT_STARS} ⭐\n"
        "Объявление переиздаётся с VIP-оформлением:\n"
        "огонь, рамка, пометка «ВИП ОБЪЯВЛЕНИЕ»\n\n"
        f"📌 ЗАКРЕП НА 24 ЧАСА — {BOOST_PIN_STARS} ⭐\n"
        "Ваше объявление закрепляется вверху канала\n"
        "на 24 часа — все видят его первым\n\n"
        f"📢 ПОВТОР ЧЕРЕЗ 24Ч — {BOOST_STORY_STARS} ⭐\n"
        "Объявление переопубликуется автоматически\n"
        "через 24 часа — снова в топе ленты\n\n"
        f"⚡ ВСЁ СРАЗУ — {BOOST_ALL_STARS} ⭐\n"
        "Выделение + Закреп + Повтор через 24ч\n"
        "Скидка 20% от общей суммы! 🔥\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "Выберите тип BOOST:",
        reply_markup=kb,
    )


# ── BOOST ОПЛАТА ──────────────────────────────────────────────────────────────
BOOST_TYPES = {
    "highlight": (BOOST_HIGHLIGHT_STARS, "🔥 Выделение объявления"),
    "pin":       (BOOST_PIN_STARS,       "📌 Закреп на 24 часа"),
    "story":     (BOOST_STORY_STARS,     "📢 Повтор публикации через 24ч"),
    "all":       (BOOST_ALL_STARS,       "⚡ Всё сразу (скидка 20%)"),
    "verify":    (VERIFY_STARS,            "✅ Верификация продавца"),
}


async def boost_buy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет invoice на оплату BOOST."""
    query = update.callback_query
    await query.answer()

    # callback: boost_buy_highlight_123456
    parts = query.data.split("_")
    boost_type = parts[2]   # highlight / pin / story
    user_id = int(parts[3])

    if boost_type not in BOOST_TYPES:
        await query.edit_message_text("Неизвестный тип BOOST.")
        return

    stars, label = BOOST_TYPES[boost_type]

    try:
        await context.bot.send_invoice(
            chat_id=user_id,
            title=label,
            description=f"BOOST для вашего объявления на TRECCC",
            payload=f"boost_{boost_type}_{user_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=label, amount=stars)],
        )
        await query.edit_message_text(
            f"⭐ Счёт на {stars} Stars отправлен!\n"
            "Найдите его выше в чате и оплатите."
        )
    except Exception as e:
        await query.edit_message_text(f"Ошибка: {e}")


# ── BOOST ПОСЛЕ ОПЛАТЫ ────────────────────────────────────────────────────────
async def _apply_boost_highlight(context, user_id: int):
    """Переиздаёт объявление с VIP-оформлением."""
    ad = db.get_ad(user_id)
    if not ad:
        return
    seller = db.get_user(user_id)
    text = build_ad_text(ad, seller, boosted=True)

    bot_info = await context.bot.get_me()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "💬 Написать продавцу",
            url=seller_contact_url(seller, user_id)
        )],
        [InlineKeyboardButton("🚩 Пожаловаться", callback_data=f"report_{user_id}")],
    ])

    media = ad.get("media", [])
    try:
        if len(media) == 1:
            m = media[0]
            if m["type"] == "photo":
                await context.bot.send_photo(CHANNEL_PUBLIC, photo=m["file_id"],
                                             caption=text, reply_markup=keyboard)
            else:
                await context.bot.send_video(CHANNEL_PUBLIC, video=m["file_id"],
                                             caption=text, reply_markup=keyboard)
        elif len(media) > 1:
            mg = []
            for i, m in enumerate(media[:10]):
                cap = text if i == 0 else None
                if m["type"] == "photo":
                    mg.append(InputMediaPhoto(media=m["file_id"], caption=cap))
                else:
                    mg.append(InputMediaVideo(media=m["file_id"], caption=cap))
            await context.bot.send_media_group(CHANNEL_PUBLIC, media=mg)
            await context.bot.send_message(CHANNEL_PUBLIC, "👆 VIP объявление", reply_markup=keyboard)
        else:
            await context.bot.send_message(CHANNEL_PUBLIC, text=text, reply_markup=keyboard)

        await context.bot.send_message(
            user_id,
            "🔥 BOOST «Выделение» активирован!\n"
            "Ваше VIP-объявление опубликовано в канале."
        )
    except Exception as e:
        print(f"[boost highlight] {e}")


async def _apply_boost_pin(context, user_id: int):
    """Публикует объявление и закрепляет его в канале."""
    ad = db.get_ad(user_id)
    if not ad:
        return
    seller = db.get_user(user_id)
    text = build_ad_text(ad, seller, boosted=False)

    bot_info = await context.bot.get_me()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "💬 Написать продавцу",
            url=seller_contact_url(seller, user_id)
        )],
        [InlineKeyboardButton("🚩 Пожаловаться", callback_data=f"report_{user_id}")],
    ])

    try:
        media = ad.get("media", [])
        if media and media[0]["type"] == "photo":
            msg = await context.bot.send_photo(
                CHANNEL_PUBLIC, photo=media[0]["file_id"],
                caption="📌 " + text, reply_markup=keyboard
            )
        elif media and media[0]["type"] == "video":
            msg = await context.bot.send_video(
                CHANNEL_PUBLIC, video=media[0]["file_id"],
                caption="📌 " + text, reply_markup=keyboard
            )
        else:
            msg = await context.bot.send_message(
                CHANNEL_PUBLIC, text="📌 " + text, reply_markup=keyboard
            )

        # Закрепляем сообщение
        await context.bot.pin_chat_message(
            chat_id=CHANNEL_PUBLIC,
            message_id=msg.message_id,
            disable_notification=True,
        )

        # Планируем открепление через 24 часа
        context.job_queue.run_once(
            _unpin_message,
            when=86400,
            data={"chat_id": CHANNEL_PUBLIC, "message_id": msg.message_id},
            name=f"unpin_{msg.message_id}",
        )

        await context.bot.send_message(
            user_id,
            "📌 BOOST «Закреп» активирован!\n"
            "Ваше объявление закреплено в канале на 24 часа."
        )
    except Exception as e:
        print(f"[boost pin] {e}")
        await context.bot.send_message(
            user_id,
            f"⚠️ Ошибка закрепления: {e}\n"
            "Убедитесь что бот является администратором канала."
        )


async def _unpin_message(context: ContextTypes.DEFAULT_TYPE):
    """Открепляет сообщение через 24ч."""
    data = context.job.data
    try:
        await context.bot.unpin_chat_message(
            chat_id=data["chat_id"],
            message_id=data["message_id"],
        )
    except Exception as e:
        print(f"[unpin] {e}")


async def _apply_boost_story(context, user_id: int):
    """Планирует повторную публикацию объявления через 24 часа."""
    ad = db.get_ad(user_id)
    if not ad:
        return

    await context.bot.send_message(
        user_id,
        "📢 BOOST «Повтор через 24ч» оплачен!\n\n"
        "Через 24 часа ваше объявление автоматически\n"
        "переопубликуется в канале — снова в топе ленты.\n\n"
        "Спасибо за использование BOOST! 🚀"
    )

    # Планируем повтор через 24 часа
    context.job_queue.run_once(
        _republish_ad,
        when=86400,
        data={"user_id": user_id},
        name=f"republish_{user_id}",
    )


async def _republish_ad(context: ContextTypes.DEFAULT_TYPE):
    """Повторно публикует объявление в канале."""
    user_id = context.job.data["user_id"]
    ad = db.get_ad(user_id)
    seller = db.get_user(user_id)
    if not ad or not seller:
        return

    text = build_ad_text(ad, seller, boosted=False)
    bot_info = await context.bot.get_me()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Написать продавцу",
                              url=seller_contact_url(seller, user_id))],
        [InlineKeyboardButton("🤍 В избранное",
                              callback_data=f"fav_add_{ad.get('id', user_id)}")],
        [InlineKeyboardButton("🚩 Пожаловаться",
                              callback_data=f"report_{user_id}")],
    ])
    try:
        media = ad.get("media", [])
        if len(media) == 1:
            m = media[0]
            if m["type"] == "photo":
                await context.bot.send_photo(CHANNEL_PUBLIC, photo=m["file_id"],
                                             caption="🔄 " + text, reply_markup=keyboard)
            else:
                await context.bot.send_video(CHANNEL_PUBLIC, video=m["file_id"],
                                             caption="🔄 " + text, reply_markup=keyboard)
        elif len(media) > 1:
            mg = [InputMediaPhoto(media=media[0]["file_id"], caption="🔄 " + text)]
            for m in media[1:10]:
                mg.append(InputMediaPhoto(media=m["file_id"]) if m["type"] == "photo"
                          else InputMediaVideo(media=m["file_id"]))
            await context.bot.send_media_group(CHANNEL_PUBLIC, media=mg)
        else:
            await context.bot.send_message(CHANNEL_PUBLIC, text="🔄 " + text,
                                           reply_markup=keyboard)
        await context.bot.send_message(user_id,
                                       "✅ Ваше объявление переопубликовано в канале!")
    except Exception as e:
        print(f"[republish] {e}")


# ── СОГЛАШЕНИЕ ────────────────────────────────────────────────────────────────
async def _show_terms(update: Update):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Принимаю", callback_data="agree_terms")],
        [InlineKeyboardButton("❌ Не принимаю", callback_data="disagree_terms")],
    ])
    await update.message.reply_text(TERMS_TEXT, reply_markup=keyboard)


# ── СОЗДАНИЕ ОБЪЯВЛЕНИЯ ───────────────────────────────────────────────────────
async def new_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.has_agreed_terms(user.id):
        context.user_data["after_terms"] = "new_ad"
        await _show_terms(update)
        return ConversationHandler.END
    context.user_data["new_ad"] = {}
    await update.message.reply_text(
        "📦 НОВОЕ ОБЪЯВЛЕНИЕ\n"
        "━━━━━━━━━━━━━━━━\n"
        "Шаг 1 из 6\n\n"
        "Введите название товара:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NAME


async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if len(text) < 3:
        await update.message.reply_text("⚠️ Название слишком короткое:")
        return NAME
    is_bad, reason = anti_scam(text)
    if is_bad:
        await update.message.reply_text(f"⚠️ {reason}\nПопробуйте снова:")
        return NAME
    context.user_data["new_ad"]["name"] = text
    await update.message.reply_text("Шаг 2 из 6\n\n📝 Введите описание товара:")
    return DESC


async def desc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    is_bad, reason = anti_scam(text)
    if is_bad:
        await update.message.reply_text(f"⚠️ {reason}\nПопробуйте снова:")
        return DESC
    context.user_data["new_ad"]["description"] = text
    await update.message.reply_text(
        "Шаг 3 из 6\n\n"
        "💰 Укажите цену в USD:\n"
        "Например: 25 или 150.50\n(Минимум $1)"
    )
    return PRICE


async def price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".").replace("$", "").replace(" ", "")
    try:
        price = float(text)
    except ValueError:
        await update.message.reply_text("⚠️ Введите число, например: 50 или 12.99")
        return PRICE
    if price < 1:
        await update.message.reply_text("⚠️ Минимум $1:")
        return PRICE
    if price > 100000:
        await update.message.reply_text("⚠️ Максимум $100 000:")
        return PRICE
    context.user_data["new_ad"]["price_usd"] = round(price, 2)
    await update.message.reply_text(
        f"💵 Цена: ${price:.2f}\n\n"
        f"📊 Покупатели увидят:\n{price_in_eaeu(price)}\n\n"
        "Шаг 4 из 6\n\n📍 Выберите страну:",
        reply_markup=COUNTRY_KBD,
    )
    return COUNTRY


async def country_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_ad"]["country"] = update.message.text
    await update.message.reply_text(
        "Шаг 5 из 6\n\n🚚 Возможна ли доставка?",
        reply_markup=DELIVERY_KBD,
    )
    return DELIVERY


async def delivery_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_ad"]["delivery"] = update.message.text
    context.user_data["new_ad"]["media"] = []
    await update.message.reply_text(
        "Шаг 6 из 6\n\n"
        "📷 Добавьте фото или видео (до 10 файлов, видео до 15 сек).\n\n"
        "➡️ Если фото нет — сразу нажмите «✅ Закончить»",
        reply_markup=FINISH_KBD,
    )
    return MEDIA


async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and "Закончить" in update.message.text:
        return await _finish_ad(update, context)
    media_list = context.user_data["new_ad"].get("media", [])
    if len(media_list) >= 10:
        await update.message.reply_text("⚠️ Максимум 10 файлов.", reply_markup=FINISH_KBD)
        return MEDIA
    if update.message.photo:
        media_list.append({"type": "photo", "file_id": update.message.photo[-1].file_id})
        context.user_data["new_ad"]["media"] = media_list
        await update.message.reply_text(
            f"✅ Фото {len(media_list)} добавлено. Ещё или «✅ Закончить»",
            reply_markup=FINISH_KBD,
        )
    elif update.message.video:
        if update.message.video.duration > 15:
            await update.message.reply_text("⚠️ Видео до 15 секунд.", reply_markup=FINISH_KBD)
            return MEDIA
        media_list.append({"type": "video", "file_id": update.message.video.file_id})
        context.user_data["new_ad"]["media"] = media_list
        await update.message.reply_text(
            f"✅ Видео {len(media_list)} добавлено. Ещё или «✅ Закончить»",
            reply_markup=FINISH_KBD,
        )
    else:
        await update.message.reply_text(
            "Отправьте фото/видео или нажмите «✅ Закончить»",
            reply_markup=FINISH_KBD,
        )
    return MEDIA


async def finish_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _finish_ad(update, context)


async def cancel_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена создания объявления — возврат в главное меню."""
    context.user_data.pop("new_ad", None)
    await update.message.reply_text(
        "❌ Создание объявления отменено.\n\nВыберите действие:",
        reply_markup=MAIN_KBD,
    )
    return ConversationHandler.END


async def _finish_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ad = context.user_data.get("new_ad", {})
    if not ad.get("name"):
        await update.message.reply_text("Что-то пошло не так. Начните заново: /new", reply_markup=MAIN_KBD)
        return ConversationHandler.END
    await _save_and_send_ad(update, context, ad)
    return ConversationHandler.END


async def _save_and_send_ad(update: Update, context: ContextTypes.DEFAULT_TYPE, ad: dict):
    user = update.effective_user
    db.save_ad(user.id, ad)
    await send_ad_to_admin(update, context, ad)
    p = ad.get("price_usd", 0)
    await update.message.reply_text(
        "✅ ОБЪЯВЛЕНИЕ ОТПРАВЛЕНО НА МОДЕРАЦИЮ!\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📦 {ad['name'].upper()}\n"
        + (f"📝 {ad['description']}\n" if ad.get("description") else "") +
        f"📍 {ad['country']}  🚚 {ad['delivery']}\n\n"
        f"💵 ${p:.2f}\n"
        f"📊 В валютах ЕАЭС:\n{price_in_eaeu(p)}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📷 Медиа: {len(ad.get('media', []))} шт.\n\n"
        "⏱ Модерация: 5–30 минут.\n"
        "После публикации придёт уведомление.\n\n"
        "💥 Хотите ускорить продажу? Используйте BOOST!",
        reply_markup=MAIN_KBD,
    )


# ── ОПЛАТА ПУБЛИКАЦИИ ─────────────────────────────────────────────────────────
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    user = update.effective_user

    # Оплата публикации
    if payload.startswith("publish_"):
        ad = context.user_data.get("pending_ad")
        if not ad:
            await update.message.reply_text(
                "⚠️ Оплата получена, но объявление не найдено.\n"
                "Создайте заново: /new"
            )
            return
        context.user_data.pop("pending_ad", None)
        await _save_and_send_ad(update, context, ad)
        return

    # Оплата BOOST
    if payload.startswith("boost_"):
        parts = payload.split("_")
        boost_type = parts[1]   # highlight / pin / story
        user_id = int(parts[2])

        if boost_type == "highlight":
            await _apply_boost_highlight(context, user_id)
        elif boost_type == "pin":
            await _apply_boost_pin(context, user_id)
        elif boost_type == "story":
            await _apply_boost_story(context, user_id)
        elif boost_type == "all":
            await _apply_boost_highlight(context, user_id)
            await _apply_boost_pin(context, user_id)
            await _apply_boost_story(context, user_id)
        return


# ── ПОИСК ─────────────────────────────────────────────────────────────────────
async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🔍 Используйте:\n/search кроссовки\n/search куртка Казахстан"
        )
        return
    query_text = " ".join(context.args)
    results = db.search_ads(query_text)
    if not results:
        await update.message.reply_text(f"🔍 По «{query_text}» ничего не найдено.")
        return
    await update.message.reply_text(f"🔍 Найдено: {len(results)} по «{query_text}»")
    for ad in results[:5]:
        sp = db.get_user(ad["user_id"])
        vmark = db.get_verified_mark(sp) if sp else ""
        rating, rcnt = db.get_seller_rating(ad["user_id"])
        p = ad.get("price_usd", 0)
        text = (
            f"📦 {ad['name'].upper()}\n"
            + (f"📝 {ad['description']}\n" if ad.get("description") else "") +
            f"📍 {ad['country']}  🚚 {ad['delivery']}\n"
            f"💵 ${p:.2f}\n"
            f"⭐ {stars_rating_str(rating, rcnt)}{vmark}"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 Написать продавцу",
                                 url=seller_contact_url(db.get_user(ad["user_id"]), ad["user_id"]))
        ]])
        media = ad.get("media", [])
        if media and media[0]["type"] == "photo":
            await update.message.reply_photo(photo=media[0]["file_id"], caption=text, reply_markup=kb)
        else:
            await update.message.reply_text(text, reply_markup=kb)




# ── ОТЗЫВЫ ────────────────────────────────────────────────────────────────────
async def leave_review_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало оставления отзыва: /review USER_ID"""
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "Использование: /review USER_ID\n"
            "Пример: /review 123456789"
        )
        return ConversationHandler.END
    try:
        seller_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID продавца.")
        return ConversationHandler.END
    if seller_id == user.id:
        await update.message.reply_text("Нельзя оставить отзыв себе.")
        return ConversationHandler.END
    seller = db.get_user(seller_id)
    if not seller:
        await update.message.reply_text("Продавец не найден.")
        return ConversationHandler.END
    context.user_data["review_seller_id"] = seller_id
    context.user_data["review_seller_name"] = seller.get("full_name", str(seller_id))
    kb = ReplyKeyboardMarkup(
        [["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]],
        one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        f"📝 ОТЗЫВ О ПРОДАВЦЕ\n{seller.get('full_name', '')}\n\n"
        "Выберите оценку:",
        reply_markup=kb
    )
    return REVIEW_RATING


async def review_rating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stars = update.message.text.count("⭐")
    if stars < 1 or stars > 5:
        await update.message.reply_text("Выберите от 1 до 5 звёзд:")
        return REVIEW_RATING
    context.user_data["review_rating"] = stars
    await update.message.reply_text(
        f"Оценка: {'⭐' * stars}\n\n"
        "Напишите текст отзыва (или /skip чтобы пропустить):",
        reply_markup=ReplyKeyboardRemove()
    )
    return REVIEW_TEXT


async def review_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip() if update.message.text != "/skip" else ""
    seller_id = context.user_data["review_seller_id"]
    rating = context.user_data["review_rating"]
    db.add_review(seller_id, update.effective_user.id, rating, text)
    seller = db.get_user(seller_id)
    # Уведомляем продавца
    try:
        buyer_name = update.effective_user.full_name
        await context.bot.send_message(
            seller_id,
            f"⭐ НОВЫЙ ОТЗЫВ\n\n"
            f"От: {buyer_name}\n"
            f"Оценка: {'⭐' * rating}\n"
            + (f"Текст: {text}" if text else "")
        )
    except Exception:
        pass
    avg, cnt = db.get_seller_rating(seller_id)
    await update.message.reply_text(
        f"✅ Отзыв отправлен!\n\n"
        f"Новый рейтинг продавца: ⭐{avg:.1f} ({cnt} отзывов)",
        reply_markup=MAIN_KBD
    )
    return ConversationHandler.END


async def review_skip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await review_text_handler(update, context)


# ── ВЕРИФИКАЦИЯ ───────────────────────────────────────────────────────────────
async def verify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = db.get_user(user_id)
    if profile and profile.get("verified"):
        await update.message.reply_text(
            "✅ Ваш аккаунт уже верифицирован!\n\n"
            "Значок ✅ отображается рядом с вашим именем.",
            reply_markup=MAIN_KBD
        )
        return ConversationHandler.END

    verif = db.get_verification(user_id)
    if verif and verif.get("status") == "pending":
        await update.message.reply_text(
            "⏳ Ваша заявка уже на рассмотрении.\n"
            "Обычно проверка занимает до 24 часов.",
            reply_markup=MAIN_KBD
        )
        return ConversationHandler.END

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"✅ Оплатить верификацию — {VERIFY_STARS} ⭐",
            callback_data=f"pay_verify_{user_id}"
        )
    ]])
    await update.message.reply_text(
        "✅ ВЕРИФИКАЦИЯ ПРОДАВЦА\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Верифицированные продавцы получают:\n"
        "• Значок ✅ рядом с именем\n"
        "• Приоритет в поиске\n"
        "• Больше доверия покупателей\n\n"
        "Процесс:\n"
        "1️⃣ Оплатите верификацию\n"
        "2️⃣ Отправьте фото документа\n"
        "3️⃣ Администратор проверит (до 24ч)\n"
        "4️⃣ Получите значок ✅\n\n"
        f"Стоимость: {VERIFY_STARS} ⭐ Stars",
        reply_markup=kb
    )
    return ConversationHandler.END


async def verify_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем фото документа после оплаты верификации."""
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text(
            "Отправьте фото документа (паспорт, ID-карта):",
        )
        return VERIFY_PHOTO

    photo_id = update.message.photo[-1].file_id
    db.save_verification(user.id, photo_id)

    # Отправляем админу
    try:
        await context.bot.send_photo(
            ADMIN_ID,
            photo=photo_id,
            caption=(
                f"✅ ЗАЯВКА НА ВЕРИФИКАЦИЮ\n\n"
                f"👤 {user.full_name}\n"
                f"🆔 ID: {user.id}\n"
                f"@{user.username or 'нет username'}\n\n"
                f"Подтвердить: /setverified {user.id}\n"
                f"Отклонить: /rejectverify {user.id}"
            )
        )
    except Exception as e:
        print(f"[verify] {e}")

    await update.message.reply_text(
        "✅ Документ отправлен на проверку!\n\n"
        "Администратор рассмотрит заявку в течение 24 часов.\n"
        "Вы получите уведомление о результате.",
        reply_markup=MAIN_KBD
    )
    return ConversationHandler.END


# ── ТОП ПРОДАВЦОВ ─────────────────────────────────────────────────────────────
async def top_sellers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sellers = db.get_top_sellers(10)
    if not sellers:
        await update.message.reply_text("Пока нет продавцов с отзывами.", reply_markup=MAIN_KBD)
        return
    text = "🏆 ТОП ПРОДАВЦОВ TRECCC\n━━━━━━━━━━━━━━━━\n\n"
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    for i, s in enumerate(sellers):
        vmark = " ✅" if s.get("verified") else ""
        username = f"@{s['username']}" if s.get("username") else s.get("full_name", "?")
        rating = s.get("avg_rating", 0)
        cnt = s.get("review_count", 0)
        deals = s.get("deals_seller", 0)
        text += (
            f"{medals[i]} {username}{vmark}\n"
            f"   ⭐ {rating:.1f} ({cnt} отзывов) | 📦 {deals} сделок\n\n"
        )
    await update.message.reply_text(text, reply_markup=MAIN_KBD)


# ── РЕФЕРАЛЬНЫЕ БОНУСЫ ────────────────────────────────────────────────────────
async def referrals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = db.get_user(user_id)
    count = profile.get("referral_count", 0) if profile else 0
    boosts = db.get_referral_boosts(user_id)
    link = f"https://t.me/{context.bot.username}?start=ref{user_id}"
    next_bonus = REF_BONUS_THRESHOLD - (count % REF_BONUS_THRESHOLD)
    await update.message.reply_text(
        "👥 РЕФЕРАЛЬНАЯ ПРОГРАММА\n\n"
        f"Ваша ссылка:\n{link}\n\n"
        f"Приглашено: {count} пользователей\n"
        f"🎁 Бесплатных BOOST: {boosts}\n\n"
        f"До следующего бонуса: {next_bonus} чел.\n\n"
        f"За каждые {REF_BONUS_THRESHOLD} приглашённых —\n"
        "1 бесплатный BOOST любого типа!\n\n"
        "Используй: /freeboost",
        reply_markup=MAIN_KBD,
    )


async def free_boost_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    boosts = db.get_referral_boosts(user_id)
    if boosts < 1:
        profile = db.get_user(user_id)
        count = profile.get("referral_count", 0) if profile else 0
        need = REF_BONUS_THRESHOLD - (count % REF_BONUS_THRESHOLD)
        await update.message.reply_text(
            f"❌ У вас нет бесплатных BOOST.\n\n"
            f"Пригласите ещё {need} друзей по реферальной ссылке!",
            reply_markup=MAIN_KBD
        )
        return
    ad = db.get_ad(user_id, status="approved")
    if not ad:
        await update.message.reply_text(
            "⚠️ Нет опубликованного объявления.\nСначала создайте: /new",
            reply_markup=MAIN_KBD
        )
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Выделение", callback_data=f"freeboost_highlight_{user_id}")],
        [InlineKeyboardButton("📌 Закреп 24ч", callback_data=f"freeboost_pin_{user_id}")],
        [InlineKeyboardButton("📢 Повтор через 24ч", callback_data=f"freeboost_story_{user_id}")],
    ])
    await update.message.reply_text(
        f"🎁 У вас {boosts} бесплатных BOOST!\n\n"
        "Выберите тип:",
        reply_markup=kb
    )

# ── ТРЕКИНГ ПОСЫЛОК ───────────────────────────────────────────────────────────
async def track_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отслеживание посылки по трек-номеру через track24.ru."""
    if not context.args:
        await update.message.reply_text(
            "📦 ОТСЛЕЖИВАНИЕ ПОСЫЛКИ\n\n"
            "Используйте:\n"
            "/track RA123456789RU\n\n"
            "Поддерживаются все почты ЕАЭС:\n"
            "🇷🇺 Почта России  🇧🇾 Белпочта\n"
            "🇰🇿 Казпочта  🇦🇲 ХайПост  🇰🇬 Кыргыз Почтасы\n"
            "🚀 СДЭК, Boxberry и другие"
        )
        return

    track_number = context.args[0].strip().upper()
    await update.message.reply_text(f"🔍 Ищу посылку {track_number}...")

    try:
        import aiohttp
        url = f"https://track24.ru/api/v1/track/{track_number}"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    events = data.get("events") or data.get("data") or []
                    if events:
                        lines = [f"📦 ПОСЫЛКА: {track_number}\n━━━━━━━━━━━━━━━━"]
                        for ev in events[:8]:
                            date = ev.get("date") or ev.get("time") or ""
                            status = ev.get("status") or ev.get("description") or ""
                            place = ev.get("place") or ev.get("location") or ""
                            line = f"\n📍 {date}"
                            if place:
                                line += f"\n   {place}"
                            if status:
                                line += f"\n   {status}"
                            lines.append(line)
                        await update.message.reply_text("\n".join(lines))
                        return
    except Exception as e:
        print(f"[track] {e}")

    # Fallback — ссылка на track24
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Отследить на track24.ru",
                              url=f"https://track24.ru/?code={track_number}")],
        [InlineKeyboardButton("📮 Почта России",
                              url=f"https://www.pochta.ru/tracking#{track_number}")],
        [InlineKeyboardButton("🚀 СДЭК",
                              url=f"https://www.cdek.ru/ru/tracking?order_id={track_number}")],
    ])
    await update.message.reply_text(
        f"📦 Трек-номер: {track_number}\n\n"
        "Нажмите кнопку для отслеживания:",
        reply_markup=keyboard,
    )


# ── ИЗБРАННОЕ ─────────────────────────────────────────────────────────────────
async def favorites_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    favs = db.get_favorites(user_id)
    if not favs:
        await update.message.reply_text(
            "🤍 ИЗБРАННОЕ\n\n"
            "Список пуст.\n\n"
            "Добавляйте объявления кнопкой\n"
            "«🤍 В избранное» прямо в канале!",
            reply_markup=MAIN_KBD,
        )
        return
    bot_info = await context.bot.get_me()
    await update.message.reply_text(
        f"❤️ ИЗБРАННОЕ — {len(favs)} объявлений:",
        reply_markup=MAIN_KBD,
    )
    for ad in favs:
        p = ad.get("price_usd", 0)
        eaeu = price_in_eaeu(p)
        sp = db.get_user(ad["user_id"])
        vmark = db.get_verified_mark(sp) if sp else ""
        text = (
            f"📦 {ad['name'].upper()}\n"
            + (f"📝 {ad['description']}\n" if ad.get("description") else "") +
            f"📍 {ad['country']}  🚚 {ad['delivery']}\n"
            f"💵 ${p:.2f}\n{eaeu}\n"
            f"{vmark}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Написать продавцу",
                                  url=seller_contact_url(db.get_user(ad["user_id"]), ad["user_id"]))],
            [InlineKeyboardButton("💔 Убрать из избранного",
                                  callback_data=f"fav_remove_{ad['id']}")],
        ])
        media = ad.get("media", [])
        if media and media[0]["type"] == "photo":
            await update.message.reply_photo(
                photo=media[0]["file_id"], caption=text, reply_markup=keyboard
            )
        else:
            await update.message.reply_text(text, reply_markup=keyboard)

# ── РАССЫЛКА (ТОЛЬКО ADMIN) ───────────────────────────────────────────────────
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "📢 РАССЫЛКА\n\nОтправьте текст. Или /skip для только медиа.",
        reply_markup=ReplyKeyboardRemove()
    )
    return BROADCAST_TEXT


async def broadcast_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["broadcast"] = {"text": update.message.text_html}
    await update.message.reply_text("Отправьте фото/видео или /skip")
    return BROADCAST_MEDIA


async def broadcast_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data["broadcast"]["media"] = {"type": "photo", "file_id": update.message.photo[-1].file_id}
    elif update.message.video:
        context.user_data["broadcast"]["media"] = {"type": "video", "file_id": update.message.video.file_id}
    else:
        await update.message.reply_text("Фото, видео или /skip")
        return BROADCAST_MEDIA
    return await _broadcast_preview(update, context)


async def broadcast_skip_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["broadcast"]["media"] = None
    return await _broadcast_preview(update, context)


async def _broadcast_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data["broadcast"]
    text = data.get("text", "")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Отправить всем", callback_data="broadcast_confirm")],
        [InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel")],
    ])
    m = data.get("media")
    if m and m["type"] == "photo":
        await update.message.reply_photo(photo=m["file_id"], caption="ПРЕДПРОСМОТР:\n\n" + text)
    elif m and m["type"] == "video":
        await update.message.reply_video(video=m["file_id"], caption="ПРЕДПРОСМОТР:\n\n" + text)
    else:
        await update.message.reply_text("ПРЕДПРОСМОТР:\n\n" + text)
    await update.message.reply_text("Подтвердите:", reply_markup=kb)
    return BROADCAST_CONFIRM


async def broadcast_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "broadcast_cancel":
        await query.edit_message_text("Рассылка отменена.")
        return ConversationHandler.END
    data = context.user_data.get("broadcast", {})
    users = db.get_all_users()
    sent = 0
    for uid in users:
        try:
            m = data.get("media")
            if m and m["type"] == "photo":
                await context.bot.send_photo(uid, photo=m["file_id"],
                                             caption=data.get("text", ""), parse_mode=ParseMode.HTML)
            elif m and m["type"] == "video":
                await context.bot.send_video(uid, video=m["file_id"],
                                             caption=data.get("text", ""), parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(uid, text=data.get("text", ""), parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Ошибка {uid}: {e}")
    await query.edit_message_text(f"✅ Рассылка завершена. Отправлено: {sent}")
    return ConversationHandler.END


# ── ОБРАБОТЧИК КНОПОК ─────────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # Соглашение
    if data == "agree_terms":
        db.set_agreed_terms(user_id)
        await query.edit_message_text("✅ Вы приняли условия использования.")
        if context.user_data.pop("after_terms", None) == "new_ad":
            context.user_data["new_ad"] = {}
            await context.bot.send_message(
                user_id,
                "📦 НОВОЕ ОБЪЯВЛЕНИЕ\n\nШаг 1 из 6\n\nВведите название товара:",
                reply_markup=ReplyKeyboardRemove()
            )
        return

    if data == "disagree_terms":
        await query.edit_message_text("❌ Без принятия условий работа невозможна.")
        return

    # Оплата публикации


    # BOOST меню из кнопки в "Мои объявления"
    if data.startswith("boost_menu_"):
        uid = int(data.replace("boost_menu_", ""))
        ad = db.get_ad(uid)
        if ad:
            await _send_boost_menu(query.message, uid, ad)
        return

    # BOOST покупка
    if data.startswith("boost_buy_"):
        await boost_buy_handler(update, context)
        return

    # Удалить своё объявление
    if data.startswith("delete_my_ad_"):
        uid = int(data.replace("delete_my_ad_", ""))
        if uid != user_id:
            return
        db.delete_ad(uid)
        await query.edit_message_text("🗑 Объявление удалено.")
        return

    # Инфо кнопки
    if data == "how_payment":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="how_back")]])
        await query.edit_message_text(
            "💰 ОПЛАТА И TELEGRAM STARS\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🎁 Первое объявление — БЕСПЛАТНО\n"
            "ЦЕНА ТОВАРА в USD:\n"
            "В объявлении автоматически показывается\n"
            "эквивалент в RUB, BYN, KZT, AMD, KGS.\n\n"
            "Расчёты с покупателем — напрямую.",
            reply_markup=kb
        )
        return

    if data == "how_delivery":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="how_back")]])
        await query.edit_message_text(
            "🚚 ДОСТАВКА В ЕАЭС\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "TRECCC — только площадка для объявлений.\n"
            "Продавец и покупатель договариваются\n"
            "о доставке НАПРЯМУЮ между собой.\n\n"
            "📮 ПОЧТОВЫЕ СЛУЖБЫ ЕАЭС:\n"
            "🇷🇺 Почта России — pochta.ru\n"
            "🇧🇾 Белпочта — belpost.by\n"
            "🇰🇿 Казпочта — kazpost.kz\n"
            "🇦🇲 ХайПост — haypost.am\n"
            "🇰🇬 Кыргыз Почтасы — kyrpost.kg\n\n"
            "🚀 КУРЬЕРСКИЕ СЛУЖБЫ:\n"
            "СДЭК, Boxberry, Европочта\n\n"
            "📦 ОТСЛЕЖИВАНИЕ ПОСЫЛКИ:\n"
            "Получите трек-номер от продавца и\n"
            "отправьте боту: /track <трек-номер>\n"
            "Бот покажет где сейчас ваша посылка!\n\n"
            "✅ Товары между странами ЕАЭС идут\n"
            "без лишних пошлин (в пределах лимитов).\n\n"
            "💡 Всегда уточняйте у продавца:\n"
            "• Какой службой отправит\n"
            "• Примерные сроки\n"
            "• Кто платит за доставку",
            reply_markup=kb
        )
        return

    if data == "how_boost":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="how_back")]])
        await query.edit_message_text(
            "💥 ЧТО ТАКОЕ BOOST?\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🔥 ВЫДЕЛЕНИЕ — {BOOST_HIGHLIGHT_STARS} ⭐\n"
            "Объявление переиздаётся с VIP-оформлением\n\n"
            f"📌 ЗАКРЕП 24 ЧАСА — {BOOST_PIN_STARS} ⭐\n"
            "Объявление закрепляется вверху канала\n\n"
            f"📢 ПОВТОР ЧЕРЕЗ 24Ч — {BOOST_STORY_STARS} ⭐\n"
            "Объявление автоматически переопубликуется\n"
            "через 24ч — снова в топе ленты\n\n"
            f"⚡ ВСЁ СРАЗУ — {BOOST_ALL_STARS} ⭐ (скидка 20%)\n"
            "Выделение + Закреп + Повтор — максимальный охват!\n\n"
            "Использовать: кнопка «💥 BOOST» в меню",
            reply_markup=kb
        )
        return

    if data == "how_back":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Оплата и Stars", callback_data="how_payment")],
            [InlineKeyboardButton("🚚 Доставка в ЕАЭС", callback_data="how_delivery")],
            [InlineKeyboardButton("💥 Что такое BOOST?", callback_data="how_boost")],
        ])
        await query.edit_message_text(
            "🛒 КАК РАБОТАЕТ TRECCC\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ Создай объявление /new\n"
            "2️⃣ Модерация → публикация в канале\n"
            "3️⃣ Покупатель пишет напрямую\n"
            "4️⃣ Договариваетесь и оплачиваете\n\n"
            "🔒 Поддержка: @treccc_support",
            reply_markup=kb
        )
        return

    # Публикация (ADMIN)
    if data.startswith("pub_"):
        uid = int(data[4:])
        ad = db.get_ad(uid)
        if not ad:
            await query.edit_message_text("Объявление не найдено.")
            return
        seller = db.get_user(uid)
        text = build_ad_text(ad, seller, boosted=False)
        bot_info = await context.bot.get_me()
        ad_id = ad.get("id", uid)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Написать продавцу",
                                  url=seller_contact_url(seller, uid))],
            [InlineKeyboardButton("🤍 В избранное", callback_data=f"fav_add_{ad_id}")],
            [InlineKeyboardButton("🚩 Пожаловаться", callback_data=f"report_{uid}")],
        ])
        try:
            media = ad.get("media", [])
            if len(media) == 1:
                m = media[0]
                if m["type"] == "photo":
                    await context.bot.send_photo(CHANNEL_PUBLIC, photo=m["file_id"],
                                                 caption=text, reply_markup=keyboard)
                else:
                    await context.bot.send_video(CHANNEL_PUBLIC, video=m["file_id"],
                                                 caption=text, reply_markup=keyboard)
            elif len(media) > 1:
                mg = []
                for i, m in enumerate(media[:10]):
                    cap = text if i == 0 else None
                    mg.append(InputMediaPhoto(media=m["file_id"], caption=cap) if m["type"] == "photo"
                              else InputMediaVideo(media=m["file_id"], caption=cap))
                await context.bot.send_media_group(CHANNEL_PUBLIC, media=mg)
                await context.bot.send_message(CHANNEL_PUBLIC, "👆", reply_markup=keyboard)
            else:
                await context.bot.send_message(CHANNEL_PUBLIC, text=text, reply_markup=keyboard)
            db.approve_ad(uid)
            db.increment_deals(uid, "seller")
            await query.edit_message_text(query.message.text + "\n\n✅ ОПУБЛИКОВАНО")
            await context.bot.send_message(
                uid,
                "🎉 Объявление опубликовано!\n\n"
                "💥 Хотите больше просмотров? Используйте BOOST:\n"
                f"🔥 Выделение — {BOOST_HIGHLIGHT_STARS} ⭐\n"
                f"📌 Закреп — {BOOST_PIN_STARS} ⭐\n"
                f"📢 История — {BOOST_STORY_STARS} ⭐\n\n"
                "Нажмите «💥 BOOST» в меню бота."
            )
        except Exception as e:
            await query.edit_message_text(query.message.text + f"\n\nОшибка: {e}")
        return

    # Отклонение (ADMIN)
    if data.startswith("rej_"):
        parts = data[4:].split("_")
        uid = int(parts[0])
        reason_code = parts[1] if len(parts) > 1 else "common"
        reasons = {"spam": "спам", "photo": "некачественные фото",
                   "price": "некорректная цена", "common": "нарушение правил"}
        db.delete_ad(uid)
        try:
            await context.bot.send_message(
                uid,
                f"❌ Объявление отклонено.\n"
                f"Причина: {reasons.get(reason_code, 'нарушение правил')}\n\n"
                "Исправьте и попробуйте: /new"
            )
            await query.edit_message_text(query.message.text + "\n\n🚫 ОТКЛОНЕНО")
        except Exception as e:
            await query.edit_message_text(f"Ошибка: {e}")
        return

    # Жалобы
    # Удалить объявление
    if data.startswith("delete_ad_"):
        ad_id = int(data.replace("delete_ad_", ""))
        db.delete_ad(ad_id=ad_id)
        await query.edit_message_caption("🗑 Объявление удалено.") if query.message.caption else await query.edit_message_text("🗑 Объявление удалено.")
        return

    # Оплата верификации
    if data.startswith("pay_verify_"):
        uid = int(data.replace("pay_verify_", ""))
        try:
            await context.bot.send_invoice(
                chat_id=uid,
                title="✅ Верификация продавца TRECCC",
                description="Подтверждение личности — получите значок ✅",
                payload=f"verify_{uid}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(label="Верификация", amount=VERIFY_STARS)],
            )
            await query.edit_message_text(
                f"⭐ Счёт на {VERIFY_STARS} Stars отправлен!\n"
                "После оплаты отправьте фото документа."
            )
        except Exception as e:
            await query.edit_message_text(f"Ошибка: {e}")
        return

    # Бесплатный BOOST за рефералов
    if data.startswith("freeboost_"):
        parts = data.split("_")
        boost_type = parts[1]
        uid = int(parts[2])
        if db.use_referral_boost(uid):
            await query.edit_message_text(f"🎁 Бесплатный BOOST активируется...")
            if boost_type == "highlight":
                await _apply_boost_highlight(context, uid)
            elif boost_type == "pin":
                await _apply_boost_pin(context, uid)
            elif boost_type == "story":
                await _apply_boost_story(context, uid)
            await context.bot.send_message(uid, "✅ Бесплатный BOOST применён!")
        else:
            await query.answer("Нет бесплатных BOOST!", show_alert=True)
        return

    if data.startswith("fav_add_"):
        ad_id = int(data.replace("fav_add_", ""))
        added = db.add_favorite(user_id, ad_id)
        if added:
            await query.answer("❤️ Добавлено в избранное!", show_alert=False)
        else:
            await query.answer("Уже в избранном!", show_alert=False)
        return

    if data.startswith("fav_remove_"):
        ad_id = int(data.replace("fav_remove_", ""))
        db.remove_favorite(user_id, ad_id)
        await query.answer("💔 Убрано из избранного", show_alert=False)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if data.startswith("report_") and not data.startswith("report_reason_"):
        seller_id = data[7:]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Спам", callback_data=f"report_reason_spam_{seller_id}")],
            [InlineKeyboardButton("Мошенничество", callback_data=f"report_reason_fraud_{seller_id}")],
            [InlineKeyboardButton("Запрещённый товар", callback_data=f"report_reason_illegal_{seller_id}")],
        ])
        await context.bot.send_message(user_id, "🚩 Причина жалобы:", reply_markup=kb)
        return

    if data.startswith("report_reason_"):
        parts = data[14:].split("_")
        reason = parts[0]
        seller_id = int(parts[1])
        rtexts = {"spam": "Спам", "fraud": "Мошенничество", "illegal": "Запрещённый товар"}
        ad = db.get_ad(seller_id)
        db.save_report(user_id, seller_id, reason)
        await query.edit_message_text("✅ Жалоба отправлена.")
        await context.bot.send_message(
            ADMIN_ID,
            f"🚨 ЖАЛОБА\nОт: @{query.from_user.username} ({user_id})\n"
            f"Товар: {ad['name'] if ad else '?'}\n"
            f"Продавец: {seller_id}\n"
            f"Причина: {rtexts.get(reason, reason)}\n\n"
            f"/deload {seller_id}"
        )
        return

    if data in ("broadcast_confirm", "broadcast_cancel"):
        await broadcast_confirm_handler(update, context)
        return


# ── ТЕКСТОВЫЕ КНОПКИ ──────────────────────────────────────────────────────────
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    text = update.message.text
    if text == "🤍 Избранное":
        await favorites_cmd(update, context)
    elif text == "👤 Мой профиль":
        await profile_cmd(update, context)
    elif "BOOST" in text or text == "💥 BOOST":
        await boost_menu(update, context)
    elif text == "❓ Как это работает?":
        await how_it_works(update, context)
    elif text == "👥 Рефералы":
        await referrals_cmd(update, context)
    elif text == "📋 Мои объявления":
        await my_ads_cmd(update, context)
    elif text == "✅ Верификация":
        await verify_cmd(update, context)
    elif text == "🏆 Топ продавцов":
        await top_sellers_cmd(update, context)


# ── ADMIN КОМАНДЫ ─────────────────────────────────────────────────────────────
async def set_verified_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("/setverified USER_ID")
        return
    uid = int(context.args[0])
    db.set_verified(uid)
    await update.message.reply_text(f"✅ {uid} верифицирован.")
    await context.bot.send_message(uid, "✅ Аккаунт верифицирован! Значок ✅ у вашего имени.")


async def deload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("/deload USER_ID")
        return
    uid = int(context.args[0])
    db.delete_ad(uid)
    await update.message.reply_text(f"✅ Объявление {uid} удалено.")
    await context.bot.send_message(uid, "🚫 Объявление удалено за нарушение правил.")


async def reject_verify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /rejectverify USER_ID")
        return
    uid = int(context.args[0])
    try:
        await context.bot.send_message(
            uid,
            "❌ Верификация отклонена.\n\n"
            "Причина: документ не прошёл проверку.\n"
            "Попробуйте снова: /verify"
        )
        await update.message.reply_text(f"✅ Верификация {uid} отклонена.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    users = db.get_all_users()
    ads = db.get_all_approved_ads()
    await update.message.reply_text(
        f"📊 СТАТИСТИКА\n\n"
        f"👤 Пользователей: {len(users)}\n"
        f"📦 Опубликованных объявлений: {len(ads)}"
    )


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    review_conv = ConversationHandler(
        entry_points=[CommandHandler("review", leave_review_start)],
        states={
            REVIEW_RATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, review_rating_handler)],
            REVIEW_TEXT:   [
                MessageHandler(filters.TEXT & ~filters.COMMAND, review_text_handler),
                CommandHandler("skip", review_skip_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END), CommandHandler("start", start)],
    )

    verify_conv = ConversationHandler(
        entry_points=[
            CommandHandler("verify", verify_cmd),
            MessageHandler(filters.Regex("^✅ Верификация$"), verify_cmd),
        ],
        states={
            VERIFY_PHOTO: [MessageHandler(filters.PHOTO, verify_photo_handler)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END), CommandHandler("start", start)],
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("niusie", broadcast_start)],
        states={
            BROADCAST_TEXT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text_handler)],
            BROADCAST_MEDIA:   [
                MessageHandler(filters.PHOTO | filters.VIDEO, broadcast_media_handler),
                CommandHandler("skip", broadcast_skip_media),
            ],
            BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_confirm_handler,
                                                     pattern="^broadcast_(confirm|cancel)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel_ad), CommandHandler("start", start), MessageHandler(filters.Regex("^❌ Отменить объявление$"), cancel_ad)],
        per_message=False,
    )

    ad_conv = ConversationHandler(
        entry_points=[
            CommandHandler("new", new_ad),
            MessageHandler(filters.Regex("^📦 Создать объявление$"), new_ad),
        ],
        states={
            NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
            DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, desc_handler)],
            PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, price_handler)],
            COUNTRY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, country_handler)],
            DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_handler)],
            MEDIA:    [
                MessageHandler(filters.PHOTO | filters.VIDEO, media_handler),
                MessageHandler(filters.Regex("^✅ Закончить$"), media_handler),
                MessageHandler(filters.Regex("^❌ Отменить объявление$"), cancel_ad),
                CommandHandler("done", finish_cmd),
                CommandHandler("cancel", cancel_ad),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_ad), CommandHandler("start", start), MessageHandler(filters.Regex("^❌ Отменить объявление$"), cancel_ad)],
    )

    app.add_handler(review_conv)
    app.add_handler(verify_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(ad_conv)

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("new",         new_ad))
    app.add_handler(CommandHandler("search",      search_cmd))
    app.add_handler(CommandHandler("review",      leave_review_start))
    app.add_handler(CommandHandler("verify",      verify_cmd))
    app.add_handler(CommandHandler("top",         top_sellers_cmd))
    app.add_handler(CommandHandler("freeboost",   free_boost_cmd))
    app.add_handler(CommandHandler("rejectverify", reject_verify_cmd))
    app.add_handler(CommandHandler("track",       track_cmd))
    app.add_handler(CommandHandler("favorites",   favorites_cmd))
    app.add_handler(CommandHandler("profile",     profile_cmd))
    app.add_handler(CommandHandler("myads",       my_ads_cmd))
    app.add_handler(CommandHandler("referrals",   referrals_cmd))
    app.add_handler(CommandHandler("boost",       boost_menu))
    app.add_handler(CommandHandler("setverified", set_verified_cmd))
    app.add_handler(CommandHandler("deload",      deload_cmd))
    app.add_handler(CommandHandler("stats",       stats_cmd))

    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("🚀 Бот TRECCC v9 (BOOST + Stars + ЕАЭС) запущен...")
    app.run_polling(stop_signals=None)


if __name__ == "__main__":
    import asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()