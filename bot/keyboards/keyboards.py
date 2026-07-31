"""Inline keyboards for the screen-based bot UI."""
from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.locales import t


def language_picker(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("btn_lang_ru", lang), callback_data="lang:ru"),
        InlineKeyboardButton(text=t("btn_lang_tk", lang), callback_data="lang:tk"),
    )
    return builder.as_markup()


def main_menu(lang: str, price_stars: int) -> InlineKeyboardMarkup:
    """The only screen without a back button: it is the navigation root."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_my_devices", lang), callback_data="nav:devices"))
    builder.row(
        InlineKeyboardButton(
            text=t("btn_buy_new", lang, price=price_stars), callback_data="nav:buy_new"
        )
    )
    builder.row(InlineKeyboardButton(text=t("btn_support", lang), callback_data="nav:support"))
    builder.row(InlineKeyboardButton(text=t("btn_language", lang), callback_data="nav:language"))
    return builder.as_markup()


def back_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def devices_keyboard(
    lang: str, devices: list[dict], price_stars: int, use_direct_link: bool = True
) -> InlineKeyboardMarkup:
    """List screen. Each device opens its own card screen."""
    builder = InlineKeyboardBuilder()
    for i, d in enumerate(devices, start=1):
        builder.row(
            InlineKeyboardButton(
                text=t("btn_device_open", lang, n=i), callback_data=f"nav:device:{d['id']}"
            )
        )
    builder.row(
        InlineKeyboardButton(text=t("btn_buy_new", lang, price=price_stars), callback_data="nav:buy_new")
    )
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def device_card_keyboard(
    lang: str,
    device: dict,
    number: int,
    price_stars: int,
    use_direct_link: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    deep_link = device.get("config_url")
    if use_direct_link and deep_link and device.get("status") == "active":
        builder.row(InlineKeyboardButton(text=t("btn_device_connect", lang, n=number), url=deep_link))
    builder.row(
        InlineKeyboardButton(
            text=t("btn_device_qr", lang, n=number), callback_data=f"show_qr:{device['id']}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("btn_device_renew", lang, n=number, price=price_stars),
            callback_data=f"nav:renew:{device['id']}",
        )
    )
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def payment_method_menu(lang: str, mode: str, target_id: Optional[int], price_stars: int = 0) -> InlineKeyboardMarkup:
    target = target_id or 0
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("btn_pay_stars", lang), callback_data=f"pay_stars:{mode}:{target}")
    )
    builder.row(
        InlineKeyboardButton(text=t("btn_pay_usdt", lang), callback_data=f"pay_usdt:{mode}:{target}")
    )
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def check_usdt_payment(lang: str, invoice_id: str, mode: str, target_id: Optional[int]) -> InlineKeyboardMarkup:
    target = target_id or 0
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("btn_i_paid", lang), callback_data=f"check_usdt:{invoice_id}:{mode}:{target}"
        )
    )
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def config_ready_keyboard(lang: str, deep_link_url: Optional[str], subscription_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if deep_link_url:
        builder.row(InlineKeyboardButton(text=t("btn_connect_amnezia", lang), url=deep_link_url))
    builder.row(
        InlineKeyboardButton(text=t("btn_show_qr", lang), callback_data=f"show_qr:{subscription_id}")
    )
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def admin_menu(lang: str, show_back: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("adm_btn_users", lang), callback_data="nav:admin:users"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_subs", lang), callback_data="nav:admin:subs"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_payments", lang), callback_data="nav:admin:payments"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_servers", lang), callback_data="nav:admin:servers"))
    if show_back:
        builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="start"))
    return builder.as_markup()


def admin_back_keyboard(lang: str) -> InlineKeyboardMarkup:
    return back_keyboard(lang)
