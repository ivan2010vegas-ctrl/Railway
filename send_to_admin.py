"""
Отправка объявления в канал модерации.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import ContextTypes
from config import CHANNEL_MODERATION

EAEU_RATES = {
    "🇷🇺 RUB": 92.5,
    "🇧🇾 BYN": 3.28,
    "🇰🇿 KZT": 455.0,
    "🇦🇲 AMD": 388.0,
    "🇰🇬 KGS": 87.5,
}


def price_in_eaeu(usd: float) -> str:
    parts = []
    for flag_code, rate in EAEU_RATES.items():
        amount = usd * rate
        parts.append(
            f"{flag_code}: {amount:,.0f}" if amount >= 1000 else f"{flag_code}: {amount:.2f}"
        )
    return "\n".join(parts)


async def send_ad_to_admin(update, context: ContextTypes.DEFAULT_TYPE, ad: dict):
    """Отправляет объявление в канал модерации с медиа и кнопками."""
    try:
        user = update.effective_user
        p = ad.get("price_usd", 0)
        eaeu = price_in_eaeu(p)

        text_info = (
            f"📝 НОВОЕ ОБЪЯВЛЕНИЕ НА МОДЕРАЦИЮ\n\n"
            f"👤 {user.full_name} (@{user.username})\n"
            f"🆔 ID: {user.id}\n\n"
            f"📦 Название: {ad['name']}\n"
            f"📝 Описание: {ad.get('description', '—')}\n"
            f"💵 Цена: ${p:.2f}\n"
            f"📊 В валютах ЕАЭС:\n{eaeu}\n"
            f"📍 Страна: {ad['country']}\n"
            f"🚚 Доставка: {ad['delivery']}\n"
            f"📷 Медиа: {len(ad.get('media', []))} шт."
        )

        media_list = ad.get("media", [])
        if media_list:
            media_group = []
            for idx, m in enumerate(media_list[:10]):
                caption = text_info if idx == 0 else None
                if m["type"] == "photo":
                    media_group.append(InputMediaPhoto(media=m["file_id"], caption=caption))
                elif m["type"] == "video":
                    media_group.append(InputMediaVideo(media=m["file_id"], caption=caption))
            await context.bot.send_media_group(chat_id=CHANNEL_MODERATION, media=media_group)
        else:
            await context.bot.send_message(chat_id=CHANNEL_MODERATION, text=text_info)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Опубликовать", callback_data=f"pub_{user.id}")],
            [
                InlineKeyboardButton("❌ Спам",  callback_data=f"rej_{user.id}_spam"),
                InlineKeyboardButton("❌ Фото",  callback_data=f"rej_{user.id}_photo"),
                InlineKeyboardButton("❌ Цена",  callback_data=f"rej_{user.id}_price"),
            ],
            [InlineKeyboardButton("🚫 Отклонить (прочее)", callback_data=f"rej_{user.id}_common")],
        ])

        await context.bot.send_message(
            chat_id=CHANNEL_MODERATION,
            text="⬆️ Выберите действие:",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Ошибка отправки на модерацию: {e}")