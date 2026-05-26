from datetime import timedelta
from decimal import Decimal
from html import escape

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import ProtectedError
from django.utils import timezone

from accounts.models import User
from catalog.models import Bike, BikeCategory, PickupLocation, Tariff
from rentals.models import Booking, Payment, Rental
from rentals.services import calculate_booking_quote


CUSTOMER_PASSWORD = "Mechabear1001"


CUSTOMERS = [
    ("customer01", "Алина", "Морозова", "79961543021", "alina.morozova@example.com", "@alina_ride", "1482"),
    ("customer02", "Даниил", "Ковалев", "79964281735", "daniil.kovalev@example.com", "@dan_kov", "7319"),
    ("customer03", "Мария", "Соколова", "79968320416", "maria.sokolova@example.com", "@maria_s", "5094"),
    ("customer04", "Илья", "Никитин", "79969753180", "ilya.nikitin@example.com", "@ilya_n", "2861"),
    ("customer05", "Вера", "Лебедева", "79962197403", "vera.lebedeva@example.com", "@vera_l", "9047"),
    ("customer06", "Артем", "Громов", "79965478012", "artem.gromov@example.com", "@art_grom", "3720"),
    ("customer07", "Ксения", "Орлова", "79963214598", "ksenia.orlova@example.com", "@ksenia_o", "6158"),
    ("customer08", "Роман", "Егоров", "79967520844", "roman.egorov@example.com", "@roman_e", "4306"),
    ("customer09", "Полина", "Федорова", "79968931472", "polina.fedorova@example.com", "@polina_f", "8523"),
    ("customer10", "Максим", "Волков", "79964490267", "", "@max_volkov", "1975"),
]


CATEGORIES = {
    "city": ("Городские", "Комфортные велосипеды для прогулок, коротких поездок и спокойного ритма."),
    "sport": ("Спортивные", "Легкие велосипеды для быстрых маршрутов и активного катания."),
    "mountain": ("Горные", "Модели с надежной рамой и амортизацией для пересеченной местности."),
    "electric": ("Электровелосипеды", "Велосипеды с мотором для длинных поездок без лишней усталости."),
}


TARIFFS = {
    "city": ("Городской", Decimal("260.00"), Decimal("1500.00"), Decimal("3000.00"), Decimal("350.00")),
    "sport": ("Спорт", Decimal("340.00"), Decimal("2100.00"), Decimal("4000.00"), Decimal("450.00")),
    "mountain": ("Трейл", Decimal("380.00"), Decimal("2400.00"), Decimal("4500.00"), Decimal("500.00")),
    "electric": ("Электро", Decimal("520.00"), Decimal("3300.00"), Decimal("7000.00"), Decimal("650.00")),
}


BIKES = [
    {
        "title": "Городской Бриз",
        "slug": "gorodskoy-briz",
        "category": "city",
        "serial": "VR-CITY-1021",
        "frame": "M",
        "wheel": "28",
        "color": "Графитовый",
        "accent": "#7fb3ff",
        "description": "Удобный городской велосипед с прямой посадкой, мягким ходом и багажником для повседневных маршрутов.",
    },
    {
        "title": "Парковый Навигатор",
        "slug": "parkovyy-navigator",
        "category": "city",
        "serial": "VR-CITY-1048",
        "frame": "L",
        "wheel": "28",
        "color": "Оливковый",
        "accent": "#8fcf9f",
        "description": "Практичная модель для прогулок по набережной и поездок по городу, хорошо держит темп на ровном асфальте.",
    },
    {
        "title": "Быстрый Маршрут",
        "slug": "bystryy-marshrut",
        "category": "sport",
        "serial": "VR-SPORT-2114",
        "frame": "M",
        "wheel": "28",
        "color": "Серебристый",
        "accent": "#c7d2fe",
        "description": "Быстрый гибрид для тех, кто хочет ехать бодрее: легкая рама, уверенное торможение и спортивная посадка.",
    },
    {
        "title": "Легкий Темп",
        "slug": "legkiy-temp",
        "category": "sport",
        "serial": "VR-SPORT-2190",
        "frame": "L",
        "wheel": "28",
        "color": "Темно-синий",
        "accent": "#60a5fa",
        "description": "Легкий велосипед для длинных городских маршрутов, тренировок выходного дня и поездок без лишней усталости.",
    },
    {
        "title": "Лесная Тропа",
        "slug": "lesnaya-tropa",
        "category": "mountain",
        "serial": "VR-MTB-3306",
        "frame": "M",
        "wheel": "29",
        "color": "Песочный",
        "accent": "#fbbf24",
        "description": "Горный велосипед с амортизационной вилкой для парков, грунтовых дорожек и маршрутов за городом.",
    },
    {
        "title": "Горный Рубеж",
        "slug": "gornyy-rubezh",
        "category": "mountain",
        "serial": "VR-MTB-3342",
        "frame": "L",
        "wheel": "29",
        "color": "Бордовый",
        "accent": "#fb7185",
        "description": "Надежная модель для активного катания: широкие покрышки, цепкое сцепление и уверенность на неровностях.",
    },
    {
        "title": "Компактный Луч",
        "slug": "kompaktnyy-luch",
        "category": "city",
        "serial": "VR-CITY-1175",
        "frame": "S",
        "wheel": "26",
        "color": "Белый",
        "accent": "#f8fafc",
        "description": "Компактный велосипед для невысоких райдеров и спокойных прогулок, легко управляется в плотном потоке.",
    },
    {
        "title": "Мятный Круизер",
        "slug": "myatnyy-kruizer",
        "category": "city",
        "serial": "VR-CITY-1220",
        "frame": "M",
        "wheel": "27.5",
        "color": "Мятный",
        "accent": "#5eead4",
        "description": "Стильный прогулочный велосипед с комфортной посадкой, широким рулем и плавным ходом.",
    },
    {
        "title": "Электро Драйв",
        "slug": "elektro-drayv",
        "category": "electric",
        "serial": "VR-ECO-4401",
        "frame": "M",
        "wheel": "27.5",
        "color": "Черный",
        "accent": "#a78bfa",
        "description": "Электровелосипед для длинных поездок и маршрутов с подъемами, запас хода рассчитан на активный день.",
    },
    {
        "title": "Электро Комфорт",
        "slug": "elektro-komfort",
        "category": "electric",
        "serial": "VR-ECO-4477",
        "frame": "L",
        "wheel": "28",
        "color": "Стальной",
        "accent": "#93c5fd",
        "description": "Комфортный электровелосипед с уверенной посадкой, хорош для длительной аренды и спокойных поездок по городу.",
    },
]


DEMO_BOOKING_NUMBERS = [
    "VR-9001",
    "VR-9002",
    "VR-9003",
    "VR-9004",
    "VR-9005",
    "VR-9006",
    "VR-9007",
    "VR-9008",
]


def build_bike_svg(title, color, accent):
    title = escape(title)
    color = escape(color)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900" role="img" aria-label="{title}">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#172033"/>
      <stop offset="0.55" stop-color="#24324c"/>
      <stop offset="1" stop-color="#0f1724"/>
    </linearGradient>
    <radialGradient id="glow" cx="62%" cy="28%" r="58%">
      <stop offset="0" stop-color="{accent}" stop-opacity="0.45"/>
      <stop offset="1" stop-color="{accent}" stop-opacity="0"/>
    </radialGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#020617" flood-opacity="0.45"/>
    </filter>
  </defs>
  <rect width="1200" height="900" rx="42" fill="url(#bg)"/>
  <rect width="1200" height="900" rx="42" fill="url(#glow)"/>
  <path d="M86 710 C250 620 420 665 575 598 C730 530 900 575 1118 450 L1118 900 L86 900 Z" fill="#0b1220" opacity="0.68"/>
  <g filter="url(#shadow)" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="360" cy="612" r="132" fill="none" stroke="#dbeafe" stroke-width="22" opacity="0.92"/>
    <circle cx="842" cy="612" r="132" fill="none" stroke="#dbeafe" stroke-width="22" opacity="0.92"/>
    <circle cx="360" cy="612" r="16" fill="{accent}"/>
    <circle cx="842" cy="612" r="16" fill="{accent}"/>
    <path d="M360 612 L520 412 L650 612 Z" fill="none" stroke="{accent}" stroke-width="34"/>
    <path d="M520 412 L720 412 L842 612" fill="none" stroke="{accent}" stroke-width="34"/>
    <path d="M650 612 L720 412" fill="none" stroke="{accent}" stroke-width="34"/>
    <path d="M500 382 H605" stroke="#f8fafc" stroke-width="28"/>
    <path d="M720 412 L755 320" stroke="#f8fafc" stroke-width="28"/>
    <path d="M742 318 H840" stroke="#f8fafc" stroke-width="24"/>
    <path d="M520 412 L480 330 H430" stroke="#f8fafc" stroke-width="24"/>
    <path d="M410 330 H520" stroke="#f8fafc" stroke-width="22"/>
  </g>
  <text x="74" y="104" fill="#f8fafc" font-family="Arial, sans-serif" font-size="54" font-weight="700">{title}</text>
  <text x="78" y="158" fill="#bfdbfe" font-family="Arial, sans-serif" font-size="28">ВелоРент / {color}</text>
  <rect x="78" y="198" width="154" height="8" rx="4" fill="{accent}"/>
</svg>
"""


def create_demo_booking(number, customer, bike, location, start_at, end_at, status, operator):
    quoted_price, deposit_amount = calculate_booking_quote(start_at, end_at, bike.tariff, customer=customer)
    booking = Booking.objects.create(
        number=number,
        customer=customer,
        bike=bike,
        pickup_location=location,
        tariff=bike.tariff,
        start_at=start_at,
        end_at=end_at,
        quoted_price=quoted_price,
        deposit_amount=deposit_amount,
        status=status,
    )

    rental_status = Rental.Status.READY
    rental_kwargs = {}

    if status == Booking.Status.ACTIVE:
        rental_status = Rental.Status.ACTIVE
        rental_kwargs = {
            "issued_by": operator,
            "actual_start_at": start_at,
            "start_condition": "Велосипед выдан в исправном состоянии.",
        }
        bike.status = Bike.Status.IN_RENT
    elif status == Booking.Status.COMPLETED:
        rental_status = Rental.Status.COMPLETED
        final_price = quoted_price
        if number == "VR-9006":
            final_price += bike.tariff.late_fee_per_hour
        rental_kwargs = {
            "issued_by": operator,
            "received_by": operator,
            "actual_start_at": start_at,
            "actual_end_at": end_at,
            "start_condition": "Велосипед выдан без замечаний.",
            "end_condition": "Велосипед возвращен, состояние проверено.",
            "late_fee": bike.tariff.late_fee_per_hour if number == "VR-9006" else Decimal("0.00"),
            "final_price": final_price,
        }
        bike.status = Bike.Status.AVAILABLE
    elif status == Booking.Status.CONFIRMED:
        bike.status = Bike.Status.RESERVED
    elif status in {Booking.Status.CANCELLED, Booking.Status.EXPIRED}:
        rental_status = Rental.Status.CANCELLED
        bike.status = Bike.Status.AVAILABLE
    else:
        bike.status = Bike.Status.AVAILABLE

    bike.save(update_fields=["status"])
    rental = Rental.objects.create(booking=booking, status=rental_status, **rental_kwargs)

    if status == Booking.Status.ACTIVE:
        Payment.objects.create(
            booking=booking,
            amount=deposit_amount,
            kind=Payment.Kind.DEPOSIT,
            method=Payment.Method.CARD,
            status=Payment.Status.PAID,
            external_id=f"demo-{number}-deposit",
        )

    if status == Booking.Status.COMPLETED:
        Payment.objects.create(
            booking=booking,
            amount=deposit_amount,
            kind=Payment.Kind.DEPOSIT,
            method=Payment.Method.CARD,
            status=Payment.Status.PAID,
            external_id=f"demo-{number}-deposit",
        )
        Payment.objects.create(
            booking=booking,
            amount=rental.final_price,
            kind=Payment.Kind.RENTAL,
            method=Payment.Method.CARD,
            status=Payment.Status.PENDING if number == "VR-9006" else Payment.Status.PAID,
            external_id=f"demo-{number}-rental",
        )
        if number != "VR-9006":
            Payment.objects.create(
                booking=booking,
                amount=deposit_amount,
                kind=Payment.Kind.REFUND,
                method=Payment.Method.CARD,
                status=Payment.Status.PAID,
                external_id=f"demo-{number}-refund",
            )

    return booking


class Command(BaseCommand):
    help = "Создает презентационное наполнение ВелоРент: клиентов, велосипеды, брони, аренды и платежи."

    def handle(self, *args, **options):
        operator, _ = User.objects.update_or_create(
            username="operator",
            defaults={
                "role": User.Role.OPERATOR,
                "email": "operator@velorent.local",
                "first_name": "Елена",
                "last_name": "Смирнова",
                "phone": "79960000001",
                "is_staff": True,
            },
        )
        operator.set_password("operator123")
        operator.save()

        now = timezone.now()
        for username, first_name, last_name, phone, email, telegram, document_last4 in CUSTOMERS:
            is_verified = username != "customer04"
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "role": User.Role.CUSTOMER,
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": phone,
                    "email": email,
                    "telegram": telegram,
                    "terms_accepted": True,
                    "terms_accepted_at": now,
                    "personal_data_consent": True,
                    "personal_data_consent_at": now,
                    "document_verified": is_verified,
                    "document_type": User.DocumentType.PASSPORT if is_verified else "",
                    "document_last4": document_last4 if is_verified else "",
                    "document_verified_at": now if is_verified else None,
                    "document_verified_by": operator if is_verified else None,
                },
            )
            user.set_password(CUSTOMER_PASSWORD)
            user.save()

        park_location, _ = PickupLocation.objects.update_or_create(
            name="ВелоРент - парк",
            defaults={
                "address": "Чита, парк ОДОРА, главный вход",
                "phone": "+7 996 000-20-20",
                "opening_hours": "10:00-22:00",
                "map_url": "https://yandex.ru/maps/?text=%D0%A7%D0%B8%D1%82%D0%B0%2C%20%D0%BF%D0%B0%D1%80%D0%BA%20%D0%9E%D0%94%D0%9E%D0%A0%D0%90%2C%20%D0%B3%D0%BB%D0%B0%D0%B2%D0%BD%D1%8B%D0%B9%20%D0%B2%D1%85%D0%BE%D0%B4",
                "is_active": True,
            },
        )

        categories = {}
        for key, (name, description) in CATEGORIES.items():
            categories[key], _ = BikeCategory.objects.update_or_create(
                name=name,
                defaults={"description": description},
            )

        tariffs = {}
        for key, (name, hourly_rate, daily_rate, deposit_amount, late_fee_per_hour) in TARIFFS.items():
            tariffs[key], _ = Tariff.objects.update_or_create(
                name=name,
                defaults={
                    "hourly_rate": hourly_rate,
                    "daily_rate": daily_rate,
                    "deposit_amount": deposit_amount,
                    "late_fee_per_hour": late_fee_per_hour,
                    "is_active": True,
                },
            )

        image_dir = settings.MEDIA_ROOT / "bikes"
        image_dir.mkdir(parents=True, exist_ok=True)
        real_photo_names = [
            image_file.name
            for image_file in sorted(image_dir.iterdir())
            if image_file.is_file()
            and image_file.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        ]

        for index, item in enumerate(BIKES, start=1):
            image_name = f"{item['slug']}.svg"
            image_path = image_dir / image_name
            image_path.write_text(
                build_bike_svg(item["title"], item["color"], item["accent"]),
                encoding="utf-8",
            )
            existing_bike = Bike.objects.filter(serial_number=item["serial"]).first()
            photo_name = f"bikes/{image_name}"
            if real_photo_names:
                real_photo_name = real_photo_names[(index - 1) % len(real_photo_names)]
                photo_name = f"bikes/{real_photo_name}"
            if existing_bike and existing_bike.photo:
                current_photo = existing_bike.photo.name
                if not current_photo.lower().endswith(".svg"):
                    photo_name = current_photo

            Bike.objects.update_or_create(
                serial_number=item["serial"],
                defaults={
                    "title": item["title"],
                    "slug": item["slug"],
                    "category": categories[item["category"]],
                    "tariff": tariffs[item["category"]],
                    "current_location": park_location,
                    "frame_size": item["frame"],
                    "wheel_size": item["wheel"],
                    "color": item["color"],
                    "status": Bike.Status.AVAILABLE,
                    "condition_notes": "ТО пройдено, велосипед готов к выдаче.",
                    "photo": photo_name,
                    "description": item["description"],
                },
            )

        Bike.objects.update(current_location=park_location)
        Booking.objects.update(pickup_location=park_location)
        Booking.objects.filter(number__in=DEMO_BOOKING_NUMBERS).delete()
        Bike.objects.filter(serial_number__in=[item["serial"] for item in BIKES]).update(status=Bike.Status.AVAILABLE)

        bikes_by_slug = {bike.slug: bike for bike in Bike.objects.filter(slug__in=[item["slug"] for item in BIKES])}
        users_by_username = {
            user.username: user
            for user in User.objects.filter(username__in=[customer[0] for customer in CUSTOMERS])
        }

        demo_specs = [
            (
                "VR-9001",
                "customer10",
                "gorodskoy-briz",
                now + timedelta(hours=2),
                now + timedelta(hours=4),
                Booking.Status.PENDING,
            ),
            (
                "VR-9002",
                "customer04",
                "parkovyy-navigator",
                now + timedelta(hours=1),
                now + timedelta(hours=5),
                Booking.Status.CONFIRMED,
            ),
            (
                "VR-9003",
                "customer02",
                "bystryy-marshrut",
                now - timedelta(hours=1),
                now + timedelta(hours=3),
                Booking.Status.ACTIVE,
            ),
            (
                "VR-9004",
                "customer03",
                "legkiy-temp",
                now - timedelta(hours=5),
                now - timedelta(hours=1),
                Booking.Status.ACTIVE,
            ),
            (
                "VR-9005",
                "customer05",
                "lesnaya-tropa",
                now - timedelta(days=2, hours=4),
                now - timedelta(days=2),
                Booking.Status.COMPLETED,
            ),
            (
                "VR-9006",
                "customer06",
                "gornyy-rubezh",
                now - timedelta(days=1, hours=5),
                now - timedelta(days=1, hours=1),
                Booking.Status.COMPLETED,
            ),
            (
                "VR-9007",
                "customer07",
                "kompaktnyy-luch",
                now - timedelta(hours=3),
                now - timedelta(hours=1),
                Booking.Status.EXPIRED,
            ),
            (
                "VR-9008",
                "customer08",
                "myatnyy-kruizer",
                now + timedelta(days=1, hours=1),
                now + timedelta(days=1, hours=4),
                Booking.Status.CONFIRMED,
            ),
        ]

        for number, username, bike_slug, start_at, end_at, status in demo_specs:
            create_demo_booking(
                number=number,
                customer=users_by_username[username],
                bike=bikes_by_slug[bike_slug],
                location=park_location,
                start_at=start_at,
                end_at=end_at,
                status=status,
                operator=operator,
            )

        service_bike = bikes_by_slug.get("elektro-komfort")
        if service_bike:
            service_bike.status = Bike.Status.SERVICE
            service_bike.condition_notes = "Плановая проверка тормозов перед выдачей."
            service_bike.save(update_fields=["status", "condition_notes"])

        demo_bikes = Bike.objects.filter(serial_number__startswith="DEMO-").order_by("serial_number")
        try:
            deleted_demo_bikes, _ = demo_bikes.delete()
        except ProtectedError:
            deleted_demo_bikes = 0
            for index, bike in enumerate(demo_bikes, start=1):
                bike.title = f"Архивный велосипед {index}"
                bike.slug = f"arkhivnyy-velosiped-{index}"
                bike.status = Bike.Status.RETIRED
                bike.description = "Архивная запись из старых броней, не используется в рабочем парке."
                bike.condition_notes = "Архивная запись, скрыта из рабочего списка оператора."
                bike.current_location = park_location
                bike.save(update_fields=[
                    "title",
                    "slug",
                    "status",
                    "description",
                    "condition_notes",
                    "current_location",
                ])

        unused_locations = PickupLocation.objects.exclude(pk=park_location.pk)
        try:
            deleted_locations, _ = unused_locations.delete()
        except ProtectedError:
            deleted_locations = 0
            unused_locations.update(is_active=False)

        self.stdout.write(self.style.SUCCESS(
            f"Готово: добавлено/обновлено {len(CUSTOMERS)} клиентов, {len(BIKES)} велосипедов "
            f"и {len(demo_specs)} демонстрационных броней. "
            f"Пароль клиентов: {CUSTOMER_PASSWORD}. Лишних точек выдачи удалено: {deleted_locations}. "
            f"Старых демо-велосипедов удалено: {deleted_demo_bikes}"
        ))
