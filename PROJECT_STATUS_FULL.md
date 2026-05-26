# Полный отчёт о состоянии проекта VeloRent

## 1. Краткое резюме

VeloRent — Django-система для велопроката: клиент выбирает велосипед в каталоге, создает бронь, оператор подтверждает бронь, проверяет документ, выдает велосипед, принимает возврат, фиксирует оплату и видит аналитику.

Проект находится в состоянии сильного учебного MVP / демонстрационного прототипа. Основной пользовательский и операторский сценарий реализован кодом, покрыт частью тестов и имеет оформленный интерфейс. Есть роли клиента, оператора и администратора, каталог, бронирования, аренды, платежные записи, уведомления на сайте, email-коды, VK OAuth, PWA и демо-наполнение.

Для реального запуска проект пока не готов без доработок: 1С-интеграция является журналом событий без фактической отправки, платежи ручные, нет production security-настроек, нет фоновых задач и ретраев уведомлений, нет реального деплоя, а часть демо-медиа подключена неполностью.

Основано на: `velorent/settings.py`, `velorent/urls.py`, `accounts/models.py`, `catalog/models.py`, `rentals/models.py`, `integrations/models.py`, `dashboard/views.py`, `rentals/views.py`, `api/views.py`, `README.md`, `docs/*.md`.

## 2. Стек технологий и зависимости

| Компонент | Что найдено | Файлы | Состояние |
|---|---|---|---|
| Backend | Django 5.1.5 | `requirements.txt`, `velorent/settings.py` | Готово для локальной разработки |
| REST API | Django REST Framework 3.15.2 | `api/views.py`, `api/serializers.py`, `api/urls.py` | Частично готово |
| БД | SQLite по умолчанию, поддержка PostgreSQL через env | `velorent/settings.py`, `.env.example`, `docker-compose.yml` | SQLite готов для демо, PostgreSQL заявлен и поддержан настройками |
| Переменные окружения | `python-dotenv`, `.env.example` | `.env.example`, `velorent/settings.py` | Готово для локальной настройки |
| Email | Django `send_mail`, SMTP/env настройки | `accounts/views.py`, `integrations/vk_notifications.py`, `.env.example` | Реализовано, зависит от SMTP в `.env` |
| VK | OAuth и отправка сообщений через VK API | `accounts/vk_oauth.py`, `accounts/views.py`, `integrations/vk_notifications.py` | Частично готово, требует VK app/group token |
| PWA | manifest, service worker, install button, offline page | `templates/manifest.webmanifest`, `templates/service-worker.js`, `templates/offline.html`, `templates/base.html` | Реализовано для демо |
| Изображения | SVG/PNG/WebP, видео hero | `static/img`, `media/bikes`, `static/video/home-hero.mp4` | Готово для демо: реальные фото из `media/bikes` назначаются велосипедам при `seed_demo`, SVG остаются fallback |
| Docker | Dockerfile и docker-compose | `Dockerfile`, `docker-compose.yml` | Черновой dev-вариант |
| Тесты | 43 теста | `accounts/tests.py`, `rentals/tests.py`, `dashboard/tests.py`, `api/tests.py` | Прогон успешен |

Фактические зависимости из `requirements.txt`: `Django==5.1.5`, `djangorestframework==3.15.2`, `psycopg2-binary==2.9.10`, `python-dotenv==1.0.1`, `Pillow==11.1.0`.

## 3. Структура проекта

| Раздел / приложение | Назначение | Ключевые файлы | Состояние |
|---|---|---|---|
| `velorent/` | Настройки проекта, корневые URL, WSGI/ASGI | `settings.py`, `urls.py`, `wsgi.py`, `asgi.py` | Работает |
| `accounts/` | Пользователи, роли, регистрация, вход, профиль, VK, уведомления, коды доступа | `models.py`, `forms.py`, `views.py`, `urls.py`, `vk_oauth.py`, `middleware.py`, `context_processors.py`, `admin.py`, `tests.py` | Реализовано хорошо для MVP |
| `catalog/` | Велосипеды, категории, тарифы, точки выдачи, каталог и карточка велосипеда | `models.py`, `views.py`, `urls.py`, `admin.py`, `management/commands/seed_demo.py` | Реализовано |
| `rentals/` | Бронирования, аренды, платежи, выдача, возврат, продление, отмена, квитанция | `models.py`, `forms.py`, `views.py`, `urls.py`, `services.py`, `admin.py`, `tests.py` | Основной сценарий реализован |
| `dashboard/` | Личный кабинет и панель оператора, клиенты, велосипеды, аналитика | `views.py`, `urls.py`, `mixins.py`, `tests.py` | Реализовано для демо |
| `integrations/` | Журнал синхронизации 1С и уведомления VK/email/site | `models.py`, `services.py`, `vk_notifications.py`, `admin.py` | Частично: 1С без реальной отправки |
| `api/` | REST API для велосипедов, бронирований, действий оператора и справочников | `views.py`, `serializers.py`, `permissions.py`, `urls.py`, `tests.py` | Частично |
| `templates/` | HTML-интерфейс | `base.html`, `home.html`, `accounts/*`, `catalog/*`, `dashboard/*`, `rentals/*`, `admin/base_site.html` | Много готовых страниц |
| `static/` | CSS, логотипы, фон, PWA-иконки, видео | `css/style.css`, `css/admin.css`, `img/*`, `video/home-hero.mp4` | Реализовано |
| `media/` | Загруженные/демо-фото велосипедов | `media/bikes/*` | Частично интегрировано |
| `docs/` | Проектная документация | `system_design.md`, `business_rules.md`, `entity_model.md`, `api_spec.md`, `folder_structure.md` | Полезно для диплома |
| `db.sqlite3` | Локальная база | `db.sqlite3` | Есть локально, не в Git |
| `start_windows.bat` | Однокнопочный запуск на Windows | `start_windows.bat` | Проверен, работает |

## 4. Архитектура и модели данных

| Модель | Назначение | Основные поля | Связи | Где используется |
|---|---|---|---|---|
| `accounts.User` | Пользователь с ролью и профилем | `phone`, `role`, `telegram`, `vk_id`, `email_verified_at`, `document_verified`, `terms_accepted`, `next_booking_hourly_surcharge` | Наследует `AbstractUser`; связан с `Booking`, `Rental`, `UserNotification`, кодами | `accounts/models.py`, `accounts/forms.py`, `accounts/views.py`, `rentals/views.py`, `dashboard/views.py` |
| `accounts.AccountAccessCode` | Одноразовый код для задания пароля клиенту, созданному оператором | `user`, `code_hash`, `created_by`, `expires_at`, `used_at`, `attempts` | FK на `User` | `accounts/forms.py::AccountClaimForm`, `rentals/views.py::GenerateAccountAccessCodeView`, `dashboard/views.py::GenerateCustomerAccessCodeView` |
| `accounts.EmailVerificationCode` | Код подтверждения email | `user`, `email`, `code_hash`, `expires_at`, `used_at`, `attempts` | FK на `User` | `accounts/views.py::send_email_verification_code`, `EmailVerificationConfirmView` |
| `accounts.PasswordChangeCode` | Код смены пароля по email | `user`, `code_hash`, `expires_at`, `used_at`, `attempts` | FK на `User` | `accounts/forms.py::PasswordChangeByEmailForm`, `accounts/views.py::PasswordChangeStartView` |
| `accounts.UserNotification` | Внутренние уведомления сайта | `user`, `title`, `message`, `url`, `level`, `read_at`, `created_at` | FK на `User` | `integrations/vk_notifications.py`, `accounts/views.py::NotificationsListView` |
| `catalog.PickupLocation` | Точка выдачи/возврата | `name`, `address`, `phone`, `opening_hours`, `latitude`, `longitude`, `map_url`, `is_active` | FK из `Bike`, `Booking` | `catalog/models.py`, `templates/base.html`, `catalog/views.py`, `rentals/forms.py` |
| `catalog.BikeCategory` | Категория велосипеда | `name`, `description` | FK из `Bike` | `catalog/models.py`, `catalog/admin.py`, `seed_demo.py` |
| `catalog.Tariff` | Тариф аренды | `hourly_rate`, `daily_rate`, `deposit_amount`, `late_fee_per_hour`, `is_active` | FK из `Bike`, `Booking` | `rentals/services.py::calculate_booking_quote`, `catalog/admin.py` |
| `catalog.Bike` | Единица велопарка | `title`, `slug`, `serial_number`, `status`, `photo`, `condition_notes`, `description` | FK на `BikeCategory`, `Tariff`, `PickupLocation`; FK из `Booking` | `catalog/views.py`, `rentals/forms.py`, `dashboard/views.py` |
| `rentals.Booking` | Заявка/бронь клиента | `number`, `customer`, `bike`, `pickup_location`, `tariff`, `start_at`, `end_at`, `comment`, `status`, `quoted_price`, `deposit_amount`, `cancellation_reason` | FK на `User`, `Bike`, `PickupLocation`, `Tariff`; OneToOne через `Rental`; FK из `Payment` | `rentals/views.py`, `dashboard/views.py`, `api/views.py` |
| `rentals.Rental` | Фактическая аренда по брони | `booking`, `issued_by`, `received_by`, `actual_start_at`, `actual_end_at`, `damage_fee`, `late_fee`, `extra_time_fee`, `final_price`, `status` | OneToOne с `Booking`; FK на операторов | `rentals/views.py::IssueRentalView`, `ReturnRentalView`, `ExtendRentalView` |
| `rentals.Payment` | Платежная операция | `booking`, `amount`, `kind`, `method`, `status`, `external_id`, `created_at` | FK на `Booking` | `rentals/views.py`, `dashboard/views.py`, `api/views.py` |
| `integrations.SyncEvent` | Журнал события для 1С | `entity`, `entity_id`, `event_type`, `payload`, `direction`, `status`, `response_text` | Нет внешних FK | `integrations/services.py::queue_booking_sync`, `integrations/admin.py` |

Архитектурный стиль фактически соответствует modular monolith: домены разделены на Django apps, но работают в одном процессе и одной базе.

## 5. Роли и права доступа

| Роль | Что может делать | Как реализовано | Ограничения / проблемы |
|---|---|---|---|
| Клиент | Регистрироваться, входить, смотреть каталог, бронировать, видеть свои брони, отменять свои `pending/confirmed` брони, получать уведомления, подтверждать email, менять пароль через email | `User.Role.CUSTOMER`, `LoginRequiredMixin`, фильтры `Booking.objects.filter(customer=request.user)` в `BookingDetailView`, `MyBookingsListView`, `BookingViewSet` | Нет отдельного запрета клиенту на доступ к некоторым URL кроме фильтрации; нет rate limiting на login/code forms |
| Оператор | Смотреть панель, подтверждать/выдавать/возвращать/продлевать аренды, проверять документы, отмечать неявку, видеть клиентов, велосипеды, аналитику | `dashboard.mixins.OperatorRequiredMixin`, `api.permissions.IsOperator`, проверки в `rentals/views.py`, `dashboard/views.py` | Web `ConfirmBookingView` теперь повторяет проверку пересечений; транзакционных блокировок для production пока нет |
| Администратор | Доступ к operator-функциям и Django Admin | `User.Role.ADMIN`, `is_staff`, `is_superuser`, `OperatorRequiredMixin`; `templates/base.html` показывает Admin link staff/admin | Демо-оператор создается `is_staff=True`, но без явных model permissions/superuser; может войти в админку, но полноценное управление через admin не гарантировано |
| Аноним | Главная, каталог, карточки велосипедов, регистрация, вход, условия | публичные `ListView/DetailView`, `AllowAny` в `BikeViewSet`/`ReferenceViewSet` | Бронирование требует логина |

## 6. Реализованный функционал клиента

| Функция | Статус | Подтверждение файлами | Комментарий |
|---|---|---|---|
| Регистрация по телефону | Готово | `accounts/forms.py::UserRegisterForm`, `accounts/views.py::UserRegisterView`, `templates/accounts/register.html` | Нормализация телефона, уникальность непустого телефона, согласия с условиями |
| Авторизация по телефону/паролю | Готово | `accounts/forms.py::UserLoginForm`, `accounts/views.py::UserLoginView`, `templates/accounts/login.html` | Можно вводить телефон, форма ищет `User.phone` |
| Установка пароля по коду оператора | Готово | `AccountAccessCode`, `AccountClaimForm`, `AccountClaimView`, `templates/accounts/claim.html` | Код хранится как hash, есть TTL и попытки |
| Вход/регистрация через VK | Частично | `accounts/vk_oauth.py`, `VKLoginStartView`, `VKCallbackView`, `templates/accounts/login.html`, `templates/accounts/register.html` | Требует `VK_CLIENT_ID`, `VK_CLIENT_SECRET`, redirect URL. Без настроек выводит сообщение |
| Профиль | Готово | `accounts/views.py::ProfileView`, `accounts/forms.py::ProfileForm`, `templates/accounts/profile.html` | Имя, фамилия, email, Telegram, телефон read-only |
| Подтверждение email кодом | Готово | `EmailVerificationCode`, `send_email_verification_code`, `EmailVerificationConfirmView`, `EmailVerificationResendView` | Отправка зависит от SMTP/backend |
| Смена пароля по email-коду | Готово | `PasswordChangeCode`, `PasswordChangeByEmailForm`, `PasswordChangeStartView`, `PasswordChangeConfirmView` | Требует подтвержденный email и текущий пароль |
| Каталог велосипедов | Готово | `catalog/views.py::CatalogListView`, `templates/catalog/catalog.html` | Показывает `available` и `reserved`, доступность reserved дополняется текстом |
| Карточка велосипеда | Готово | `BikeDetailView`, `templates/catalog/bike_detail.html` | Есть тариф, точка выдачи, карта, статус, доступность |
| Бронирование клиентом | Готово | `BookingCreateView`, `BookingForm`, `rentals/services.py::bike_available_for_period`, `templates/rentals/booking_form.html` | Плановый возврат задается длительностью в часах |
| Альтернативные велосипеды при недоступности | Готово | `BookingCreateView.get_alternative_bikes`, `templates/rentals/booking_form.html` | Показывается при невалидной форме/конфликте |
| Просмотр своих броней | Готово | `dashboard/views.py::UserDashboardView`, `rentals/views.py::MyBookingsListView`, `templates/dashboard/user_dashboard.html`, `templates/rentals/my_bookings.html` | Личный кабинет + отдельная страница |
| Детальная бронь | Готово | `BookingDetailView`, `templates/rentals/booking_detail.html` | Есть таймлайн, суммы, документы, платежи, карта |
| Отмена своей брони | Готово | `CancelBookingView.post`, `templates/rentals/booking_detail.html` | Клиент может отменить `pending/confirmed`; GET-экран отмены только для оператора |
| Уведомления на сайте | Готово | `UserNotification`, `notify_booking_event`, `NotificationsListView`, `templates/accounts/notifications.html`, `accounts/context_processors.py` | Уведомления помечаются прочитанными при открытии страницы |
| Email-уведомления по броням | Готово при SMTP | `integrations/vk_notifications.py::send_booking_email` | Только если `email_is_verified=True` |
| VK-уведомления | Частично | `send_vk_message`, `VKNotificationsToggleView`, `VKTestNotificationView`, `templates/accounts/profile.html` | Требует `VK_GROUP_TOKEN` и разрешение сообщений от пользователя |
| Квитанция | Готово | `BookingReceiptView`, `receipt_is_ready`, `templates/rentals/booking_receipt.html` | Доступна после завершения аренды и оплаты |
| PWA/установка приложения | Частично готово | `manifest.webmanifest`, `service-worker.js`, `base.html` | Работает как PWA-заготовка, но без push-уведомлений |

## 7. Реализованный функционал оператора и администратора

| Функция | Статус | Подтверждение файлами | Комментарий |
|---|---|---|---|
| Панель оператора | Готово | `OperatorDashboardView`, `templates/dashboard/operator_dashboard.html` | Быстрые фильтры, список броней, метки внимания |
| Создание брони по телефону | Готово | `OperatorBookingCreateView`, `OperatorBookingForm`, `templates/rentals/operator_booking_form.html` | Создает клиента при необходимости и код доступа, если нет пароля |
| Генерация кода доступа клиенту | Готово | `GenerateAccountAccessCodeView`, `GenerateCustomerAccessCodeView`, `templates/dashboard/customer_detail.html` | Доступно из брони и карточки клиента |
| Подтверждение брони | Готово | `ConfirmBookingView`, `api/views.py::OperatorActionViewSet.confirm` | API и web проверяют недоступность велосипеда и конфликтующие брони перед подтверждением |
| Выдача велосипеда | Готово | `IssueRentalView`, `OperatorActionViewSet.issue` | Требует подтвержденную бронь и проверенный документ |
| Проверка документа клиента | Готово | `VerifyCustomerDocumentView`, `User.document_verified*`, `templates/rentals/booking_detail.html` | Хранится тип документа и последние 4 цифры |
| Возврат велосипеда | Готово | `ReturnRentalView`, `compute_late_fee`, `templates/rentals/booking_detail.html` | Считает просрочку и damage fee, создает pending payment |
| Продление активной аренды | Готово | `ExtendRentalView`, тесты в `rentals/tests.py` | Проверяет будущие пересечения и пересчитывает стоимость |
| Неявка | Готово | `NoShowConfirmView`, `MarkNoShowView`, `templates/rentals/no_show_confirm.html` | Доступно через 15 минут после старта; может назначить надбавку на следующее бронирование |
| Отмена оператором с причиной | Готово | `BookingCancelForm`, `CancelBookingView`, `templates/rentals/cancel_confirm.html` | Причина сохраняется и попадает в уведомление/email |
| Подтверждение оплаты | Готово | `ConfirmRentalPaymentView` | Меняет pending rental payment на paid, создает refund по залогу |
| История платежей | Готово | `Payment`, `templates/rentals/booking_detail.html`, `booking_receipt.html` | Ручная модель учета платежей |
| Управление велосипедами в операторской | Частично | `OperatorBikeListView`, `SendBikeToServiceView`, `ReturnBikeFromServiceView`, `templates/dashboard/bikes_list.html` | Можно смотреть, фильтровать, отправлять/возвращать из обслуживания; создание/редактирование через admin |
| Управление клиентами | Готово для просмотра | `OperatorCustomersListView`, `OperatorCustomerDetailView`, `templates/dashboard/customers_list.html`, `customer_detail.html` | Список, поиск, пагинация, карточка клиента, аренды/платежи |
| Аналитика | Частично готово | `AnalyticsView`, `AnalyticsBookingsDetailView`, `AnalyticsRentalsDetailView`, `AnalyticsPaymentsDetailView`, templates `dashboard/analytics*` | Есть базовые KPI за 7/30/90 дней, выручка, популярные велосипеды |
| Django Admin | Частично готово | `accounts/admin.py`, `catalog/admin.py`, `rentals/admin.py`, `integrations/admin.py`, `static/css/admin.css`, `templates/admin/base_site.html` | Оформлен и зарегистрированы модели; риск в `SyncEventAdmin.search_fields` закрыт, полноценные production-permissions остаются будущей задачей |
| Управление тарифами/точками выдачи | Через admin | `catalog/admin.py` | Нет отдельного красивого operator UI для тарифов и точек |

## 8. Бизнес-процесс бронирования и аренды

Фактический сценарий по коду:

1. Клиент открывает каталог: `catalog/views.py::CatalogListView`, `templates/catalog/catalog.html`.
2. Клиент выбирает велосипед: `catalog/views.py::BikeDetailView`, `templates/catalog/bike_detail.html`.
3. Клиент создает бронь: `rentals/views.py::BookingCreateView`, `rentals/forms.py::BookingForm`.
4. Форма рассчитывает `end_at` из `start_at + duration_hours`: `BookingForm.clean`.
5. Сервис проверяет доступность велосипеда на период: `rentals/services.py::bike_available_for_period`.
6. Сервис рассчитывает стоимость и залог: `rentals/services.py::calculate_booking_quote`.
7. Создается `Booking` со статусом `pending` и связанный `Rental` со статусом `ready`: `BookingCreateView.form_valid`.
8. Создается `SyncEvent` для 1С: `integrations/services.py::queue_booking_sync`.
9. Создаются уведомления: `integrations/vk_notifications.py::notify_booking_event`.
10. Оператор подтверждает бронь: `ConfirmBookingView.post`, статус `confirmed`, велосипед `reserved`.
11. Перед выдачей оператор проверяет документ: `VerifyCustomerDocumentView.post`.
12. Оператор выдает велосипед: `IssueRentalView.post`, `Rental.active`, `Booking.active`, `Bike.in_rent`, создается платеж-залог.
13. Если клиент хочет продлить аренду, оператор использует `ExtendRentalView.post`; система проверяет будущие брони и пересчитывает `quoted_price`.
14. Оператор принимает возврат: `ReturnRentalView.post`; рассчитывается `late_fee`, `damage_fee`, `final_price`, создается pending payment.
15. Оператор подтверждает оплату: `ConfirmRentalPaymentView.post`; pending rental payment становится paid, залог возвращается отдельным `Payment.REFUND`.
16. После оплаты доступна квитанция: `BookingReceiptView`, `receipt_is_ready`.

Частные сценарии:

- Если клиент не пришел: `MarkNoShowView` переводит бронь в `expired`, освобождает велосипед и может назначить надбавку на следующее бронирование.
- Если бронь отменена: `CancelBookingView` переводит в `cancelled`, отменяет `Rental.ready`, освобождает reserved-велосипед.
- Если бронь создана оператором для нового клиента: `OperatorBookingCreateView` может сгенерировать одноразовый код для задания пароля.

## 9. Интеграции и уведомления

| Интеграция | Статус | Какие файлы найдены | Что требуется доделать |
|---|---|---|---|
| 1С | Частично / заглушка очереди | `integrations/models.py::SyncEvent`, `integrations/services.py::queue_booking_sync`, `.env.example` `ONEC_API_URL`, `ONEC_API_TOKEN` | Нет HTTP-отправителя в 1С, нет фоновой задачи, нет ретраев, нет обработки входящих событий, `ONEC_API_TOKEN` не используется |
| Site notifications | Готово | `accounts/models.py::UserNotification`, `integrations/vk_notifications.py::create_site_notification`, `NotificationsListView` | Для MVP достаточно; для production нужны настройки хранения/архивации |
| Email уведомления по броням | Готово при SMTP | `send_booking_email`, `send_email_verification_code`, `send_password_change_code`, `.env.example` | Нужен реальный SMTP, обработка ошибок/ретраи, шаблоны HTML-писем |
| Email подтверждение | Готово | `EmailVerificationCode`, `EmailVerificationForm`, `EmailVerificationConfirmView` | Для production добавить rate limiting |
| Email смена пароля | Готово | `PasswordChangeCode`, `PasswordChangeByEmailForm`, `PasswordChangeStartView` | Для production добавить аудит и rate limiting |
| VK OAuth | Частично | `accounts/vk_oauth.py`, `VKLoginStartView`, `VKCallbackView` | Нужны реальные настройки VK и проверка на боевом домене |
| VK сообщения | Частично | `send_vk_message`, `VKNotificationsToggleView`, `VKTestNotificationView` | Нужен `VK_GROUP_TOKEN`, разрешение сообщений от пользователя, обработка ошибок API не через поиск строки `"error"` |
| SMS | Отсутствует | Не найдено | Подключить SMS-провайдера, если требуется |
| Telegram | Отсутствует как отправка | `User.telegram`, `ProfileForm` | В проекте есть только поле Telegram; отправки сообщений/бота нет |
| Онлайн-оплата | Отсутствует | `Payment` model only | Нет интеграции с эквайрингом/кассой |

Заявлено, но не подтверждено реализацией:

- В `docs/system_design.md` сказано, что данные отправляются в 1С. Реально создается `SyncEvent`, но отправки по `ONEC_API_URL` нет.
- В документации указан PostgreSQL как основная БД. Реально настройки PostgreSQL поддержаны, но локальный и быстрый запуск используют SQLite.

## 10. Интерфейс и существующие страницы

| Страница | URL | Шаблон | Для кого | Состояние |
|---|---|---|---|---|
| Главная | `/` | `templates/home.html` | Все | Законченная, video hero |
| Условия аренды | `/terms/` | `templates/terms.html` | Все | Готово |
| Каталог | `/catalog/` | `templates/catalog/catalog.html` | Все | Готово |
| Карточка велосипеда | `/catalog/<slug>/` | `templates/catalog/bike_detail.html` | Все, operator actions условно | Готово |
| Регистрация | `/accounts/register/` | `templates/accounts/register.html` | Аноним | Готово |
| Вход | `/accounts/login/` | `templates/accounts/login.html` | Аноним | Готово |
| Доступ по коду | `/accounts/claim/` | `templates/accounts/claim.html` | Клиент без пароля | Готово |
| Профиль | `/accounts/profile/` | `templates/accounts/profile.html` | Клиент/пользователь | Функционально насыщенно, но сложная страница |
| Уведомления | `/accounts/notifications/` | `templates/accounts/notifications.html` | Авторизованные | Готово |
| Личный кабинет | `/dashboard/` | `templates/dashboard/user_dashboard.html` | Клиент | Готово |
| Мои брони | `/rentals/book/` | `templates/rentals/my_bookings.html` | Клиент | Работает, визуально проще личного кабинета |
| Создание брони | `/rentals/book/<slug>/new/` | `templates/rentals/booking_form.html` | Клиент | Готово |
| Деталь брони | `/rentals/booking/<pk>/` | `templates/rentals/booking_detail.html` | Клиент/оператор | Готово, ключевая страница |
| Квитанция | `/rentals/booking/<pk>/receipt/` | `templates/rentals/booking_receipt.html` | Клиент/оператор | Готово |
| Отмена брони | `/rentals/booking/<pk>/cancel/` | `templates/rentals/cancel_confirm.html` | Оператор GET, клиент POST из детали | Готово |
| Неявка | `/rentals/booking/<pk>/no-show/confirm/` | `templates/rentals/no_show_confirm.html` | Оператор | Готово |
| Панель оператора | `/operator/` | `templates/dashboard/operator_dashboard.html` | Оператор/админ | Готово |
| Создание брони оператором | `/rentals/operator/new/` | `templates/rentals/operator_booking_form.html` | Оператор | Готово |
| Парк велосипедов | `/operator/bikes/` | `templates/dashboard/bikes_list.html` | Оператор | Готово для просмотра/сервиса |
| Клиенты | `/operator/customers/` | `templates/dashboard/customers_list.html` | Оператор | Готово |
| Карточка клиента | `/operator/customers/<pk>/` | `templates/dashboard/customer_detail.html` | Оператор | Готово |
| Аналитика | `/operator/analytics/` | `templates/dashboard/analytics.html` | Оператор | Частично |
| Детали аналитики: брони | `/operator/analytics/bookings/` | `templates/dashboard/analytics_bookings.html` | Оператор | Частично |
| Детали аналитики: аренды | `/operator/analytics/rentals/` | `templates/dashboard/analytics_rentals.html` | Оператор | Частично |
| Детали аналитики: платежи | `/operator/analytics/payments/` | `templates/dashboard/analytics_payments.html` | Оператор | Частично |
| Выручка | `/operator/revenue/` | `templates/dashboard/revenue_list.html` | Оператор | Есть, но отдельная навигация ограничена |
| Offline | `/offline/` | `templates/offline.html` | PWA | Готово |
| Django Admin | `/admin/` | `templates/admin/base_site.html`, Django admin | Staff/admin | Оформлено, права требуют настройки |

Навигация:

- Верхняя навигация в `templates/base.html`.
- Для операторов есть левая панель `operator-sidebar`.
- Для клиентов: каталог, кабинет, профиль, уведомления.
- Есть кнопка назад и кнопка наверх в `base.html`.

## 11. Отчёты и аналитика

Реализовано:

- Основные KPI за период 7/30/90 дней: выручка, брони, завершенные аренды, неявки, отмены.
- Популярные велосипеды по бронированиям.
- Выручка по велосипедам.
- Детализация бронирований, аренд и платежей.

Файлы:

- `dashboard/views.py::AnalyticsView`
- `dashboard/views.py::AnalyticsBookingsDetailView`
- `dashboard/views.py::AnalyticsRentalsDetailView`
- `dashboard/views.py::AnalyticsPaymentsDetailView`
- `templates/dashboard/analytics.html`
- `templates/dashboard/analytics_bookings.html`
- `templates/dashboard/analytics_rentals.html`
- `templates/dashboard/analytics_payments.html`

Ограничения:

- Нет графиков, экспортов CSV/XLSX/PDF.
- Нет отчетов по загрузке часов/дней, среднему чеку, просрочкам по клиентам, техническому простою.
- Выручка основана только на `Payment.Status.PAID` и `kind in rental/fine`.
- Нет разделения реальных онлайн-платежей и ручных кассовых операций.

## 12. Django Admin

Реализовано:

- Кастомные заголовки admin: `velorent/urls.py`.
- Кастомный шаблон: `templates/admin/base_site.html`.
- Стилизация: `static/css/admin.css`.
- Регистрация моделей:
  - `accounts/admin.py`: `User`, `AccountAccessCode`, `EmailVerificationCode`, `PasswordChangeCode`, `UserNotification`.
  - `catalog/admin.py`: `PickupLocation`, `BikeCategory`, `Tariff`, `Bike` с preview фото.
  - `rentals/admin.py`: `Booking`, `Rental`, `Payment`.
  - `integrations/admin.py`: `SyncEvent`.

Проблемы:

- В `integrations/admin.py::SyncEventAdmin.search_fields` раньше было указано `error_message`, но в `integrations/models.py::SyncEvent` такого поля нет. Закрыто 24.05.2026: поиск переведен на реальные поля, включая `response_text`.
- `seed_demo.py` создает `operator` с `is_staff=True`, но не назначает model permissions и не делает superuser. Поэтому демо-оператор может видеть ссылку на админку, но не обязательно сможет полноценно управлять моделями через Django Admin.

## 13. Безопасность, проверки и ограничения

Что реализовано:

- CSRF middleware включен: `velorent/settings.py`.
- `LoginRequiredMixin` для личных и операторских страниц.
- `OperatorRequiredMixin` проверяет `role in operator/admin` или staff/superuser.
- Клиентские брони фильтруются по текущему пользователю: `BookingDetailView.get_queryset`, `MyBookingsListView.get_queryset`, `BookingViewSet.get_queryset`.
- Коды доступа/email/password хранятся hash-значениями, имеют TTL и лимит попыток.
- Телефон уникален на уровне БД для непустого значения: `User.Meta.constraints`.
- Документы клиента хранятся ограниченно: тип и последние 4 цифры, не полный документ.
- Для авторизованных HTML-страниц добавлены no-store headers: `accounts/middleware.py::AuthenticatedPageNoStoreMiddleware`.

Проверки запуска:

- `python manage.py check` — успешно, 0 issues.
- `python manage.py makemigrations --check --dry-run` — `No changes detected`.
- `python manage.py migrate --check` — успешно, непримененных миграций нет.
- `python manage.py test` — 43 теста, все OK.
- `python manage.py check --deploy` — 6 warning security-настроек.

Security warnings из `check --deploy`:

- Не настроен `SECURE_HSTS_SECONDS`.
- `SECURE_SSL_REDIRECT` не `True`.
- `SECRET_KEY` слабый/не production.
- `SESSION_COOKIE_SECURE` не `True`.
- `CSRF_COOKIE_SECURE` не `True`.
- `DEBUG=True`.

Ограничения и риски:

- Нет rate limiting для логина и одноразовых кодов.
- Нет транзакционной блокировки на проверку доступности и создание брони, возможна гонка при высокой конкуренции.
- Web-подтверждение брони повторяет проверку недоступности велосипеда и пересечений периода по логике API-подтверждения. Закрыто 24.05.2026 в `rentals/views.py::ConfirmBookingView`.
- REST API использует session/basic authentication; отдельной token-auth/JWT/OAuth для внешних интеграций нет.
- `ONEC_API_TOKEN` есть в настройках, но не используется в коде API/интеграции.
- Нет audit log действий оператора, кроме частичных полей `issued_by`, `received_by`, `document_verified_by` и платежных записей.

## 14. Найденные ошибки, технический долг и незавершённые места

### Критично

1. 1С-интеграция не выполняет реальную отправку.
   - Файлы: `integrations/services.py`, `integrations/models.py`.
   - Реально создается `SyncEvent`, но нет клиента, который отправляет payload в `ONEC_API_URL`, нет статусов `sent/failed` по ответу внешней системы.

2. Production security не настроена.
   - Файл: `velorent/settings.py`.
   - Подтверждение: `python manage.py check --deploy` выдал 6 warning.
   - Для диплома не критично, для реального запуска критично.

3. Возможна гонка двойного бронирования.
   - Файлы: `rentals/services.py::bike_available_for_period`, `rentals/views.py::BookingCreateView.form_valid`, `OperatorBookingCreateView.form_valid`, `api/views.py::BookingViewSet.create`.
   - Проверка доступности и создание брони не завернуты в transaction/select_for_update/уникальное ограничение периода.

4. Web-подтверждение брони не повторяло конфликт-проверку. Закрыто 24.05.2026.
   - Файл: `rentals/views.py::ConfirmBookingView`.
   - API-вариант `api/views.py::OperatorActionViewSet.confirm` проверяет конфликт, web-вариант только меняет статус.

5. Реальные фото велосипедов добавлены в репозиторий, fresh-start демо теперь назначает их автоматически. Закрыто 24.05.2026.
   - Файлы: `media/bikes/1.webp`, `2.png`, ..., `catalog/management/commands/seed_demo.py`.
   - `seed_demo.py` выбирает существующие PNG/WebP/JPG/JPEG из `media/bikes`; если их нет, остается fallback на `bikes/<slug>.svg`.
   - Повторный запуск команды не ломается: существующие non-SVG фото сохраняются.

### Важно

1. `SyncEventAdmin.search_fields` содержал несуществующее поле. Закрыто 24.05.2026.
   - Файлы: `integrations/admin.py`, `integrations/models.py`.
   - `error_message` заменено на реально существующее поле `response_text`.

2. Платежи реализованы только как ручные записи.
   - Файл: `rentals/models.py::Payment`, `rentals/views.py::ConfirmRentalPaymentView`.
   - Нет эквайринга, кассы, чеков по 54-ФЗ, webhook-статусов.

3. `start_windows.bat` всегда запускает `seed_demo`.
   - Файл: `start_windows.bat`.
   - Хорошо для демонстрации, но опасно для реальной базы: демо-данные будут обновляться при каждом запуске.

4. Docker-конфигурация dev-уровня.
   - Файлы: `Dockerfile`, `docker-compose.yml`.
   - Используется `runserver`; нет gunicorn/uvicorn, collectstatic, nginx, healthcheck.
   - `docker-compose.yml` поднимает Postgres, но `.env.example` по умолчанию указывает SQLite.

5. VK-отправка упрощена.
   - Файл: `integrations/vk_notifications.py::send_vk_message`.
   - Ошибка определяется поиском строки `"error"` в теле ответа; нет полноценного JSON-разбора ответа VK.

6. API неполный для внешних систем.
   - Файлы: `api/views.py`, `docs/api_spec.md`.
   - Нет endpoint'ов для всех справочников/платежных сценариев/синхронизации, нет OpenAPI/Swagger.

7. Нет фоновых задач.
   - Заявлено развитие в `docs/system_design.md`.
   - В коде нет Celery/RQ/APScheduler; уведомления и SyncEvent выполняются синхронно при запросе.

### Можно оставить после защиты

1. Нет графиков в аналитике.
2. Нет экспорта отчетов.
3. Нет отдельного UI для управления тарифами и точками выдачи вне admin.
4. Нет фотофиксации состояния велосипеда при выдаче/возврате.
5. Нет Telegram-бота, хотя поле Telegram в профиле есть.
6. Нет полноценного мобильного native app; есть PWA.
7. Нет продвинутого дизайна квитанции под печать кассового документа.

## 15. Git-состояние и последние изменения

Состояние на момент аудита:

- Ветка: `main`.
- Remote: `origin/main`.
- `git status --short` — рабочее дерево чистое до создания этого отчета.
- `db.sqlite3`, `.env`, `.venv`, `cloudflared.exe` не отслеживаются Git.
- В Git отслеживаются `media/bikes/*.svg`, `media/bikes/*.png`, `media/bikes/*.webp`, `static/video/home-hero.mp4`.

Последние крупные коммиты:

| Коммит | Назначение |
|---|---|
| `f2230ed` | Выравнивание дат бронирований в личном кабинете |
| `4f15dbd` | Исправление устаревшего PWA CSS cache |
| `c71ca28` | Выделение дат бронирований |
| `d576405` | Добавлены фото велосипедов |
| `a31fa5b` | Улучшен список броней клиента |
| `2713d22` | Исправлен Windows startup script |
| `553a074` | Стилизация Django admin и preview фото |
| `cd208a5` | Безопасная смена пароля |
| `81971d4` | Улучшение rental workflow и уведомлений |
| `fafed62` | Видео hero на главной |
| `c582115` | Усиление доступности бронирования и operator API |
| `861e6e2` | Таймлайн брони и квитанция |
| `bb8da0b` | User notifications и email alerts |
| `d540e2e` | Windows one-click startup |
| `0541bb0` | Начальный проект |

## 16. Инструкция запуска проекта

### Быстрый запуск Windows

Файл: `start_windows.bat`.

1. Установить Python 3.12+ и добавить в PATH.
2. Скачать проект.
3. Запустить `start_windows.bat`.
4. Скрипт:
   - создает `.env` из `.env.example`, если его нет;
   - создает `.venv`;
   - восстанавливает/обновляет `pip`;
   - ставит зависимости;
   - применяет миграции;
   - запускает `seed_demo`;
   - открывает `http://127.0.0.1:8000/`;
   - запускает Django `runserver`.

Демо-логины из `README.md` и `seed_demo.py`:

- Оператор: `operator` / `operator123`.
- Клиенты: `customer01` ... `customer10` / `Mechabear1001`.

### Ручной запуск

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

### Проверки

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate --check
.\.venv\Scripts\python.exe manage.py test
```

Фактический результат аудита:

- `check` — OK.
- `makemigrations --check --dry-run` — `No changes detected`.
- `migrate --check` — OK.
- `test` — 43 tests OK.
- `check --deploy` — 6 security warnings.

Команда `migrate --check --dry-run` не поддерживается Django CLI в этой версии; это не ошибка проекта.

## 17. Что показать на демонстрации диплома

Сценарий на 3–5 минут:

1. Открыть главную `/` и показать, что это PWA/веб-приложение велопроката с брендингом.
2. Открыть каталог `/catalog/`: показать карточки велосипедов, тарифы, статусы, доступность reserved-велосипеда.
3. Войти клиентом `customer08` / `Mechabear1001`, открыть личный кабинет `/dashboard/`, показать брони, уведомления и профиль.
4. Создать новую бронь клиентом: выбрать велосипед, указать время и длительность, показать расчет суммы и залога.
5. Войти оператором `operator` / `operator123`, открыть `/operator/`: показать быстрые фильтры `Все`, `В работе`, `Новые`, `Активные`.
6. Открыть бронь: показать статус, клиента, велосипед, период, расчет, таймлайн, документы.
7. Показать проверку документа клиента и выдачу велосипеда.
8. Показать активную аренду: продление, возврат, расчет просрочки/штрафа.
9. Подтвердить оплату и открыть квитанцию.
10. Открыть аналитику `/operator/analytics/`: показать выручку, брони, популярные велосипеды.

Дополнительно можно показать:

- Код доступа для клиента, созданного по телефону.
- Уведомления на сайте.
- Email-подтверждение в профиле, если SMTP настроен.
- Django Admin с кастомным стилем.

## 18. Что доделать перед защитой

| Приоритет | Задача | Почему важна | Сложность | Где менять |
|---|---|---|---|---|
| Закрыто 24.05.2026 | Назначить реальные фото велосипедов в `seed_demo` | Fresh-start демо теперь получает реальные фото из `media/bikes` | Выполнено | `catalog/management/commands/seed_demo.py` |
| Закрыто 24.05.2026 | Исправить `SyncEventAdmin.search_fields` | Риск ошибки в admin при поиске событий закрыт | Выполнено | `integrations/admin.py` |
| Закрыто 24.05.2026 | Добавить проверку конфликтов в web `ConfirmBookingView` | Web и API подтверждение теперь согласованы по проверке конфликтов | Выполнено | `rentals/views.py::ConfirmBookingView` |
| Средний | Создать суперпользователя/админа в demo или описать команду | Для показа Django Admin нужен настоящий доступ | Низкая | `seed_demo.py` или README |
| Средний | Добавить короткую страницу/блок “Интеграция с 1С: журнал событий” | Чтобы честно показать, что 1С пока очередь событий | Низкая | `templates/dashboard`, `integrations/admin.py` |
| Средний | Обновить README по реальным фото и ограничениям 1С | Чтобы документация не обещала больше, чем код | Низкая | `README.md`, `docs/system_design.md` |
| Низкий | Сделать страницу `my_bookings.html` визуально в стиле нового кабинета | Сейчас она проще остальных страниц | Низкая | `templates/rentals/my_bookings.html`, `static/css/style.css` |

## 19. Что доделать для полноценного реального запуска

1. Production deployment:
   - `DEBUG=False`;
   - надежный `SECRET_KEY`;
   - `ALLOWED_HOSTS`;
   - HTTPS;
   - `SECURE_SSL_REDIRECT=True`;
   - `SESSION_COOKIE_SECURE=True`;
   - `CSRF_COOKIE_SECURE=True`;
   - HSTS после проверки домена.

2. База данных:
   - перейти на PostgreSQL;
   - настроить backup;
   - убрать автозапуск `seed_demo` в production.

3. Бронирования:
   - транзакции и блокировки при создании/подтверждении брони;
   - защита от двойного бронирования на уровне сервиса/БД;
   - аудит действий оператора.

4. 1С:
   - реализовать HTTP-клиент отправки `SyncEvent`;
   - использовать `ONEC_API_TOKEN`;
   - статусы `sent/failed`;
   - retry/backoff;
   - входящие endpoint'ы, если 1С должна менять справочники/статусы.

5. Платежи:
   - интеграция с эквайрингом;
   - webhook подтверждения;
   - кассовые чеки/фискализация;
   - раздельный учет залога, аренды, штрафа и возврата.

6. Уведомления:
   - фоновые задачи;
   - ретраи email/VK;
   - HTML email-шаблоны;
   - SMS или Telegram, если требуется бизнесом.

7. Администрирование:
   - полноценные группы и permissions;
   - отдельная роль администратора;
   - UI для тарифов/точек выдачи или четкий admin workflow.

8. Эксплуатация:
   - логирование;
   - мониторинг;
   - healthcheck;
   - Docker production setup;
   - static/media hosting.

9. Юридическая часть:
   - реальные условия аренды;
   - политика персональных данных;
   - согласия;
   - договор/акт/квитанция, если требуется.

## 20. Итоговая оценка готовности

- MVP: 88%
- Для защиты диплома: 94%
- Для реального клиента: 55%

Объяснение:

MVP оценен высоко, потому что основной цикл “каталог -> бронь -> подтверждение -> выдача -> возврат -> оплата -> квитанция” реализован в коде и частично покрыт тестами. Есть роли, уведомления, профиль, документы, аналитика, demo seed, Windows one-click startup.

Для защиты диплома готовность еще выше, потому что проект демонстрационно цельный: есть понятные данные, сценарий показа, интерфейс, аналитика, PWA, admin styling и тесты. Самые опасные для защиты места из первичного аудита закрыты 24.05.2026: реальные фото после fresh-start, admin search в `SyncEventAdmin`, конфликт-проверка web-подтверждения брони.

Для реального клиента оценка существенно ниже: нет настоящей 1С-синхронизации, онлайн-оплаты, production security, блокировок от гонок, фоновых задач, надежного деплоя и полноценной эксплуатационной инфраструктуры. Это нормальная стадия для дипломного MVP, но не для коммерческой эксплуатации без следующего этапа разработки.

### Обновление 24.05.2026 после критичных доработок

Закрыто для стабильной демонстрации:

- `rentals/views.py::ConfirmBookingView`: добавлена повторная проверка состояния велосипеда и конфликтующих броней перед подтверждением. При конфликте бронь не подтверждается, оператор получает понятное сообщение.
- `integrations/admin.py::SyncEventAdmin.search_fields`: несуществующее поле `error_message` заменено на существующее `response_text`.
- `catalog/management/commands/seed_demo.py`: fresh-start демо теперь назначает велосипедам реальные изображения из `media/bikes`, если найдены `.jpg`, `.jpeg`, `.png` или `.webp`; SVG остаются fallback, повторный запуск команды сохраняет существующие non-SVG фото.

Проверки после изменений:

- `python manage.py check` — OK, 0 issues.
- `python manage.py makemigrations --check --dry-run` — OK, `No changes detected`.
- `python manage.py migrate --check` — OK.
- `python manage.py test` — OK, 43 теста.

Остается для будущего реального запуска, не для текущей защиты:

- полноценная отправка событий в 1С с retry/backoff и статусами `sent/failed`;
- онлайн-оплата, фискализация и webhook статусов платежей;
- production security-настройки (`DEBUG=False`, HTTPS, secure cookies, HSTS, надежный `SECRET_KEY`);
- транзакционные блокировки от гонок при создании/подтверждении брони;
- фоновые задачи для email/VK-уведомлений и эксплуатационный деплой.
