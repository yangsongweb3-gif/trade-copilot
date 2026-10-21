"""加载本机配置（.env）和交易计划（plans.yaml）。

计划用 pydantic 校验：价格写反、区间写错这类问题在启动时就报出来，而不是等到行情触发时才出错。
"""
import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    account_usdt: float = Field(gt=0)
    risk_per_trade_pct: float = Field(gt=0, le=100)
    no_chase_pct_24h: float = Field(gt=0)


class CancelCondition(BaseModel):
    symbol: str
    close_below: float = Field(gt=0)   # 该币日线收盘价跌破这个价位


class Plan(BaseModel):
    id: str
    symbol: str
    note: str = ''
    enabled: bool = True
    buy_zone: Optional[tuple[float, float]] = None
    close_above: Optional[float] = None
    stop: Optional[float] = None
    targets: list[float] = []
    max_usdt: Optional[float] = None
    close_below_ma: Optional[int] = Field(default=None, ge=2, le=200)
    cancel_if: list[CancelCondition] = []

    @field_validator('symbol')
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode='after')
    def check_prices(self):
        if self.buy_zone:
            low, high = self.buy_zone
            if not 0 < low <= high:
                raise ValueError(f'{self.id}: buy_zone 要写成 [低价, 高价]')
            if self.stop is not None and self.stop >= low:
                raise ValueError(f'{self.id}: 止损 {self.stop} 应低于买入区下沿 {low}')
            if any(t <= high for t in self.targets):
                raise ValueError(f'{self.id}: 目标价应高于买入区上沿 {high}')
        return self


class Scanner(BaseModel):
    """强势山寨扫描：长期持仓不参与，只在市值排名区间里找比 BTC 强的币。"""
    hold: list[str] = ['BTC']     # 长期持有、不做短线的币；自己的写在 plans.yaml 的 scanner.hold
    rank_min: int = Field(default=5, ge=1)
    rank_max: int = Field(default=50, le=250)
    min_quote_volume: float = Field(default=10_000_000, ge=0)   # 24h 成交额（USDT）

    @field_validator('hold')
    @classmethod
    def upper_all(cls, v: list[str]) -> list[str]:
        return [s.upper() for s in v]


class Plans(BaseModel):
    settings: Settings
    plans: list[Plan]
    scanner: Scanner = Scanner()

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [p.id for p in self.plans]
        if len(ids) != len(set(ids)):
            raise ValueError('计划 id 不能重复')
        return self


def load_env(path: Path = ROOT / '.env') -> dict:
    """读 .env（KEY=VALUE 每行一个），系统环境变量优先。"""
    env = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env[key.strip()] = value.strip()
    for key in list(env):
        env[key] = os.environ.get(key, env[key])
    return env


def load_plans(path: Path = ROOT / 'config' / 'plans.yaml') -> Plans:
    if not path.exists():
        raise FileNotFoundError(f'找不到 {path}，先把 config/plans.example.yaml 复制成 plans.yaml')
    return Plans.model_validate(yaml.safe_load(path.read_text(encoding='utf-8')))
