import sys
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Убеждаемся, что корневая директория проекта есть в sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Импортируем встроенные и composable стратегии (чтобы они зарегистрировались в реестре)
import src.strategy.strategies
from src.strategy import discover_composable_strategies

# Импортируем нужные классы нашего движка и моделей
from src.engine.models import Candle, RunContext, OptimizationResult
from src.engine.optimization_engine import RandomSearchExecutionEngine

def generate_dummy_candles(n_bars: int = 150) -> list[Candle]:
    """Генерирует тестовые свечи (волнообразное движение цены с трендом),
    чтобы стратегия MA Crossover точно совершала сделки.
    """
    candles = []
    base_price = 100.0
    start_time = datetime.now(timezone.utc) - timedelta(hours=n_bars)

    for i in range(n_bars):
        # Генерируем цену по синусоиде + небольшой восходящий тренд
        price = base_price + math.sin(i / 5.0) * 10.0 + (i * 0.1)
        high = price + 1.5
        low = price - 1.5
        open_price = price - 0.5
        close_price = price + 0.5
        
        timestamp = (start_time + timedelta(hours=i)).isoformat()

        # Создаем свечу только со стандартными полями OHLCV + timestamp
        candles.append(
            Candle(
                timestamp=timestamp,
                open=open_price,
                high=high,
                low=low,
                close=close_price,
                volume=1000
            )
        )
    return candles

def run_test():
    print("=" * 60)
    print("1. Инициализация и поиск доступных стратегий...")
    try:
        discover_composable_strategies()
    except ValueError:
        print("   -> Стратегии уже были автоматически загружены при импорте, пропускаем повторную регистрацию.")

    # Генерируем тестовые данные
    print("2. Генерация тестовых свечей...")
    candles = generate_dummy_candles(n_bars=200)
    
    # Создаем контекст симуляции
    context = RunContext(
        run_id="test_opt_run_001",
        strategy_id="ma_rsi_composable",
        strategy_version="1",
        instrument="TEST_SBER",
        timeframe="1h",
        period_start=candles[0].timestamp,
        period_end=candles[-1].timestamp,
        initial_capital=100_000.0,
    )

    # Задаем сетку параметров строго из разрешенных choices в YAML и пресетах
    param_grid = {
        "fast": [10],                      # Фиксируем дефолтное (чтобы не гадать preset:ma_short)
        "slow": [20, 30, 50],              # Точно есть в preset:ma_long [20, 30, 50, 100, 200]
        "rsi_period": [14, 20],            # Разрешено в YAML: choices: [14, 20]
        "rsi_buy_min": [40, 50, 60],       # Разрешено в YAML: choices: [40, 50, 60]
        "rsi_overbought": [70],            # Фиксируем дефолтное 70
        "stop_loss_pct": [5],              # Фиксируем дефолтное 5
        "take_profit_pct": [10],           # Фиксируем дефолтное 10
        "order_size": 1.0                  # Скалярное значение -> строго фиксировано
    }

    print("3. Запуск RandomSearchExecutionEngine...")
    engine = RandomSearchExecutionEngine()
    
    # Запускаем оптимизацию на 8 уникальных итераций
    result: OptimizationResult = engine.run_optimization(
        strategy_id="ma_rsi_composable",
        param_grid=param_grid,
        candles=candles,
        initial_capital=100_000.0,
        run_context=context,
        n_iterations=8,
        target_metric="total_pnl"
    )

    print("=" * 60)
    print("РЕЗУЛЬТАТЫ ОПТИМИЗАЦИИ:")
    print(f"Стратегия:            {result.strategy_id}")
    print(f"Актив:                {result.instrument}")
    print(f"Проверено комбинаций: {result.total_iterations_run}")
    print("-" * 60)
    print("ЛУЧШИЕ ПАРАМЕТРЫ:")
    for k, v in result.best_params.items():
        print(f"  {k}: {v}")
    print("-" * 60)
    print("МЕТРИКИ ПОБЕДИТЕЛЯ:")
    print(f"  Total P&L:          {result.best_metrics.total_pnl:.2f}")
    print(f"  Sharpe Ratio:       {result.best_metrics.sharpe_ratio:.4f}")
    print(f"  Max Drawdown:       {result.best_metrics.max_drawdown * 100:.2f}%")
    print(f"  Win Rate:           {result.best_metrics.win_rate * 100:.2f}%")
    print(f"  Финальный эквити:   {result.best_final_portfolio.equity:.2f}")
    print("-" * 60)
    print("ИСТОРИЯ ИТЕРАЦИЙ (ТОП по P&L):")
    
    # Сортируем итерации по убыванию P&L для наглядности вывода
    sorted_iterations = sorted(result.iterations, key=lambda x: x.metrics.total_pnl, reverse=True)
    for it in sorted_iterations:
        print(f"  Попытка #{it.iteration_index:02d} | PnL: {it.metrics.total_pnl:10.2f} | Параметры: fast={it.params['fast']}, slow={it.params['slow']}, rsi_min={it.params['rsi_buy_min']}")
    print("=" * 60)

if __name__ == "__main__":
    run_test()