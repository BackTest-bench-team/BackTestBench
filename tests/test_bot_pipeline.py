import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Добавляем корень проекта в путь
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.strategy import discover_composable_strategies
from src.engine.models import Candle, RunContext
from src.engine.optimization_engine import RandomSearchExecutionEngine
from src.engine.trading_bot import run_trading_bot, load_bot_params

def generate_candles_slice(start_offset_hours: int, n_bars: int) -> list[Candle]:
    """Генерирует срез свечей для симуляции."""
    candles = []
    base_price = 150.0
    start_time = datetime.now(timezone.utc) - timedelta(hours=start_offset_hours)

    for i in range(n_bars):
        price = base_price + math.sin(i / 4.0) * 8.0 + (i * 0.05)
        candles.append(
            Candle(
                timestamp=(start_time + timedelta(hours=i)).isoformat(),
                open=price - 0.5, high=price + 1.0, low=price - 1.0, close=price + 0.5,
                volume=5000
            )
        )
    return candles

def run_e2e_pipeline():
    print("=" * 70)
    print("ШАГ 0: Инициализация стратегий...")
    try:
        discover_composable_strategies()
    except ValueError:
        pass

    # ---------------------------------------------------------
    # ШАГ 1: ОПТИМИЗАЦИЯ (На истории 30 дней назад -> 10 дней назад)
    # ---------------------------------------------------------
    print("\n[1/3] Запускаем оптимизацию на старых исторических данных...")
    historical_candles = generate_candles_slice(start_offset_hours=720, n_bars=300)
    
    context = RunContext(
        run_id="opt_historical_001", strategy_id="ma_rsi_composable", strategy_version="1",
        instrument="SBER", timeframe="1h", period_start=historical_candles[0].timestamp,
        period_end=historical_candles[-1].timestamp, initial_capital=100_000.0
    )

    param_grid = {
        "fast": [10], "slow": [20, 30, 50], "rsi_period": [14],
        "rsi_buy_min": [40, 50], "rsi_overbought": [70], 
        "stop_loss_pct": [0.5, 1.0],      # <-- ИСПРАВЛЕНО: берем из разрешенных [0.3, 0.5, 0.7, 1.0]
        "take_profit_pct": [1.0, 2.0],    # <-- Ставим реалистичные значения для тейка
        "order_size": 1.0
    }

    opt_engine = RandomSearchExecutionEngine()
    opt_result = opt_engine.run_optimization(
        "ma_rsi_composable", param_grid, historical_candles, 100_000.0, context, n_iterations=5
    )

    # Проверяем, что оптимизатор нашел хотя бы одну рабочую комбинацию
    if opt_result.best_metrics is None:
        print("\n[Ошибка] Ни одна итерация оптимизации не прошла успешно!")
        print("Проверь разрешенные значения (choices) для параметров в YAML-конфиге стратегии.")
        return

    # Сохраняем лучший результат в JSON (имитация выхода оптимизатора)
    best_json_path = ROOT_DIR / "temp_best_optimizer_result.json"
    with open(best_json_path, "w", encoding="utf-8") as f:
        json.dump({"best_params": opt_result.best_params, "score": opt_result.best_metrics.total_pnl}, f, indent=2)
    print(f"   -> Оптимизация завершена! Лучшие параметры сохранены в: {best_json_path.name}")
    print(f"   -> Победившие параметры: {opt_result.best_params}")

    # ---------------------------------------------------------
    # ШАГ 2: ПОДГОТОВКА СВЕЖИХ ДАННЫХ (Последние 5 дней)
    # ---------------------------------------------------------
    print("\n[2/3] Загружаем СВЕЖИЙ срез данных (Out-of-Sample)...")
    # Генерируем свечи за последние 120 часов (которые оптимизатор НЕ видел!)
    fresh_candles = generate_candles_slice(start_offset_hours=120, n_bars=120)
    print(f"   -> Загружено {len(fresh_candles)} свежих свечей (с {fresh_candles[0].timestamp[:10]} по {fresh_candles[-1].timestamp[:10]}).")

    # ---------------------------------------------------------
    # ШАГ 3: ЗАПУСК ТОРГОВОГО БОТА (Validation Pass)
    # ---------------------------------------------------------
    print("\n[3/3] Запускаем Minimal Trading Bot на свежих данных...")
    val_report = run_trading_bot(
        strategy_id="ma_rsi_composable",
        config_path=str(best_json_path),
        instrument="SBER",
        recent_candles=fresh_candles,
        initial_capital=100_000.0
    )

    print("\n" + "=" * 70)
    print("ИТОГОВЫЙ ОТЧЕТ ВАЛИДАЦИИ БОТА (ValidationMetricsReport JSON):")
    print("-" * 70)
    # Выводим в формате JSON, как требует Scope
    report_dict = {
        "validation_run_id": val_report.validation_run_id,
        "strategy_id": val_report.strategy_id,
        "instrument": val_report.instrument,
        "source_backtest_run_id": val_report.source_backtest_run_id,
        "metrics": {
            "total_pnl": val_report.metrics.total_pnl,
            "sharpe_ratio": val_report.metrics.sharpe_ratio,
            "max_drawdown": val_report.metrics.max_drawdown,
            "win_rate": val_report.metrics.win_rate
        }
    }
    print(json.dumps(report_dict, indent=2, ensure_ascii=False))
    print("=" * 70)

    # Удаляем временный файл
    if best_json_path.exists():
        best_json_path.unlink()

if __name__ == "__main__":
    run_e2e_pipeline()