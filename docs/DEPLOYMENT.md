# Развёртывание ВелоРент на VPS

Продакшен-конфигурация использует Ubuntu VPS, Docker Compose, Gunicorn,
PostgreSQL и Caddy. Caddy выступает обратным прокси и автоматически получает
HTTPS-сертификат для домена.

## 1. Подготовить домен и сервер

Минимальная рекомендуемая конфигурация VPS:

- 2 vCPU;
- 2 ГБ RAM;
- 20 ГБ SSD;
- Ubuntu 24.04 LTS.

У регистратора домена создайте DNS-запись типа `A`:

```text
@ -> ПУБЛИЧНЫЙ_IP_СЕРВЕРА
```

Откройте входящие TCP-порты `22`, `80` и `443`, а также UDP-порт `443`.

## 2. Установить Docker на VPS

Подключитесь к серверу по SSH и выполните:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 git
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

После добавления пользователя в группу Docker переподключитесь по SSH.

## 3. Скачать проект

```bash
git clone https://github.com/denchikslazieeet/velorent_system.git
cd velorent_system
```

Разворачивайте проверенную ветку или предварительно объедините её с `main`.

## 4. Настроить окружение

```bash
cp .env.production.example .env.production
```

Создать безопасные значения можно командами:

```bash
openssl rand -base64 48
openssl rand -base64 32
```

В `.env.production` обязательно замените:

- `DOMAIN`, `SITE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`;
- `SECRET_KEY`;
- `DB_PASSWORD` и `POSTGRES_PASSWORD` на одинаковый сложный пароль;
- реквизиты арендодателя;
- настройки SMTP, VK и 1С, если эти интеграции используются.

Файл `.env.production` содержит секреты и не должен добавляться в Git.

## 5. Запустить сайт

```bash
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
docker compose --env-file .env.production -f docker-compose.production.yml ps
```

Caddy автоматически запросит HTTPS-сертификат после того, как DNS-запись
домена начнёт указывать на сервер.

Просмотреть журналы:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml logs -f --tail=200
```

## 6. Создать администратора и демонстрационные данные

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec web python manage.py createsuperuser
```

Заполнять демонстрационными данными следует только пустую базу:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec web python manage.py seed_demo --allow-production
```

## 7. Обновлять проект

```bash
git pull
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
docker image prune -f
```

Контейнер `web` при запуске автоматически применяет миграции и собирает
статические файлы.

## 8. Резервное копирование

Создать дамп PostgreSQL:

```bash
mkdir -p backups
docker compose --env-file .env.production -f docker-compose.production.yml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "backups/velorent-$(date +%F-%H%M).sql"
```

Также сохраняйте каталог `media`, поскольку в нём находятся загруженные
пользователями файлы. Восстановление дампа сначала следует проверять на
отдельной тестовой базе.

## 9. Диагностика

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec web python manage.py check --deploy
docker compose --env-file .env.production -f docker-compose.production.yml ps
curl -I "https://ВАШ_ДОМЕН"
```
