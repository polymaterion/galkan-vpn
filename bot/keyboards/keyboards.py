"""Inline keyboards for the screen-based bot UI."""
from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.locales import t


def language_picker(lang: str = "ru", include_back: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("btn_lang_ru", lang), callback_data="lang:ru"),
        InlineKeyboardButton(text=t("btn_lang_tk", lang), callback_data="lang:tk"),
    )
    if include_back:
        builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def main_menu(lang: str, price_stars: int, show_trial: bool = False) -> InlineKeyboardMarkup:
    """The only screen without a back button: it is the navigation root.

    show_trial adds a free-trial button right under the header — passed as
    True only when the caller has confirmed (via billing_client.trial_eligible)
    that this user hasn't claimed their trial yet. Kept as a separate
    top-of-menu row rather than folded into "Add device" so it's visible
    without extra taps and disappears on its own once used.
    """
    builder = InlineKeyboardBuilder()
    if show_trial:
        builder.row(InlineKeyboardButton(text=t("btn_trial", lang), callback_data="nav:trial"))
    builder.row(InlineKeyboardButton(text=t("btn_my_devices", lang), callback_data="nav:devices"))
    builder.row(
        InlineKeyboardButton(
            text=t("btn_buy_new", lang, price=price_stars), callback_data="nav:buy_new"
        )
    )
    builder.row(InlineKeyboardButton(text=t("btn_support", lang), callback_data="nav:support"))
    builder.row(InlineKeyboardButton(text=t("btn_instructions", lang), callback_data="nav:instructions"))
    builder.row(InlineKeyboardButton(text=t("btn_language", lang), callback_data="nav:language"))
    return builder.as_markup()


def trial_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_trial_activate", lang), callback_data="trial:activate"))
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def back_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def devices_keyboard(
    lang: str, devices: list[dict], price_stars: int
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
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if device.get("config_url") and device.get("status") == "active":
        builder.row(
            InlineKeyboardButton(
                text=t("btn_device_connect", lang, n=number), callback_data=f"show_key:{device['id']}"
            )
        )
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


def invoice_keyboard(lang: str, price_stars: int) -> InlineKeyboardMarkup:
    """
    reply_markup for send_invoice: Telegram requires the first button to be
    a `pay=True` button when reply_markup is provided at all (otherwise
    Telegram auto-generates one with English "Pay {price}" text, which is
    what we're overriding here for tk/ru). '⭐' in the button text is
    rendered by Telegram as its native Star icon, not a literal emoji.
    A second row with a normal callback button (nav:back) is allowed by the
    API as long as the Pay button stays first.
    """
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_invoice_pay", lang, price=price_stars), pay=True))
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


def config_ready_keyboard(lang: str, has_config: bool, subscription_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_config:
        builder.row(
            InlineKeyboardButton(text=t("btn_connect_amnezia", lang), callback_data=f"show_key:{subscription_id}")
        )
        builder.row(
            InlineKeyboardButton(text=t("btn_show_qr", lang), callback_data=f"show_qr:{subscription_id}")
        )
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def instructions_keyboard(lang: str, download_url: str, guide_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_amnezia_download", lang), url=download_url))
    builder.row(InlineKeyboardButton(text=t("btn_amnezia_guide", lang), url=guide_url))
    builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="nav:back"))
    return builder.as_markup()


def admin_menu(lang: str, show_back: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("adm_btn_users", lang), callback_data="nav:admin:users"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_subs", lang), callback_data="nav:admin:subs"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_payments", lang), callback_data="nav:admin:payments"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_servers", lang), callback_data="nav:admin:servers"))
    builder.row(InlineKeyboardButton(text=t("adm_btn_broadcast", lang), callback_data="nav:admin:broadcast"))
    if show_back:
        builder.row(InlineKeyboardButton(text=t("btn_back", lang), callback_data="start"))
    return builder.as_markup()


def admin_back_keyboard(lang: str) -> InlineKeyboardMarkup:
    return back_keyboard(lang)


def broadcast_skip_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("bc_btn_skip", lang), callback_data="bc:skip_buttons"))
    return builder.as_markup()


def broadcast_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("btn_bc_send", lang), callback_data="bc:send"))
    builder.row(InlineKeyboardButton(text=t("btn_bc_cancel", lang), callback_data="bc:cancel"))
    return builder.as_markup()


def broadcast_link_buttons(buttons: list[tuple[str, str]]) -> Optional[InlineKeyboardMarkup]:
    """Builds the url-button row(s) that get attached to the actual
    broadcast message itself (as opposed to the two keyboards above, which
    control the admin's compose flow). One button per row, in the order
    given — matches how they were entered."""
    if not buttons:
        return None
    builder = InlineKeyboardBuilder()
    for text, url in buttons:
        builder.row(InlineKeyboardButton(text=text, url=url))
    return builder.as_markup()
