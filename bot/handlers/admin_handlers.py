"""
Admin Telegram commands.
Only accessible to users in ADMIN_IDS.

Navigation is deliberately kept separate from the customer-facing flow:
every admin screen's "back" button returns to the admin panel (callback
"adm_menu", handled here), never to the customer main menu ("start", handled
in main_handlers.py). Mixing the two meant an admin browsing e.g. Users and
tapping "back" would land in the "buy a device" screen instead of back in
the admin panel — confusing and easy to mis-tap through by accident.

The admin panel respects the admin's own selected language (same `lang`
middleware-injected value as the rest of the bot) rather than being
hardcoded to Russian — every string lives in bot/locales/{ru,tk}.py under
the "adm_" prefix.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.billing_client import billing_client
from bot.config import settings
from bot.keyboards.keyboards import admin_back_keyboard, admin_menu
from bot.locales import t

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids_list


# --- Admin panel entry / navigation ---

@router.message(Command("admin"))
async def cmd_admin(msg: Message, lang: str):
    if not _is_admin(msg.from_user.id):
        await msg.answer(t("adm_access_denied", lang))
        return
    await msg.answer(t("adm_panel_title", lang), reply_markup=admin_menu(lang))


@router.callback_query(F.data == "adm_menu")
async def cb_adm_menu(cb: CallbackQuery, lang: str):
    """Back button target for every admin sub-screen — stays within the
    admin panel, never falls through to the customer menu."""
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("adm_no_access", lang), show_alert=True)
        return
    await cb.message.edit_text(t("adm_panel_title", lang), reply_markup=admin_menu(lang))
    await cb.answer()


# --- Users ---
@router.callback_query(F.data == "adm_users")
async def adm_users(cb: CallbackQuery, lang: str):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("adm_no_access", lang), show_alert=True)
        return
    try:
        data = await billing_client.admin_list_users()
    except Exception as e:
        await cb.answer(t("adm_error", lang, error=e), show_alert=True)
        return

    total = data.get("total", 0)
    users = data.get("items", [])
    lines = [t("adm_users_title", lang, total=total)]
    for u in users[:15]:
        uname = f"@{u['username']}" if u.get("username") else u.get("first_name", "—")
        lines.append(f"• <code>{u['telegram_id']}</code> {uname}")

    await cb.message.edit_text("\n".join(lines), reply_markup=admin_back_keyboard(lang))
    await cb.answer()


# --- Subscriptions ---
@router.callback_query(F.data == "adm_subs")
async def adm_subs(cb: CallbackQuery, lang: str):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("adm_no_access", lang), show_alert=True)
        return
    try:
        data = await billing_client.admin_list_subscriptions()
    except Exception as e:
        await cb.answer(t("adm_error", lang, error=e), show_alert=True)
        return

    subs = data.get("items", [])
    lines = [t("adm_subs_title", lang)]
    for s in subs[:15]:
        exp = (s.get("expires_at") or "")[:10]
        lines.append(f"• #{s['id']} user={s['user_id']} [{s['status']}] до {exp}")

    await cb.message.edit_text("\n".join(lines), reply_markup=admin_back_keyboard(lang))
    await cb.answer()


# --- Payments ---
@router.callback_query(F.data == "adm_payments")
async def adm_payments(cb: CallbackQuery, lang: str):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("adm_no_access", lang), show_alert=True)
        return
    try:
        data = await billing_client.admin_list_payments()
    except Exception as e:
        await cb.answer(t("adm_error", lang, error=e), show_alert=True)
        return

    items = data.get("items", [])
    lines = [t("adm_payments_title", lang)]
    for p in items[:15]:
        lines.append(
            f"• #{p['id']} {p['provider']} {p['amount']} {p['currency']} [{p['status']}]"
        )

    await cb.message.edit_text("\n".join(lines), reply_markup=admin_back_keyboard(lang))
    await cb.answer()


# --- Servers ---
@router.callback_query(F.data == "adm_servers")
async def adm_servers(cb: CallbackQuery, lang: str):
    if not _is_admin(cb.from_user.id):
        await cb.answer(t("adm_no_access", lang), show_alert=True)
        return
    try:
        data = await billing_client.admin_list_servers()
    except Exception as e:
        await cb.answer(t("adm_error", lang, error=e), show_alert=True)
        return

    items = data.get("items", [])
    lines = [t("adm_servers_title", lang)]
    for s in items:
        load = s.get("load", {})
        cpu = load.get("cpu", "?")
        lines.append(
            f"• #{s['id']} {s['name']} [{s['status']}] protocol={s.get('protocol', '?')} "
            f"{s['current_clients']}/{s['max_clients']} клиентов CPU={cpu}"
        )

    await cb.message.edit_text(
        "\n".join(lines) if items else t("adm_no_servers", lang),
        reply_markup=admin_back_keyboard(lang),
    )
    await cb.answer()


# --- Text commands for admin actions ---

@router.message(Command("extend"))
async def cmd_extend(msg: Message, lang: str):
    """Usage: /extend <sub_id> [days]"""
    if not _is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer(t("adm_extend_usage", lang))
        return
    try:
        sub_id = int(parts[1])
        days = int(parts[2]) if len(parts) > 2 else 30
        await billing_client.admin_extend_subscription(sub_id, days)
        await msg.answer(t("adm_extend_success", lang, sub_id=sub_id, days=days))
    except Exception as e:
        await msg.answer(t("adm_generic_error", lang, error=e))


@router.message(Command("disable_sub"))
async def cmd_disable_sub(msg: Message, lang: str):
    """Usage: /disable_sub <sub_id>"""
    if not _is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer(t("adm_disable_usage", lang))
        return
    try:
        sub_id = int(parts[1])
        await billing_client.admin_disable_subscription(sub_id)
        await msg.answer(t("adm_disable_success", lang, sub_id=sub_id))
    except Exception as e:
        await msg.answer(t("adm_generic_error", lang, error=e))


@router.message(Command("server_status"))
async def cmd_server_status(msg: Message, lang: str):
    """Usage: /server_status <server_id> <active|disabled>"""
    if not _is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 3:
        await msg.answer(t("adm_server_status_usage", lang))
        return
    try:
        server_id = int(parts[1])
        status = parts[2]
        await billing_client.admin_set_server_status(server_id, status)
        await msg.answer(t("adm_server_status_success", lang, server_id=server_id, status=status))
    except Exception as e:
        await msg.answer(t("adm_generic_error", lang, error=e))


@router.message(Command("add_server"))
async def cmd_add_server(msg: Message, lang: str):
    """
    Usage: /add_server <name> <base_url> <api_key> [region] [weight] [max_clients] [protocol]

    Example:
      /add_server Server-DE http://45.10.20.30 8f2a1c... DE 100 200 amneziawg2

    base_url should point at the amnezia-api instance on that VPN server
    (port 80 through its nginx proxy — not 4001). api_key is the
    FASTIFY_API_KEY that amnezia-api's setup.sh printed on that server.
    protocol must match what's actually installed/enabled on that server
    (check its amnezia-api .env: PROTOCOLS_ENABLED) — "amneziawg",
    "amneziawg2" or "xray". Wrong value causes every client creation on
    this server to fail with 400 Bad Request. Defaults to "amneziawg2".
    """
    if not _is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 4:
        await msg.answer(t("adm_add_server_usage", lang))
        return
    try:
        name = parts[1]
        base_url = parts[2]
        api_key = parts[3]
        region = parts[4] if len(parts) > 4 else "EU"
        weight = int(parts[5]) if len(parts) > 5 else 100
        max_clients = int(parts[6]) if len(parts) > 6 else 200
        protocol = parts[7] if len(parts) > 7 else "amneziawg2"
        result = await billing_client.admin_add_server(
            name=name,
            base_url=base_url,
            api_key=api_key,
            region=region,
            weight=weight,
            max_clients=max_clients,
            protocol=protocol,
        )
        await msg.answer(
            t(
                "adm_add_server_success",
                lang,
                id=result["id"],
                name=result["name"],
                protocol=result["protocol"],
            )
        )
    except Exception as e:
        await msg.answer(t("adm_generic_error", lang, error=e))
