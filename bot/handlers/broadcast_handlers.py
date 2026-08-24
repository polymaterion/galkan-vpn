"""
/broadcast — admin-only mass messaging to every user who has ever
/start'ed the bot (their telegram_id lives in the `users` table, populated
by LanguageMiddleware's get_or_create() on every update, so this covers
everyone the bot has ever seen — not just people with an active
subscription).

Flow (aiogram FSM, MemoryStorage — same as the rest of the bot):
  1. /broadcast            -> BroadcastStates.waiting_content
  2. admin sends the message (text, or photo/video/animation + caption)
                            -> BroadcastStates.waiting_buttons
  3. admin sends button lines, or taps "Skip"
                            -> BroadcastStates.waiting_confirm
  4. admin taps "Send" (bc:send) -> fans out via bot.copy_message(), or
     "Cancel" (bc:cancel) to abort. /cancel works at any step.

The source message the admin sent in step 2 is copied to every recipient
via Bot.copy_message() — this handles text/photo/video/animation/document
uniformly without the handler needing to branch on content type, and lets
us attach the url-button keyboard from step 3 to the copy.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.billing_client import billing_client
from bot.config import settings
from bot.keyboards.keyboards import (
    broadcast_confirm_keyboard,
    broadcast_link_buttons,
    broadcast_skip_keyboard,
)
from bot.locales import t

logger = logging.getLogger(__name__)
router = Router()

MAX_BUTTONS = 2
# Telegram allows ~30 msg/sec bot-wide across ALL chats, but bursts to a
# single-digit number of *different* users per second are the practical
# safe ceiling before hitting 429s in normal (non-broadcast-tier) bots.
# Small sleep between sends keeps this comfortably under that regardless of
# list size, at the cost of the broadcast itself taking longer.
SEND_INTERVAL_SECONDS = 0.05


class BroadcastStates(StatesGroup):
    waiting_content = State()
    waiting_buttons = State()
    waiting_confirm = State()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids_list


def _parse_buttons(text: str) -> tuple[list[tuple[str, str]] | None, str | None]:
    """Parses button lines in "Label - https://url" format.

    Returns (buttons, None) on success, or (None, error_message_key_data)
    on the first invalid line — the caller re-prompts rather than trying to
    salvage a partial list, since silently dropping a malformed button the
    admin meant to include is worse than asking them to resend.
    """
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    buttons: list[tuple[str, str]] = []
    for n, line in enumerate(lines, start=1):
        if " - " not in line:
            return None, ("bc_invalid_button_line", {"n": n, "line": line})
        label, url = line.split(" - ", 1)
        label, url = label.strip(), url.strip()
        if not label or not url:
            return None, ("bc_invalid_button_line", {"n": n, "line": line})
        if not (url.startswith("http://") or url.startswith("https://")):
            return None, ("bc_invalid_button_url", {"n": n, "url": url})
        buttons.append((label, url))
    if len(buttons) > MAX_BUTTONS:
        return None, ("bc_too_many_buttons", {"n": len(buttons)})
    return buttons, None


# --- Entry point ---------------------------------------------------------

@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message, state: FSMContext, lang: str):
    if not _is_admin(msg.from_user.id):
        return
    await state.set_state(BroadcastStates.waiting_content)
    await msg.answer(t("bc_start", lang))


@router.message(Command("cancel"), BroadcastStates.waiting_content)
@router.message(Command("cancel"), BroadcastStates.waiting_buttons)
@router.message(Command("cancel"), BroadcastStates.waiting_confirm)
async def cmd_broadcast_cancel(msg: Message, state: FSMContext, lang: str):
    await state.clear()
    await msg.answer(t("bc_cancelled", lang))


# --- Step 1: content -------------------------------------------------------

@router.message(BroadcastStates.waiting_content)
async def bc_receive_content(msg: Message, state: FSMContext, lang: str):
    # Anything with no text/caption and no media at all (e.g. a sticker with
    # no caption support, or a service message) isn't broadcastable.
    has_content = bool(msg.text or msg.caption or msg.photo or msg.video or msg.animation or msg.document)
    if not has_content:
        await msg.answer(t("bc_empty_content", lang))
        return

    await state.update_data(source_chat_id=msg.chat.id, source_message_id=msg.message_id)
    await state.set_state(BroadcastStates.waiting_buttons)
    await msg.answer(t("bc_ask_buttons", lang), reply_markup=broadcast_skip_keyboard(lang))


# --- Step 2: buttons ---------------------------------------------------

async def _go_to_confirm(msg: Message, state: FSMContext, lang: str, buttons: list[tuple[str, str]]) -> None:
    data = await state.get_data()
    await state.update_data(buttons=buttons)
    await state.set_state(BroadcastStates.waiting_confirm)

    try:
        ids = await billing_client.admin_broadcast_ids()
    except Exception as exc:
        logger.error("admin_broadcast_ids failed: %s", exc)
        await msg.answer(t("adm_generic_error", lang, error=exc))
        await state.clear()
        return

    if not ids:
        await msg.answer(t("bc_no_recipients", lang))
        await state.clear()
        return

    await state.update_data(recipient_ids=ids)

    markup = broadcast_link_buttons(buttons)
    await msg.answer(t("bc_preview_title", lang))
    await msg.bot.copy_message(
        chat_id=msg.chat.id,
        from_chat_id=data["source_chat_id"],
        message_id=data["source_message_id"],
        reply_markup=markup,
    )
    await msg.answer(
        t("bc_confirm_prompt", lang, count=len(ids)),
        reply_markup=broadcast_confirm_keyboard(lang),
    )


@router.callback_query(BroadcastStates.waiting_buttons, F.data == "bc:skip_buttons")
async def bc_skip_buttons(cb: CallbackQuery, state: FSMContext, lang: str):
    await cb.answer()
    await _go_to_confirm(cb.message, state, lang, [])


@router.message(BroadcastStates.waiting_buttons)
async def bc_receive_buttons(msg: Message, state: FSMContext, lang: str):
    text = (msg.text or "").strip()
    if text in ("-", "", "Пропустить", "Geçmek") or text.lower() == "skip":
        await _go_to_confirm(msg, state, lang, [])
        return

    buttons, error = _parse_buttons(text)
    if error:
        key, params = error
        await msg.answer(t(key, lang, **params))
        return

    await _go_to_confirm(msg, state, lang, buttons)


# --- Step 3: confirm & send ----------------------------------------------

@router.callback_query(BroadcastStates.waiting_confirm, F.data == "bc:cancel")
async def bc_cancel(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await cb.answer()
    await cb.message.answer(t("bc_cancelled", lang))


@router.callback_query(BroadcastStates.waiting_confirm, F.data == "bc:send")
async def bc_send(cb: CallbackQuery, state: FSMContext, lang: str):
    data = await state.get_data()
    await state.clear()
    await cb.answer()

    ids: list[int] = data.get("recipient_ids", [])
    buttons: list[tuple[str, str]] = [tuple(b) for b in data.get("buttons", [])]
    source_chat_id = data["source_chat_id"]
    source_message_id = data["source_message_id"]
    markup: InlineKeyboardMarkup | None = broadcast_link_buttons(buttons)

    await cb.message.answer(t("bc_sending", lang, total=len(ids)))

    sent = 0
    failed = 0
    for telegram_id in ids:
        try:
            await cb.bot.copy_message(
                chat_id=telegram_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
                reply_markup=markup,
            )
            sent += 1
        except Exception as exc:
            # Expected in bulk: users who blocked the bot, deleted their
            # account, or never actually had a DM chat opened with it.
            # Logged at debug so one broadcast run doesn't flood the logs;
            # the sent/failed counts in the summary are the actionable signal.
            logger.debug("Broadcast failed for %s: %s", telegram_id, exc)
            failed += 1
        await asyncio.sleep(SEND_INTERVAL_SECONDS)

    await cb.message.answer(t("bc_done", lang, sent=sent, failed=failed, total=len(ids)))
