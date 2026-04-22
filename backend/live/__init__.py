"""Live trading stack.

Submodules:
    settings           - env var loader + safety flags (dry-run by default)
    bus                - asyncio pub/sub event bus + ring log buffer
    logger             - Rich + bus-piped structured logger
    tradovate          - Tradovate REST auth, 30m renewal loop, trading + MD WS
    gexbot_ws          - GEXbot realtime orderflow hub (negotiate, zstd decode)
    databento_live     - Databento Live ohlcv-1s subscription
    strategy_live      - Flow-burst signal + bracket order placement
    app                - FastAPI server: static + REST + client WS
"""
