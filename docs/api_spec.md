# API-спецификация

## Публичные и клиентские методы
### `GET /api/bikes/`
Список велосипедов.

### `GET /api/bikes/{slug}/`
Детальная карточка велосипеда.

### `GET /api/references/tariffs/`
Активные тарифы.

### `GET /api/references/pickup_locations/`
Список точек выдачи.

### `GET /api/bookings/`
Список бронирований текущего клиента.

### `POST /api/bookings/`
Создание брони.

Пример тела:
```json
{
  "bike": 1,
  "pickup_location": 1,
  "start_at": "2026-03-15T10:00:00+09:00",
  "end_at": "2026-03-15T14:00:00+09:00",
  "comment": "Нужен шлем"
}
```

## Методы оператора
### `GET /api/operator/dashboard/`
Операционные KPI.

### `POST /api/operator/{booking_id}/confirm/`
Подтверждение брони.

### `POST /api/operator/{booking_id}/issue/`
Выдача велосипеда.

### `POST /api/operator/{booking_id}/complete/`
Завершение аренды, прием возврата, фиксация итоговой оплаты и возврата залога.
