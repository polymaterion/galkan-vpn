"""Unit tests for bot/handlers/broadcast_handlers.py's pure logic —
_parse_buttons(). No Telegram/DB/network involved.
"""
from bot.handlers.broadcast_handlers import _parse_buttons, MAX_BUTTONS


def test_parse_single_button():
    buttons, error = _parse_buttons("Открыть сайт - https://example.com")
    assert error is None
    assert buttons == [("Открыть сайт", "https://example.com")]


def test_parse_two_buttons_multiline():
    text = "Сайт - https://example.com\nПоддержка - https://t.me/support"
    buttons, error = _parse_buttons(text)
    assert error is None
    assert buttons == [
        ("Сайт", "https://example.com"),
        ("Поддержка", "https://t.me/support"),
    ]


def test_parse_ignores_blank_lines():
    text = "\n\nСайт - https://example.com\n\n"
    buttons, error = _parse_buttons(text)
    assert error is None
    assert buttons == [("Сайт", "https://example.com")]


def test_parse_rejects_missing_separator():
    buttons, error = _parse_buttons("Просто текст без разделителя")
    assert buttons is None
    assert error[0] == "bc_invalid_button_line"


def test_parse_rejects_non_http_url():
    buttons, error = _parse_buttons("Сайт - tg://resolve?domain=x")
    assert buttons is None
    assert error[0] == "bc_invalid_button_url"


def test_parse_rejects_empty_label():
    buttons, error = _parse_buttons(" - https://example.com")
    assert buttons is None
    assert error[0] == "bc_invalid_button_line"


def test_parse_rejects_too_many_buttons():
    lines = [f"Кнопка {i} - https://example.com/{i}" for i in range(MAX_BUTTONS + 1)]
    buttons, error = _parse_buttons("\n".join(lines))
    assert buttons is None
    assert error[0] == "bc_too_many_buttons"


def test_parse_accepts_http_scheme_too():
    buttons, error = _parse_buttons("Старый сайт - http://legacy.example.com")
    assert error is None
    assert buttons == [("Старый сайт", "http://legacy.example.com")]


def test_parse_handles_dash_in_label():
    """The separator is the exact 3-char sequence " - " (space-dash-space).
    A dash inside the label without surrounding spaces (e.g. "-50%") isn't
    a match, so splitting on the first real " - " still finds the one
    separating label from URL."""
    buttons, error = _parse_buttons("Скидка -50% - https://example.com/sale")
    assert error is None
    assert buttons == [("Скидка -50%", "https://example.com/sale")]
