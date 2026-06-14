# Теоретическая часть: Broker-Independent Abstraction Layer и схема БД

## 1. Broker-Independent Abstraction Layer (независимый от брокера слой абстракции)

Слой абстракции обеспечивает унифицированный доступ к рыночным данным и торговым операциям, скрывая детали реализации конкретного брокера (T-Bank Invest API, другие). Это позволяет легко заменять брокера или добавлять новых без изменения основной логики анализа и стратегий.

### 1.1 Интерфейс `BrokerAdapter`

Интерфейс определяет контракт, который должен реализовать каждый адаптер для конкретного брокера.

**Методы:**

- **`get_candles(symbol: str, interval: str, start_date: datetime, end_date: datetime) -> List[Candle]`**  
  Получение исторических свечей по инструменту за указанный период.
  - *Параметры*: символ (тикер), интервал (1min, 5min, hour, day и т.д.), начальная и конечная дата.
  - *Возвращает*: список моделей `Candle`.

- **`place_order(order_data: OrderRequest) -> OrderResult`**  
  Размещение торгового ордера (покупка/продажа).
  - *Параметры*: структура `OrderRequest` содержит символ, сторону (buy/sell), количество, тип ордера (market/limit), цену (опционально).
  - *Возвращает*: структуру `OrderResult` с идентификатором ордера, статусом, исполненной ценой и т.д.

- **`get_portfolio(account_id: str) -> Portfolio`**  
  Получение текущего портфеля клиента.
  - *Параметры*: идентификатор счета (опционально).
  - *Возвращает*: структуру `Portfolio` со списком позиций (актив, количество, средняя цена, текущая стоимость и пр.).

### 1.2 Общая модель `Candle`

Модель свечи, используемая во всей системе (как для получения от брокера, так и для передачи в модули анализа).

| Поле         | Тип          | Описание                                   |
|--------------|--------------|--------------------------------------------|
| `symbol`     | str          | Тикер инструмента (например, AAPL)         |
| `timestamp`  | datetime     | Время начала свечи (UTC)                   |
| `interval`   | str          | Интервал свечи (1m, 5m, 1h, 1d)           |
| `open`       | float        | Цена открытия                              |
| `high`       | float        | Максимальная цена за период                |
| `low`        | float        | Минимальная цена за период                 |
| `close`      | float        | Цена закрытия                              |
| `volume`     | int/float    | Объем торгов (количество акций/контрактов) |

Дополнительно может включаться поле `adjusted_close` для учета корпоративных действий (сплиты, дивиденды). Модель должна быть сериализуема в JSON и совместима с Pandas DataFrame для анализа.

### 1.3 API Contracts reviewed with Data Loader

Контракты API между `BrokerAdapter` и модулем `Data Loader` (отвечающим за загрузку данных в систему) должны быть проверены и утверждены. Основные требования:

- **Форматы данных**: все обмены происходят через строго типизированные модели (Pydantic или dataclasses).  
- **Обработка ошибок**: стандартизированные исключения (например, `RateLimitError`, `InvalidSymbolError`).  
- **Асинхронность**: методы адаптера предполагают асинхронные вызовы (async/await) для эффективной работы с сетевыми запросами.  
- **Пагинация**: методы, возвращающие списки (особенно `get_candles`), поддерживают пагинацию через параметры `limit` и `offset` или курсоры.  
- **Кэширование**: на уровне Data Loader допускается кэширование свечей для снижения нагрузки на API брокера. Контракт фиксирует, что адаптер не отвечает за кэш, а только за вычитку «сырых» данных.

Согласование считается завершённым после успешного выполнения набора интеграционных тестов с мок-адаптером и тестовым брокером.

---

## 2. Схема базы данных (Entity Relationship Diagram)

Проект требует хранения исторических данных, результатов анализа стратегий, портфеля и ордеров. Ниже представлена реляционная схема (SQLite/PostgreSQL) с сущностями и связями.

### 2.1 Сущности и атрибуты

| Сущность          | Атрибуты (поле, тип, описание)                                                                 | Связи                                                                 |
|-------------------|-----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| **Stock**         | `id` SERIAL PK<br>`symbol` VARCHAR(20) UNIQUE NOT NULL<br>`name` VARCHAR(200)<br>`exchange` VARCHAR(50)<br>`currency` VARCHAR(3) | 1 : N → Candle<br>1 : N → Position<br>1 : N → StrategyResult          |
| **Candle**        | `id` SERIAL PK<br>`stock_id` INT FK → Stock.id<br>`timestamp` TIMESTAMP<br>`interval` VARCHAR(10)<br>`open` DECIMAL(12,4)<br>`high` DECIMAL(12,4)<br>`low` DECIMAL(12,4)<br>`close` DECIMAL(12,4)<br>`volume` BIGINT<br>UNIQUE(stock_id, interval, timestamp) | N : 1 → Stock                                                         |
| **Strategy**      | `id` SERIAL PK<br>`name` VARCHAR(100) UNIQUE NOT NULL<br>`description` TEXT<br>`parameters` JSON (гиперпараметры стратегии)<br>`created_at` TIMESTAMP | 1 : N → StrategyResult                                                |
| **StrategyResult**| `id` SERIAL PK<br>`stock_id` INT FK → Stock.id<br>`strategy_id` INT FK → Strategy.id<br>`analysis_date` DATE<br>`rank` INT (1-10)<br>`score` DECIMAL(10,4) (оценка пригодности)<br>`expected_return` DECIMAL(10,4)<br>`confidence` DECIMAL(5,4)<br>`details` JSON (доп. метрики) | N : 1 → Stock<br>N : 1 → Strategy                                     |
| **Position**      | `id` SERIAL PK<br>`stock_id` INT FK → Stock.id<br>`quantity` DECIMAL(18,8)<br>`avg_price` DECIMAL(12,4)<br>`current_price` DECIMAL(12,4) (может быть computed)<br>`updated_at` TIMESTAMP | N : 1 → Stock                                                         |
| **Order**         | `id` SERIAL PK<br>`broker_order_id` VARCHAR(100) (идентификатор у брокера)<br>`stock_id` INT FK → Stock.id<br>`side` VARCHAR(4) (buy/sell)<br>`quantity` DECIMAL(18,8)<br>`price` DECIMAL(12,4) (для лимитных ордеров)<br>`type` VARCHAR(10) (market/limit)<br>`status` VARCHAR(20) (pending, filled, cancelled)<br>`placed_at` TIMESTAMP<br>`executed_at` TIMESTAMP NULL<br>`executed_price` DECIMAL(12,4) NULL | N : 1 → Stock                                                         |
| **SelectionRun**  | `id` SERIAL PK<br>`run_date` TIMESTAMP<br>`top_count` INT (10)<br>`method` VARCHAR(50) (способ отбора лучших стратегий) | 1 : N → SelectionResult                                               |
| **SelectionResult**| `id` SERIAL PK<br>`run_id` INT FK → SelectionRun.id<br>`strategy_id` INT FK → Strategy.id<br>`stock_id` INT FK → Stock.id<br>`rank_in_run` INT (позиция в топ-10) | N : 1 → SelectionRun<br>N : 1 → Strategy<br>N : 1 → Stock            |

### 2.2 ER-диаграмма (текстовое описание)

```text
┌─────────────┐       ┌─────────────┐
│   Stock     │       │  Strategy   │
│─────────────│       │─────────────│
│ id (PK)     │◄──┐   │ id (PK)     │
│ symbol      │   │   │ name        │
│ name        │   │   │ ...         │
└─────────────┘   │   └─────────────┘
       │          │          │
       │          │          │
       ▼          │          ▼
┌─────────────┐   │   ┌─────────────────┐
│   Candle    │   │   │ StrategyResult  │
│─────────────│   │   │─────────────────│
│ id (PK)     │   │   │ id (PK)         │
│ stock_id(FK)│   │   │ stock_id (FK)   │
│ timestamp   │   │   │ strategy_id(FK) │
│ ...         │   │   │ rank, score,... │
└─────────────┘   │   └─────────────────┘
                  │
┌─────────────┐   │   ┌─────────────┐
│  Position   │   │   │   Order     │
│─────────────│   │   │─────────────│
│ id (PK)     │   │   │ id (PK)     │
│ stock_id(FK)│   │   │ stock_id(FK)│
│ quantity    │   │   │ side, price │
│ ...         │   │   │ ...         │
└─────────────┘   │   └─────────────┘
                  │
                  │   ┌─────────────────┐
                  └──►│ SelectionResult │
                      │─────────────────│
                      │ id (PK)         │
                      │ run_id (FK)     │
                      │ strategy_id(FK) │
                      │ stock_id (FK)   │
                      └─────────────────┘
                            │
                            │
                      ┌─────▼──────┐
                      │SelectionRun│
                      │────────────│
                      │ id (PK)    │
                      │ run_date   │
                      └────────────┘