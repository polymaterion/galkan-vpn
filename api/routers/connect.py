"""
Public, unauthenticated router — the landing page behind the "Подключить в
Amnezia" button. Deliberately excluded from verify_internal_key: Telegram
and mobile browsers can't send the X-Billing-Key header.

Security note: the only thing this route can do is show ONE already-issued
VPN config to whoever holds the exact public_token (a 48-char random hex
value, never guessable, never reused). It cannot enumerate users, list
other devices, or touch anything else. Every other route in this service
still requires X-Billing-Key even though this router is exposed on the
same public port.
"""
from __future__ import annotations

import html
import json

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from billing.database import get_db
from billing.repositories.other_repos import VpnClientRepository
from models.models import VpnClientStatus

router = APIRouter()

AMNEZIA_DOWNLOAD_URL = "https://amnezia.org/downloads"

_CSS = """
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #0f1117; color: #e8eaed;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    padding: 24px;
  }
  .card {
    max-width: 420px; width: 100%; background: #171a23; border-radius: 20px;
    padding: 32px 24px; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }
  h1 { font-size: 22px; margin: 0 0 12px; }
  p { color: #a8adb8; line-height: 1.5; font-size: 15px; }
  .hint { font-size: 13px; margin-top: 20px; }
  .btn {
    display: block; text-decoration: none; padding: 15px 20px; border-radius: 14px;
    font-size: 16px; font-weight: 600; margin-top: 18px;
  }
  .btn.primary { background: #4f7cff; color: #fff; }
  .btn.secondary { background: #232733; color: #e8eaed; margin-top: 10px; }
"""


def _page(config_url: str | None, expired: bool = False, not_found: bool = False) -> str:
    if not_found or expired:
        title = "Ссылка недействительна" if not_found else "Устройство отключено"
        body = (
            "Эта ссылка больше не активна. Если вы ожидали рабочую конфигурацию, "
            "вернитесь в бота и запросите её заново."
        )
        return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style></head>
<body><div class="card">
<h1>⚠️ {title}</h1>
<p>{body}</p>
</div></body></html>"""

    # config_url comes from our own DB, not user input, but this route is
    # public and unauthenticated — never trust it enough to skip escaping.
    # html.escape() for the HTML attribute context (href="...");
    # json.dumps() for the JS string-literal context (it safely escapes
    # quotes/backslashes AND produces a valid quoted JS string in one step).
    safe_href = html.escape(config_url, quote=True)
    safe_js_string = json.dumps(config_url)

    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Подключение к VPN</title>
<style>{_CSS}</style></head>
<body>
<div class="card">
  <h1>🛡 Ваш VPN-ключ готов</h1>
  <p>Нажмите кнопку ниже, чтобы открыть его в приложении <b>AmneziaVPN</b> —
  всё настроится автоматически.</p>

  <a class="btn primary" id="open-btn" href="{safe_href}">🔑 Открыть в Amnezia</a>

  <p class="hint">Если приложение не открылось — оно не установлено.</p>

  <a class="btn secondary" href="{AMNEZIA_DOWNLOAD_URL}" target="_blank" rel="noopener">
    ⬇️ Скачать AmneziaVPN
  </a>
</div>
<script>
  // Best-effort automatic attempt. Many mobile browsers only allow custom
  // URL schemes to fire from a genuine user tap, so this may silently do
  // nothing — the visible button above is the reliable path either way.
  try {{ window.location.href = {safe_js_string}; }} catch (e) {{}}
</script>
</body></html>"""


@router.get("/connect/{token}", response_class=HTMLResponse)
async def connect_page(token: str, session=Depends(get_db)):
    repo = VpnClientRepository(session)
    vc = await repo.get_by_public_token(token)

    if not vc:
        return HTMLResponse(_page(None, not_found=True), status_code=404)

    if vc.status != VpnClientStatus.active or not vc.config_url:
        return HTMLResponse(_page(None, expired=True), status_code=410)

    return HTMLResponse(_page(vc.config_url))
