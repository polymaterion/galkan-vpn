"""All inline keyboards for the bot. Every label goes through bot.locales.t()."""
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
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_my_devices", lang), callback_data="devices"))
    builder.row(
        InlineKeyboardButton(
            text=t("btn_buy_new", lang, price=price_stars), callback_data="buy_new"
        )
    )
    builder.row(InlineKeyboardButton(text=t("btn_support", lang), callback_data="support"))
    builder.row(InlineKeyboardButton(text=t("btn_language", lang), callback_data="language_menu"))
    return builder.as_markup()


def devices_keyboard(
    lang: str, devices: list[dict], price_stars: int
) -> InlineKeyboardMarkup:
    """One row of buttons per device (connect / QR / renew), plus a buy-new
    and back row at the bottom."""
    builder = InlineKeyboardBuilder()
    for i, d in enumerate(devices, start=1):
        row: list[InlineKeyboardButton] = []
        connect_url = d.get("connect_url")
        if connect_url and d.get("status") == "active":
            row.append(
                InlineKeyboardButton(
                    text=t("btn_device_connect", lang, n=i), url=connect_url
                )
            )
        row.append(
            InlineKeyboardButton(
                text=t("btn_device_qr", lang, n=i), callback_data=f"show_qr:{d['id']}"
            )
        )
        builder.row(*row)
        builder.row(
            InlineKeyboardButton(
                text=t("btn_device_renew", lang, n=i, price=price_stars),
                callback_data=f"renew:{d['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text=t("btn_buy_new", lang, price=price_stars), callback_data="buy_new"))
    builder.row(InlineKeyboardButton(text=t("btn_back_to_menu", lang), callback_data="start"))
    return builder.as_markup()


def payment_method_menu(lang: str, mode: str, target_id: Optional[int]) -> InlineKeyboardMarkup:
    target = target_id or 0
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("btn_pay_stars", lang), callback_data=f"pay_stars:{mode}:{target}"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("btn_pay_usdt", lang), callback_data=f"pay_usdt:{mode}:{target}"
        )
    )
    back_cb = "devices" if mode == "renew" else "start"
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data=back_cb))
    return builder.as_markup()


def back_to_menu(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_back_to_menu", lang), callback_data="start"))
    return builder.as_markup()


def check_usdt_payment(
    lang: str, invoice_id: str, mode: str, target_id: Optional[int]
) -> InlineKeyboardMarkup:
    target = target_id or 0
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("btn_i_paid", lang),
            callback_data=f"check_usdt:{invoice_id}:{mode}:{target}",
        )
    )
    builder.row(InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="start"))
    return builder.as_markup()


def config_ready_keyboard(
    lang: str, connect_url: Optional[str], subscription_id: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if connect_url:
        builder.row(
            InlineKeyboardButton(text=t("btn_connect_amnezia", lang), url=connect_url)
        )
    builder.row(
        InlineKeyboardButton(
            text=t("btn_show_qr", lang), callback_data=f"show_qr:{subscription_id}"
        )
    )
    builder.row(InlineKeyboardButton(text=t("btn_back_to_menu", lang), callback_data="start"))
    return builder.as_markup()


def admin_menu(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("adm_btn_users", lang), callback_data="adm_users"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_subs", lang), callback_data="adm_subs"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_payments", lang), callback_data="adm_payments"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_servers", lang), callback_data="adm_servers"))
    return builder.as_markup()


def admin_back_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Back button for admin sub-screens. Deliberately a SEPARATE
    callback ("adm_menu") from the customer-facing back_to_menu()
    ("start") — otherwise an admin browsing e.g. Users and hitting "back"
    would land in the customer purchase flow instead of the admin panel."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("adm_btn_back", lang), callback_data="adm_menu"))
    return builder.as_markup()
