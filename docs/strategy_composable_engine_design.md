# Composable Strategy Engine — Design Document

**Status:** Implemented (Week 5, PR #127; constraints/trailing/time filters in PR #142) — architecture reference  
**Last updated:** July 14, 2026  
**Implementation:** `src/strategy/composable/`, `config/strategies/*.yaml`  
**Related:** `strategy_module_architecture.md`, `transcriptions/29-06-26-customer.txt`

---

## Table of Contents

1. [English](#1-english)
2. [Русский](#2-русский)

---

# 1. English

## 1.1 Problem

Strategies must be defined in **config files**, not as new Python classes per idea.  
**Input:** period-end price + timestamp `(t, price)` only — no open/high/low/volume.  
**Output:** trade log and performance metrics from the backtester.

Today each strategy (`ma_crossover`, `rsi_threshold`, `ma_rsi`) is a separate Python class with duplicated indicator code. Adding a new combination (e.g. RSI + another moving average) requires a developer — not a flexible workflow for strategy authors.

## 1.2 Key Concepts

Terms used throughout this document. Trading terms (RSI, SMA, stop loss) are assumed known.

### Bar (period)

One row of input data. Each bar has:

- **timestamp** — when the period closed;
- **price** — closing price of the period.

Example (1-minute bars):

```
10:00 → 100
10:01 → 101
10:02 → 99
```

The engine walks through bars **one by one**, in time order, simulating how a strategy would behave in real time.

### Series

A **Series** is a sequence of values — one value per bar. It stores a number (or true/false) for each point on the timeline, so internally it is an array (`float[]` or `bool[]`).

Examples:

```
price = [100, 101, 99]
sma20 = [100, 100.3, 100.1]
rsi14 = [55, 58, 52]
```

Series can be built from raw **price**, or from other Series (e.g. MACD from two EMAs). That dependency graph is a **DAG** (see below).

### Predicate

A **Predicate** is a condition that returns `true` or `false` for the **current** bar.

Examples in plain language:

- RSI > 70
- fast EMA crossed above slow EMA
- position is open and loss exceeds 5%

Predicates are combined inside **Rules**. Complex logic (AND / OR) needs no new code — only config.

### Rule

A **Rule** is: **WHEN** condition **THEN** action.

```
WHEN  fast_ma crosses above slow_ma AND rsi >= 50
THEN  buy
```

Rules also have **scope** (when the rule is allowed to run) and **priority** (order of checking). See §1.4.

### Action

An **Action** is what the engine **does** when a rule fires: open or close a position, adjust a stop, wait, etc.

Examples: `buy`, `sell`, `set_stop_loss`, `move_stop`, `sell_partial`, `wait`.

### Context

**Context** is a snapshot of everything the engine knows **at the current bar**: price, time, portfolio (cash, position, average entry, P&L), strategy state (bars in trade, counters), and all precomputed Series.

Predicates read Context to decide true/false. Without Context, conditions like "drawdown > 5%" or "last hour of session" are impossible.

### DAG (Series dependency graph)

Series can depend on each other:

```
price
  ├── EMA12 ──┐
  └── EMA26 ──┴── MACD ── signal line
```

**DAG** = Directed Acyclic Graph: dependencies flow one way, no cycles. The engine uses it to compute indicators in the correct order before the simulation starts.

### PositionEffect (engine-internal)

When you set stop loss / take profit on entry, the engine stores an internal **PositionEffect** on the open position — an automatic check each bar ("exit if price moved against us by X%").

Strategy authors work with **Actions** only; PositionEffect is an optimization inside the engine, not something you configure as a separate entity.

---

## 1.3 Solution

One **declarative rule engine**: a single class `ComposableStrategy` reads YAML/JSON and runs the pipeline below. No visual node editor.

**Compile** — once per strategy load: validate config, resolve `${params}`, build the Series DAG, turn `when` blocks into executable predicates, sort rules by priority.

**Precompute** — before the bar loop: calculate every Series for the **entire** price history once; all rules reuse these arrays (important for speed, especially parameter optimization).

```
Input (timestamp, price)[]
            │
            ▼
     Series (DAG)          ← precompute once
            │
            ▼
 Predicates (Context)      ← per bar
            │
            ▼
         Rules              ← scope + priority
            │
            ▼
        Actions
            │
            ▼
   Execution Engine        ← PositionEffect fast-path + orders
            │
            ▼
       Portfolio / metrics
```

Reuses existing pieces where possible: `BaseStrategy`, strategy registry, `ParameterSpec`, and the engine's bar-by-bar loop.

## 1.4 Pipeline

Every strategy follows the same path: **compute indicators → evaluate conditions → run actions**.

In config, authors still say "indicator" and "trigger"; the engine implements them as **Series** and **Predicates**.

| Layer | Role |
|---|---|
| **Series (DAG)** | Named arrays over the timeline. Each bar gets one value. Nodes depend on `price` or other series; engine topologically sorts, then **precomputes** all values before the simulation. |
| **Predicates** | True/false at bar index `i`, using **Context** (not price alone). |
| **Rules** | `{ id, scope, priority, when, then }`. Engine checks eligible rules in **priority** order; **first match wins** for that bar. |
| **Actions** | Executed from `then`: trades, stops, partial exits, etc. |

### Scope

Controls **when a rule is even considered**:

| scope | Meaning |
|---|---|
| `flat` | No open position — typical for entry rules |
| `long` | Long position is open — typical for exits and stop management |
| `always` | Every bar — e.g. session filters, global disables |

### Priority

Rules with the **same** scope are sorted by `priority` (**higher number = checked first**):

```
100  →  stop loss (must fire before signal exit)
 90  →  take profit
 10  →  signal-based exit
 10  →  entry (flat scope — separate from long rules)
```

If two rules could both match, the higher priority runs first; lower rules are skipped for that bar.

### Series DAG (config)

```yaml
series:
  ema12:  { fn: ema,  source: price, period: 12 }
  ema26:  { fn: ema,  source: price, period: 26 }
  macd:   { fn: diff, a: ema12, b: ema26 }
  rsi14:  { fn: rsi,  source: price, period: 14 }
```

Generic ops (`diff`, `shift`, `highest`) let you combine series without a new indicator plugin. Indicators that need high/low/volume (e.g. classic ATR) stay unavailable until the input model grows.

### Predicates & Context

**Context** holds the full state visible to predicates at bar `i`:

| Field | Used for |
|---|---|
| `price`, `timestamp`, `index` | price levels, time-of-day, weekday |
| `portfolio` | in/out of market, size, avg entry, profit/loss % |
| `strategy_state` | bars since entry, last action, trade counts |
| precomputed `series` | RSI, crosses, patterns |

Time conditions (`time_in_range`, `weekday_in`, `bars_since` an event) are **predicates** reading Context — not a separate "time source" layer.

### Actions & PositionEffect

Authors always write **Actions**. Examples:

```yaml
# shorthand on buy (P0) — engine creates PositionEffects internally
then:
  action: buy
  size: ${order_size}
  stop_loss_pct: ${stop_loss_pct}
  take_profit_pct: ${take_profit_pct}

# explicit actions (P1+) — same model, for dynamic stops
then:
  action: set_stop_loss
  value_pct: 0          # move stop to break-even

then:
  action: move_stop
  trailing_pct: 2
```

On each bar the engine: (1) checks **PositionEffects** in O(1); (2) evaluates **Rules**; (3) sends orders to **OrderExecutor**.

**Typed params** — each param has `type`, `default`, and usually **`choices`** (discrete allowed values). **`optimizable: true`** marks params included in grid search; params with `choices` but `optimizable: false` (e.g. `order_size`) are validated but not swept. Optional `min`/`max` only when free numeric input is allowed without a fixed `choices` list. See §1.7.

## 1.5 Types & Implementation

What already exists in the repo vs what we add.

### Exists today (`src/`)

| Type | Location | Notes |
|---|---|---|
| `BaseStrategy` | `strategy/base.py` | `on_candle(context) → Signal` — **keep** |
| `@register_strategy`, `create_strategy` | `strategy/registry.py` | add strategy id `"composable"` |
| `ParameterSpec`, `describe_strategy` | `strategy/schema.py` | typed params for UI / optimizer |
| `StrategyConfig`, loader, store | `strategy/config.py`, `loader.py`, `store.py` | load/save strategy files |
| `ExecutionEngine`, `OrderExecutor` | `engine/` | bar loop; buy/sell/hold today |
| `ExecutionContext` | `engine/context.py` | candle + portfolio (will feed composable layer) |
| `Portfolio` | `engine/portfolio.py` | cash, position size, average entry |
| `Signal`, `Candle`, `Trade` | `engine/models.py` | `Signal` = type + size only for now |
| Legacy strategies | `strategy/strategies/*.py` | remain as presets until YAML migration |

### New (composable module)

| Type | Responsibility |
|---|---|
| `StrategyDefinition` | Parsed YAML: `params`, `series`, `rules` |
| `CompiledStrategy` | Output of **compile**: resolved DAG, bound params, compiled predicates/rules |
| `SeriesNode` | One node in the DAG: `{ id, fn, inputs, params }` |
| `FloatSeries` / `BoolSeries` | `list[float]` / `list[bool]`, length = number of bars |
| `Predicate` | Function `(Context, bar_index) → bool` |
| `Rule` | `{ id, scope, priority, predicate, action }` |
| `Action` | Dataclass: `{ type, size?, stop_loss_pct?, … }` — not a bare string |
| `EvaluationContext` | Context for composable layer: prices, timestamps, series map, portfolio, `StrategyState` |
| `StrategyState` | Strategy-owned memory: bars in trade, event times, counters |
| `PositionEffect` | **Internal only**: `{ kind, value_pct }` attached to portfolio after certain actions |
| `ComposableStrategy(BaseStrategy)` | **compile** + **precompute** + rule evaluation in `on_candle` |
| `OptimizeSpec` | Per-param grid: params where `optimizable: true`, values from `choices` |
| `GridOptimizer` | Engine service: run backtests for all param combos, rank results |

### Registries

All extensible parts use a **registry**. To add a new indicator, condition, or action type, register one function — **the interpreter core does not change**.

```python
@register_series_fn("ema")
def ema(source: FloatSeries, period: int) -> FloatSeries: ...

@register_predicate("cross_above")
def cross_above(a: FloatSeries, b: FloatSeries, ctx: EvaluationContext, i: int) -> bool: ...

@register_action("sell_partial")
def sell_partial(ctx: EvaluationContext, action: Action) -> Signal: ...
```

### Engine changes (minimal)

1. Build **EvaluationContext** each bar from price history + portfolio + `StrategyState`.
2. Add **`Portfolio.effects: list[PositionEffect]`** — filled by `buy` / `set_stop_loss` / `move_stop`.
3. Bar loop order: check effects → call strategy → execute signal.
4. **P1+:** partial sizing in `OrderExecutor`; **P2:** short positions.
5. **`GridOptimizer`** — reads each strategy's `choices` + `optimizable` flags, runs backtests, returns ranked configs (see §1.7).

**Adapter:** engine still passes `Candle` objects today; composable layer uses `close` + `timestamp` until the API narrows to `(t, price)`.

## 1.6 Config Example (`ma_rsi`)

Full strategy equivalent to the current `ma_rsi` Python class:

```yaml
name: ma_rsi_composable
params:
  fast:           { type: int,   default: 10, choices: [5, 10, 12, 21, 30], optimizable: true }
  slow:           { type: int,   default: 30, choices: [20, 30, 50, 100, 200], optimizable: true }
  rsi_period:     { type: int,   default: 14, choices: [14, 20], optimizable: true }
  rsi_buy_min:    { type: float, default: 50, choices: [40, 50, 60], optimizable: true }
  rsi_overbought: { type: float, default: 70, choices: [65, 70, 80], optimizable: true }
  stop_loss_pct:  { type: float, default: 5,  choices: [3, 5, 7, 10], optimizable: true }
  take_profit_pct: { type: float, default: 10, choices: [5, 10, 15, 20], optimizable: true }
  order_size:     { type: float, default: 1,  choices: [1, 2, 3], optimizable: false }

series:
  fast_ma: { fn: sma, source: price, period: "${fast}" }
  slow_ma: { fn: sma, source: price, period: "${slow}" }
  rsi:     { fn: rsi, source: price, period: "${rsi_period}" }

rules:
  - id: stop_loss
    scope: long
    priority: 100
    when: { loss_pct: { gt: "${stop_loss_pct}" } }
    then: { action: sell, size: all }

  - id: take_profit
    scope: long
    priority: 90
    when: { profit_pct: { gt: "${take_profit_pct}" } }
    then: { action: sell, size: all }

  - id: signal_exit
    scope: long
    priority: 10
    when:
      any:
        - cross_below: [fast_ma, slow_ma]
        - gte: [rsi, "${rsi_overbought}"]
    then: { action: sell, size: all }

  - id: entry
    scope: flat
    priority: 10
    when:
      all:
        - cross_above: [fast_ma, slow_ma]
        - gte: [rsi, "${rsi_buy_min}"]
    then:
      action: buy
      size: "${order_size}"
      stop_loss_pct: "${stop_loss_pct}"
      take_profit_pct: "${take_profit_pct}"
```

**Shorter variant:** remove the `stop_loss` / `take_profit` rules and keep only `stop_loss_pct` / `take_profit_pct` on the `buy` action — same behaviour, less YAML.

## 1.7 Parameter Optimization (grid search)

**Customer goal:** the backtester finds good parameters **for each strategy** on an instrument. Search uses **discrete `choices` lists** (commonly used values), not brute-force min..max.

### UI note (customer scope)

The dashboard is a **visualizer only** — not a strategy builder. Strategies are authored in **YAML files** by developers; the UI lists registered strategies, shows metrics/charts/ranking, and lets the user pick param values from `choices` and run backtests. No node editor, no rule composer in the frontend.

### Split of responsibility

| Layer | Responsibility |
|---|---|
| **Strategy YAML** | Logic (`series`, `rules`) + `choices` / `optimizable` per param |
| **Engine (`GridOptimizer`)** | Cartesian product of optimizable params, filter invalid combos, rank, export JSON |
| **Dashboard** | Display results; optional read-only table of optimizer top configs |

Each strategy brings its own search space via `choices`. Engine does not hardcode MA periods.

### Config: `choices` + `optimizable`

One list serves **validation**, **UI dropdowns**, and **grid search**:

```yaml
params:
  fast: { type: int, default: 10, choices: [5, 10, 12, 21, 30], optimizable: true }
  slow: { type: int, default: 30, choices: preset:ma_long, optimizable: true }
  order_size: { type: float, default: 1, choices: [1, 2, 3], optimizable: false }
```

Shared presets in `config/param_presets.yaml`:

```yaml
ma_short:  [5, 10, 12, 21, 30, 50]
ma_long:   [20, 30, 50, 100, 200]
rsi_period: [7, 14, 20, 21]
stop_loss_pct: [3, 5, 7, 10]
take_profit_pct: [5, 10, 15, 20]
```

Legacy Python strategies: `ParameterSpec.choices` + new `optimizable` flag (default true when choices set).

When `choices` is set, value must be in the list — separate `min`/`max` not required.

### Constraints (avoid invalid combos)

Before running, filter combinations that violate strategy rules, e.g. `fast >= slow`, `rsi_buy_min >= rsi_overbought`. Invalid combos are skipped, not errors.

### Performance

Series **precompute** (§1.3) is keyed by param values that affect each series node — unchanged nodes are reused across grid runs where possible.

### Optimizer output

```json
{
  "strategy_id": "ma_rsi_composable",
  "instrument": "SBER",
  "ranked": [
    { "rank": 1, "params": { "fast": 12, "slow": 30, ... }, "metrics": { "total_pnl": ..., "sharpe_ratio": ... } }
  ]
}
```

Dashboard displays top-N; user picks a row → loads params into a single backtest run.

## 1.8 Extensibility

| Who | Task | Writes code? |
|---|---|---|
| **Strategy author** | Edit YAML: series, rules, choices | No |
| **Platform developer** | Add new series fn / predicate / action | One plugin file |

New strategy combination = new YAML file. New primitive (KAMA, head-and-shoulders pattern) = one registry entry.

## 1.9 MVP Phases

| Label | Meaning |
|---|---|
| **P0** | Minimum viable — current / next sprint week |
| **P1** | First extension |
| **P2** | Post-course |

| Phase | Deliverables |
|---|---|
| **P0** | ComposableStrategy, Series DAG, rules, actions + SL/TP on buy, ma_rsi YAML, engine integration |
| **P0** | **GridOptimizer**; `choices` + `optimizable` in YAML; ranked JSON |
| **P1** | Optimizer for legacy strategies; read-only optimizer results in dashboard |
| **P2** | Smarter search (random/Bayesian), cross-instrument batch |

## 1.10 Summary

Authors define strategies **and their parameter search grids** in config. Engine runs single backtests and **grid optimization** per strategy. Risk control uses Actions; PositionEffect is internal.

```text
Input (timestamp, price)
            │
            ▼
     Series (DAG)
            │
            ▼
 Predicates (Context) → Rules → Actions → Engine
            │
            ├─ single run (user params)
            └─ GridOptimizer (optimizable choices) → ranked configs
            │
            ▼
   Trades & metrics
```

---

# 2. Русский

## 2.1 Проблема

Стратегии должны задаваться **файлами конфигурации**, а не новым Python-классом на каждую идею.  
**Вход:** цена закрытия периода + timestamp `(t, price)` — без open/high/low/volume.  
**Выход:** журнал сделок и метрики бэктестера.

Сейчас каждая стратегия (`ma_crossover`, `rsi_threshold`, `ma_rsi`) — отдельный класс с дублированием индикаторов. Новая комбинация условий требует разработчика.

## 2.2 Основные понятия

Термины, которые используются далее. Базовые торговые термины (RSI, SMA, stop loss) предполагаются известными.

### Bar (период, бар)

Одна запись входных данных:

- **timestamp** — время закрытия периода;
- **price** — цена закрытия.

Пример (минутные бары):

```
10:00 → 100
10:01 → 101
10:02 → 99
```

Движок обрабатывает бары **последовательно**, имитируя работу стратегии во времени.

### Series (ряд, серия)

**Series** — последовательность значений, по одному на каждый bar. Поэтому внутри это массив (`float[]` или `bool[]`).

Примеры:

```
price = [100, 101, 99]
sma20 = [100, 100.3, 100.1]
rsi14 = [55, 58, 52]
```

Series строится от **price** или от других Series (MACD от двух EMA). Граф таких зависимостей — **DAG** (ниже).

### Predicate (предикат, условие)

**Predicate** — условие, которое для **текущего** бара возвращает `true` или `false`.

Примеры:

- RSI > 70
- быстрая EMA пересекла медленную снизу вверх
- позиция открыта и убыток больше 5%

Predicates объединяются в **Rules**. Сложная логика (AND / OR) — только конфиг, без нового кода.

### Rule (правило)

**Rule** — это **WHEN** условие **THEN** действие.

```
WHEN  fast_ma пересекла slow_ma снизу AND rsi >= 50
THEN  buy
```

У правила также есть **scope** (когда правило вообще рассматривается) и **priority** (порядок проверки). См. §2.4.

### Action (действие)

**Action** — что движок **делает**, когда правило сработало: открыть/закрыть позицию, сдвинуть стоп, подождать и т.д.

Примеры: `buy`, `sell`, `set_stop_loss`, `move_stop`, `sell_partial`, `wait`.

### Context (контекст)

**Context** — снимок всего, что движок знает **на текущем баре**: цена, время, портфель (cash, позиция, средняя цена входа, P&L), состояние стратегии (баров в сделке, счётчики), все заранее посчитанные Series.

Predicates читают Context. Без него нельзя выразить «просадка > 5%» или «последний час сессии».

### DAG (граф зависимостей Series)

Series могут зависеть друг от друга:

```
price
  ├── EMA12 ──┐
  └── EMA26 ──┴── MACD ── signal line
```

**DAG** (Directed Acyclic Graph) — направленный ациклический граф: зависимости идут в одну сторону, без циклов. Движок по нему определяет порядок расчёта индикаторов до начала симуляции.

### PositionEffect (внутри engine)

Когда на входе задают stop loss / take profit, движок сохраняет внутренний **PositionEffect** на открытой позиции — автоматическую проверку каждый bar («выйти, если цена ушла против нас на X%»).

Автор стратегии работает только с **Actions**; PositionEffect — оптимизация внутри engine, отдельно в YAML не настраивается.

---

## 2.3 Решение

Один **декларативный rule engine**: класс `ComposableStrategy` читает YAML/JSON и выполняет pipeline ниже. Без визуального редактора узлов.

**Compile (компиляция)** — один раз при загрузке: проверить конфиг, подставить `${params}`, построить DAG Series, скомпилировать predicates, отсортировать rules.

**Precompute (предрасчёт)** — перед циклом по барам: посчитать все Series на **всём** ряде цен один раз; все rules переиспользуют массивы (важно для скорости и оптимизатора параметров).

```
Input (timestamp, price)[]
            │
            ▼
     Series (DAG)          ← precompute один раз
            │
            ▼
 Predicates (Context)      ← на каждом баре
            │
            ▼
         Rules              ← scope + priority
            │
            ▼
        Actions
            │
            ▼
   Execution Engine        ← PositionEffect + ордера
            │
            ▼
   Портфель / метрики
```

Переиспользуем: `BaseStrategy`, registry, `ParameterSpec`, bar loop engine.

## 2.4 Pipeline

Любая стратегия проходит один путь: **посчитать индикаторы → проверить условия → выполнить действия**.

В конфиге автор говорит «индикатор» и «триггер»; движок реализует их как **Series** и **Predicates**.

| Слой | Роль |
|---|---|
| **Series (DAG)** | Именованные массивы по timeline. На каждый bar — одно значение. Зависимости от `price` или друг от друга; engine сортирует DAG и **precompute** до симуляции. |
| **Predicates** | true/false на баре `i` через **Context**. |
| **Rules** | `{ id, scope, priority, when, then }`. Проверка по **priority**; **первое сработавшее** в своём scope побеждает. |
| **Actions** | Исполнение из `then`: сделки, стопы, частичные выходы. |

### Scope

Когда правило **допускается** к проверке:

| scope | Смысл |
|---|---|
| `flat` | Нет открытой позиции — обычно вход |
| `long` | Открыта long-позиция — выходы и стопы |
| `always` | Каждый bar — фильтры сессии, глобальные отключения |

### Priority

Правила с одним **scope** сортируются по `priority` (**большее число = проверяется раньше**):

```
100  →  stop loss
 90  →  take profit
 10  →  выход по сигналу
 10  →  вход (scope flat — отдельно от long)
```

Если могут сработать несколько правил, побеждает более высокий priority; остальные на этом bar пропускаются.

### Series DAG (конфиг)

```yaml
series:
  ema12:  { fn: ema,  source: price, period: 12 }
  ema26:  { fn: ema,  source: price, period: 26 }
  macd:   { fn: diff, a: ema12, b: ema26 }
  rsi14:  { fn: rsi,  source: price, period: 14 }
```

Generic ops (`diff`, `shift`, `highest`) — комбинации без нового plugin. Индикаторы на high/low/volume недоступны, пока не расширят вход.

### Predicates & Context

**Context** — полное состояние на баре `i`:

| Поле | Для чего |
|---|---|
| `price`, `timestamp`, `index` | уровни цены, время, день недели |
| `portfolio` | в рынке / вне, размер, avg entry, P&L % |
| `strategy_state` | баров с входа, последнее действие, счётчики |
| precomputed `series` | RSI, пересечения, паттерны |

Время (`time_in_range`, `weekday_in`, `bars_since`) — **predicates** над Context.

### Actions & PositionEffect

Автор всегда пишет **Actions**:

```yaml
then:
  action: buy
  size: ${order_size}
  stop_loss_pct: ${stop_loss_pct}
  take_profit_pct: ${take_profit_pct}

then:
  action: set_stop_loss
  value_pct: 0          # break-even (P1+)

then:
  action: move_stop
  trailing_pct: 2
```

На каждом bar: (1) **PositionEffects**; (2) **Rules**; (3) **OrderExecutor**.

**Параметры** — `choices` (список значений для UI и grid), `optimizable: true/false`. Без отдельного `optimize` и без min/max, если choices задан (§2.7).

### UI (scope заказчика)

Dashboard — **только визуализация**. Стратегии пишутся в YAML; UI показывает метрики, графики, ranking, позволяет выбрать params из `choices` и запустить backtest. Конструктор правил/узлов во frontend **не делаем**.

## 2.5 Типы и имплементация

### Уже есть (`src/`)

| Тип | Где | |
|---|---|---|
| `BaseStrategy` | `strategy/base.py` | **сохраняем** |
| registry, `create_strategy` | `strategy/registry.py` | + id `"composable"` |
| `ParameterSpec`, `describe_strategy` | `strategy/schema.py` | typed params |
| config, loader, store | `strategy/` | загрузка файлов |
| `ExecutionEngine`, `OrderExecutor` | `engine/` | bar loop |
| `ExecutionContext`, `Portfolio` | `engine/` | candle + portfolio |
| `Signal`, `Candle`, `Trade` | `engine/models.py` | расширять по мере нужды |
| Legacy strategies | `strategy/strategies/` | presets до миграции |

### Новое (composable module)

| Тип | Задача |
|---|---|
| `StrategyDefinition` | YAML → `params`, `series`, `rules` |
| `CompiledStrategy` | Результат **compile**: DAG, params, predicates/rules |
| `SeriesNode` | Узел DAG |
| `FloatSeries` / `BoolSeries` | массивы длиной = число баров |
| `Predicate` | `(Context, bar_index) → bool` |
| `Rule` | scope + priority + when + then |
| `Action` | dataclass с type и полями |
| `EvaluationContext` | prices, timestamps, series, portfolio, `StrategyState` |
| `StrategyState` | память стратегии между барами |
| `PositionEffect` | **только engine** — SL/TP/trailing на позиции |
| `ComposableStrategy` | compile + precompute + eval |
| `OptimizeSpec` | params с `optimizable: true`, значения из `choices` |
| `GridOptimizer` | engine: прогон всех комбо, ранжирование |

### Registries

Расширяемые части — через **registry**. Новый индикатор / условие / action = одна зарегистрированная функция; **ядро интерпретатора не меняется**.

```python
@register_series_fn("ema")
def ema(source: FloatSeries, period: int) -> FloatSeries: ...

@register_predicate("cross_above")
def cross_above(a, b, ctx, i) -> bool: ...

@register_action("sell_partial")
def sell_partial(ctx, action) -> Signal: ...
```

### Изменения engine

1. **EvaluationContext** на каждом bar.
2. **`Portfolio.effects`** — из `buy` / `set_stop_loss` / `move_stop`.
3. Порядок: effects → strategy → executor.
4. **P1+:** partial size; **P2:** short.
5. **`GridOptimizer`** — params с `optimizable: true`, значения из `choices` (§2.7).

**Адаптер:** пока engine отдаёт `Candle` — composable берёт `close` + `timestamp`.

## 2.6 Пример конфига (`ma_rsi`)

```yaml
name: ma_rsi_composable
params:
  fast:           { type: int,   default: 10, choices: [5, 10, 12, 21, 30], optimizable: true }
  slow:           { type: int,   default: 30, choices: [20, 30, 50, 100, 200], optimizable: true }
  rsi_period:     { type: int,   default: 14, choices: [14, 20], optimizable: true }
  rsi_buy_min:    { type: float, default: 50, choices: [40, 50, 60], optimizable: true }
  rsi_overbought: { type: float, default: 70, choices: [65, 70, 80], optimizable: true }
  stop_loss_pct:  { type: float, default: 5,  choices: [3, 5, 7, 10], optimizable: true }
  take_profit_pct: { type: float, default: 10, choices: [5, 10, 15, 20], optimizable: true }
  order_size:     { type: float, default: 1,  choices: [1, 2, 3], optimizable: false }

series:
  fast_ma: { fn: sma, source: price, period: "${fast}" }
  slow_ma: { fn: sma, source: price, period: "${slow}" }
  rsi:     { fn: rsi, source: price, period: "${rsi_period}" }

rules:
  - id: stop_loss
    scope: long
    priority: 100
    when: { loss_pct: { gt: "${stop_loss_pct}" } }
    then: { action: sell, size: all }

  - id: take_profit
    scope: long
    priority: 90
    when: { profit_pct: { gt: "${take_profit_pct}" } }
    then: { action: sell, size: all }

  - id: signal_exit
    scope: long
    priority: 10
    when:
      any:
        - cross_below: [fast_ma, slow_ma]
        - gte: [rsi, "${rsi_overbought}"]
    then: { action: sell, size: all }

  - id: entry
    scope: flat
    priority: 10
    when:
      all:
        - cross_above: [fast_ma, slow_ma]
        - gte: [rsi, "${rsi_buy_min}"]
    then:
      action: buy
      size: "${order_size}"
      stop_loss_pct: "${stop_loss_pct}"
      take_profit_pct: "${take_profit_pct}"
```

**Короткий вариант:** убрать rules stop/take и оставить поля на `buy` — тот же результат, меньше YAML.

## 2.7 Подбор параметров (grid search)

Перебор по **`choices`**, не min..max. **`optimizable: true`** — param участвует в grid.

| Слой | Задача |
|---|---|
| **YAML** | `choices` + `optimizable`; presets в `config/param_presets.yaml` |
| **Engine** | GridOptimizer: product optimizable params, filter invalid, ranked JSON |
| **Dashboard** | Визуализация; read-only top configs из optimizer (P1) |

Legacy: `ParameterSpec.choices`. UI — не конструктор стратегий (§2.4).

## 2.8 Расширяемость

| Кто | Задача | Код? |
|---|---|---|
| **Автор стратегии** | YAML: rules + choices | Нет |
| **Разработчик платформы** | series fn / predicate / action | Один plugin |

## 2.9 Фазы MVP

| Фаза | Deliverables |
|---|---|
| **P0** | Composable + ma_rsi YAML + engine SL/TP + **GridOptimizer** |
| **P1** | Optimizer для legacy; top configs в UI |
| **P2** | Умный search, multi-instrument batch |

## 2.10 Итог

Стратегия задаёт **логику и сетки параметров**. Engine: single run + grid optimization.

```text
Input → Series → Rules → Actions → Engine
                    ├─ single run
                    └─ GridOptimizer → ranked configs
```

---

## Document History

| Date | Change |
|---|---|
| 2026-06-30 | Initial proposal |
| 2026-06-30 | Input: price + timestamp only |
| 2026-06-30 | Unified rules, Series DAG, Actions+PositionEffect |
| 2026-07-02 | Key concepts, plain-language explanations |
| 2026-07-02 | choices + optimizable; UI = visualizer only; GridOptimizer |
| 2026-07-04 | Quote `${param}` placeholders in YAML examples (valid YAML in flow maps) |