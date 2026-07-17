# Coolify Telegram Bot 🤖

Telegram-бот для оперативного мониторинга и безопасного управления приложениями на **Coolify** — без доступа к веб-панели, с телефона за 30 секунд.

## Возможности

| Функция | Описание |
|---------|----------|
| 📱 **Список приложений** | Статусы (🟢/🔴/🟡/⚠️), inline-пагинация, карточка с деталями |
| 🖥 **Серверы** | Health-check, статус доступности |
| 📋 **Логи** | Tail N строк, полные логи файлом |
| 🔄 **Restart / Stop / Start** | С подтверждением, TTL 45 сек, аудит |
| 📦 **Redeploy** | Триггер деплоя с отслеживанием статуса |
| 🔔 **Подписки** | Push-уведомления при сбоях приложения |
| 📊 **Аудит** | Все действия логируются (Admin) |
| ⏱ **Rate-limit** | Защита от спама и случайного нажатия |

## Быстрый старт

### 1. Конфигурация

```bash
cp .env.example .env
```

Заполните переменные:

| Переменная | Описание |
|-----------|----------|
| `BOT_TOKEN` | Токен Telegram бота (от @BotFather) |
| `COOLIFY_API_URL` | URL вашего Coolify API (по умолч. `https://app.coolify.io/api/v1`) |
| `COOLIFY_API_TOKEN` | Bearer-токен Coolify (scope: write) |
| `ADMIN_IDS` | Telegram User ID администраторов через запятую |

### 2. Запуск через Docker

```bash
docker compose up -d --build
```

### 3. Добавление пользователей

Пользователи добавляются вручную через SQLite (`bot.db` / таблица `users`).

По умолчанию работает только whitelist — неизвестные пользователи игнорируются.

## Ролевая модель

| Роль | Права |
|------|-------|
| **viewer** | Просмотр статусов, логов, серверов |
| **operator** | Viewer + restart/stop/start/redeploy (с подтверждением) |
| **admin** | Operator + /audit, управление пользователями |

## API Endpoints (Coolify)

Бот использует следующие эндпоинты Coolify API v4:

- `GET /health` — Health-check
- `GET /version` — Версия панели
- `GET /applications` — Список приложений
- `GET /applications/{uuid}` — Карточка приложения
- `GET /applications/{uuid}/logs?lines=N` — Логи
- `GET /applications/{uuid}/start` — Запуск
- `GET /applications/{uuid}/stop` — Остановка
- `GET /applications/{uuid}/restart` — Перезапуск
- `GET /deploy?tag=` — Триггер деплоя
- `GET /deployments` — Список деплоев
- `GET /deployments/{uuid}` — Статус деплоя
- `GET /servers` — Список серверов
- `GET /teams/current` — Текущая команда

## Архитектура

```
coolify-telegram-bot/
├── bot/
│   ├── main.py              # Точка входа
│   ├── config.py            # Конфигурация (pydantic-settings)
│   ├── router.py            # Регистрация роутеров
│   ├── handlers/            # Обработчики команд
│   ├── middleware/          # Auth + Rate-limit
│   ├── services/            # Coolify API client + Pydantic модели
│   ├── db/                  # SQLAlchemy модели + репозиторий
│   └── utils/               # Форматирование, пагинация, security
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Безопасность

- **Whitelist** — неизвестные пользователи игнорируются
- **Подтверждение действий** — одноразовые HMAC-токены с TTL 45 сек
- **Cooldown** — повторный restart не чаще 1 раза в 2 минуты
- **Rate-limit** — 10 запросов/мин на пользователя
- **Аудит** — все не-readonly действия логируются
- **API-токен** — хранится только в `.env`, не в git, не в образе

## Разработка

```bash
# Установка зависимостей
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Запуск
python -m bot.main
```

## Лицензия

MIT
