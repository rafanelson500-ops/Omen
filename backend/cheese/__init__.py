"""cheese: GEXbot-driven ES futures research stack.

Submodules:
    gex        - GEXbot orderflow fetch / load / resample
    market     - Databento ES continuous-front fetch / load
    features   - Feature engineering (flow z-scores, regime, walls)
    strategy   - Signal generators (flow-burst, wall-reject, etc.)
    backtest   - ATR-based stop/target event engine with realistic costs
    metrics    - Performance + regime-conditional statistics
    config     - Shared paths / constants / dataclass configs
"""

from cheese import config, gex, market, features, strategy, backtest, metrics  # noqa: F401
