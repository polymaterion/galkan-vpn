"""All inline keyboards for the bot."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(has_subscription: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_subscription:
        builder.row(InlineKeyboardButton(text="📋 Моя подписка", callback_data="my_sub"))
        builder.row(InlineKeyboardButton(text="🔑 Получить ключ", callback_data="get_config"))
        builder.row(InlineKeyboardButton(text="💳 Продлить", callback_data="buy"))
    else:
        builder.row(InlineKeyboardButton(text="💳 Купить VPN", callback_data="buy"))
    builder.row(InlineKeyboardButton(text="💬 Поддержка", callback_data="support"))
    return builder.as_markup()


def payment_method_menu(plan_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⭐ Оплатить Telegram Stars",
            callback_data=f"pay_stars:{plan_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💎 Оплатить USDT (Crypto)",
            callback_data=f"pay_usdt:{plan_id}",
        )
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="start"))
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ В главное меню", callback_data="start"))
    return builder.as_markup()


def check_usdt_payment(invoice_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Я оплатил",
            callback_data=f"check_usdt:{invoice_id}",
        )
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="start"))
    return builder.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👥 Пользователи", callback_data="adm_users"))
    builder.row(InlineKeyboardButton(text="📋 Подписки", callback_data="adm_subs"))
    builder.row(InlineKeyboardButton(text="💰 Платежи", callback_data="adm_payments"))
    builder.row(InlineKeyboardButton(text="🖥 Серверы", callback_data="adm_servers"))
    return builder.as_markup()
