# Развёртывание на REG.RU Host-0

Эта инструкция предназначена для виртуального хостинга REG.RU с ISPmanager,
Python/Passenger и MySQL. Основной домен: `velo-rent-chita.ru`.

Docker и PostgreSQL на тарифе Host-0 не используются. Локальная PostgreSQL-база
остаётся резервной копией после переноса.

## 1. Включить Python для сайта

В ISPmanager откройте `Сайты`, выберите `velo-rent-chita.ru` и нажмите
`Изменить`. Включите CGI-скрипты и Python, затем выберите Python 3.10.
Django 5.1 требует Python 3.10 или новее.

Корневая директория сайта должна остаться:

```text
/www/velo-rent-chita.ru
```

## 2. Создать MySQL-базу

Откройте `Базы данных` и создайте базу с кодировкой `utf8mb4`.
Сохраните выданные панелью:

- имя базы;
- пользователя базы;
- пароль;
- сервер базы, обычно `localhost`;
- порт, обычно `3306`.

Не отправляйте пароль базы в публичные сообщения и не добавляйте его в Git.

## 3. Экспортировать текущие данные PostgreSQL

На локальном компьютере из каталога проекта:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py export_portable_data
```

Команда создаст в `backups/hosting_transfer`:

- `velorent-data-*.json` с пользователями, велосипедами, бронями, платежами и
  остальными рабочими данными;
- `velorent-inventory-*.json` с контрольным количеством записей;
- SHA-256 хэш fixture для проверки целостности.

Каталог `media` переносится отдельно целиком.
Активные браузерные сессии не переносятся: пользователям потребуется войти
снова, но их аккаунты и пароли сохранятся.

## 4. Загрузить проект на хостинг

Откройте `Shell-клиент` в ISPmanager:

```bash
cd /var/www/u3539071/data/www
git clone -b codex/rental-contract-and-layout-polish \
  https://github.com/denchikslazieeet/velorent_system.git velo-rent-chita.ru

ls -la /opt/python/*/bin/python
/opt/python/python-3.10.X/bin/python -m venv /var/www/u3539071/data/velorentenv
/var/www/u3539071/data/velorentenv/bin/pip install --upgrade pip
/var/www/u3539071/data/velorentenv/bin/pip install -r \
  /var/www/u3539071/data/www/velo-rent-chita.ru/requirements.txt
```

В команде создания окружения замените `python-3.10.X` на точное имя каталога
Python 3.10, показанное командой `ls`.

Если каталог сайта не пустой, сначала сохраните или удалите созданный панелью
стандартный `index.html`. Не удаляйте пользовательские файлы без проверки.

## 5. Настроить приложение

В каталоге сайта:

```bash
cd /var/www/u3539071/data/www/velo-rent-chita.ru
cp .env.reg.example .env
```

Откройте `.env` через файловый менеджер ISPmanager и замените:

- `SECRET_KEY`;
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`;
- реквизиты арендодателя;
- SMTP, VK и 1С, если они используются.

Создать случайный ключ:

```bash
openssl rand -base64 48
```

## 6. Создать таблицы и статику

```bash
cd /var/www/u3539071/data/www/velo-rent-chita.ru
/var/www/u3539071/data/velorentenv/bin/python manage.py migrate
/var/www/u3539071/data/velorentenv/bin/python manage.py collectstatic --noinput
touch .restart-app
```

## 7. Перенести данные и медиафайлы

Через файловый менеджер загрузите:

- `velorent-data-*.json` в закрытый каталог, например
  `/var/www/u3539071/data/transfer`;
- содержимое локального каталога `media` в каталог `media` сайта.

Импорт в пустую MySQL-базу:

```bash
/var/www/u3539071/data/velorentenv/bin/python manage.py import_portable_data \
  /var/www/u3539071/data/transfer/velorent-data-YYYYMMDD-HHMMSS.json \
  --inventory-output /var/www/u3539071/data/transfer/mysql-inventory.json
touch .restart-app
```

Команда откажется смешивать fixture с уже существующими рабочими данными.

Сравните локальный `velorent-inventory-*.json` и созданный на сервере
`mysql-inventory.json`. Количество записей по рабочим моделям должно совпасть.

## 8. Проверить сайт

```bash
/var/www/u3539071/data/velorentenv/bin/python manage.py check --deploy --fail-level ERROR
```

Проверьте:

- `https://velo-rent-chita.ru/`;
- вход существующего пользователя;
- каталог и фотографии;
- существующую бронь;
- панель оператора;
- создание тестовой брони.

После проверки удалите fixture с сервера или перенесите его в защищённое
резервное хранилище: он содержит персональные данные.

## 9. Настроить второй домен

После запуска основного сайта настройте постоянное перенаправление
`velo-rent-chita.online` на `https://velo-rent-chita.ru`. Не запускайте две
независимые копии сайта с общей базой.
