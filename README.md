# galkan-vpn

Telegram-бот продажи VPN-доступа. Оплата через Telegram Stars или USDT (CryptoPay). Провижининг VPN-клиентов — через отдельный сторонний сервис [`amnezia-api`](https://github.com/kyoresuas/amnezia-api), который этот проект не модифицирует, а только вызывает по сети.

Бот двуязычный (русский/туркменский), ориентирован на туркменоязычную аудиторию.

Текущий статус проекта, история изменений и открытые вопросы — в [`PROJECT_STATUS.md`](./PROJECT_STATUS.md). Этот README — про то, как развернуть и пользоваться; за «что происходило и что осталось» — туда.

---

## Архитектура

```
┌──────────┐        ┌──────────┐        ┌─────────────┐        ┌────────────┐
│   bot    │──httpx─▶│ billing  │──httpx─▶│ amnezia-api │──exec─▶│  WireGuard │
│ (aiogram)│         │ (FastAPI)│         │ (сторонний) │        │  / xray    │
└──────────┘         └────┬─────┘        └─────────────┘        └────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          PostgreSQL     Redis       worker
                                  (APScheduler,
                                   фоновые задачи)
```

- **`bot`** — aiogram 3, всё общение с пользователем. Сам никогда не трогает БД напрямую — только ходит в `billing` по HTTP (`bot/billing_client.py`).
- **`billing`** — FastAPI-сервис, вся бизнес-логика (платежи, подписки, провижининг). Единственный, кто пишет в PostgreSQL.
- **`worker`** — тот же образ, что `billing`, но команда `python -m billing.workers.scheduler`: раз в 5 минут отключает истёкшие подписки, раз в 3 минуты повторяет застрявший провижининг.
- **`amnezia-api`** — **не часть этого репозитория**. Отдельный проект, разворачивается отдельно на каждом VPN-сервере, управляет WireGuard/xray-конфигами через `docker exec`. `billing`/`worker` обращаются к нему по сети как к чёрному ящику.
- **Redis** используется для распределённой блокировки (`billing/redis_lock.py`) — сериализует конкурентные запросы на изменение клиентов к одному и тому же VPN-серверу, так как `amnezia-api` сам не защищён от гонок при записи конфига.

## Структура репозитория

```
api/                      # FastAPI-приложение (billing)
├── main.py                 # точка входа, /health, /ready
├── dependencies.py          # проверка X-Billing-Key
└── routers/
    ├── payments.py          # POST /stars, /usdt — обработка оплат
    ├── subscriptions.py      # GET /my, /devices — подписки пользователя
    ├── users.py              # GET /me, POST /language
    ├── admin.py              # управление пользователями/подписками/серверами/платежами
    └── connect.py            # GET /connect/{token} — публичная страница "Открыть в Amnezia"

billing/
├── database.py              # engine, AsyncSessionLocal, get_db()
├── redis_lock.py             # распределённая блокировка per-VPN-server
├── services/billing_service.py  # вся бизнес-логика: платежи, провижининг, admin-действия
├── repositories/             # доступ к БД по сущностям (users, subscriptions, servers, ...)
└── workers/scheduler.py      # APScheduler-джобы (истечение подписок, ретрай провижининга)

bot/
├── main.py                  # точка входа, регистрация роутеров
├── config.py                  # настройки из .env (pydantic-settings)
├── navigation.py               # стек экранов поверх aiogram FSM
├── billing_client.py            # HTTP-клиент к billing
├── handlers/
│   ├── main_handlers.py          # весь пользовательский флоу
│   └── admin_handlers.py          # /admin, /extend, /reissue_device и т.д.
├── keyboards/keyboards.py         # inline-клавиатуры
├── locales/{ru,tk}.py               # весь пользовательский текст, по 86 ключей в каждом
├── middlewares/language.py         # подставляет lang= в каждый хендлер
└── payments/crypto_pay.py          # обёртка над CryptoPay API

integrations/amnezia/         # типизированный клиент к amnezia-api (httpx + pydantic)
models/models.py               # SQLAlchemy-модели, единый источник схемы
migrations/versions/            # Alembic-миграции
seeds/seed.py                    # первичное наполнение: план + VPN-серверы из env
tests/                           # pytest (unit — billing_service; integration — API)
infra/Dockerfile.{billing,bot}    # образы
docker-compose.yml
```

## Предварительные требования

- Docker + Docker Compose.
- **Уже развёрнутый и работающий `amnezia-api`** хотя бы на одном сервере — этот проект без него бесполезен, он только вызывает его API. См. [репозиторий amnezia-api](https://github.com/kyoresuas/amnezia-api) для установки. Держите под рукой: URL, на котором он слушает, и `FASTIFY_API_KEY`, который печатает его `setup.sh`.
- Telegram-бот, зарегистрированный через [@BotFather](https://t.me/BotFather), и его токен.
- Свой Telegram user id (например, через [@userinfobot](https://t.me/userinfobot)) — понадобится для `ADMIN_IDS`.
- Опционально: аккаунт [@CryptoBot](https://t.me/CryptoBot) и токен приложения, если нужна оплата в USDT (без него доступна только оплата Stars).

## Быстрый старт

```bash
git clone <this-repo>
cd galkan-vpn
cp .env.example .env
```

Откройте `.env` и заполните как минимум:

| Переменная | Что это |
|---|---|
| `TELEGRAM_TOKEN` | токен от @BotFather |
| `ADMIN_IDS` | ваш Telegram user id (через запятую, если админов несколько) |
| `POSTGRES_PASSWORD` | замените дефолт на реальный пароль |
| `BILLING_SECRET_KEY` | любая длинная случайная строка — **обязательна**, сервис не запустится без неё |
| `PUBLIC_BASE_URL` / `PUBLIC_PORT` | см. секцию ниже — без них не заработает кнопка «Открыть в Amnezia» |
| `VPN_SERVER1_URL` / `VPN_SERVER1_KEY` | адрес и ключ вашего `amnezia-api` |

Полный список переменных с комментариями — в самом `.env.example`, он актуальнее любого README и обновляется вместе с кодом.

> **Заметка:** `PLAN_DURATION_DAYS` в `.env.example` сейчас ни на что не влияет — реальная длительность тарифа захардкожена как 30 дней в `seeds/seed.py`. Если нужен другой срок, меняйте `duration_days=30` там до первого запуска seed. После — ни бот, ни `PATCH /api/v1/admin/plans/{id}` (он меняет только цену) это не редактируют, нужен прямой `UPDATE plans SET duration_days = ...` в БД.

```bash
docker compose up -d --build
```

Это по цепочке: поднимет `db`+`redis` → прогонит `migrate` (Alembic) → прогонит `seed` (создаст тариф и настроенные VPN-серверы) → запустит `billing`+`worker`+`bot`.

Проверить, что billing поднялся:

```bash
curl http://localhost:${PUBLIC_PORT:-8080}/health   # {"status": "ok"} — процесс жив
curl http://localhost:${PUBLIC_PORT:-8080}/ready     # проверяет реальное подключение к БД
```

Дальше — идите в Telegram и напишите своему боту `/start`.

### Важно про сеть

`docker-compose.yml` объявляет `amnezia_api_net` как **внешнюю** сеть (`external: true`, имя `amnezia-api_default`) — это сеть, которую создаёт свой собственный compose-стек `amnezia-api`. Если `amnezia-api` ещё не запущен на этой машине, `docker compose up` здесь упадёт с ошибкой "network not found". Разверните `amnezia-api` первым.

Если `amnezia-api` работает на **другой** машине (не на том же хосте, что `billing`/`worker`) — присоединение к его docker-сети по имени не сработает, вместо этого укажите его реальный публичный адрес и порт в `VPN_SERVER{N}_URL` и уберите `amnezia_api_net` из `docker-compose.yml`.

### Про `PUBLIC_BASE_URL`

`billing` отдаёт по адресу `/connect/{token}` **публичную, неаутентифицированную** HTML-страницу с кнопкой «Открыть в Amnezia» — именно на неё ведёт кнопка показа ключа в боте. Чтобы кнопка вообще появилась, эта страница должна быть доступна из интернета:

```
PUBLIC_BASE_URL=http://<ip-вашего-сервера>:8080
PUBLIC_PORT=8080
```

и порт должен быть открыт в файрволе (`ufw allow 8080/tcp`). Для продакшена лучше поставить перед `billing` reverse-proxy с TLS (nginx/Caddy) и указать `https://ваш-домен` в `PUBLIC_BASE_URL` — VPN-ключ в открытом виде не должен ходить по HTTP.

Без `PUBLIC_BASE_URL` бот всё равно работает, просто без этой кнопки — конфиг тогда показывается только текстом/QR-кодом прямо в чате.

## Добавление VPN-серверов

Два способа, оба работают в любой момент (не только при первом запуске):

**Через .env + seed** — только если это первый запуск (`seed.py` не пересеивает, если в БД уже есть хотя бы один сервер):
```
VPN_SERVER1_URL=http://amnezia-api:4001
VPN_SERVER1_KEY=<ваш FASTIFY_API_KEY>
VPN_SERVER1_NAME=Server-EU        # опционально
VPN_SERVER1_REGION=EU             # опционально, дефолт EU
VPN_SERVER1_WEIGHT=100            # опционально, влияет на балансировку
VPN_SERVER1_MAX_CLIENTS=200       # опционально, дефолт 200
VPN_SERVER1_PROTOCOL=amneziawg2   # опционально, дефолт amneziawg2
```
Слоты `VPN_SERVER2_*`, `VPN_SERVER3_*` и так далее (до 10) работают так же — заполняйте по одному на сервер.

**Через команду бота, в любой момент** (проще для второго и последующих серверов, не требует пересборки):
```
/add_server <name> <base_url> <api_key> [region] [weight] [max_clients] [protocol]
```
Пример:
```
/add_server Server-DE http://45.10.20.30 8f2a1c... DE 100 200 amneziawg2
```
`protocol` обязан совпадать с тем, что реально включено на этом сервере (`PROTOCOLS_ENABLED` в `.env` того `amnezia-api`) — допустимые значения: `amneziawg`, `amneziawg2`, `xray`. Несовпадение = все попытки создать клиента на этом сервере будут падать с 400.

## Команды бота

**Пользовательские:**
- `/start` — открывает главное меню (или выбор языка, если это первый запуск для этого пользователя).

Остальное — через inline-кнопки: покупка/продление, просмотр устройств, показ ключа/QR-кода, поддержка, инструкция по подключению.

**Админские** (только для `ADMIN_IDS`):

| Команда | Назначение |
|---|---|
| `/admin` | inline-панель: списки пользователей/подписок/платежей/серверов |
| `/extend <sub_id> [days]` | продлить подписку (по умолчанию на 30 дней) |
| `/disable_sub <sub_id>` | отключить подписку и её VPN-клиента |
| `/reissue_device <sub_id>` | переиздать VPN-клиента — когда у клиента валидный на вид ключ, но подключение не работает, **или** когда провижининг вообще не завершился (ключа нет вовсе). Безопасно вызывать в обоих случаях. |
| `/server_status <server_id> <active\|disabled>` | включить/отключить сервер (отключённый не участвует в балансировке новых клиентов). Модель поддерживает и третье значение, `maintenance` — команда бота его не документирует в своей usage-строке, но реально принимает: `VpnServerStatus("maintenance")` пройдёт валидацию так же, как `active`/`disabled`. |
| `/add_server ...` | см. секцию выше |

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

`requirements-dev.txt` содержит `requirements.billing.txt` плюс тестовые зависимости — прод-образ (`infra/Dockerfile.billing`) ставит только `requirements.billing.txt`, тестовые пакеты в него не попадают.

Известно падающий тест и почему — см. «Известные проблемы» в `PROJECT_STATUS.md`; он не блокирует остальные.

## Разработка

Локальный запуск отдельного сервиса без Docker (например, для отладки `billing`):

```bash
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+asyncpg://vpnbot:pass@localhost:5432/vpnbot
export REDIS_URL=redis://localhost:6379/0
export BILLING_SECRET_KEY=любая-строка
uvicorn api.main:app --reload
```

`docker-compose.yml` не публикует порты Postgres/Redis на хост (по умолчанию доступны только внутри docker-сети) — для этого сценария временно добавьте `ports: ["5432:5432"]` к сервису `db` (и/или `["6379:6379"]` к `redis`) в свою локальную копию compose-файла.

Миграции:
```bash
alembic upgrade head              # применить все
alembic revision --autogenerate -m "описание"   # создать новую после правки models/models.py
```

## Лицензия

См. [`LICENSE`](./LICENSE).
