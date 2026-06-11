from django.conf import settings
from django.utils import timezone


def rental_contract_context(booking=None):
    if booking is None:
        return {
            "is_template": True,
            "contract_number": "[номер брони]",
            "contract_date": "[дата заключения]",
            "provider_name": settings.RENTAL_PROVIDER_NAME,
            "provider_details": settings.RENTAL_PROVIDER_DETAILS,
            "provider_inn": settings.RENTAL_PROVIDER_INN,
            "provider_ogrnip": settings.RENTAL_PROVIDER_OGRNIP,
            "provider_registration_details": settings.RENTAL_PROVIDER_REGISTRATION_DETAILS,
            "provider_address": settings.RENTAL_PROVIDER_ADDRESS,
            "provider_phone": settings.RENTAL_PROVIDER_PHONE,
            "provider_email": settings.RENTAL_PROVIDER_EMAIL,
            "privacy_email": settings.PERSONAL_DATA_EMAIL,
            "customer_name": "[фамилия, имя]",
            "customer_phone": "[телефон]",
            "customer_email": "[email при наличии]",
            "document_type": "[вид документа]",
            "document_last4": "[последние 4 цифры]",
            "bike_title": "[модель велосипеда]",
            "bike_serial_number": "[серийный номер]",
            "pickup_location": "[точка выдачи]",
            "pickup_address": "[адрес точки выдачи]",
            "pickup_phone": "[телефон точки выдачи]",
            "rental_start": "[дата и время выдачи]",
            "rental_end": "[плановая дата и время возврата]",
            "tariff_name": "[тариф]",
            "quoted_price": "[стоимость аренды]",
            "deposit_amount": "[сумма залога]",
            "operator_name": "[ФИО оператора]",
        }

    rental = getattr(booking, "rental", None)
    operator_name = (
        rental.issued_by.staff_display
        if rental and rental.issued_by
        else "Оператор ВелоРент"
    )
    return {
        "is_template": False,
        "contract_number": booking.number,
        "contract_date": timezone.localdate().strftime("%d.%m.%Y"),
        "provider_name": settings.RENTAL_PROVIDER_NAME,
        "provider_details": settings.RENTAL_PROVIDER_DETAILS,
        "provider_inn": settings.RENTAL_PROVIDER_INN,
        "provider_ogrnip": settings.RENTAL_PROVIDER_OGRNIP,
        "provider_registration_details": settings.RENTAL_PROVIDER_REGISTRATION_DETAILS,
        "provider_address": settings.RENTAL_PROVIDER_ADDRESS,
        "provider_phone": settings.RENTAL_PROVIDER_PHONE,
        "provider_email": settings.RENTAL_PROVIDER_EMAIL,
        "privacy_email": settings.PERSONAL_DATA_EMAIL,
        "customer_name": booking.customer.get_full_name().strip(),
        "customer_phone": booking.customer.phone or "-",
        "customer_email": booking.customer.email or "-",
        "document_type": booking.customer.get_document_type_display(),
        "document_last4": booking.customer.document_last4,
        "bike_title": booking.bike.title,
        "bike_serial_number": booking.bike.serial_number,
        "pickup_location": booking.pickup_location.name,
        "pickup_address": booking.pickup_location.address,
        "pickup_phone": booking.pickup_location.phone or "-",
        "rental_start": timezone.localtime(booking.start_at).strftime("%d.%m.%Y %H:%M"),
        "rental_end": timezone.localtime(booking.end_at).strftime("%d.%m.%Y %H:%M"),
        "tariff_name": booking.tariff.name,
        "quoted_price": booking.quoted_price,
        "deposit_amount": booking.deposit_amount,
        "operator_name": operator_name,
    }
