"""screener — composite fundamental screener built on pit_fundamentals.

Pipeline: universe -> PIT snapshots -> F/Z/O scores -> sector-neutral
z-scores -> LASSO composite -> decile backtest -> statistical validation.
"""
