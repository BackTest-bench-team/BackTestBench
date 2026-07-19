from src.engine import ExecutionEngine
from src.engine.models import Candle, Signal
from src.engine.types import SignalType


class StrategyMock:
    __test__ = False
    
    def __init__(self):
        self.counter = 0


    def on_candle(self, context):

        self.counter += 1

        # первая свеча покупаем
        if self.counter == 1:
            return Signal(
                type=SignalType.BUY
            )

        # третья свеча продаем
        if self.counter == 3:
            return Signal(
                type=SignalType.SELL
            )


        return Signal(
            type=SignalType.HOLD
        )



def test_execution_engine():

    candles = [

        Candle(
            timestamp="2025-01-01",
            open=100,
            high=110,
            low=90,
            close=100,
            volume=1000
        ),

        Candle(
            timestamp="2025-01-02",
            open=100,
            high=120,
            low=100,
            close=110,
            volume=1000
        ),

        Candle(
            timestamp="2025-01-03",
            open=110,
            high=130,
            low=100,
            close=120,
            volume=1000
        )

    ]


    engine = ExecutionEngine()

    strategy = StrategyMock()


    result = engine.run(
        strategy=strategy,
        candles=candles,
        initial_capital=10000
    )


    trades = result["trade_log"]

    portfolio = result["final_portfolio"]


    # Проверяем что была сделка
    assert len(trades) == 1


    trade = trades[0]


    print(trade)


    # BUY 10000 / 100 = 100 акций
    # SELL 100 акций * (120-100)
    assert trade.pnl == 2000


    # после продажи деньги вернулись
    assert portfolio.cash == 12000
    assert result["equity_curve"] == [10000.0, 10000.0, 11000.0, 12000.0]
    assert result["trade_log_report"].final_portfolio_value == 12000.0


    print("ENGINE TEST PASSED")


class BuyAndHoldStrategy:
    def __init__(self):
        self.done = False

    def on_candle(self, context):
        if not self.done:
            self.done = True
            return Signal(type=SignalType.BUY)
        return Signal(type=SignalType.HOLD)


def test_engine_force_closes_open_position_on_last_candle():
    candles = [
        Candle("2025-01-01", 100, 100, 100, 100, 1),
        Candle("2025-01-02", 120, 120, 120, 120, 1),
    ]

    result = ExecutionEngine().run(BuyAndHoldStrategy(), candles, initial_capital=1000.0)

    assert len(result["trade_log"]) == 1
    assert result["trade_log"][0].pnl == 200.0
    assert result["final_portfolio"].cash == 1200.0
    assert result["final_portfolio"].position_size == 0.0
    assert result["equity_curve"] == [1000.0, 1000.0, 1200.0]


def test_engine_applies_commission_and_slippage():
    candles = [
        Candle("2025-01-01", 100, 100, 100, 100, 1),
        Candle("2025-01-02", 100, 100, 100, 100, 1),
        Candle("2025-01-03", 120, 120, 120, 120, 1),
    ]

    from src.engine.execution_config import ExecutionConfig

    initial_capital = 10_000.0
    result = ExecutionEngine(
        ExecutionConfig(commission_pct=0.05, slippage_pct=0.01),
    ).run(StrategyMock(), candles, initial_capital=initial_capital)

    trade = result["trade_log"][0]
    assert trade.pnl < 2_000.0
    assert result["final_portfolio"].cash < 12_000.0

    total_pnl = sum(item.pnl for item in result["trade_log"])
    expected = result["final_portfolio"].equity - initial_capital
    assert abs(total_pnl - expected) < 1e-6


class FlipStrategy:
    __test__ = False

    def __init__(self):
        self.counter = 0

    def on_candle(self, context):
        self.counter += 1
        if self.counter in {1, 3}:
            return Signal(type=SignalType.BUY)
        if self.counter in {2, 4}:
            return Signal(type=SignalType.SELL)
        return Signal(type=SignalType.HOLD)


def test_engine_pnl_integrity_with_commission_on_multiple_trades():
    candles = [
        Candle("2025-01-01", 100, 100, 100, 100, 1),
        Candle("2025-01-02", 110, 110, 110, 110, 1),
        Candle("2025-01-03", 105, 105, 105, 105, 1),
        Candle("2025-01-04", 115, 115, 115, 115, 1),
        Candle("2025-01-05", 120, 120, 120, 120, 1),
    ]

    from src.engine.execution_config import ExecutionConfig

    initial_capital = 10_000_000.0
    result = ExecutionEngine(
        ExecutionConfig(commission_pct=0.05, slippage_pct=0.01),
    ).run(FlipStrategy(), candles, initial_capital=initial_capital)

    total_pnl = sum(item.pnl for item in result["trade_log"])
    expected = result["final_portfolio"].equity - initial_capital
    assert abs(total_pnl - expected) < 1e-4
    assert len(result["trade_log"]) == 2
