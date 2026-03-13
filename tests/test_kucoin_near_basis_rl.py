from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from kucoin_near_basis_rl.baseline import BaselinePolicy
from kucoin_near_basis_rl.config import FeatureConfig
from kucoin_near_basis_rl.env import BasisTradingEnv
from kucoin_near_basis_rl.features import FEATURE_COLUMNS, build_feature_frame
from kucoin_near_basis_rl.kucoin_api import KuCoinExecutionClient
from kucoin_near_basis_rl.qlearning import (
    QLearningAgent,
    StateDiscretizer,
    build_quantile_bins,
    train_qlearning,
)


def _synthetic_raw(rows: int = 500) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ts = [start + timedelta(minutes=i) for i in range(rows)]
    x = np.linspace(0.0, 30.0, rows)
    spot = 5.0 + 0.04 * np.sin(x) + 0.005 * np.cos(2.0 * x)
    basis = 0.002 * np.sin(0.5 * x)
    futures = spot * (1.0 + basis)
    spot_volume = 1000 + 120 * np.sin(0.7 * x)
    futures_volume = 1100 + 80 * np.cos(0.5 * x)
    return pd.DataFrame(
        {
            "timestamp": ts,
            "spot_close": spot,
            "futures_close": futures,
            "spot_volume": spot_volume,
            "futures_volume": futures_volume,
        }
    )


def test_feature_frame_has_required_columns() -> None:
    raw = _synthetic_raw()
    frame = build_feature_frame(raw, FeatureConfig())
    assert not frame.empty
    for col in FEATURE_COLUMNS:
        assert col in frame.columns


def test_qlearning_training_runs() -> None:
    raw = _synthetic_raw()
    frame = build_feature_frame(raw, FeatureConfig())
    baseline = BaselinePolicy(enter_zscore=1.2, exit_zscore=0.25)

    baseline_positions = []
    position = 0
    for row in frame.itertuples():
        position = baseline.decide_position(float(row.basis_zscore), position)
        baseline_positions.append(position)

    env = BasisTradingEnv(
        feature_frame=frame,
        observation_columns=FEATURE_COLUMNS,
        fee_rate_per_rebalance=0.0005,
        risk_penalty=0.0001,
    )
    bins = build_quantile_bins(frame, FEATURE_COLUMNS, [0.1, 0.3, 0.5, 0.7, 0.9])
    discretizer = StateDiscretizer(bin_edges=bins)
    agent = QLearningAgent(num_actions=3, alpha=0.1, gamma=0.98, seed=1)
    rewards = train_qlearning(
        env=env,
        agent=agent,
        discretizer=discretizer,
        baseline_positions=baseline_positions,
        episodes=5,
        epsilon_start=0.25,
        epsilon_end=0.05,
        epsilon_decay=0.9,
        imitation_start=0.25,
        imitation_end=0.05,
        imitation_decay=0.9,
        baseline_bonus=0.00005,
        max_steps_per_episode=300,
    )
    assert len(rewards) == 5
    assert len(agent.q_table) > 0


def test_construct_with_supported_kwargs_handles_sdk_signature_variants() -> None:
    class OldStyleClient:
        def __init__(self, key: str, secret: str, passphrase: str) -> None:
            self.key = key
            self.secret = secret
            self.passphrase = passphrase

    class NewStyleClient:
        def __init__(
            self,
            key: str,
            secret: str,
            passphrase: str,
            is_sandbox: bool = False,
            url: str | None = None,
        ) -> None:
            self.key = key
            self.secret = secret
            self.passphrase = passphrase
            self.is_sandbox = is_sandbox
            self.url = url

    kwargs = {
        "key": "k",
        "secret": "s",
        "passphrase": "p",
        "is_sandbox": True,
        "url": "https://example.com",
        "unexpected": "ignored",
    }
    old = KuCoinExecutionClient._construct_with_supported_kwargs(OldStyleClient, **kwargs)
    new = KuCoinExecutionClient._construct_with_supported_kwargs(NewStyleClient, **kwargs)

    assert old.key == "k"
    assert old.secret == "s"
    assert old.passphrase == "p"
    assert new.is_sandbox is True
    assert new.url == "https://example.com"
