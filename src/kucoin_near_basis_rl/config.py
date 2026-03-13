from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ApiConfig:
    api_key_env: str = "KUCOIN_API_KEY"
    api_secret_env: str = "KUCOIN_API_SECRET"
    api_passphrase_env: str = "KUCOIN_API_PASSPHRASE"
    is_sandbox: bool = False
    spot_base_url: str = "https://api.kucoin.com"
    futures_base_url: str = "https://api-futures.kucoin.com"


@dataclass
class DataConfig:
    spot_symbol: str = "NEAR-USDT"
    futures_symbol: str = "NEARUSDTM"
    interval: str = "1min"
    futures_granularity_minutes: int = 1
    lookback_minutes: int = 6_000


@dataclass
class FeatureConfig:
    zscore_window: int = 120
    volatility_window: int = 60
    volume_window: int = 30
    basis_momentum_lag: int = 5


@dataclass
class BaselineConfig:
    enter_zscore: float = 1.8
    exit_zscore: float = 0.35


@dataclass
class RlConfig:
    episodes: int = 80
    alpha: float = 0.08
    gamma: float = 0.98
    epsilon_start: float = 0.25
    epsilon_end: float = 0.02
    epsilon_decay: float = 0.97
    use_baseline_guidance: bool = False
    imitation_start: float = 0.35
    imitation_end: float = 0.05
    imitation_decay: float = 0.97
    baseline_bonus: float = 0.00008
    max_steps_per_episode: int = 2_000
    quantile_bins: list[float] = field(
        default_factory=lambda: [0.05, 0.15, 0.3, 0.5, 0.7, 0.85, 0.95]
    )


@dataclass
class ExecutionConfig:
    quote_notional_usdt: float = 60.0
    futures_contract_multiplier: float = 1.0
    fee_rate_per_rebalance: float = 0.0012
    risk_penalty: float = 0.0002
    leverage: int = 2
    poll_seconds: int = 60
    default_paper_mode: bool = True
    allow_spot_short: bool = False


@dataclass
class AppConfig:
    api: ApiConfig = field(default_factory=ApiConfig)
    data: DataConfig = field(default_factory=DataConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    rl: RlConfig = field(default_factory=RlConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppConfig":
        return cls(
            api=ApiConfig(**payload.get("api", {})),
            data=DataConfig(**payload.get("data", {})),
            features=FeatureConfig(**payload.get("features", {})),
            baseline=BaselineConfig(**payload.get("baseline", {})),
            rl=RlConfig(**payload.get("rl", {})),
            execution=ExecutionConfig(**payload.get("execution", {})),
        )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return AppConfig.from_dict(payload)
