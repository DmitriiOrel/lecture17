from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from .config import ApiConfig, DataConfig


SPOT_INTERVAL_SECONDS: dict[str, int] = {
    "1min": 60,
    "3min": 180,
    "5min": 300,
    "15min": 900,
    "30min": 1_800,
    "1hour": 3_600,
    "2hour": 7_200,
    "4hour": 14_400,
    "6hour": 21_600,
    "8hour": 28_800,
    "12hour": 43_200,
    "1day": 86_400,
}


@dataclass
class PriceSnapshot:
    spot_price: float
    futures_price: float


class KuCoinPublicDataClient:
    def __init__(self, api_cfg: ApiConfig, timeout_sec: int = 10) -> None:
        self.api_cfg = api_cfg
        self.timeout_sec = timeout_sec
        self.session = requests.Session()

    def _get(self, base_url: str, path: str, params: dict[str, Any]) -> Any:
        response = self.session.get(
            f"{base_url}{path}",
            params=params,
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "200000":
            raise RuntimeError(f"KuCoin request failed: {payload}")
        return payload["data"]

    def fetch_price_snapshot(self, spot_symbol: str, futures_symbol: str) -> PriceSnapshot:
        spot = self._get(
            self.api_cfg.spot_base_url,
            "/api/v1/market/orderbook/level1",
            {"symbol": spot_symbol},
        )
        futures = self._get(
            self.api_cfg.futures_base_url,
            "/api/v1/ticker",
            {"symbol": futures_symbol},
        )
        return PriceSnapshot(spot_price=float(spot["price"]), futures_price=float(futures["price"]))

    def fetch_spot_candles(
        self,
        symbol: str,
        interval: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> pd.DataFrame:
        interval_sec = SPOT_INTERVAL_SECONDS.get(interval)
        if interval_sec is None:
            raise ValueError(f"Unsupported spot interval: {interval}")
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())
        # KuCoin spot endpoint returns at most ~1500 candles per request.
        # Use deterministic windows to avoid relying on response sort order.
        window_sec = interval_sec * 1_200
        cursor_start = start_ts
        rows: list[dict[str, Any]] = []

        while cursor_start <= end_ts:
            cursor_end = min(end_ts, cursor_start + window_sec)
            data = self._get(
                self.api_cfg.spot_base_url,
                "/api/v1/market/candles",
                {
                    "type": interval,
                    "symbol": symbol,
                    "startAt": cursor_start,
                    "endAt": cursor_end,
                },
            )
            if data:
                rows.extend(self._parse_spot_candle(raw) for raw in data)
            cursor_start = cursor_end + interval_sec

        if not rows:
            raise RuntimeError("No spot candles received from KuCoin.")
        frame = pd.DataFrame(rows).drop_duplicates(subset=["ts_sec"]).sort_values("ts_sec")
        return frame[(frame["ts_sec"] >= start_ts) & (frame["ts_sec"] <= end_ts)].reset_index(drop=True)

    def fetch_futures_candles(
        self,
        symbol: str,
        granularity_minutes: int,
        start_dt: datetime,
        end_dt: datetime,
    ) -> pd.DataFrame:
        granularity_ms = granularity_minutes * 60_000
        start_ms = int(start_dt.timestamp() * 1_000)
        end_ms = int(end_dt.timestamp() * 1_000)
        # KuCoin futures kline query usually returns a limited page.
        # Window requests make pagination stable even if ordering changes.
        window_ms = granularity_ms * 180
        cursor_from = start_ms
        rows: list[dict[str, Any]] = []

        while cursor_from <= end_ms:
            cursor_to = min(end_ms, cursor_from + window_ms)
            data = self._get(
                self.api_cfg.futures_base_url,
                "/api/v1/kline/query",
                {
                    "symbol": symbol,
                    "granularity": granularity_minutes,
                    "from": cursor_from,
                    "to": cursor_to,
                },
            )
            if data:
                rows.extend(self._parse_futures_candle(raw) for raw in data)
            cursor_from = cursor_to + granularity_ms

        if not rows:
            raise RuntimeError("No futures candles received from KuCoin.")
        frame = pd.DataFrame(rows).drop_duplicates(subset=["ts_ms"]).sort_values("ts_ms")
        return frame[(frame["ts_ms"] >= start_ms) & (frame["ts_ms"] <= end_ms)].reset_index(drop=True)

    def fetch_merged_candles(
        self,
        data_cfg: DataConfig,
        start_dt: datetime,
        end_dt: datetime,
    ) -> pd.DataFrame:
        spot = self.fetch_spot_candles(
            symbol=data_cfg.spot_symbol,
            interval=data_cfg.interval,
            start_dt=start_dt,
            end_dt=end_dt,
        )
        futures = self.fetch_futures_candles(
            symbol=data_cfg.futures_symbol,
            granularity_minutes=data_cfg.futures_granularity_minutes,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        spot["timestamp"] = pd.to_datetime(spot["ts_sec"], unit="s", utc=True).dt.floor("min")
        futures["timestamp"] = pd.to_datetime(futures["ts_ms"], unit="ms", utc=True).dt.floor("min")

        merged = pd.merge(
            spot[["timestamp", "close", "volume"]].rename(
                columns={"close": "spot_close", "volume": "spot_volume"}
            ),
            futures[["timestamp", "close", "volume"]].rename(
                columns={"close": "futures_close", "volume": "futures_volume"}
            ),
            on="timestamp",
            how="inner",
        ).sort_values("timestamp")
        if merged.empty:
            raise RuntimeError("Merged spot/futures dataframe is empty.")
        return merged.reset_index(drop=True)

    @staticmethod
    def _parse_spot_candle(raw: list[Any]) -> dict[str, Any]:
        # Spot format (KuCoin): [time, open, close, high, low, volume, turnover]
        return {
            "ts_sec": int(raw[0]),
            "open": float(raw[1]),
            "close": float(raw[2]),
            "high": float(raw[3]),
            "low": float(raw[4]),
            "volume": float(raw[5]),
            "turnover": float(raw[6]) if len(raw) > 6 else 0.0,
        }

    @staticmethod
    def _parse_futures_candle(raw: list[Any]) -> dict[str, Any]:
        # Futures format in KuCoin docs: [time, open, high, low, close, volume, turnover]
        ts = int(raw[0])
        if ts < 10**12:
            ts *= 1_000
        close_idx = 4 if len(raw) > 4 else 2
        vol_idx = 5 if len(raw) > 5 else len(raw) - 1
        return {
            "ts_ms": ts,
            "open": float(raw[1]),
            "high": float(raw[2]),
            "low": float(raw[3]),
            "close": float(raw[close_idx]),
            "volume": float(raw[vol_idx]),
            "turnover": float(raw[6]) if len(raw) > 6 else 0.0,
        }

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def utc_lookback(minutes: int) -> tuple[datetime, datetime]:
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(minutes=minutes)
        return start_dt, end_dt


class KuCoinExecutionClient:
    def __init__(self, api_cfg: ApiConfig, dry_run: bool = True) -> None:
        self.api_cfg = api_cfg
        self.dry_run = dry_run
        self._spot_trade = None
        self._futures_trade = None
        if not self.dry_run:
            self._init_sdk_clients()

    def _init_sdk_clients(self) -> None:
        try:
            from kucoin.client import Trade as SpotTradeClient  # type: ignore
            from kucoin_futures.client import Trade as FuturesTradeClient  # type: ignore
        except Exception as exc:
            if "pkg_resources" in str(exc):
                raise RuntimeError(
                    "kucoin-python SDK failed to import because pkg_resources is unavailable. "
                    "Run: python -m pip install \"setuptools<81\""
                ) from exc
            raise RuntimeError(
                "KuCoin SDK is not installed. Install kucoin-python and kucoin-futures-python."
            ) from exc

        api_key = os.getenv(self.api_cfg.api_key_env, "")
        api_secret = os.getenv(self.api_cfg.api_secret_env, "")
        passphrase = os.getenv(self.api_cfg.api_passphrase_env, "")
        if not api_key or not api_secret or not passphrase:
            raise RuntimeError(
                "Missing API credentials in env vars: "
                f"{self.api_cfg.api_key_env}, {self.api_cfg.api_secret_env}, {self.api_cfg.api_passphrase_env}"
            )

        auth_candidates = {
            "key": api_key,
            "secret": api_secret,
            "passphrase": passphrase,
            "api_key": api_key,
            "api_secret": api_secret,
            "api_passphrase": passphrase,
            "password": passphrase,
        }

        spot_candidates = {
            **auth_candidates,
            "is_sandbox": self.api_cfg.is_sandbox,
            "sandbox": self.api_cfg.is_sandbox,
            "url": "https://openapi-sandbox.kucoin.com"
            if self.api_cfg.is_sandbox
            else self.api_cfg.spot_base_url,
            "base_url": "https://openapi-sandbox.kucoin.com"
            if self.api_cfg.is_sandbox
            else self.api_cfg.spot_base_url,
        }
        futures_candidates = {
            **auth_candidates,
            "is_sandbox": self.api_cfg.is_sandbox,
            "sandbox": self.api_cfg.is_sandbox,
            "url": "https://api-sandbox-futures.kucoin.com"
            if self.api_cfg.is_sandbox
            else self.api_cfg.futures_base_url,
            "base_url": "https://api-sandbox-futures.kucoin.com"
            if self.api_cfg.is_sandbox
            else self.api_cfg.futures_base_url,
        }

        self._spot_trade = self._construct_with_supported_kwargs(SpotTradeClient, **spot_candidates)
        self._futures_trade = self._construct_with_supported_kwargs(
            FuturesTradeClient, **futures_candidates
        )

    def rebalance_basis_position(
        self,
        current_position: int,
        target_position: int,
        spot_symbol: str,
        futures_symbol: str,
        spot_size: float,
        futures_size: int,
        leverage: int,
    ) -> dict[str, Any]:
        if target_position not in (-1, 0, 1):
            raise ValueError("target_position must be one of {-1, 0, 1}")
        if current_position not in (-1, 0, 1):
            raise ValueError("current_position must be one of {-1, 0, 1}")
        if target_position == current_position:
            return {"changed": False, "orders": []}

        orders: list[dict[str, Any]] = []
        if current_position != 0:
            orders.extend(
                self._send_hedged_pair(
                    position=-current_position,
                    spot_symbol=spot_symbol,
                    futures_symbol=futures_symbol,
                    spot_size=spot_size,
                    futures_size=futures_size,
                    leverage=leverage,
                    reduce_only=True,
                )
            )
        if target_position != 0:
            orders.extend(
                self._send_hedged_pair(
                    position=target_position,
                    spot_symbol=spot_symbol,
                    futures_symbol=futures_symbol,
                    spot_size=spot_size,
                    futures_size=futures_size,
                    leverage=leverage,
                    reduce_only=False,
                )
            )
        return {"changed": True, "orders": orders}

    def _send_hedged_pair(
        self,
        position: int,
        spot_symbol: str,
        futures_symbol: str,
        spot_size: float,
        futures_size: int,
        leverage: int,
        reduce_only: bool,
    ) -> list[dict[str, Any]]:
        if position == 1:
            futures_side = "buy"
            spot_side = "sell"
        elif position == -1:
            futures_side = "sell"
            spot_side = "buy"
        else:
            return []

        if self.dry_run:
            return [
                {
                    "market": "futures",
                    "symbol": futures_symbol,
                    "side": futures_side,
                    "size": futures_size,
                    "reduce_only": reduce_only,
                },
                {
                    "market": "spot",
                    "symbol": spot_symbol,
                    "side": spot_side,
                    "size": spot_size,
                    "reduce_only": reduce_only,
                },
            ]

        futures_result = self._call_with_supported_kwargs(
            self._futures_trade.create_market_order,
            futures_symbol,
            futures_side,
            size=futures_size,
            leverage=leverage,
            reduceOnly=reduce_only,
            reduce_only=reduce_only,
        )
        spot_result = self._call_with_supported_kwargs(
            self._spot_trade.create_market_order,
            spot_symbol,
            spot_side,
            size=str(spot_size),
        )
        return [
            {"market": "futures", "result": futures_result},
            {"market": "spot", "result": spot_result},
        ]

    @staticmethod
    def _call_with_supported_kwargs(method: Any, *args: Any, **kwargs: Any) -> Any:
        signature = inspect.signature(method)
        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
            return method(*args, **kwargs)
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in signature.parameters}
        return method(*args, **filtered_kwargs)

    @staticmethod
    def _construct_with_supported_kwargs(factory: Any, **kwargs: Any) -> Any:
        signature = inspect.signature(factory)
        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
            return factory(**kwargs)
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in signature.parameters}
        return factory(**filtered_kwargs)
