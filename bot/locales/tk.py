"""
Turkmen (Türkmençe) strings.

NOTE: this translation was produced by Claude without a native-speaker
review. Standard modern Turkmen (Latin script) vocabulary was used
throughout, but for a real customer-facing product we'd recommend having a
native Turkmen speaker proofread this file before relying on it at scale —
especially the payment/legal-sensitive strings. Any key missing here (or
that fails to .format()) automatically falls back to the Russian string, so
a typo here never breaks the bot, just shows Russian for that one line.
"""

STRINGS: dict[str, str] = {
    "language_prompt": "🌐 Diliňizi saýlaň / Выберите язык:",
    "btn_lang_ru": "🇷🇺 Русский",
    "btn_lang_tk": "🇹🇲 Türkmençe",
    "language_saved": "Dil saklandy: Türkmençe ✅",

    "welcome": (
        "👋 <b>Galkan VPN</b>-a hoş geldiňiz!\n\n"
        "🛡 AmneziaWG esasynda howpsuz VPN — päsgelçilikleri yzsyz aşýar.\n\n"
        "Hereketi saýlaň:"
    ),
    "btn_my_devices": "📱 Meniň enjamlarym",
    "btn_buy_new": "➕ Enjam goşmak",
    "btn_support": "💬 Goldaw",
    "btn_instructions": "📖 Görkezme",
    "btn_language": "🌐 Dil",
    "btn_back": "◀️ Yza",
    "btn_back_to_menu": "◀️ Baş menýu",

    "devices_title": "📱 <b>Siziň enjamlaryňyz</b>\n\nHer enjam — aýratyn tölenen açar.",
    "devices_empty": (
        "Siziň entek birikdirilen enjamyňyz ýok.\n\n"
        "Her enjam — {price}⭐ üçin aýratyn VPN açary, bir telefonda/kompýuterde "
        "ulanyp bolýar."
    ),
    "device_line": (
        "{emoji} <b>Enjam #{n}</b>\n"
        "Ýagdaýy: {status}\n"
        "Şu senä çenli hereket edýär: {expires}\n"
    ),
    "btn_device_connect": "🔑 #{n} birikdirmek",
    "btn_device_open": "📄 #{n} enjamy açmak",
    "btn_device_qr": "📱 #{n} QR",
    "btn_device_renew": "🔄 #{n} uzaltmak — {price}⭐",
    "status_active": "✅ Işjeň",
    "status_expired": "❌ Möhleti geçen",
    "status_pending_provisioning": "⏳ Döredilýär",
    "status_error": "⚠️ Ýalňyşlyk",
    "status_disabled": "🔒 Öçürilen",
    "status_pending_payment": "💳 Töleg garaşylýar",
    "unknown_expiry": "näbelli",
    "device_card": (
        "📄 <b>Enjam #{n}</b>\n\n"
        "Ýagdaýy: {status}\n"
        "Şu senä çenli hereket edýär: {expires}\n\n"
        "Hereketi saýlaň:"
    ),

    "plan_name_text": "VPN — {duration_days} gün",
    "plan_description_text": "AmneziaWG protokoly esasynda {duration_days} günlük çäksiz VPN.",
    "plan_card": (
        "💎 <b>{name}</b>\n\n"
        "{description}\n\n"
        "⏱ Möhlet: <b>{duration_days} gün</b>\n"
        "⭐ Bahasy: <b>{price_stars} Telegram Stars</b>\n"
        "💵 ýa-da <b>${price_usdt} USDT</b>\n\n"
        "Bu aýratyn enjam: bir töleg = bir enjam üçin bir VPN açary. Başga bir "
        "enjam üçin açar şol bir bahadan aýratyn töleg bilen resmileşdirilýär.\n\n"
        "Töleg usulyny saýlaň:"
    ),
    "renew_card": (
        "🔄 <b>#{n} enjamyny uzaltmak</b>\n\n"
        "⏱ Ýene {duration_days} gün\n"
        "⭐ Bahasy: <b>{price_stars} Telegram Stars</b>\n"
        "💵 ýa-da <b>${price_usdt} USDT</b>\n\n"
        "Açar şol bir bolup galýar — diňe hereket möhleti uzaldylýar.\n\n"
        "Töleg usulyny saýlaň:"
    ),
    "btn_pay_stars": "⭐ Telegram Stars bilen tölemek",
    "btn_pay_usdt": "💎 USDT (Kripto) bilen tölemek",
    "btn_invoice_pay": "Tölemek ⭐{price}",
    "plan_unavailable": "Tarifler wagtlaýyn elýeterli däl.",
    "plan_load_error": "Tarifi ýüklemekde ýalňyşlyk.",

    "payment_processing": "⏳ Töleg kabul edildi! {action}",
    "payment_processing_new": "Täze VPN açaryňyz döredilýär...",
    "payment_processing_renew": "Enjam uzaldylýar...",
    "payment_error": (
        "❗ Töleg geçdi, ýöne VPN elýeterliligini döretmekde ýalňyşlyk ýüze çykdy.\n"
        "Goldawa ýüz tutuň — hemme zady düzederis!"
    ),
    "provisioning_pending": (
        "⏳ VPN elýeterliligi döredilýär, bu birnäçe minut wagt alar.\n"
        "Taýyn bolanda habar alarsyňyz — «Meniň enjamlarym» bölümine serediň."
    ),

    "config_ready": (
        "✅ <b>Enjam taýyn!</b>\n"
        "⏳ Şu senä çenli hereket edýär: <b>{expires}</b>\n\n"
        "Açar aşakdaky düwme arkaly islendik wagt elýeterli."
    ),
    "btn_connect_amnezia": "🔑 Açary görkezmek",
    "btn_show_qr": "📱 QR-kody görkezmek",
    "qr_caption": "📷 Bu QR-kody AmneziaVPN programmasynda skanirläň",
    "qr_unavailable": "Konfigurasiýa elýeterli däl. Soňra synanyşyň.",
    "config_key_message": (
        "🔑 Birikdirmek üçin açaryňyz:\n"
        "<pre>{config_url}</pre>\n\n"
        "Ýokardaky blokda «Copy Code» basyň, soňra AmneziaVPN programmasynda "
        "«Konfigurasiýa goşmak» → «Buferden» arkaly ýerleşdiriň."
    ),

    "usdt_unavailable": "USDT tölegi wagtlaýyn elýeterli däl. Telegram Stars-y synanyşyň.",
    "usdt_invoice_error": "Hasap-faktura döretmekde ýalňyşlyk. Soňra synanyşyň.",
    "usdt_invoice_card": (
        "💎 <b>USDT tölegi</b>\n\n"
        "Möçberi: <b>${amount} USDT</b>\n\n"
        "👉 <a href='{pay_url}'>Tölege geçmek</a>\n\n"
        "Töleg edenizden soň ✅ düwmesine basyň"
    ),
    "btn_i_paid": "✅ Men töledim",
    "btn_cancel": "❌ Ýatyr",
    "usdt_check_error": "Tölegi barlamakda ýalňyşlyk. Soňra synanyşyň.",
    "usdt_not_paid_yet": "Töleg entek gelip gowuşmady. Bir minutdan soň synanyşyň.",
    "usdt_confirmed": "⏳ Töleg tassyklandy! {action}",
    "usdt_activation_error": "❗ Işjeňleşdirmekde ýalňyşlyk. Goldawa ýüz tutuň.",

    "support_text": "💬 <b>Goldaw</b>\n\nIslendik sorag boýunça: {support_link}",

    "instructions_text": (
        "📖 <b>Birikdirmek boýunça görkezme</b>\n\n"
        "1️⃣ Enjamyňyz üçin AmneziaVPN programmasyny ýükläň.\n"
        "2️⃣ Programmany açyň, ➕ (ýa-da «Başlamak») basyň.\n"
        "3️⃣ Açar meýdançasynyň ýanyndaky «Goýmak» düwmesine basyň, «Meniň "
        "enjamlarym» → «Açary görkezmek» bölüminden alan açaryňyzy goýuň.\n"
        "4️⃣ «Dowam etmek» → «Birikdirmek» basyň.\n\n"
        "Aşakda — programmany ýüklemek üçin resmi sahypa we Amnezia "
        "işläp taýýarlaýjylaryndan jikme-jik görkezme."
    ),
    "btn_amnezia_download": "⬇️ AmneziaVPN ýüklemek",
    "btn_amnezia_guide": "📄 Amnezia sahypasyndaky görkezme",

    "no_active_device": "Işjeň enjam tapylmady.",

    # --- Admin panel ---
    "adm_access_denied": "⛔ Girmek gadagan.",
    "adm_no_access": "⛔ Elýeterlilik ýok.",
    "adm_panel_title": "🔧 <b>Administrator paneli</b>",
    "adm_btn_users": "👥 Ulanyjylar",
    "adm_btn_subs": "📋 Abunalar",
    "adm_btn_payments": "💰 Tölegler",
    "adm_btn_servers": "🖥 Serwerler",
    "adm_btn_back": "◀️ Administrator paneline",
    "adm_users_title": "👥 <b>Ulanyjylar</b> (jemi: {total})\n",
    "adm_subs_title": "📋 <b>Abunalar</b>\n",
    "adm_payments_title": "💰 <b>Tölegler</b>\n",
    "adm_servers_title": "🖥 <b>VPN serwerleri</b>\n",
    "adm_no_servers": "Serwer ýok",
    "adm_error": "Ýalňyşlyk: {error}",
    "adm_extend_usage": "Usage: /extend <sub_id> [days=30]",
    "adm_extend_success": "✅ #{sub_id} abunasy {days} güne uzaldyldy.",
    "adm_disable_usage": "Usage: /disable_sub <sub_id>",
    "adm_disable_success": "✅ #{sub_id} abunasy öçürildi.",
    "adm_reissue_usage": "Usage: /reissue_device <sub_id>",
    "adm_reissue_success": (
        "✅ #{sub_id} abunasynyň enjamy täzeden döredildi. Köne açar indi "
        "işlemeýär — täzesi ulanyjy üçin «Açary görkezmek» arkaly elýeterli."
    ),
    "adm_server_status_usage": "Usage: /server_status <server_id> <active|disabled>",
    "adm_server_status_success": "✅ #{server_id} serwer → {status}",
    "adm_add_server_usage": (
        "Usage: /add_server <name> <base_url> <api_key> [region] [weight] [max_clients] [protocol]\n"
        "Example: /add_server Server-DE http://1.2.3.4 <FASTIFY_API_KEY> DE 100 200 amneziawg2"
    ),
    "adm_add_server_success": "✅ #{id} «{name}» serweri goşuldy we işjeň (protokol: {protocol}).",
    "adm_generic_error": "❌ Ýalňyşlyk: {error}",
}
