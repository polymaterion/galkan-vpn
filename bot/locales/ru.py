"""
Russian strings. This is the fallback language — if a key is missing from
another locale, or the value fails to format, this is what gets shown.
"""

STRINGS: dict[str, str] = {
    # --- Language picker (shown once, on first /start) ---
    "language_prompt": "🌐 Выберите язык / Diliňizi saýlaň:",
    "btn_lang_ru": "🇷🇺 Русский",
    "btn_lang_tk": "🇹🇲 Türkmençe",
    "language_saved": "Язык сохранён: Русский ✅",

    # --- Welcome / main menu ---
    "welcome": (
        "👋 Добро пожаловать в <b>VPN Bot</b>!\n\n"
        "🛡 Безопасный VPN на основе AmneziaWG — обходит блокировки без следов.\n\n"
        "Выберите действие:"
    ),
    "btn_my_devices": "📱 Мои устройства",
    "btn_buy_new": "➕ Подключить новое устройство — {price}⭐",
    "btn_support": "💬 Поддержка",
    "btn_language": "🌐 Язык",
    "btn_back": "◀️ Назад",
    "btn_back_to_menu": "◀️ В главное меню",

    # --- Devices list ---
    "devices_title": "📱 <b>Ваши устройства</b>\n\nКаждое устройство — отдельный оплаченный ключ.",
    "devices_empty": (
        "У вас пока нет подключённых устройств.\n\n"
        "Каждое устройство — это отдельный VPN-ключ за {price}⭐, "
        "который можно использовать на одном телефоне/компьютере."
    ),
    "device_line": (
        "{emoji} <b>Устройство #{n}</b>\n"
        "Статус: {status}\n"
        "Действует до: {expires}\n"
    ),
    "btn_device_connect": "🔑 Подключить #{n}",
    "btn_device_qr": "📱 QR #{n}",
    "btn_device_renew": "🔄 Продлить #{n} — {price}⭐",
    "status_active": "✅ Активно",
    "status_expired": "❌ Истекло",
    "status_pending_provisioning": "⏳ Создаётся",
    "status_error": "⚠️ Ошибка",
    "status_disabled": "🔒 Отключено",
    "status_pending_payment": "💳 Ожидает оплаты",
    "unknown_expiry": "неизвестно",

    # --- Buy flow ---
    "plan_card": (
        "💎 <b>{name}</b>\n\n"
        "{description}\n\n"
        "⏱ Срок: <b>{duration_days} дней</b>\n"
        "⭐ Стоимость: <b>{price_stars} Telegram Stars</b>\n"
        "💵 или <b>${price_usdt} USDT</b>\n\n"
        "Это отдельное устройство: одна оплата = один VPN-ключ для одного "
        "устройства. Ключ для ещё одного устройства оформляется отдельной "
        "оплатой по той же цене.\n\n"
        "Выберите способ оплаты:"
    ),
    "renew_card": (
        "🔄 <b>Продление устройства #{n}</b>\n\n"
        "⏱ Ещё {duration_days} дней\n"
        "⭐ Стоимость: <b>{price_stars} Telegram Stars</b>\n"
        "💵 или <b>${price_usdt} USDT</b>\n\n"
        "Ключ остаётся тем же — просто продлевается срок действия.\n\n"
        "Выберите способ оплаты:"
    ),
    "btn_pay_stars": "⭐ Оплатить Telegram Stars",
    "btn_pay_usdt": "💎 Оплатить USDT (Crypto)",
    "plan_unavailable": "Тарифы временно недоступны.",
    "plan_load_error": "Ошибка загрузки тарифа.",

    # --- Payment processing ---
    "payment_processing": "⏳ Оплата получена! {action}",
    "payment_processing_new": "Создаём ваш новый VPN-ключ...",
    "payment_processing_renew": "Продлеваем устройство...",
    "payment_error": (
        "❗ Оплата прошла, но возникла ошибка при создании VPN-доступа.\n"
        "Обратитесь в поддержку — мы всё исправим!"
    ),
    "provisioning_pending": (
        "⏳ VPN-доступ создаётся, это займёт несколько минут.\n"
        "Вы получите уведомление, как только он будет готов — загляните в "
        "«Мои устройства»."
    ),

    # --- Config ready (post-payment / resend) ---
    "config_ready": (
        "✅ <b>Устройство готово!</b>\n"
        "⏳ Действует до: <b>{expires}</b>\n\n"
        "Нажмите кнопку, чтобы подключить — конфигурация настроится "
        "автоматически в приложении Amnezia."
    ),
    "btn_connect_amnezia": "🔑 Подключить в Amnezia",
    "btn_show_qr": "📱 Показать QR-код",
    "qr_caption": "📷 Отсканируйте этот QR-код в приложении AmneziaVPN",
    "qr_unavailable": "Конфигурация недоступна. Попробуйте позже.",
    "config_link_fallback": (
        "🔗 Ссылка для ручного добавления в Amnezia:\n<code>{config_url}</code>"
    ),

    # --- USDT flow ---
    "usdt_unavailable": "USDT оплата временно недоступна. Попробуйте Telegram Stars.",
    "usdt_invoice_error": "Ошибка создания инвойса. Попробуйте позже.",
    "usdt_invoice_card": (
        "💎 <b>Оплата USDT</b>\n\n"
        "Сумма: <b>${amount} USDT</b>\n\n"
        "👉 <a href='{pay_url}'>Перейти к оплате</a>\n\n"
        "После оплаты нажмите кнопку ✅"
    ),
    "btn_i_paid": "✅ Я оплатил",
    "btn_cancel": "❌ Отмена",
    "usdt_check_error": "Ошибка проверки оплаты. Попробуйте позже.",
    "usdt_not_paid_yet": "Оплата ещё не поступила. Попробуйте через минуту.",
    "usdt_confirmed": "⏳ Оплата подтверждена! {action}",
    "usdt_activation_error": "❗ Ошибка при активации. Обратитесь в поддержку.",

    # --- Support ---
    "support_text": "💬 <b>Поддержка</b>\n\nПо любым вопросам: {support_link}",

    # --- Misc errors ---
    "no_active_device": "Устройство не найдено.",

    # --- Admin panel (respects the admin's own selected language, same as
    # the rest of the bot — see admin_handlers.py) ---
    "adm_access_denied": "⛔ Доступ запрещён.",
    "adm_no_access": "⛔ Нет доступа.",
    "adm_panel_title": "🔧 <b>Панель администратора</b>",
    "adm_btn_users": "👥 Пользователи",
    "adm_btn_subs": "📋 Подписки",
    "adm_btn_payments": "💰 Платежи",
    "adm_btn_servers": "🖥 Серверы",
    "adm_btn_back": "◀️ В панель администратора",
    "adm_users_title": "👥 <b>Пользователи</b> (всего: {total})\n",
    "adm_subs_title": "📋 <b>Подписки</b>\n",
    "adm_payments_title": "💰 <b>Платежи</b>\n",
    "adm_servers_title": "🖥 <b>Серверы VPN</b>\n",
    "adm_no_servers": "Нет серверов",
    "adm_error": "Ошибка: {error}",
    "adm_extend_usage": "Usage: /extend <sub_id> [days=30]",
    "adm_extend_success": "✅ Подписка #{sub_id} продлена на {days} дней.",
    "adm_disable_usage": "Usage: /disable_sub <sub_id>",
    "adm_disable_success": "✅ Подписка #{sub_id} отключена.",
    "adm_server_status_usage": "Usage: /server_status <server_id> <active|disabled>",
    "adm_server_status_success": "✅ Сервер #{server_id} → {status}",
    "adm_add_server_usage": (
        "Usage: /add_server <name> <base_url> <api_key> [region] [weight] [max_clients] [protocol]\n"
        "Example: /add_server Server-DE http://1.2.3.4 <FASTIFY_API_KEY> DE 100 200 amneziawg2"
    ),
    "adm_add_server_success": "✅ Сервер #{id} «{name}» добавлен и активен (протокол: {protocol}).",
    "adm_generic_error": "❌ Ошибка: {error}",
}
