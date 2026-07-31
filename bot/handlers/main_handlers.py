"""Customer-facing Telegram screens.

The bot keeps one UI message per conversation. Callback handlers push a
screen into the FSM navigation stack and render it by editing that message.
The only intentional extra Telegram messages are payment invoices and QR
images, both of which Telegram requires to be separate message types.
"""
from __future__ import annotations

import html
import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
)

from bot import navigation
from bot.billing_client import billing_client
from bot.config import settings
from bot.keyboards.keyboards import (
    back_keyboard,
    check_usdt_payment,
    config_ready_keyboard,
    device_card_keyboard,
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

STATUS_EMOJI = {
    "active": "✅",
    "expired": "❌",
    "pending_provisioning": "⏳",
    "error": "⚠️",
    "disabled": "🔒",
    "pending_payment": "💸",
}


async def _get_price_stars() -> int:
    try:
        plan = await billing_client.get_plan()
        if plan:
            return plan["price_stars"]
    except Exception as exc:
        logger.warning("get_plan failed, using configured default: %s", exc)
    return settings.PLAN_PRICE_STARS


async def _edit_view(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest as exc:
        # Telegram returns this for a repeated tap on an already rendered
        # screen. It is safe to acknowledge and keep the current view.
        if "message is not modified" not in str(exc).lower():
            raise
    await navigation.set_ui_message(state, message.message_id)


async def _edit_ui_message(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> bool:
    message_id = await navigation.get_ui_message_id(state)
    if not message_id:
        return False
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            **kwargs,
        )
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return True
        logger.warning("Unable to edit navigation message %s: %s", message_id, exc)
        return False


async def _main_view(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    price = await _get_price_stars()
    return t("welcome", lang), main_menu(lang, price)


async def _devices_view(
    telegram_id: int, lang: str
) -> tuple[str, InlineKeyboardMarkup]:
    try:
        devices = await billing_client.get_devices(telegram_id)
    except Exception as exc:
        logger.error("get_devices failed: %s", exc)
        devices = []

    price = await _get_price_stars()
    if not devices:
        return t("devices_empty", lang, price=price), back_keyboard(lang)

    lines = [t("devices_title", lang), ""]
    for number, device in enumerate(devices, start=1):
        status = t(f"status_{device['status']}", lang)
        expires = (device.get("expires_at") or "")[:10] or t("unknown_expiry", lang)
        emoji = STATUS_EMOJI.get(device["status"], "❔")
        lines.append(
            t(
                "device_line",
                lang,
                emoji=emoji,
                n=number,
                status=status,
                expires=expires,
            )
        )
    return "\n".join(lines), devices_keyboard(lang, devices, price)


async def _device_view(
    telegram_id: int, lang: str, subscription_id: int
) -> tuple[str, InlineKeyboardMarkup | None]:
    try:
        devices = await billing_client.get_devices(telegram_id)
    except Exception as exc:
        logger.error("get_devices failed: %s", exc)
        devices = []
    device_number = next(
        (number for number, item in enumerate(devices, start=1) if item["id"] == subscription_id),
        None,
    )
    if device_number is None:
        return t("no_active_device", lang), back_keyboard(lang)

    device = devices[device_number - 1]
    status = t(f"status_{device['status']}", lang)
    expires = (device.get("expires_at") or "")[:10] or t("unknown_expiry", lang)
    text = t(
        "device_card",
        lang,
        n=device_number,
        status=status,
        expires=expires,
    )
    return text, device_card_keyboard(lang, device, device_number, await _get_price_stars())


async def _plan_view(
    lang: str, mode: str, target_id: int | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    try:
        plan = await billing_client.get_plan()
    except Exception as exc:
        logger.error("get_plan failed: %s", exc)
        plan = None
    if not plan:
        return t("plan_unavailable", lang), back_keyboard(lang)

    if mode == "renew":
        number = target_id or 0
        # The number is only cosmetic; the subscription id remains the source
        # of truth for the payment payload.
        text = t(
            "renew_card",
            lang,
            n=number,
            duration_days=plan["duration_days"],
            price_stars=plan["price_stars"],
            price_usdt=plan["price_usdt"],
        )
    else:
        text = t(
            "plan_card",
            lang,
            name=t("plan_name_text", lang, duration_days=plan["duration_days"]),
            description=t("plan_description_text", lang, duration_days=plan["duration_days"]),
            duration_days=plan["duration_days"],
            price_stars=plan["price_stars"],
            price_usdt=plan["price_usdt"],
        )
    return text, payment_method_menu(lang, mode, target_id, plan["price_stars"])


async def _render_entry(
    message: Message, state: FSMContext, lang: str, entry: dict[str, Any]
) -> None:
    screen = entry.get("screen", "main")
    params = entry.get("params", {})
    if screen == "main":
        text, markup = await _main_view(lang)
    elif screen == "devices":
        text, markup = await _devices_view(message.chat.id, lang)
    elif screen == "device_card":
        text, markup = await _device_view(message.chat.id, lang, int(params["subscription_id"]))
    elif screen == "purchase_new":
        text, markup = await _plan_view(lang, "new")
    elif screen == "renew":
        text, markup = await _plan_view(lang, "renew", int(params["subscription_id"]))
    elif screen == "support":
        text, markup = t("support_text", lang, support_link=settings.SUPPORT_LINK), back_keyboard(lang)
    elif screen == "language":
        text, markup = t("language_prompt", lang), language_picker(lang, include_back=True)
    elif screen == "config_ready":
        text = t("config_ready", lang, expires=params.get("expires") or t("unknown_expiry", lang))
        markup = config_ready_keyboard(
            lang, bool(params.get("config_url")), int(params["subscription_id"])
        )
    elif screen == "provisioning":
        text, markup = t("provisioning_pending", lang), back_keyboard(lang)
    else:
        text, markup = await _main_view(lang)
        await navigation.reset(state)
    await _edit_view(message, state, text, markup, disable_web_page_preview=True)


async def _deliver_result(
    bot: Bot,
    chat_id: int,
    lang: str,
    state: FSMContext,
    result: dict,
    fallback_message: Message | None = None,
) -> None:
    config_url = result.get("config_url")
    sub_id = result["subscription_id"]
    expires = (result.get("expires_at") or "")[:10] or t("unknown_expiry", lang)
    if not config_url:
        await navigation.replace(state, "provisioning")
        text, markup = t("provisioning_pending", lang), back_keyboard(lang)
    else:
        await navigation.replace(
            state,
            "config_ready",
            subscription_id=sub_id,
            config_url=config_url,
            expires=expires,
        )
        text = t("config_ready", lang, expires=expires)
        markup = config_ready_keyboard(lang, True, sub_id)

    edited = await _edit_ui_message(bot, chat_id, state, text, markup, disable_web_page_preview=True)
    if edited or fallback_message is None:
        return
    await fallback_message.answer(text, reply_markup=markup, disable_web_page_preview=True)


async def _get_device_config_url(telegram_id: int, sub_id: int) -> str | None:
    try:
        devices = await billing_client.get_devices(telegram_id)
        device = next((item for item in devices if item["id"] == sub_id), None)
        return device.get("config_url") if device else None
    except Exception as exc:
        logger.warning("Failed to fetch device %s: %s", sub_id, exc)
        return None


async def _send_qr(bot: Bot, chat_id: int, lang: str, telegram_id: int, sub_id: int) -> None:
    config_url = await _get_device_config_url(telegram_id, sub_id)
    if not config_url:
        await bot.send_message(chat_id, t("qr_unavailable", lang))
        return
    try:
        await bot.send_photo(
            chat_id,
            photo=BufferedInputFile(generate_qr(config_url), filename="vpn_qr.png"),
            caption=t("qr_caption", lang),
        )
    except Exception as exc:
        logger.warning("QR generation failed: %s", exc)
        await bot.send_message(chat_id, t("qr_unavailable", lang))


async def _send_key(bot: Bot, chat_id: int, lang: str, telegram_id: int, sub_id: int) -> None:
    config_url = await _get_device_config_url(telegram_id, sub_id)
    if not config_url:
        await bot.send_message(chat_id, t("qr_unavailable", lang))
        return
    await bot.send_message(chat_id, t("config_key_message", lang, config_url=html.escape(config_url)))


# --- Root and stack navigation ------------------------------------------------

@router.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext, lang: str):
    if not lang:
        await msg.answer(t("language_prompt"), reply_markup=language_picker())
        return
    await navigation.reset(state)
    text, markup = await _main_view(lang)
    ui_message = await msg.answer(text, reply_markup=markup)
    await navigation.set_ui_message(state, ui_message.message_id)


@router.callback_query(F.data == "start")
async def cb_start(cb: CallbackQuery, state: FSMContext, lang: str):
    await navigation.reset(state)
    await _render_entry(cb.message, state, lang, await navigation.current(state))
    await cb.answer()


@router.callback_query(F.data == "nav:back")
async def cb_back(cb: CallbackQuery, state: FSMContext, lang: str):
    entry = await navigation.back(state)
    if entry["screen"].startswith("admin_"):
        # Admin handlers use the same stack primitive; the admin root is the
        # only admin target needed when going one level back.
        from bot.keyboards.keyboards import admin_menu

        await _edit_view(cb.message, state, t("adm_panel_title", lang), admin_menu(lang))
    else:
        await _render_entry(cb.message, state, lang, entry)
    await cb.answer()


@router.callback_query(F.data == "nav:language")
async def cb_language_menu(cb: CallbackQuery, state: FSMContext, lang: str):
    await navigation.push(state, "language")
    await _render_entry(cb.message, state, lang, await navigation.current(state))
    await cb.answer()


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(cb: CallbackQuery, state: FSMContext):
    new_lang = cb.data.split(":", 1)[1]
    try:
        await billing_client.set_user_language(cb.from_user.id, new_lang)
    except Exception as exc:
        logger.error("Failed to save language for %s: %s", cb.from_user.id, exc)
    await navigation.reset(state)
    await _render_entry(cb.message, state, new_lang, await navigation.current(state))
    await cb.answer(t("language_saved", new_lang))


@router.callback_query(F.data == "nav:devices")
async def cb_devices(cb: CallbackQuery, state: FSMContext, lang: str):
    await navigation.push(state, "devices")
    await _render_entry(cb.message, state, lang, await navigation.current(state))
    await cb.answer()


@router.callback_query(F.data.startswith("nav:device:"))
async def cb_device(cb: CallbackQuery, state: FSMContext, lang: str):
    await navigation.push(state, "device_card", subscription_id=int(cb.data.rsplit(":", 1)[1]))
    await _render_entry(cb.message, state, lang, await navigation.current(state))
    await cb.answer()


@router.callback_query(F.data == "nav:buy_new")
async def cb_buy_new(cb: CallbackQuery, state: FSMContext, lang: str):
    await navigation.push(state, "purchase_new")
    await _render_entry(cb.message, state, lang, await navigation.current(state))
    await cb.answer()


@router.callback_query(F.data.startswith("nav:renew:"))
async def cb_renew(cb: CallbackQuery, state: FSMContext, lang: str):
    await navigation.push(state, "renew", subscription_id=int(cb.data.rsplit(":", 1)[1]))
    await _render_entry(cb.message, state, lang, await navigation.current(state))
    await cb.answer()


@router.callback_query(F.data == "nav:support")
async def cb_support(cb: CallbackQuery, state: FSMContext, lang: str):
    await navigation.push(state, "support")
    await _render_entry(cb.message, state, lang, await navigation.current(state))
    await cb.answer()


# --- Payments -----------------------------------------------------------------

@router.callback_query(F.data.startswith("pay_stars:"))
async def cb_pay_stars(cb: CallbackQuery, bot: Bot, lang: str):
    _, mode, target = cb.data.split(":")
    target_id = int(target) if target != "0" else 0
    try:
        plan = await billing_client.get_plan()
    except Exception as exc:
        logger.error("get_plan failed: %s", exc)
        plan = None
    if not plan:
        await cb.answer(t("plan_load_error", lang), show_alert=True)
        return
    plan_name = t("plan_name_text", lang, duration_days=plan["duration_days"])
    await bot.send_invoice(
        chat_id=cb.from_user.id,
        title=plan_name,
        description=t("plan_description_text", lang, duration_days=plan["duration_days"]),
        payload=f"stars:{mode}:{target_id}:{plan['id']}",
        currency="XTR",
        prices=[LabeledPrice(label=plan_name, amount=plan["price_stars"])],
        provider_token="",
    )
    await cb.answer()


@router.pre_checkout_query()
async def pre_checkout(pq: PreCheckoutQuery):
    await pq.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(msg: Message, state: FSMContext, lang: str):
    payment: SuccessfulPayment = msg.successful_payment
    parts = payment.invoice_payload.split(":")
    mode = parts[1] if len(parts) > 1 else "new"
    target = int(parts[2]) if len(parts) > 2 and parts[2] != "0" else None
    plan_id = int(parts[3]) if len(parts) > 3 else None
    action_key = "payment_processing_renew" if mode == "renew" else "payment_processing_new"
    await _edit_ui_message(
        msg.bot,
        msg.chat.id,
        state,
        t("payment_processing", lang, action=t(action_key, lang)),
        back_keyboard(lang),
    )
    try:
        result = await billing_client.handle_stars_payment(
            telegram_id=msg.from_user.id,
            username=msg.from_user.username,
            first_name=msg.from_user.first_name,
            last_name=msg.from_user.last_name,
            charge_id=payment.telegram_payment_charge_id,
            total_amount=payment.total_amount,
            plan_id=plan_id,
            mode=mode,
            target_subscription_id=target,
        )
    except Exception as exc:
        logger.error("Stars payment processing failed: %s", exc)
        await navigation.replace(state, "support")
        await _edit_ui_message(msg.bot, msg.chat.id, state, t("payment_error", lang), back_keyboard(lang))
        return
    await _deliver_result(msg.bot, msg.chat.id, lang, state, result, msg)


@router.callback_query(F.data.startswith("pay_usdt:"))
async def cb_pay_usdt(cb: CallbackQuery, state: FSMContext, lang: str):
    _, mode, target = cb.data.split(":")
    target_id = int(target) if target != "0" else None
    try:
        plan = await billing_client.get_plan()
    except Exception:
        plan = None
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
    except Exception as exc:
        logger.error("CryptoPay invoice creation failed: %s", exc)
        await cb.answer(t("usdt_invoice_error", lang), show_alert=True)
        return
    await navigation.push(state, "payment_usdt", invoice_id=invoice.get("invoice_id"), mode=mode, target_id=target_id)
    await _edit_view(
        cb.message,
        state,
        t("usdt_invoice_card", lang, amount=plan["price_usdt"], pay_url=invoice.get("pay_url", "")),
        check_usdt_payment(lang, str(invoice.get("invoice_id")), mode, target_id),
        disable_web_page_preview=True,
    )
    await cb.answer()


@router.callback_query(F.data.startswith("check_usdt:"))
async def cb_check_usdt(cb: CallbackQuery, state: FSMContext, lang: str):
    _, invoice_id_s, mode, target_s = cb.data.split(":")
    invoice_id = int(invoice_id_s)
    target_id = int(target_s) if target_s != "0" else None
    try:
        paid = await crypto_pay.is_paid(invoice_id)
    except Exception as exc:
        logger.error("CryptoPay check failed: %s", exc)
        await cb.answer(t("usdt_check_error", lang), show_alert=True)
        return
    if not paid:
        await cb.answer(t("usdt_not_paid_yet", lang), show_alert=True)
        return
    try:
        invoice = await crypto_pay.get_invoice(invoice_id)
    except Exception:
        invoice = {}
    parts = (invoice or {}).get("payload", "").split(":")
    plan_id = int(parts[1]) if len(parts) > 1 else None
    amount = float((invoice or {}).get("amount", settings.PLAN_PRICE_USDT))
    action_key = "payment_processing_renew" if mode == "renew" else "payment_processing_new"
    await _edit_view(cb.message, state, t("usdt_confirmed", lang, action=t(action_key, lang)), back_keyboard(lang))
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
    except Exception as exc:
        logger.error("USDT activation failed: %s", exc)
        await navigation.replace(state, "support")
        await _edit_view(cb.message, state, t("usdt_activation_error", lang), back_keyboard(lang))
        await cb.answer()
        return
    await _deliver_result(cb.bot, cb.from_user.id, lang, state, result, cb.message)
    await cb.answer()


@router.callback_query(F.data.startswith("show_qr:"))
async def cb_show_qr(cb: CallbackQuery, lang: str):
    await _send_qr(cb.bot, cb.from_user.id, lang, cb.from_user.id, int(cb.data.split(":")[1]))
    await cb.answer()


@router.callback_query(F.data.startswith("show_key:"))
async def cb_show_key(cb: CallbackQuery, lang: str):
    await _send_key(cb.bot, cb.from_user.id, lang, cb.from_user.id, int(cb.data.split(":")[1]))
    await cb.answer()
