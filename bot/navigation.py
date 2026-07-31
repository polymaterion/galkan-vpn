"""Small, storage-agnostic navigation stack for Telegram screens.

The Telegram message is the viewport.  ``FSMContext`` stores the stack for
each user, while handlers are responsible for rendering the screen returned
by :func:`back`.  Keeping the stack separate from callback payloads means a
back tap always returns to the actual previous screen, even when the user
entered a screen from a different branch.
"""
from __future__ import annotations

from typing import Any

from aiogram.fsm.context import FSMContext

STACK_KEY = "navigation_stack"
UI_MESSAGE_ID_KEY = "navigation_ui_message_id"


def _entry(screen: str, **params: Any) -> dict[str, Any]:
    return {"screen": screen, "params": params}


async def reset(state: FSMContext, screen: str = "main", **params: Any) -> None:
    """Start a new navigation session at ``screen``."""
    await state.update_data(navigation_stack=[_entry(screen, **params)])


async def push(state: FSMContext, screen: str, **params: Any) -> None:
    data = await state.get_data()
    stack = list(data.get(STACK_KEY, []))
    if not stack:
        stack = [_entry("main")]
    stack.append(_entry(screen, **params))
    await state.update_data(navigation_stack=stack)


async def replace(state: FSMContext, screen: str, **params: Any) -> None:
    """Replace the current screen without changing its parent."""
    data = await state.get_data()
    stack = list(data.get(STACK_KEY, []))
    if not stack:
        stack = [_entry("main")]
    stack[-1] = _entry(screen, **params)
    await state.update_data(navigation_stack=stack)


async def back(state: FSMContext) -> dict[str, Any]:
    """Pop one level and return the screen to render.

    The root is never popped; this makes a stale or repeated back callback
    safe and guarantees that the main screen never renders a back button.
    """
    data = await state.get_data()
    stack = list(data.get(STACK_KEY, []))
    if not stack:
        stack = [_entry("main")]
    if len(stack) > 1:
        stack.pop()
    await state.update_data(navigation_stack=stack)
    return stack[-1]


async def current(state: FSMContext) -> dict[str, Any]:
    data = await state.get_data()
    stack = list(data.get(STACK_KEY, []))
    return stack[-1] if stack else _entry("main")


async def set_ui_message(state: FSMContext, message_id: int) -> None:
    await state.update_data(**{UI_MESSAGE_ID_KEY: message_id})


async def get_ui_message_id(state: FSMContext) -> int | None:
    data = await state.get_data()
    value = data.get(UI_MESSAGE_ID_KEY)
    return int(value) if value else None
