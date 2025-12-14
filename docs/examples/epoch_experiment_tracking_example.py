#!/usr/bin/env python3
"""
Example: Epoch and Experiment Tracking

This example demonstrates how to use the epoch/experiment tracking system
for strategy lifecycle management. All examples use the SAME symbol (BTCUSDT).

Features demonstrated:
1. Single strategy going through epochs (IDEA → CREATION → BACKTEST → DEMO → LIVE)
2. Timeframe-mix experiment (same strategy, multiple timeframes)
3. Multi-strategy experiment (different strategies, same symbol)
4. Parameter sweep experiment (same strategy, different parameters)
5. Using the run_epoch wrapper for streamlined execution
6. Artifacts written to backtests/<timestamp>/<run_id>/

Run this example:
    python docs/examples/epoch_experiment_tracking_example.py
"""

import sys
sys.path.insert(0, ".")

from src.utils.epoch_tracking import (
    StrategyEpoch,
    ExperimentType,
    StrategyEpochTracker,
    ExperimentTracker,
    make_timeframe_mix_experiment,
    make_multi_strategy_experiment,
    make_parameter_sweep_experiment,
    run_epoch,
)
from src.utils.log_context import log_context_scope


def example_1_single_strategy_lifecycle():
    """
    Example 1: Track a single strategy through all epochs.
    
    This shows the complete lifecycle from idea to live trading.
    """
    print("\n" + "=" * 60)
    print("Example 1: Single Strategy Lifecycle")
    print("=" * 60)
    
    symbol = "BTCUSDT"
    tracker = StrategyEpochTracker("momentum-v1", "Momentum Strategy v1")
    
    # -------------------------------------------------------------------------
    # Epoch 1: IDEA
    # -------------------------------------------------------------------------
    print("\n1. IDEA epoch...")
    idea_run_id = tracker.epoch_start(
        epoch=StrategyEpoch.IDEA,
        symbol=symbol,
        metadata={
            "source": "book",
            "concepts": ["momentum", "breakout", "volume"],
            "description": "Breakout strategy based on price momentum",
        },
    )
    
    # Validate idea (you would have actual validation logic here)
    tracker.epoch_complete(
        run_id=idea_run_id,
        epoch=StrategyEpoch.IDEA,
        symbol=symbol,
        metrics={"validation_score": 0.85},
        passed=True,
        next_epoch=StrategyEpoch.CREATION,
        promotion_reason="Concept validated - clear entry/exit rules",
    )
    print(f"   Run ID: {idea_run_id}")
    print(f"   [OK] Promoted to CREATION")
    
    # -------------------------------------------------------------------------
    # Epoch 2: CREATION
    # -------------------------------------------------------------------------
    print("\n2. CREATION epoch...")
    creation_run_id = tracker.epoch_start(
        epoch=StrategyEpoch.CREATION,
        symbol=symbol,
        timeframes=["1h"],
        metadata={
            "modules": ["entry_momentum", "exit_trailing_stop", "filter_volume"],
            "parameters": {"momentum_period": 20, "volume_threshold": 1.5},
        },
    )
    
    # Strategy creation complete
    tracker.epoch_complete(
        run_id=creation_run_id,
        epoch=StrategyEpoch.CREATION,
        symbol=symbol,
        metrics={"unit_tests": "passed", "integration_tests": "passed"},
        passed=True,
        next_epoch=StrategyEpoch.BACKTEST,
        promotion_reason="Implementation complete, tests pass",
    )
    print(f"   Run ID: {creation_run_id}")
    print(f"   [OK] Promoted to BACKTEST")
    
    # -------------------------------------------------------------------------
    # Epoch 3: BACKTEST
    # -------------------------------------------------------------------------
    print("\n3. BACKTEST epoch...")
    backtest_run_id = tracker.epoch_start(
        epoch=StrategyEpoch.BACKTEST,
        symbol=symbol,
        timeframes=["1h"],
        metadata={
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "initial_capital": 10000,
        },
    )
    
    # Simulate some trades during backtest
    tracker.log_trade(
        run_id=backtest_run_id,
        symbol=symbol,
        side="BUY",
        size_usd=1000,
        price=45000,
    )
    tracker.log_trade(
        run_id=backtest_run_id,
        symbol=symbol,
        side="SELL",
        size_usd=1000,
        price=46500,
        pnl=150,
    )
    
    # Backtest complete
    backtest_metrics = {
        "total_pnl": 1250,
        "win_rate": 0.65,
        "sharpe_ratio": 1.8,
        "max_drawdown": -350,
        "total_trades": 45,
    }
    
    tracker.epoch_complete(
        run_id=backtest_run_id,
        epoch=StrategyEpoch.BACKTEST,
        symbol=symbol,
        metrics=backtest_metrics,
        passed=True,
        next_epoch=StrategyEpoch.DEMO,
        promotion_reason="Sharpe > 1.5, win rate > 0.6",
    )
    print(f"   Run ID: {backtest_run_id}")
    print(f"   Total PnL: ${backtest_metrics['total_pnl']}")
    print(f"   Win Rate: {backtest_metrics['win_rate']:.0%}")
    print(f"   [OK] Promoted to DEMO")
    
    # -------------------------------------------------------------------------
    # Epoch 4: DEMO
    # -------------------------------------------------------------------------
    print("\n4. DEMO epoch...")
    demo_run_id = tracker.epoch_start(
        epoch=StrategyEpoch.DEMO,
        symbol=symbol,
        timeframes=["1h"],
        metadata={"initial_capital": 1000, "demo_account": True},
    )
    
    # Simulate demo trading
    tracker.log_trade(
        run_id=demo_run_id,
        symbol=symbol,
        side="BUY",
        size_usd=100,
        price=50000,
    )
    
    demo_metrics = {
        "total_pnl": 85,
        "win_rate": 0.62,
        "total_trades": 12,
        "duration_days": 30,
    }
    
    tracker.epoch_complete(
        run_id=demo_run_id,
        epoch=StrategyEpoch.DEMO,
        symbol=symbol,
        metrics=demo_metrics,
        passed=True,
        next_epoch=StrategyEpoch.LIVE,
        promotion_reason="Demo performance matches backtest expectations",
    )
    print(f"   Run ID: {demo_run_id}")
    print(f"   Total PnL: ${demo_metrics['total_pnl']}")
    print(f"   [OK] Promoted to LIVE")
    
    print("\n[OK] Strategy lifecycle complete!")
    print(f"  Check backtests/ for artifacts")


def example_2_timeframe_mix_experiment():
    """
    Example 2: Test same strategy on multiple timeframes (same symbol).
    
    This helps find the optimal timeframe for a strategy.
    """
    print("\n" + "=" * 60)
    print("Example 2: Timeframe Mix Experiment")
    print("=" * 60)
    
    symbol = "BTCUSDT"
    
    # Create experiment using helper
    experiment = make_timeframe_mix_experiment(
        symbol=symbol,
        strategy_id="momentum-v1",
        timeframes=["1h", "4h", "1d"],
        metadata={"purpose": "Find optimal timeframe for momentum strategy"},
    )
    
    # Start experiment
    exp_run_id = experiment.start()
    print(f"\nExperiment Run ID: {exp_run_id}")
    print(f"Testing timeframes: 1h, 4h, 1d on {symbol}")
    
    # Test each timeframe
    results = {}
    tracker = StrategyEpochTracker("momentum-v1", "Momentum Strategy")
    
    for tf in ["1h", "4h", "1d"]:
        print(f"\n  Testing {tf}...")
        
        # Run backtest for this timeframe (within experiment context)
        with log_context_scope(run_id=exp_run_id):
            backtest_run_id = tracker.epoch_start(
                epoch=StrategyEpoch.BACKTEST,
                symbol=symbol,
                timeframes=[tf],
                experiment_id=experiment.experiment_id,
                metadata={"timeframe": tf},
            )
            
            # Simulate backtest results (varying by timeframe)
            if tf == "1h":
                metrics = {"total_pnl": 800, "win_rate": 0.62, "sharpe": 1.5}
            elif tf == "4h":
                metrics = {"total_pnl": 1200, "win_rate": 0.68, "sharpe": 1.9}
            else:
                metrics = {"total_pnl": 600, "win_rate": 0.58, "sharpe": 1.2}
            
            tracker.epoch_complete(
                run_id=backtest_run_id,
                epoch=StrategyEpoch.BACKTEST,
                symbol=symbol,
                metrics=metrics,
            )
            
            results[tf] = metrics
            print(f"    PnL: ${metrics['total_pnl']}, Win Rate: {metrics['win_rate']:.0%}")
    
    # Complete experiment
    best_tf = max(results.items(), key=lambda x: x[1]["total_pnl"])[0]
    experiment.complete(
        results=results,
        overall_metrics={
            "best_timeframe": best_tf,
            "combined_pnl": sum(r["total_pnl"] for r in results.values()),
        },
    )
    
    print(f"\n[OK] Experiment complete!")
    print(f"  Best timeframe: {best_tf}")
    print(f"  Check backtests/ for artifacts")


def example_3_multi_strategy_experiment():
    """
    Example 3: Test multiple strategies on the same symbol.
    
    This helps find complementary strategies for the same symbol.
    """
    print("\n" + "=" * 60)
    print("Example 3: Multi-Strategy Experiment")
    print("=" * 60)
    
    symbol = "BTCUSDT"
    
    # Create experiment using helper
    experiment = make_multi_strategy_experiment(
        symbol=symbol,
        strategy_timeframes=[
            {"strategy_id": "momentum-v1", "timeframes": ["1h"]},
            {"strategy_id": "mean-reversion-v1", "timeframes": ["15m"]},
            {"strategy_id": "trend-following-v1", "timeframes": ["4h"]},
        ],
        metadata={"purpose": "Test complementary strategies on BTCUSDT"},
    )
    
    exp_run_id = experiment.start()
    print(f"\nExperiment Run ID: {exp_run_id}")
    print(f"Testing 3 strategies on {symbol}")
    
    results = {}
    
    for strategy_config in experiment.strategies:
        strategy_id = strategy_config["strategy_id"]
        timeframe = strategy_config["timeframes"][0]
        
        print(f"\n  Testing {strategy_id} on {timeframe}...")
        
        tracker = StrategyEpochTracker(strategy_id, strategy_id)
        
        with log_context_scope(run_id=exp_run_id):
            backtest_run_id = tracker.epoch_start(
                epoch=StrategyEpoch.BACKTEST,
                symbol=symbol,
                timeframes=[timeframe],
                experiment_id=experiment.experiment_id,
            )
            
            # Simulate different results per strategy
            if "momentum" in strategy_id:
                metrics = {"total_pnl": 900, "win_rate": 0.63}
            elif "mean-reversion" in strategy_id:
                metrics = {"total_pnl": 600, "win_rate": 0.72}
            else:
                metrics = {"total_pnl": 750, "win_rate": 0.55}
            
            tracker.epoch_complete(
                run_id=backtest_run_id,
                epoch=StrategyEpoch.BACKTEST,
                symbol=symbol,
                metrics=metrics,
            )
            
            results[strategy_id] = metrics
            print(f"    PnL: ${metrics['total_pnl']}, Win Rate: {metrics['win_rate']:.0%}")
    
    experiment.complete(
        results=results,
        overall_metrics={
            "combined_pnl": sum(r["total_pnl"] for r in results.values()),
            "strategy_count": len(results),
        },
    )
    
    print(f"\n[OK] Experiment complete!")
    print(f"  Combined PnL: ${sum(r['total_pnl'] for r in results.values())}")


def example_4_parameter_sweep():
    """
    Example 4: Parameter optimization for a strategy on one symbol.
    """
    print("\n" + "=" * 60)
    print("Example 4: Parameter Sweep Experiment")
    print("=" * 60)
    
    symbol = "BTCUSDT"
    
    experiment = make_parameter_sweep_experiment(
        symbol=symbol,
        strategy_id="momentum-v1",
        timeframes=["1h"],
        parameter_sets=[
            {"momentum_period": 10, "volume_threshold": 1.2},
            {"momentum_period": 20, "volume_threshold": 1.5},
            {"momentum_period": 30, "volume_threshold": 2.0},
        ],
    )
    
    exp_run_id = experiment.start()
    print(f"\nExperiment Run ID: {exp_run_id}")
    print(f"Testing 3 parameter sets on {symbol}")
    
    results = {}
    tracker = StrategyEpochTracker("momentum-v1", "Momentum Strategy")
    
    for i, strategy_config in enumerate(experiment.strategies):
        params = strategy_config["parameters"]
        param_key = f"period_{params['momentum_period']}_vol_{params['volume_threshold']}"
        
        print(f"\n  Testing {param_key}...")
        
        with log_context_scope(run_id=exp_run_id):
            backtest_run_id = tracker.epoch_start(
                epoch=StrategyEpoch.BACKTEST,
                symbol=symbol,
                timeframes=["1h"],
                experiment_id=experiment.experiment_id,
                metadata={"parameters": params, "param_set": i},
            )
            
            # Simulate results (better with higher period in this example)
            metrics = {
                "total_pnl": 500 + i * 150,
                "sharpe_ratio": 1.2 + i * 0.2,
                "win_rate": 0.58 + i * 0.04,
            }
            
            tracker.epoch_complete(
                run_id=backtest_run_id,
                epoch=StrategyEpoch.BACKTEST,
                symbol=symbol,
                metrics=metrics,
            )
            
            results[param_key] = metrics
            print(f"    PnL: ${metrics['total_pnl']}, Sharpe: {metrics['sharpe_ratio']:.2f}")
    
    best_params = max(results.items(), key=lambda x: x[1]["sharpe_ratio"])
    
    experiment.complete(
        results=results,
        overall_metrics={
            "best_parameters": best_params[0],
            "best_sharpe": best_params[1]["sharpe_ratio"],
        },
    )
    
    print(f"\n[OK] Experiment complete!")
    print(f"  Best parameters: {best_params[0]}")


def example_5_run_epoch_wrapper():
    """
    Example 5: Using the run_epoch wrapper for streamlined execution.
    
    The run_epoch function handles all the boilerplate for you.
    """
    print("\n" + "=" * 60)
    print("Example 5: run_epoch Wrapper")
    print("=" * 60)
    
    symbol = "BTCUSDT"
    
    # Define a simple backtest function
    def my_backtest(symbol: str, timeframe: str, start_date: str, end_date: str) -> dict:
        """Simulated backtest function."""
        print(f"  Running backtest: {symbol} {timeframe} from {start_date} to {end_date}")
        
        # Your actual backtest logic would go here
        # For this example, we just return simulated metrics
        return {
            "total_pnl": 850,
            "win_rate": 0.64,
            "sharpe_ratio": 1.7,
            "total_trades": 32,
        }
    
    # Run backtest with automatic epoch tracking
    result = run_epoch(
        epoch=StrategyEpoch.BACKTEST,
        symbol=symbol,
        strategy_id="momentum-v1",
        strategy_name="Momentum Strategy v1",
        runner_fn=my_backtest,
        timeframes=["1h"],
        metadata={"source": "example"},
        promotion_criteria=lambda m: m.get("win_rate", 0) > 0.6,
        next_epoch=StrategyEpoch.DEMO,
        # These are passed to runner_fn:
        timeframe="1h",
        start_date="2024-01-01",
        end_date="2024-06-30",
    )
    
    print(f"\nRun ID: {result['run_id']}")
    print(f"Strategy: {result['strategy_id']}")
    print(f"Epoch: {result['epoch']}")
    print(f"Metrics: {result['metrics']}")
    print(f"Passed: {result['passed']}")
    print(f"Next Epoch: {result['next_epoch']}")
    
    print(f"\n[OK] run_epoch wrapper complete!")


if __name__ == "__main__":
    print("=" * 60)
    print("Epoch & Experiment Tracking Examples")
    print("=" * 60)
    print("\nAll examples use BTCUSDT as the symbol.")
    print("Artifacts will be written to backtests/<timestamp>/<run_id>/")
    
    example_1_single_strategy_lifecycle()
    example_2_timeframe_mix_experiment()
    example_3_multi_strategy_experiment()
    example_4_parameter_sweep()
    example_5_run_epoch_wrapper()
    
    print("\n" + "=" * 60)
    print("All examples complete!")
    print("=" * 60)
    print("\nCheck:")
    print("  - logs/events_*.jsonl for structured events")
    print("  - backtests/ for run artifacts (config.json, results.json, summary.json)")

