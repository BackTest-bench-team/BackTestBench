# Strategy Signal & Position Rules

The customer (22-06 meeting) asked that the rules for entries, exits, and
repeated signals be made **explicit and unambiguous**. This document states the
contract the built-in strategies follow and what the engine is expected to do
with each signal. It is the strategy-side companion to
`strategy_module_architecture.md`.

## What a strategy returns

Each `on_candle(context)` call returns exactly one `Signal(type, size, reason)`
where `type` is `BUY`, `SELL`, or `HOLD`. A strategy returns **one signal per
candle** and never returns nothing — "do nothing" is `HOLD`.

## Meaning of each signal (MVP-1, long-only)

| Signal | Meaning | Engine action |
|---|---|---|
| `BUY`  | enter / be long  | open a long position (engine sizing) |
| `SELL` | exit / be flat   | close the open long position |
| `HOLD` | no change        | keep the current position, place no order |

## Repeated-signal rules (the customer's open question)

A strategy is responsible for not emitting redundant entries/exits, by reading
the portfolio before deciding:

- **BUY while already long → the strategy returns `HOLD`.** The built-ins check
  `context.portfolio.position_size > 0` and only emit `BUY` when **flat**. They
  never pyramid (no adding to an open position) in MVP-1.
- **SELL while flat → the strategy returns `HOLD`.** The built-ins only emit
  `SELL` when a position is open.
- As a safety net, the engine treats a `BUY` while already long, or a `SELL`
  while flat, as a no-op. So position size is the source of truth and duplicate
  signals cannot double a position.

This makes the behaviour deterministic regardless of how often the underlying
indicator condition stays true across consecutive candles.

## Position sizing

`Signal.size` carries the intended order size (from the strategy's `order_size`
param). In MVP-1 the engine executes a full enter/exit (all-in / all-out), so
`size` is advisory; richer sizing is a later enhancement. Strategies set it so
the contract is ready when the engine honours it.

## Out of scope for MVP-1 (noted for later)

The customer raised these as future needs, not MVP work:

- **Stop-loss / take-profit.** A single decision may eventually need to describe
  several related actions (enter + protective exits). The current `Signal` is
  one action; extending it (or adding engine-side position-control that polls
  price and exits on SL/TP) is a future change to be agreed with the engine
  owner — it is **not** embedded in the current strategies.
- **Short positions / pyramiding.** Long-only, single-entry for now.

These are recorded so the entry/exit rules above stay simple and explicit while
the richer behaviour is designed later.
