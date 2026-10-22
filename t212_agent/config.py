"""Configuration loaded from environment variables (optionally a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env loader so we don't need python-dotenv. Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # --- Trading 212 credentials / environment ---
    api_key: str = ""
    api_secret: str = ""
    environment: str = "demo"  # "demo" (paper) or "live"
    dry_run: bool = True  # log orders instead of sending them

    # --- Universe: T212 ticker -> market-data (Yahoo) symbol ---
    symbols: dict[str, str] = field(default_factory=dict)

    # --- Market session (exchange local time) ---
    timezone: str = "America/New_York"
    session_open: str = "09:30"
    session_close: str = "16:00"
    no_new_entries_minutes_before_close: int = 30
    flatten_minutes_before_close: int = 10
    skip_first_minutes: int = 15  # let the opening auction noise settle

    # --- Strategy ---
    bar_interval: str = "5m"
    fast_ema: int = 9
    slow_ema: int = 21
    atr_period: int = 14
    stop_atr_mult: float = 1.5
    target_atr_mult: float = 3.0
    poll_seconds: int = 60

    # --- Risk ---
    risk_per_trade_pct: float = 0.5  # % of account value risked per trade
    max_position_pct: float = 20.0  # max % of account value in one position
    max_open_positions: int = 3
    max_daily_loss_pct: float = 2.0  # stop trading for the day past this drawdown
    max_trades_per_day: int = 10

    log_file: str = "trades.jsonl"

    @property
    def base_url(self) -> str:
        return f"https://{self.environment}.trading212.com/api/v0"

    def validate(self) -> None:
        if self.environment not in {"demo", "live"}:
            raise ValueError("T212_ENV must be 'demo' or 'live'")
        if not self.api_key:
            raise ValueError("T212_API_KEY is not set")
        if not self.symbols:
            raise ValueError("SYMBOLS is empty")
        if self.environment == "live" and not self.dry_run:
            if os.getenv("I_UNDERSTAND_THIS_TRADES_REAL_MONEY") != "yes":
                raise ValueError(
                    "Live trading requires I_UNDERSTAND_THIS_TRADES_REAL_MONEY=yes"
                )


def parse_symbols(raw: str) -> dict[str, str]:
    """Parse 'AAPL_US_EQ:AAPL,MSFT_US_EQ:MSFT' into a dict.

    If the data symbol is omitted ('AAPL_US_EQ') it is derived from the T212 ticker.
    """
    out: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            t212, data = item.split(":", 1)
        else:
            t212, data = item, item.split("_")[0]
        out[t212.strip()] = data.strip()
    return out


def load_config() -> Config:
    _load_dotenv()
    cfg = Config(
        api_key=os.getenv("T212_API_KEY", ""),
        api_secret=os.getenv("T212_API_SECRET", ""),
        environment=os.getenv("T212_ENV", "demo").lower(),
        dry_run=_bool("DRY_RUN", True),
        symbols=parse_symbols(
            os.getenv("SYMBOLS", "AAPL_US_EQ:AAPL,MSFT_US_EQ:MSFT,NVDA_US_EQ:NVDA")
        ),
    )
    int_fields = {
        "poll_seconds", "fast_ema", "slow_ema", "atr_period", "max_open_positions",
        "max_trades_per_day", "skip_first_minutes", "no_new_entries_minutes_before_close",
        "flatten_minutes_before_close",
    }
    float_fields = {
        "stop_atr_mult", "target_atr_mult", "risk_per_trade_pct", "max_position_pct",
        "max_daily_loss_pct",
    }
    str_fields = {"timezone", "session_open", "session_close", "bar_interval", "log_file"}
    for name in int_fields | float_fields | str_fields:
        raw = os.getenv(name.upper())
        if raw is None:
            continue
        if name in int_fields:
            setattr(cfg, name, int(raw))
        elif name in float_fields:
            setattr(cfg, name, float(raw))
        else:
            setattr(cfg, name, raw)
    return cfg
