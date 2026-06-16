# Core Performance Metrics — Specification

This document specifies the **exact formulas and calculation rules** for the first set of performance metrics produced by the Analytics Module.

## Scope - "computed using only Candles"

The first metric set is computed exclusively from **candle-derived data**:

- the `TradeLog` produced by the Simulation Engine while iterating over a `List[Candle]`, and
- candle **close** prices, used to mark the portfolio to market.

No order-book, tick-level, or sentiment data is used. This matches MVP-1 (one strategy, one instrument, long-only).

The four metrics in the Definition of Done map directly onto `MetricsReport`:

|`MetricsReport` field|Metric|
|---|---|
|`total_pnl`|P&L|
|`sharpe_ratio`|Sharpe ratio|
|`max_drawdown`|Max drawdown|
|`win_rate`|Win rate|

`deposit_baseline_pnl` is also specified here because the top-N filter depends on it, but it is a **comparison baseline**, not a performance metric.

---

## Inputs

The Analytics Module needs the following per run. Items marked **(new)** are not yet on the current `TradeLog` contract - see _Open coordination points_.

|Input|Source|Used by|
|---|---|---|
|`trades: List[Trade]`|`TradeLog`|P&L, win rate, fallback equity curve|
|`final_portfolio_value: float`|`TradeLog`|consistency check|
|`initial_capital: float` **(new)**|run config / Simulation Engine|returns, drawdown, deposit baseline|
|`equity_curve: List[float]` **(new)**|Simulation Engine|Sharpe, max drawdown|
|`timeframe: str`|strategy config / candle|annualization|
|`period_start`, `period_end: datetime`|candle range (`from_dt`, `to_dt`)|deposit baseline, periods/year|

### Equity curve

The **equity curve** `E = [E_0, E_1, ..., E_T]` is the portfolio value evaluated at every candle, marked to market on the candle close:

```
E_0 = initial_capital
E_i = cash_i + Σ_p ( position_quantity_p × candle_i.close_p )      (i = 1..T)
```

For MVP-1 (single instrument, long-only) this reduces to:

```
E_i = cash_i + held_quantity_i × candle_i.close
```

This curve is the canonical basis for Sharpe and max drawdown.

**Fallback (if the equity curve is not yet emitted by the engine):** reconstruct a coarse, realized-only curve stepping at each closed trade:

```
E_0      = initial_capital
E_k      = initial_capital + Σ_{j ≤ k} trades[j].pnl
```

The fallback ignores unrealized intra-trade fluctuations, so it under-reports drawdown and changes the Sharpe sampling frequency from per-candle to per-trade. It is acceptable for the very first MVP but the per-candle curve is the target.

---

## Shared conventions

- **Per-trade P&L** is produced by the Simulation Engine, not the Analytics Module. For consistency the assumed convention (long-only MVP) is:

    ```
    trade.pnl = (exit_price − entry_price) × quantity − commission
    ```

    `commission` defaults to `0.0` for MVP-1 and is configurable. This convention must be confirmed with the Core Engine developer.

- A trade is a **win** when `pnl > 0`. Break-even (`pnl == 0`) is **not** a win.

- All amounts are in account currency; `max_drawdown` and `win_rate` are unitless fractions in `[0, 1]`.

- Empty / degenerate inputs return the neutral values defined per metric below (never raise, never return `NaN`), so a strategy that never trades is still rankable.

---

## 1. P&L - `total_pnl`

Sum of realized profit/loss across all closed trades:

```
total_pnl = Σ_{t ∈ trades} t.pnl
```

- Empty trade list → `total_pnl = 0.0`.

- **Rule:** any position still open at the last candle is force-closed by the Simulation Engine at that candle's close, so realized P&L equals net P&L and the metric is unambiguous. With this rule:

    ```
    total_pnl  ==  final_portfolio_value − initial_capital     (consistency check)
    ```

    The Analytics Module asserts this equality (within a small float tolerance) and raises a data-integrity alert if it fails.

---

## 2. Win rate - `win_rate`

Fraction of profitable trades:

```
wins      = | { t ∈ trades : t.pnl > 0 } |
n_trades  = | trades |
win_rate  = wins / n_trades
```

- `n_trades == 0` → `win_rate = 0.0`.
- Result is in `[0.0, 1.0]`, matching `MetricsReport.win_rate`.

---

## 3. Max drawdown - `max_drawdown`

Largest peak-to-trough decline of the equity curve, as a **positive fraction** relative to the running peak (e.g. `0.15` = 15%).

Given the equity curve `E_0 .. E_T`:

```
peak_i        = max(E_0, E_1, ..., E_i)                 (running maximum)
drawdown_i    = (peak_i − E_i) / peak_i
max_drawdown  = max_i ( drawdown_i )
```

- Denominator is the **running peak** (relative drawdown), not initial capital.
- Fewer than 2 equity points, or a flat/monotonically rising curve → `max_drawdown = 0.0`.
- `initial_capital > 0` is assumed, so `peak_i > 0` and the division is safe. If a peak is ever `≤ 0` (only possible with leverage, out of MVP scope), that point is skipped.
- Result is in `[0.0, 1.0]`, matching `MetricsReport.max_drawdown`

![Max drawdown on an equity curve](images/max_drawdown_on_equity_curve.svg)

---

## 4. Sharpe ratio - `sharpe_ratio`

Annualized risk-adjusted return, computed from **per-period simple returns** of the equity curve.

**Step 1 - period returns** (i = 1..n, n = T):

```
r_i = (E_i − E_{i−1}) / E_{i−1}
```

**Step 2 - excess returns** over the per-period risk-free rate `r_f`:

```
x_i = r_i − r_f
```

**Step 3 - mean and sample standard deviation** (n − 1 denominator):

```
mean_x = (1/n) · Σ x_i
std_x  = sqrt( (1/(n−1)) · Σ (x_i − mean_x)^2 )
```

**Step 4 - per-period Sharpe, then annualize**:

```
sharpe_period = mean_x / std_x
sharpe_ratio  = sharpe_period × sqrt(periods_per_year)
```

![Sharpe ratio: same return, different risk](images/sharpe_smooth_vs_jagged_same_return.svg)

### Parameters and rules

- **Risk-free rate `r_f`:** per-period rate derived from the annual deposit baseline (13%/year), converted to the candle timeframe:

    ```
    r_f = (1 + 0.13)^(1 / periods_per_year) − 1
    ```

    For MVP-1 `r_f = 0.0` is an acceptable simplification (configurable).

- **`periods_per_year`** depends on `timeframe` and the traded calendar. Defaults (configurable, MOEX-oriented):

    |timeframe|periods_per_year|
    |---|---|
    |`1d`|252|
    |`1h`|252 × trading_hours_per_day|
    |`1m`|252 × trading_hours_per_day × 60|

    Using a fixed `periods_per_year` keeps Sharpe comparable across strategies on the same timeframe.

- **Standard deviation** uses the sample estimator (n − 1). This is a deliberate choice; switching to the population estimator (n) must be a team-wide decision so all strategies are ranked on the same basis.

- **Edge cases:** `n < 2` → `sharpe_ratio = 0.0`; `std_x == 0` (no variation) → `sharpe_ratio = 0.0`.

- Simple returns are used. Log returns are a possible later refinement but change the numbers, so they are out of scope for the first set.

---

## Comparison baseline - `deposit_baseline_pnl`

P&L the same capital would have earned in a bank deposit over the same period (compound, 13% annual):

```
years                 = (period_end − period_start) / 365 days
deposit_baseline_pnl  = initial_capital × ( (1 + 0.13)^years − 1 )
```

- `years` is measured over the **candle range actually backtested** (`period_start = from_dt`, `period_end = to_dt`).
- The top-N filter keeps a strategy when `total_pnl > deposit_baseline_pnl` (ranking logic lives in the Analytics ranking step, not in this metric).
- The annual rate `0.13` is a single configurable constant shared across the module.

---

## Edge-case summary

|Situation|total_pnl|win_rate|max_drawdown|sharpe_ratio|
|---|---|---|---|---|
|No trades|0.0|0.0|0.0|0.0|
|< 2 equity points|—|—|0.0|0.0|
|Flat / rising equity|—|—|0.0|0.0 (if std = 0)|
|Zero return variance|—|—|as computed|0.0|

No metric raises an exception or returns `NaN`; a failing consistency check raises a **data-integrity alert** instead of corrupting the metric.

---

## Configuration parameters

|Parameter|Default|Description|
|---|---|---|
|`initial_capital`|run config|Starting capital `E_0`|
|`commission`|`0.0`|Per-trade cost in the P&L convention|
|`annual_deposit_rate`|`0.13`|Baseline deposit / risk-free source|
|`risk_free_rate`|derived from `annual_deposit_rate` (MVP: `0.0`)|Per-period `r_f` in Sharpe|
|`periods_per_year`|per timeframe table|Sharpe annualization factor|
|`trading_hours_per_day`|venue-dependent|Used to derive `periods_per_year`|

---

## Open coordination points

1. **Equity curve (with Core Engine - Samy).** Sharpe and max drawdown require a per-candle equity curve, which the current `TradeLog` does not carry. _Recommendation:_ add `equity_curve: List[float]` (aligned 1:1 with the candle series) to `TradeLog`. _Alternative:_ pass the curve to Analytics alongside the `TradeLog`. _Fallback for the first MVP:_ reconstruct the realized-only curve from trade P&L (documented above). I recommend adding the field - it is a small change and unlocks the two hardest metrics correctly.
2. **`initial_capital` availability (with Core Engine).** Analytics needs `E_0` for returns, drawdown, and the deposit baseline. Either add it to the run payload or expose it on `TradeLog`.
3. **Per-trade P&L convention (with Core Engine).** Confirm the `(exit − entry) × qty − commission` long-only convention and where commissions are applied.
4. **Sample vs population standard deviation (team-wide).** Affects every Sharpe value; must be fixed once for fair ranking. Proposed: sample (n − 1).
5. **`periods_per_year` per venue/timeframe (team-wide).** Needs agreed defaults so Sharpe is comparable.
