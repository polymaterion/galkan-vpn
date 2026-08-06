# VPN Bot MVP

Telegram-бот для продажи VPN-подписок на базе **AmneziaWG** через REST API  
[kyoresuas/amnezia-api](https://github.com/kyoresuas/amnezia-api).

## Архитектура

```
Telegram User
     │
     ▼
[Telegram Bot]  (aiogram 3, polling)
     │  HTTP + X-Billing-Key
     ▼
[Billing Service]  (FastAPI + SQLAlchemy + PostgreSQL)
     │  HTTP + x-api-key
     ▼
[Amnezia API]  (kyoresuas/amnezia-api, running on each VPN server)
     │
     ▼
[WireGuard / Xray on VPN Server]
```

**Worker** (APScheduler) работает рядом с Billing Service и каждые N минут:
- отключает истёкшие подписки
- повторяет неудавшийся provisioning

## Дерево проекта

```
vpn-bot/
├── bot/                      # Telegram-бот (aiogram 3)
│   ├── main.py               # Точка входа, polling
│   ├── config.py             # Настройки из ENV
│   ├── billing_client.py     # HTTP-клиент к Billing Service
│   ├── utils.py              # QR-генерация
│   ├── handlers/
│   │   ├── main_handlers.py  # /start, buy, config, support
│   │   └── admin_handlers.py # /admin, /extend, /disable_sub
│   ├── keyboards/
│   │   └── keyboards.py      # Все inline-клавиатуры
│   └── payments/
│       └── crypto_pay.py     # CryptoPay USDT адаптер
│
├── billing/                  # Billing Service (бизнес-логика)
│   ├── database.py           # AsyncSession factory
│   ├── services/
│   │   └── billing_service.py  # Оплата, provisioning, продление, expiry
│   ├── repositories/
│   │   ├── user_repo.py
│   │   ├── subscription_repo.py
│   │   ├── server_repo.py    # Выбор сервера с учётом нагрузки
│   │   └── other_repos.py    # Plan, Order, Payment, VpnClient, Audit
│   └── workers/
│       └── scheduler.py      # APScheduler background tasks
│
├── integrations/
│   └── amnezia/              # Тонкая обёртка над amnezia-api REST
│       ├── client.py         # AmneziaClient (HTTP)
│       ├── schemas.py        # Pydantic-схемы запросов/ответов
│       └── errors.py         # Типизированные исключения
│
├── api/                      # FastAPI Billing Service
│   ├── main.py               # FastAPI app, middleware
│   ├── dependencies.py       # Internal API key auth
│   └── routers/
│       ├── payments.py       # POST /payments/stars|usdt
│       ├── subscriptions.py  # GET /subscriptions/my|plan
│       └── admin.py          # Admin CRUD
│
├── models/
│   ├── __init__.py           # Base, TimestampMixin
│   └── models.py             # Все ORM-модели
│
├── migrations/
│   ├── env.py                # Alembic async env
│   └── versions/
│       └── 0001_initial.py   # Начальная схема
│
├── seeds/
│   └── seed.py               # Один тариф + два VPN-сервера
│
├── tests/
│   ├── conftest.py           # Shared fixtures (SQLite in-memory)
│   ├── unit/
│   │   └── test_billing_service.py  # 8 unit-тестов
│   └── integration/
│       └── test_api.py       # FastAPI endpoint-тесты
│
├── infra/
│   ├── Dockerfile.billing
│   └── Dockerfile.bot
│
├── docker-compose.yml
├── alembic.ini
├── .env.example
├── requirements.billing.txt
└── requirements.bot.txt
```

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/your-org/vpn-bot.git
cd vpn-bot
```

### 2. Подготовить `.env`

```bash
cp .env.example .env
```

Обязательно заполнить:

| Переменная | Где взять |
|---|---|
| `TELEGRAM_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS` | Ваш Telegram ID (через [@userinfobot](https://t.me/userinfobot)) |
| `BILLING_SECRET_KEY` | Любая длинная случайная строка |
| `POSTGRES_PASSWORD` | Любой сложный пароль |
| `VPN_SERVER1_URL` | `http://<ip-вашего-vpn-сервера>:4001` |
| `VPN_SERVER1_KEY` | `FASTIFY_API_KEY` из `.env` на VPN-сервере |
| `CRYPTOPAY_TOKEN` | [@CryptoBot](https://t.me/CryptoBot) → Create App (опционально) |

### 3. Запустить

```bash
docker compose up -d --build
```

Docker Compose автоматически:
1. Запустит PostgreSQL и Redis
2. Выполнит миграции Alembic
3. Загрузит seed-данные (тариф + два сервера)
4. Запустит Billing Service
5. Запустит Worker
6. Запустит Telegram Bot

### 4. Проверить работу

```bash
# Статус всех контейнеров
docker compose ps

# Логи бота
docker compose logs -f bot

# Логи billing service
docker compose logs -f billing

# Health check
curl http://localhost:8000/health
```

### 5. Открыть бота в Telegram и нажать /start

---

## Настройка VPN-серверов

Каждый VPN-сервер должен иметь запущенный [kyoresuas/amnezia-api](https://github.com/kyoresuas/amnezia-api):

```bash
# На VPN-сервере:
git clone https://github.com/kyoresuas/amnezia-api.git
cd amnezia-api
bash scripts/setup.sh
```

После установки возьмите `FASTIFY_API_KEY` из `.env` на VPN-сервере и пропишите его в `VPN_SERVER1_KEY` в вашем `.env`.

Дополнительные серверы можно добавить через `seeds/seed.py` или напрямую в БД.

---

## Админ-команды в Telegram

Доступны только пользователям из `ADMIN_IDS`.

| Команда | Описание |
|---|---|
| `/admin` | Панель управления (инлайн-меню) |
| `/extend <sub_id> [days]` | Продлить подписку на N дней (по умолч. 30) |
| `/disable_sub <sub_id>` | Отключить подписку |
| `/server_status <id> <active\|disabled>` | Включить/выключить сервер |

Через инлайн-меню `/admin` → кнопки:
- 👥 Пользователи — список с Telegram ID и никами
- 📋 Подписки — последние подписки с статусами
- 💰 Платежи — история платежей
- 🖥 Серверы — статус, нагрузка, CPU/RAM

---

## Оплата

### Telegram Stars
Встроена в Telegram. Не требует отдельного провайдера.  
Установите `PLAN_PRICE_STARS=100` (100 XTR ≈ $1.99 по курсу Telegram).

### USDT через CryptoPay
1. Откройте [@CryptoBot](https://t.me/CryptoBot) → *Create App*
2. Получите API-токен и вставьте в `CRYPTOPAY_TOKEN`
3. Установите `CRYPTOPAY_NETWORK=mainnet` (или `testnet` для тестирования)
4. Установите `PLAN_PRICE_USDT=3.00`

---

## Запуск тестов

```bash
# Установить зависимости локально
pip install -r requirements.billing.txt aiosqlite pytest-asyncio respx

# Запустить тесты
pytest tests/ -v
```

Тесты используют SQLite in-memory — PostgreSQL не нужен.

---

## Переменные окружения (полный список)

```env
# Telegram
TELEGRAM_TOKEN=          # токен бота
ADMIN_IDS=               # ID администраторов через запятую

# БД
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=vpnbot
POSTGRES_USER=vpnbot
POSTGRES_PASSWORD=

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Internal API auth между ботом и billing
BILLING_SECRET_KEY=
BILLING_BASE_URL=http://billing:8000

# Stars оплата
PLAN_PRICE_STARS=100

# USDT (CryptoPay)
CRYPTOPAY_TOKEN=
CRYPTOPAY_NETWORK=mainnet
PLAN_PRICE_USDT=3.00

# Тариф
PLAN_DURATION_DAYS=30

# VPN серверы (для seed.py)
VPN_SERVER1_URL=http://vpn1:4001
VPN_SERVER1_KEY=
VPN_SERVER2_URL=http://vpn2:4001
VPN_SERVER2_KEY=

# Прочее
ENVIRONMENT=production
LOG_LEVEL=INFO
SUPPORT_LINK=https://t.me/your_support
```

---

## Что можно улучшить

1. **Webhook вместо polling** — использовать Telegram webhook + nginx для production
2. **Уведомления** — слать пользователю сообщение за 3 дня до истечения подписки
3. **Реферальная программа** — реферальные коды и бонусные дни
4. **Мультитарифность** — несколько планов (1 месяц / 3 месяца / год)
5. **Web-админка** — React/Vue dashboard поверх существующего admin API
6. **Метрики** — Prometheus + Grafana для мониторинга платежей и нагрузки серверов
7. **Xray протокол** — сейчас используется amneziawg, можно добавить xray через тот же адаптер
8. **Auto-scaling** — автоматически добавлять новые серверы при превышении порога нагрузки
9. **Stripe/YooKassa** — дополнительные платёжные адаптеры
10. **Rate limiting** — защита API от флуда через slowapi или redis
11. **Celery вместо APScheduler** — для масштабирования воркеров на несколько инстансов
12. **E2E тесты** — тесты с реальной БД через testcontainers
```
