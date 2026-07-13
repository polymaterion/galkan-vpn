"""
Main Telegram bot handlers.
/start, buy flow, subscription info, config delivery.
"""
from __future__ import annotations

import logging
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
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
    main_menu,
    payment_method_menu,
)
from bot.payments.crypto_pay import crypto_pay
from bot.utils import generate_qr

logger = logging.getLogger(__name__)
router = Router()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_info(msg_or_cb):
    user = msg_or_cb.from_user if hasattr(msg_or_cb, "from_user") else msg_or_cb.message.from_user
    return user


async def _send_config(bot: Bot, chat_id: int, config_url: str, expires_at: str | None):
    """Send the VPN config URL + QR to the user."""
    expires_text = f"\n⏳ Действует до: <b>{expires_at[:10] if expires_at else '?'}</b>" if expires_at else ""

    await bot.send_message(
        chat_id,
        f"✅ <b>Ваш VPN готов!</b>{expires_text}\n\n"
        f"🔗 Скопируйте ссылку и импортируйте в приложение <b>Amnezia VPN</b>:\n"
        f"<code>{config_url[:120]}...</code>\n\n"
        f"📱 Или отсканируйте QR-код ниже.",
        parse_mode="HTML",
    )
    try:
        qr_bytes = generate_qr(config_url)
        await bot.send_photo(
            chat_id,
            photo=BufferedInputFile(qr_bytes, filename="vpn_qr.png"),
            caption="📷 QR-код для Amnezia VPN",
        )
    except Exception as e:
        logger.warning("QR generation failed: %s", e)
        # Fallback: send full URL as text
        await bot.send_message(chat_id, f"<code>{config_url}</code>", parse_mode="HTML")


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(msg: Message):
    sub = None
    try:
        sub = await billing_client.get_subscription(msg.from_user.id)
    except Exception:
        pass

    has_sub = sub is not None and sub.get("status") == "active"
    await msg.answer(
        "👋 Добро пожаловать в <b>VPN Bot</b>!\n\n"
        "🛡 Безопасный VPN на основе AmneziaWG — обходит блокировки без следов.\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu(has_subscription=has_sub),
    )


@router.callback_query(F.data == "start")
async def cb_start(cb: CallbackQuery):
    sub = None
    try:
        sub = await billing_client.get_subscription(cb.from_user.id)
    except Exception:
        pass
    has_sub = sub is not None and sub.get("status") == "active"
    await cb.message.edit_text(
        "👋 Добро пожаловать в <b>VPN Bot</b>!\n\n"
        "🛡 Безопасный VPN на основе AmneziaWG — обходит блокировки без следов.\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu(has_subscription=has_sub),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Buy flow
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "buy")
async def cb_buy(cb: CallbackQuery):
    plan = None
    try:
        plan = await billing_client.get_plan()
    except Exception as e:
        logger.error("get_plan failed: %s", e)

    if not plan:
        await cb.answer("Тарифы временно недоступны.", show_alert=True)
        return

    text = (
        f"💎 <b>{plan['name']}</b>\n\n"
        f"{plan.get('description', '')}\n\n"
        f"⏱ Срок: <b>{plan['duration_days']} дней</b>\n"
        f"⭐ Стоимость: <b>{plan['price_stars']} Telegram Stars</b>\n"
        f"💵 или <b>${plan['price_usdt']} USDT</b>\n\n"
        "Выберите способ оплаты:"
    )
    await cb.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=payment_method_menu(plan["id"]),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Payment — Telegram Stars
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("pay_stars:"))
async def cb_pay_stars(cb: CallbackQuery, bot: Bot):
    plan_id = int(cb.data.split(":")[1])
    plan = None
    try:
        plan = await billing_client.get_plan()
    except Exception:
        pass

    if not plan:
        await cb.answer("Ошибка загрузки тарифа.", show_alert=True)
        return

    await bot.send_invoice(
        chat_id=cb.from_user.id,
        title=plan["name"],
        description=plan.get("description", "VPN подписка"),
        payload=f"stars:{plan['id']}:{cb.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=plan["name"], amount=plan["price_stars"])],
        provider_token="",  # Empty for Stars
    )
    await cb.answer()


@router.pre_checkout_query()
async def pre_checkout(pq: PreCheckoutQuery):
    """Telegram calls this before completing Stars payment. Must answer within 10s."""
    await pq.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(msg: Message):
    sp: SuccessfulPayment = msg.successful_payment
    payload_parts = sp.invoice_payload.split(":")
    plan_id = int(payload_parts[1]) if len(payload_parts) > 1 else None

    await msg.answer("⏳ Оплата получена! Создаём VPN-доступ...", parse_mode="HTML")

    try:
        result = await billing_client.handle_stars_payment(
            telegram_id=msg.from_user.id,
            username=msg.from_user.username,
            first_name=msg.from_user.first_name,
            last_name=msg.from_user.last_name,
            charge_id=sp.telegram_payment_charge_id,
            total_amount=sp.total_amount,
            plan_id=plan_id,
        )
    except Exception as e:
        logger.error("Stars payment processing failed: %s", e)
        await msg.answer(
            "❗ Оплата прошла, но возникла ошибка при создании VPN-доступа.\n"
            "Обратитесь в поддержку — мы всё исправим!",
            reply_markup=back_to_menu(),
        )
        return

    config_url = result.get("config_url")
    if config_url:
        await _send_config(msg.bot, msg.chat.id, config_url, result.get("expires_at"))
    else:
        await msg.answer(
            "⏳ VPN-доступ создаётся, это займёт несколько минут.\n"
            "Вы получите конфиг, как только он будет готов.",
            reply_markup=back_to_menu(),
        )


# ---------------------------------------------------------------------------
# Payment — USDT via CryptoPay
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("pay_usdt:"))
async def cb_pay_usdt(cb: CallbackQuery):
    plan_id = int(cb.data.split(":")[1])
    plan = None
    try:
        plan = await billing_client.get_plan()
    except Exception:
        pass

    if not plan or not settings.CRYPTOPAY_TOKEN:
        await cb.answer(
            "USDT оплата временно недоступна. Попробуйте Telegram Stars.",
            show_alert=True,
        )
        return

    try:
        invoice = await crypto_pay.create_invoice(
            amount=float(plan["price_usdt"]),
            asset="USDT",
            description=f"{plan['name']} — VPN",
            payload=f"{cb.from_user.id}:{plan['id']}",
        )
    except Exception as e:
        logger.error("CryptoPay invoice creation failed: %s", e)
        await cb.answer("Ошибка создания инвойса. Попробуйте позже.", show_alert=True)
        return

    pay_url = invoice.get("pay_url", "")
    invoice_id = invoice.get("invoice_id")

    await cb.message.edit_text(
        f"💎 <b>Оплата USDT</b>\n\n"
        f"Сумма: <b>${plan['price_usdt']} USDT</b>\n\n"
        f"👉 <a href='{pay_url}'>Перейти к оплате</a>\n\n"
        f"После оплаты нажмите кнопку ✅",
        parse_mode="HTML",
        reply_markup=check_usdt_payment(invoice_id),
        disable_web_page_preview=True,
    )
    await cb.answer()


@router.callback_query(F.data.startswith("check_usdt:"))
async def cb_check_usdt(cb: CallbackQuery):
    invoice_id = int(cb.data.split(":")[1])

    try:
        paid = await crypto_pay.is_paid(invoice_id)
    except Exception as e:
        logger.error("CryptoPay check failed: %s", e)
        await cb.answer("Ошибка проверки оплаты. Попробуйте позже.", show_alert=True)
        return

    if not paid:
        await cb.answer("Оплата ещё не поступила. Попробуйте через минуту.", show_alert=True)
        return

    # Get invoice details to extract amount and user
    try:
        invoice = await crypto_pay.get_invoice(invoice_id)
    except Exception:
        invoice = {}

    payload = (invoice or {}).get("payload", "")
    parts = payload.split(":")
    plan_id = int(parts[1]) if len(parts) > 1 else None
    amount = float((invoice or {}).get("amount", settings.PLAN_PRICE_USDT))

    await cb.message.edit_text("⏳ Оплата подтверждена! Создаём VPN-доступ...")

    try:
        result = await billing_client.handle_usdt_payment(
            telegram_id=cb.from_user.id,
            username=cb.from_user.username,
            first_name=cb.from_user.first_name,
            last_name=cb.from_user.last_name,
            invoice_id=str(invoice_id),
            amount=amount,
            plan_id=plan_id,
        )
    except Exception as e:
        logger.error("USDT payment processing failed: %s", e)
        await cb.message.answer(
            "❗ Ошибка при активации. Обратитесь в поддержку.",
            reply_markup=back_to_menu(),
        )
        return

    config_url = result.get("config_url")
    if config_url:
        await _send_config(cb.bot, cb.from_user.id, config_url, result.get("expires_at"))
    else:
        await cb.message.answer(
            "⏳ VPN создаётся. Конфиг придёт в течение нескольких минут.",
            reply_markup=back_to_menu(),
        )
    await cb.answer()


# ---------------------------------------------------------------------------
# My subscription
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "my_sub")
async def cb_my_sub(cb: CallbackQuery):
    try:
        sub = await billing_client.get_subscription(cb.from_user.id)
    except Exception:
        sub = None

    if not sub:
        await cb.answer("Активная подписка не найдена.", show_alert=True)
        return

    status_emoji = {
        "active": "✅",
        "expired": "❌",
        "pending_provisioning": "⏳",
        "error": "⚠️",
        "disabled": "🔒",
    }.get(sub["status"], "❓")

    expires = sub.get("expires_at", "")[:10] if sub.get("expires_at") else "неизвестно"

    await cb.message.edit_text(
        f"{status_emoji} <b>Ваша подписка</b>\n\n"
        f"Тариф: <b>{sub.get('plan_name', '—')}</b>\n"
        f"Статус: <b>{sub['status']}</b>\n"
        f"Действует до: <b>{expires}</b>",
        parse_mode="HTML",
        reply_markup=main_menu(has_subscription=True),
    )
    await cb.answer()


# ---------------------------------------------------------------------------
# Get config (resend)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "get_config")
async def cb_get_config(cb: CallbackQuery):
    try:
        sub = await billing_client.get_subscription(cb.from_user.id)
    except Exception:
        sub = None

    if not sub or not sub.get("config_url"):
        await cb.answer("Конфигурация недоступна. Попробуйте позже.", show_alert=True)
        return

    await _send_config(cb.bot, cb.from_user.id, sub["config_url"], sub.get("expires_at"))
    await cb.answer()


# ---------------------------------------------------------------------------
# Support
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "support")
async def cb_support(cb: CallbackQuery):
    await cb.message.edit_text(
        f"💬 <b>Поддержка</b>\n\n"
        f"По любым вопросам: {settings.SUPPORT_LINK}",
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )
    await cb.answer()
