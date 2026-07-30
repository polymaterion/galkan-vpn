"""
Main Telegram bot handlers.
/start, language picker, devices list, buy/renew flow, config delivery.

Hard rule: one payment = one device. Buying always creates a brand-new VPN
key (mode="new"); renewing extends one specific existing device by id
(mode="renew"). See billing/services/billing_service.py for the enforcement.
"""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
)

from bot.billing_client import billing_client
from bot.config import settings
from bot.keyboards.keyboards import (
    back_to_menu,
    check_usdt_payment,
    config_ready_keyboard,
    devices_keyboard,
    language_picker,
    main_menu,
    payment_method_menu,
)
from bot.locales import t
from bot.payments.crypto_pay import crypto_pay
from bot.utils import generate_qr

logger = logging.getLogger(__name__)
router = Router()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_price_stars() -> int:
    try:
        plan = await billing_client.get_plan()
        if plan:
            return plan["price_stars"]
    except Exception as e:
        logger.warning("get_plan failed, using configured default: %s", e)
    return settings.PLAN_PRICE_STARS


async def _main_menu_view(lang: str) -> tuple[str, "InlineKeyboardMarkup"]:
    price = await _get_price_stars()
    return t("welcome", lang), main_menu(lang, price)


STATUS_EMOJI = {
    "active": "✅",
    "expired": "❌",
    "pending_provisioning": "⏳",
    "error": "⚠️",
    "disabled": "🔒",
    "pending_payment": "💳",
}


async def _deliver_result(bot: Bot, chat_id: int, lang: str, result: dict) -> None:
    """After a successful payment: show the 'device ready' card with a
    connect button pointing DIRECTLY at the vpn:// config (no intermediate
    landing page), plus a QR button. Or a 'still provisioning' message if
    the VPN key isn't ready yet (worker will retry; user checks 'Мои
    устройства' later).

    Telegram only officially guarantees http(s)/tg:// urls for inline
    buttons — a vpn:// button can in principle be rejected outright when
    sending. If that happens we retry once without the url button so the
    user still gets their config (via text + QR), rather than losing the
    message entirely."""
    config_url = result.get("config_url")
    sub_id = result["subscription_id"]
    expires = (result.get("expires_at") or "")[:10] or t("unknown_expiry", lang)

    if not config_url:
        await bot.send_message(
            chat_id,
            t("provisioning_pending", lang),
            reply_markup=back_to_menu(lang),
        )
        return

    text = t("config_ready", lang, expires=expires)
    try:
        await bot.send_message(
            chat_id, text, reply_markup=config_ready_keyboard(lang, config_url, sub_id)
        )
    except TelegramBadRequest as e:
        logger.warning(
            "Telegram rejected the vpn:// connect button (%s) — falling back to text link", e
        )
        text_fallback = text + "\n\n" + t("config_link_fallback", lang, config_url=config_url)
        await bot.send_message(
            chat_id, text_fallback, reply_markup=config_ready_keyboard(lang, None, sub_id)
        )


async def _send_qr(bot: Bot, chat_id: int, lang: str, telegram_id: int, sub_id: int) -> None:
    config_url = None
    try:
        devices = await billing_client.get_devices(telegram_id)
        device = next((d for d in devices if d["id"] == sub_id), None)
        config_url = device.get("config_url") if device else None
    except Exception as e:
        logger.warning("Failed to fetch device for QR: %s", e)

    if not config_url:
        await bot.send_message(chat_id, t("qr_unavailable", lang))
        return

    try:
        qr_bytes = generate_qr(config_url)
        await bot.send_photo(
            chat_id,
            photo=BufferedInputFile(qr_bytes, filename="vpn_qr.png"),
            caption=t("qr_caption", lang),
        )
    except Exception as e:
        logger.warning("QR generation failed: %s", e)
        await bot.send_message(chat_id, t("config_link_fallback", lang, config_url=config_url))


# ---------------------------------------------------------------------------
# /start & language
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(msg: Message, lang: str):
    if not lang:
        await msg.answer(t("language_prompt"), reply_markup=language_picker())
        return
    text, kb = await _main_menu_view(lang)
    await msg.answer(text, reply_markup=kb)


@router.callback_query(F.data == "start")
async def cb_start(cb: CallbackQuery, lang: str):
    text, kb = await _main_menu_view(lang)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "language_menu")
async def cb_language_menu(cb: CallbackQuery, lang: str):
    await cb.message.edit_text(t("language_prompt", lang), reply_markup=language_picker(lang))
    await cb.answer()


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(cb: CallbackQuery):
    new_lang = cb.data.split(":", 1)[1]
    try:
        await billing_client.set_user_language(cb.from_user.id, new_lang)
    except Exception as e:
        logger.error("Failed to save language for %s: %s", cb.from_user.id, e)

    text, kb = await _main_menu_view(new_lang)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer(t("language_saved", new_lang))


# ---------------------------------------------------------------------------
# Devices list ("Мои устройства")
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "devices")
async def cb_devices(cb: CallbackQuery, lang: str):
    try:
        devices = await billing_client.get_devices(cb.from_user.id)
    except Exception as e:
        logger.error("get_devices failed: %s", e)
        devices = []

    price = await _get_price_stars()

    if not devices:
        await cb.message.edit_text(
            t("devices_empty", lang, price=price),
            reply_markup=main_menu(lang, price),
        )
        await cb.answer()
        return

    lines = [t("devices_title", lang), ""]
    for i, d in enumerate(devices, start=1):
        status_text = t(f"status_{d['status']}", lang)
        expires = (d.get("expires_at") or "")[:10] or t("unknown_expiry", lang)
        emoji = STATUS_EMOJI.get(d["status"], "❓")
        lines.append(t("device_line", lang, emoji=emoji, n=i, status=status_text, expires=expires))

    text = "\n".join(lines)
    try:
        await cb.message.edit_text(text, reply_markup=devices_keyboard(lang, devices, price))
    except TelegramBadRequest as e:
        logger.warning(
            "Telegram rejected a vpn:// connect button in devices list (%s) — "
            "falling back to QR-only buttons",
            e,
        )
        await cb.message.edit_text(
            text, reply_markup=devices_keyboard(lang, devices, price, use_direct_link=False)
        )
    await cb.answer()


# ---------------------------------------------------------------------------
# Buy a NEW device / Renew an EXISTING device
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "buy_new")
async def cb_buy_new(cb: CallbackQuery, lang: str):
    plan = None
    try:
        plan = await billing_client.get_plan()
    except Exception as e:
        logger.error("get_plan failed: %s", e)

    if not plan:
        await cb.answer(t("plan_unavailable", lang), show_alert=True)
        return

    text = t(
        "plan_card",
        lang,
        name=t("plan_name_text", lang, duration_days=plan["duration_days"]),
        description=t("plan_description_text", lang, duration_days=plan["duration_days"]),
        duration_days=plan["duration_days"],
        price_stars=plan["price_stars"],
        price_usdt=plan["price_usdt"],
    )
    await cb.message.edit_text(text, reply_markup=payment_method_menu(lang, "new", None))
    await cb.answer()


@router.callback_query(F.data.startswith("renew:"))
async def cb_renew(cb: CallbackQuery, lang: str):
    sub_id = int(cb.data.split(":")[1])
    plan = None
    try:
        plan = await billing_client.get_plan()
    except Exception as e:
        logger.error("get_plan failed: %s", e)

    if not plan:
        await cb.answer(t("plan_unavailable", lang), show_alert=True)
        return

    n = sub_id
    try:
        devices = await billing_client.get_devices(cb.from_user.id)
        found = next((i for i, d in enumerate(devices, start=1) if d["id"] == sub_id), None)
        if found:
            n = found
    except Exception:
        pass

    text = t(
        "renew_card",
        lang,
        n=n,
        duration_days=plan["duration_days"],
        price_stars=plan["price_stars"],
        price_usdt=plan["price_usdt"],
    )
    await cb.message.edit_text(text, reply_markup=payment_method_menu(lang, "renew", sub_id))
    await cb.answer()


# ---------------------------------------------------------------------------
# Payment — Telegram Stars
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("pay_stars:"))
async def cb_pay_stars(cb: CallbackQuery, bot: Bot, lang: str):
    _, mode, target = cb.data.split(":")
    target_id = int(target) if target != "0" else 0

    plan = None
    try:
        plan = await billing_client.get_plan()
    except Exception as e:
        logger.error("get_plan failed: %s", e)

    if not plan:
        await cb.answer(t("plan_load_error", lang), show_alert=True)
        return

    payload = f"stars:{mode}:{target_id}:{plan['id']}"
    plan_name = t("plan_name_text", lang, duration_days=plan["duration_days"])
    plan_description = t("plan_description_text", lang, duration_days=plan["duration_days"])
    await bot.send_invoice(
        chat_id=cb.from_user.id,
        title=plan_name,
        description=plan_description,
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label=plan_name, amount=plan["price_stars"])],
        provider_token="",  # Empty for Stars
    )
    await cb.answer()


@router.pre_checkout_query()
async def pre_checkout(pq: PreCheckoutQuery):
    """Telegram calls this before completing Stars payment. Must answer within 10s."""
    await pq.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(msg: Message, lang: str):
    sp: SuccessfulPayment = msg.successful_payment
    parts = sp.invoice_payload.split(":")
    # payload format: stars:{mode}:{target_or_0}:{plan_id}
    mode = parts[1] if len(parts) > 1 else "new"
    target = int(parts[2]) if len(parts) > 2 and parts[2] != "0" else None
    plan_id = int(parts[3]) if len(parts) > 3 else None

    action_key = "payment_processing_renew" if mode == "renew" else "payment_processing_new"
    await msg.answer(t("payment_processing", lang, action=t(action_key, lang)))

    try:
        result = await billing_client.handle_stars_payment(
            telegram_id=msg.from_user.id,
            username=msg.from_user.username,
            first_name=msg.from_user.first_name,
            last_name=msg.from_user.last_name,
            charge_id=sp.telegram_payment_charge_id,
            total_amount=sp.total_amount,
            plan_id=plan_id,
            mode=mode,
            target_subscription_id=target,
        )
    except Exception as e:
        logger.error("Stars payment processing failed: %s", e)
        await msg.answer(t("payment_error", lang), reply_markup=back_to_menu(lang))
        return

    await _deliver_result(msg.bot, msg.chat.id, lang, result)


# ---------------------------------------------------------------------------
# Payment — USDT via CryptoPay
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("pay_usdt:"))
async def cb_pay_usdt(cb: CallbackQuery, lang: str):
    _, mode, target = cb.data.split(":")
    target_id = int(target) if target != "0" else None

    plan = None
    try:
        plan = await billing_client.get_plan()
    except Exception:
        pass

    if not plan or not settings.CRYPTOPAY_TOKEN:
        await cb.answer(t("usdt_unavailable", lang), show_alert=True)
        return

    try:
        invoice = await crypto_pay.create_invoice(
            amount=float(plan["price_usdt"]),
            asset="USDT",
            description=t("plan_name_text", lang, duration_days=plan["duration_days"]),
            payload=f"{cb.from_user.id}:{plan['id']}:{mode}:{target_id or 0}",
        )
    except Exception as e:
        logger.error("CryptoPay invoice creation failed: %s", e)
        await cb.answer(t("usdt_invoice_error", lang), show_alert=True)
        return

    pay_url = invoice.get("pay_url", "")
    invoice_id = invoice.get("invoice_id")

    await cb.message.edit_text(
        t("usdt_invoice_card", lang, amount=plan["price_usdt"], pay_url=pay_url),
        reply_markup=check_usdt_payment(lang, str(invoice_id), mode, target_id),
        disable_web_page_preview=True,
    )
    await cb.answer()


@router.callback_query(F.data.startswith("check_usdt:"))
async def cb_check_usdt(cb: CallbackQuery, lang: str):
    _, invoice_id_s, mode, target_s = cb.data.split(":")
    invoice_id = int(invoice_id_s)
    target_id = int(target_s) if target_s != "0" else None

    try:
        paid = await crypto_pay.is_paid(invoice_id)
    except Exception as e:
        logger.error("CryptoPay check failed: %s", e)
        await cb.answer(t("usdt_check_error", lang), show_alert=True)
        return

    if not paid:
        await cb.answer(t("usdt_not_paid_yet", lang), show_alert=True)
        return

    try:
        invoice = await crypto_pay.get_invoice(invoice_id)
    except Exception:
        invoice = {}

    payload = (invoice or {}).get("payload", "")
    parts = payload.split(":")
    plan_id = int(parts[1]) if len(parts) > 1 else None
    amount = float((invoice or {}).get("amount", settings.PLAN_PRICE_USDT))

    action_key = "payment_processing_renew" if mode == "renew" else "payment_processing_new"
    await cb.message.edit_text(t("usdt_confirmed", lang, action=t(action_key, lang)))

    try:
        result = await billing_client.handle_usdt_payment(
            telegram_id=cb.from_user.id,
            username=cb.from_user.username,
            first_name=cb.from_user.first_name,
            last_name=cb.from_user.last_name,
            invoice_id=str(invoice_id),
            amount=amount,
            plan_id=plan_id,
            mode=mode,
            target_subscription_id=target_id,
        )
    except Exception as e:
        logger.error("USDT payment processing failed: %s", e)
        await cb.message.answer(t("usdt_activation_error", lang), reply_markup=back_to_menu(lang))
        return

    await _deliver_result(cb.bot, cb.from_user.id, lang, result)
    await cb.answer()


# ---------------------------------------------------------------------------
# Show QR on demand
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("show_qr:"))
async def cb_show_qr(cb: CallbackQuery, lang: str):
    sub_id = int(cb.data.split(":")[1])
    await _send_qr(cb.bot, cb.from_user.id, lang, cb.from_user.id, sub_id)
    await cb.answer()


# ---------------------------------------------------------------------------
# Support
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "support")
async def cb_support(cb: CallbackQuery, lang: str):
    await cb.message.edit_text(
        t("support_text", lang, support_link=settings.SUPPORT_LINK),
        reply_markup=back_to_menu(lang),
    )
    await cb.answer()
