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


    print("ENGINE TEST PASSED")