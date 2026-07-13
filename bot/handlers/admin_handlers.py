"""
Admin Telegram commands.
Only accessible to users in ADMIN_IDS.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.billing_client import billing_client
from bot.config import settings
from bot.keyboards.keyboards import admin_menu, back_to_menu

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids_list


# --- Admin gate filter ---
@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not _is_admin(msg.from_user.id):
        await msg.answer("⛔ Доступ запрещён.")
        return
    await msg.answer("🔧 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=admin_menu())


# --- Users ---
@router.callback_query(F.data == "adm_users")
async def adm_users(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    try:
        data = await billing_client.admin_list_users()
    except Exception as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return

    total = data.get("total", 0)
    users = data.get("items", [])
    lines = [f"👥 <b>Пользователи</b> (всего: {total})\n"]
    for u in users[:15]:
        uname = f"@{u['username']}" if u.get("username") else u.get("first_name", "—")
        lines.append(f"• <code>{u['telegram_id']}</code> {uname}")

    await cb.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )
    await cb.answer()


# --- Subscriptions ---
@router.callback_query(F.data == "adm_subs")
async def adm_subs(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    try:
        data = await billing_client.admin_list_subscriptions()
    except Exception as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return

    subs = data.get("items", [])
    lines = [f"📋 <b>Подписки</b>\n"]
    for s in subs[:15]:
        exp = (s.get("expires_at") or "")[:10]
        lines.append(f"• #{s['id']} user={s['user_id']} [{s['status']}] до {exp}")

    await cb.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )
    await cb.answer()


# --- Payments ---
@router.callback_query(F.data == "adm_payments")
async def adm_payments(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    try:
        data = await billing_client.admin_list_payments()
    except Exception as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return

    items = data.get("items", [])
    lines = [f"💰 <b>Платежи</b>\n"]
    for p in items[:15]:
        lines.append(
            f"• #{p['id']} {p['provider']} {p['amount']} {p['currency']} [{p['status']}]"
        )

    await cb.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )
    await cb.answer()


# --- Servers ---
@router.callback_query(F.data == "adm_servers")
async def adm_servers(cb: CallbackQuery):
    if not _is_admin(cb.from_user.id):
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    try:
        data = await billing_client.admin_list_servers()
    except Exception as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return

    items = data.get("items", [])
    lines = [f"🖥 <b>Серверы VPN</b>\n"]
    for s in items:
        load = s.get("load", {})
        cpu = load.get("cpu", "?")
        lines.append(
            f"• #{s['id']} {s['name']} [{s['status']}] "
            f"{s['current_clients']}/{s['max_clients']} клиентов CPU={cpu}"
        )

    await cb.message.edit_text(
        "\n".join(lines) or "Нет серверов",
        parse_mode="HTML",
        reply_markup=back_to_menu(),
    )
    await cb.answer()


# --- Text commands for admin actions ---

@router.message(Command("extend"))
async def cmd_extend(msg: Message):
    """Usage: /extend <sub_id> [days]"""
    if not _is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Usage: /extend <sub_id> [days=30]")
        return
    try:
        sub_id = int(parts[1])
        days = int(parts[2]) if len(parts) > 2 else 30
        await billing_client.admin_extend_subscription(sub_id, days)
        await msg.answer(f"✅ Подписка #{sub_id} продлена на {days} дней.")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")


@router.message(Command("disable_sub"))
async def cmd_disable_sub(msg: Message):
    """Usage: /disable_sub <sub_id>"""
    if not _is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Usage: /disable_sub <sub_id>")
        return
    try:
        sub_id = int(parts[1])
        await billing_client.admin_disable_subscription(sub_id)
        await msg.answer(f"✅ Подписка #{sub_id} отключена.")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")


@router.message(Command("server_status"))
async def cmd_server_status(msg: Message):
    """Usage: /server_status <server_id> <active|disabled>"""
    if not _is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 3:
        await msg.answer("Usage: /server_status <server_id> <active|disabled>")
        return
    try:
        server_id = int(parts[1])
        status = parts[2]
        await billing_client.admin_set_server_status(server_id, status)
        await msg.answer(f"✅ Сервер #{server_id} → {status}")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
