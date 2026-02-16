"""
Margin Configuration Module - Market-type-aware margin parameters.

Defines margin parameters per market type (stock futures, crypto futures, crypto perps).
All values are configurable and loaded from database when available, falling back
to code defaults.

CRITICAL: Margin rates change constantly. This module provides defaults that MUST
be overridden by real exchange data or database-stored values in production.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MarketType(Enum):
    """Classification of market types with fundamentally different margin mechanics."""
    STOCK_FUTURES = "stock_futures"       # ES, NQ, etc. via CME
    CRYPTO_FUTURES = "crypto_futures"     # BTC, ETH futures via CME (fixed expiry)
    CRYPTO_PERPETUAL = "crypto_perpetual" # Via exchanges like Binance, Bybit (no expiry)
    OPTIONS = "options"                   # SPX/SPY options via Tradier
    CRYPTO_SPOT = "crypto_spot"          # Spot crypto via Coinbase (no margin)


class MarginMode(Enum):
    """How margin is allocated across positions."""
    CROSS = "cross"       # All positions share the same margin pool
    ISOLATED = "isolated" # Each position has its own margin allocation


class LiquidationMethod(Enum):
    """How the exchange handles liquidations."""
    MARGIN_CALL = "margin_call"       # Broker issues margin call, then forced close
    AUTO_PARTIAL = "auto_partial"     # Exchange auto-liquidates smallest positions first
    AUTO_FULL = "auto_full"           # Exchange liquidates entire position at once
    NONE = "none"                     # No leverage (spot trading)


class SettlementType(Enum):
    """How daily P&L is settled."""
    DAILY_MTM = "daily_mark_to_market" # Daily settlement (stock/crypto futures)
    CONTINUOUS = "continuous"           # Continuous settlement (perpetuals)
    ON_CLOSE = "on_close"             # Settled when position is closed (options, spot)


@dataclass
class MarketConfig:
    """Configuration for a specific market type.

    These values serve as DEFAULTS. In production, they should be overridden
    by real exchange API data or database-stored values that are regularly updated.
    """
    market_type: MarketType
    exchange: str                           # CME, Binance, Bybit, Tradier, Coinbase

    # Margin mechanics
    margin_mode: MarginMode = MarginMode.CROSS
    liquidation_method: LiquidationMethod = LiquidationMethod.MARGIN_CALL

    # Margin rates
    # For stock futures: per-contract fixed $ amounts
    # For crypto: percentage of notional value
    initial_margin_rate: float = 0.0        # % of notional OR fixed $ per contract
    maintenance_margin_rate: float = 0.0    # % of notional OR fixed $ per contract
    is_margin_per_contract: bool = False     # True = fixed $ per contract, False = % of notional

    # Leverage
    max_leverage: float = 1.0               # Maximum allowed leverage
    default_leverage: float = 1.0           # Default leverage for new positions

    # Contract specs
    contract_multiplier: float = 1.0        # Notional multiplier (e.g., ES=$50/point)
    tick_size: float = 0.01                 # Minimum price increment
    tick_value: float = 0.01                # Dollar value per tick

    # Expiration
    has_expiry: bool = False
    settlement_type: SettlementType = SettlementType.ON_CLOSE

    # Funding (perpetuals only)
    has_funding_rate: bool = False
    funding_interval_hours: float = 8.0     # Typically every 8 hours

    # Liquidation thresholds (exchange-specific)
    margin_call_threshold_pct: float = 120.0   # Warn when equity < X% of maint margin
    auto_liquidation_threshold_pct: float = 100.0  # Liquidate at this %

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_type": self.market_type.value,
            "exchange": self.exchange,
            "margin_mode": self.margin_mode.value,
            "liquidation_method": self.liquidation_method.value,
            "initial_margin_rate": self.initial_margin_rate,
            "maintenance_margin_rate": self.maintenance_margin_rate,
            "is_margin_per_contract": self.is_margin_per_contract,
            "max_leverage": self.max_leverage,
            "default_leverage": self.default_leverage,
            "contract_multiplier": self.contract_multiplier,
            "tick_size": self.tick_size,
            "tick_value": self.tick_value,
            "has_expiry": self.has_expiry,
            "settlement_type": self.settlement_type.value,
            "has_funding_rate": self.has_funding_rate,
            "funding_interval_hours": self.funding_interval_hours,
            "margin_call_threshold_pct": self.margin_call_threshold_pct,
            "auto_liquidation_threshold_pct": self.auto_liquidation_threshold_pct,
        }


@dataclass
class BotMarginConfig:
    """Per-bot margin configuration.

    Each trading bot has its own margin settings that wrap around a MarketConfig.
    These are the bot-level guardrails on top of exchange-level margin rules.
    """
    bot_name: str
    market_config: MarketConfig

    # Bot-level margin limits (more conservative than exchange limits)
    max_margin_usage_pct: float = 70.0          # Never use more than 70% of available margin
    min_liquidation_distance_pct: float = 5.0   # Reject trades if liq price < 5% away
    max_effective_leverage: float = 10.0         # Absolute max leverage for this bot
    max_single_position_margin_pct: float = 40.0 # No single position > 40% of margin

    # Alert thresholds
    warning_threshold_pct: float = 60.0     # Yellow alert
    danger_threshold_pct: float = 80.0      # Orange alert
    critical_threshold_pct: float = 90.0    # Red alert

    # Auto-risk-reduction (off by default)
    auto_reduce_enabled: bool = False
    auto_reduce_margin_pct: float = 85.0        # Trigger when margin usage > this
    auto_reduce_duration_seconds: int = 300      # Must be above threshold for this long
    auto_reduce_position_pct: float = 25.0       # Reduce largest position by this %
    auto_close_liq_distance_pct: float = 3.0     # Auto-close 50% if liq < this %

    # Leverage override (if set, overrides market_config default)
    leverage_override: Optional[float] = None

    # Account identification
    account_id: Optional[str] = None        # Exchange account ID for this bot
    account_label: str = "default"          # For multi-account bots (e.g., AGAPE)

    @property
    def effective_leverage(self) -> float:
        """Get the effective leverage setting for this bot."""
        if self.leverage_override is not None:
            return min(self.leverage_override, self.market_config.max_leverage)
        return self.market_config.default_leverage

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bot_name": self.bot_name,
            "market_config": self.market_config.to_dict(),
            "max_margin_usage_pct": self.max_margin_usage_pct,
            "min_liquidation_distance_pct": self.min_liquidation_distance_pct,
            "max_effective_leverage": self.max_effective_leverage,
            "max_single_position_margin_pct": self.max_single_position_margin_pct,
            "warning_threshold_pct": self.warning_threshold_pct,
            "danger_threshold_pct": self.danger_threshold_pct,
            "critical_threshold_pct": self.critical_threshold_pct,
            "auto_reduce_enabled": self.auto_reduce_enabled,
            "effective_leverage": self.effective_leverage,
            "account_id": self.account_id,
            "account_label": self.account_label,
        }


# =============================================================================
# DEFAULT MARKET CONFIGURATIONS
# =============================================================================
# These serve as starting points. In production, values should be loaded from
# the database (margin_config table) or fetched from exchange APIs.

MARKET_DEFAULTS: Dict[str, MarketConfig] = {
    # --- CME Stock Index Futures ---
    "ES": MarketConfig(
        market_type=MarketType.STOCK_FUTURES,
        exchange="CME",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.MARGIN_CALL,
        initial_margin_rate=13200.0,       # ~$13,200 per ES contract (changes frequently)
        maintenance_margin_rate=12000.0,   # ~$12,000 per ES contract
        is_margin_per_contract=True,
        max_leverage=20.0,                 # ES notional ~$300K, margin ~$13K = ~23x
        default_leverage=1.0,              # Implicit leverage
        contract_multiplier=50.0,          # $50 per point
        tick_size=0.25,
        tick_value=12.50,                  # $12.50 per tick
        has_expiry=True,
        settlement_type=SettlementType.DAILY_MTM,
    ),
    "NQ": MarketConfig(
        market_type=MarketType.STOCK_FUTURES,
        exchange="CME",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.MARGIN_CALL,
        initial_margin_rate=18700.0,       # ~$18,700 per NQ contract
        maintenance_margin_rate=17000.0,
        is_margin_per_contract=True,
        max_leverage=20.0,
        default_leverage=1.0,
        contract_multiplier=20.0,          # $20 per point
        tick_size=0.25,
        tick_value=5.00,
        has_expiry=True,
        settlement_type=SettlementType.DAILY_MTM,
    ),
    "MES": MarketConfig(
        market_type=MarketType.STOCK_FUTURES,
        exchange="CME",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.MARGIN_CALL,
        initial_margin_rate=1320.0,        # Micro ES = 1/10 of ES
        maintenance_margin_rate=1200.0,
        is_margin_per_contract=True,
        max_leverage=20.0,
        default_leverage=1.0,
        contract_multiplier=5.0,           # $5 per point
        tick_size=0.25,
        tick_value=1.25,
        has_expiry=True,
        settlement_type=SettlementType.DAILY_MTM,
    ),
    "MNQ": MarketConfig(
        market_type=MarketType.STOCK_FUTURES,
        exchange="CME",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.MARGIN_CALL,
        initial_margin_rate=1870.0,        # Micro NQ = 1/10 of NQ
        maintenance_margin_rate=1700.0,
        is_margin_per_contract=True,
        max_leverage=20.0,
        default_leverage=1.0,
        contract_multiplier=2.0,           # $2 per point
        tick_size=0.25,
        tick_value=0.50,
        has_expiry=True,
        settlement_type=SettlementType.DAILY_MTM,
    ),

    # --- CME Crypto Futures ---
    "/MBT": MarketConfig(
        market_type=MarketType.CRYPTO_FUTURES,
        exchange="CME",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.MARGIN_CALL,
        initial_margin_rate=1320.0,        # CME Micro Bitcoin Futures
        maintenance_margin_rate=1200.0,
        is_margin_per_contract=True,
        max_leverage=20.0,
        default_leverage=1.0,
        contract_multiplier=0.1,           # 0.1 BTC per contract
        tick_size=5.0,
        tick_value=0.50,
        has_expiry=True,
        settlement_type=SettlementType.DAILY_MTM,
    ),
    "/MET": MarketConfig(
        market_type=MarketType.CRYPTO_FUTURES,
        exchange="CME",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.MARGIN_CALL,
        initial_margin_rate=660.0,         # CME Micro Ether Futures
        maintenance_margin_rate=600.0,
        is_margin_per_contract=True,
        max_leverage=15.0,
        default_leverage=1.0,
        contract_multiplier=0.1,           # 0.1 ETH per contract
        tick_size=0.05,
        tick_value=0.005,
        has_expiry=True,
        settlement_type=SettlementType.DAILY_MTM,
    ),

    "/XRP": MarketConfig(
        market_type=MarketType.CRYPTO_FUTURES,
        exchange="CME",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.MARGIN_CALL,
        initial_margin_rate=1650.0,        # CME XRP Futures
        maintenance_margin_rate=1500.0,
        is_margin_per_contract=True,
        max_leverage=15.0,
        default_leverage=1.0,
        contract_multiplier=2500.0,        # 2,500 XRP per contract
        tick_size=0.0001,
        tick_value=0.25,
        has_expiry=True,
        settlement_type=SettlementType.DAILY_MTM,
    ),

    # --- Crypto Perpetual Futures ---
    "BTC-PERP": MarketConfig(
        market_type=MarketType.CRYPTO_PERPETUAL,
        exchange="PERPETUAL",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.AUTO_FULL,
        initial_margin_rate=0.01,          # 1% = 100x max leverage
        maintenance_margin_rate=0.005,     # 0.5% maintenance
        is_margin_per_contract=False,      # % of notional
        max_leverage=100.0,
        default_leverage=10.0,
        contract_multiplier=1.0,           # 1 BTC per unit
        tick_size=0.01,
        tick_value=0.01,
        has_expiry=False,
        settlement_type=SettlementType.CONTINUOUS,
        has_funding_rate=True,
        funding_interval_hours=8.0,
    ),
    "ETH-PERP": MarketConfig(
        market_type=MarketType.CRYPTO_PERPETUAL,
        exchange="PERPETUAL",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.AUTO_FULL,
        initial_margin_rate=0.02,          # 2% = 50x max leverage
        maintenance_margin_rate=0.01,      # 1% maintenance
        is_margin_per_contract=False,
        max_leverage=50.0,
        default_leverage=10.0,
        contract_multiplier=1.0,
        tick_size=0.01,
        tick_value=0.01,
        has_expiry=False,
        settlement_type=SettlementType.CONTINUOUS,
        has_funding_rate=True,
        funding_interval_hours=8.0,
    ),
    "XRP-PERP": MarketConfig(
        market_type=MarketType.CRYPTO_PERPETUAL,
        exchange="PERPETUAL",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.AUTO_FULL,
        initial_margin_rate=0.05,          # 5% = 20x max leverage
        maintenance_margin_rate=0.025,
        is_margin_per_contract=False,
        max_leverage=20.0,
        default_leverage=5.0,
        contract_multiplier=1.0,
        tick_size=0.0001,
        tick_value=0.0001,
        has_expiry=False,
        settlement_type=SettlementType.CONTINUOUS,
        has_funding_rate=True,
        funding_interval_hours=8.0,
    ),
    "DOGE-PERP": MarketConfig(
        market_type=MarketType.CRYPTO_PERPETUAL,
        exchange="PERPETUAL",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.AUTO_FULL,
        initial_margin_rate=0.05,
        maintenance_margin_rate=0.025,
        is_margin_per_contract=False,
        max_leverage=20.0,
        default_leverage=5.0,
        contract_multiplier=1.0,
        tick_size=0.00001,
        tick_value=0.00001,
        has_expiry=False,
        settlement_type=SettlementType.CONTINUOUS,
        has_funding_rate=True,
        funding_interval_hours=8.0,
    ),
    "SHIB-PERP": MarketConfig(
        market_type=MarketType.CRYPTO_PERPETUAL,
        exchange="PERPETUAL",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.AUTO_FULL,
        initial_margin_rate=0.10,          # 10% = 10x max leverage
        maintenance_margin_rate=0.05,
        is_margin_per_contract=False,
        max_leverage=10.0,
        default_leverage=3.0,
        contract_multiplier=1.0,
        tick_size=0.00000001,
        tick_value=0.00000001,
        has_expiry=False,
        settlement_type=SettlementType.CONTINUOUS,
        has_funding_rate=True,
        funding_interval_hours=8.0,
    ),

    # --- Options (SPX/SPY via Tradier) ---
    "SPX": MarketConfig(
        market_type=MarketType.OPTIONS,
        exchange="TRADIER",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.MARGIN_CALL,
        initial_margin_rate=0.0,           # Options: margin = max loss of spread
        maintenance_margin_rate=0.0,       # Defined spreads have fixed max loss
        is_margin_per_contract=False,
        max_leverage=1.0,                  # Options risk is defined by spread width
        default_leverage=1.0,
        contract_multiplier=100.0,         # $100 per point
        tick_size=0.05,
        tick_value=5.00,
        has_expiry=True,
        settlement_type=SettlementType.ON_CLOSE,
    ),
    "SPY": MarketConfig(
        market_type=MarketType.OPTIONS,
        exchange="TRADIER",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.MARGIN_CALL,
        initial_margin_rate=0.0,
        maintenance_margin_rate=0.0,
        is_margin_per_contract=False,
        max_leverage=1.0,
        default_leverage=1.0,
        contract_multiplier=100.0,
        tick_size=0.01,
        tick_value=1.00,
        has_expiry=True,
        settlement_type=SettlementType.ON_CLOSE,
    ),

    # --- Crypto Spot (Coinbase) ---
    "ETH-USD": MarketConfig(
        market_type=MarketType.CRYPTO_SPOT,
        exchange="COINBASE",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.NONE,
        initial_margin_rate=1.0,           # 100% - spot = no leverage
        maintenance_margin_rate=1.0,
        is_margin_per_contract=False,
        max_leverage=1.0,
        default_leverage=1.0,
        contract_multiplier=1.0,
        tick_size=0.01,
        tick_value=0.01,
        has_expiry=False,
        settlement_type=SettlementType.ON_CLOSE,
    ),
    "BTC-USD": MarketConfig(
        market_type=MarketType.CRYPTO_SPOT,
        exchange="COINBASE",
        margin_mode=MarginMode.CROSS,
        liquidation_method=LiquidationMethod.NONE,
        initial_margin_rate=1.0,
        maintenance_margin_rate=1.0,
        is_margin_per_contract=False,
        max_leverage=1.0,
        default_leverage=1.0,
        contract_multiplier=1.0,
        tick_size=0.01,
        tick_value=0.01,
        has_expiry=False,
        settlement_type=SettlementType.ON_CLOSE,
    ),
}


# =============================================================================
# BOT-TO-INSTRUMENT MAPPING
# =============================================================================
# Maps each AlphaGEX bot to its instrument and market configuration.

BOT_INSTRUMENT_MAP: Dict[str, str] = {
    # Options bots (SPX Iron Condors)
    "ANCHOR": "SPX",
    "FORTRESS": "SPX",
    "SAMSON": "SPX",
    "GIDEON": "SPY",
    "SOLOMON": "SPX",

    # CME Crypto Futures
    "AGAPE_BTC": "/MBT",
    "AGAPE_XRP": "/XRP",

    # Crypto Perpetuals
    "AGAPE_BTC_PERP": "BTC-PERP",
    "AGAPE_ETH_PERP": "ETH-PERP",
    "AGAPE_XRP_PERP": "XRP-PERP",
    "AGAPE_DOGE_PERP": "DOGE-PERP",
    "AGAPE_SHIB_PERP": "SHIB-PERP",

    # Crypto Spot
    "AGAPE_SPOT": "ETH-USD",       # Primary ticker

    # Stock Index Futures
    "VALOR": "MES",
    "PHOENIX": "MES",
    "ATLAS": "SPX",
    "HERMES": "MNQ",
}


def get_default_market_config(instrument: str) -> Optional[MarketConfig]:
    """Get the default market configuration for an instrument.

    Args:
        instrument: The trading instrument (e.g., 'ES', 'BTC-PERP', 'SPX')

    Returns:
        MarketConfig or None if instrument not recognized
    """
    return MARKET_DEFAULTS.get(instrument)


def get_bot_margin_config(
    bot_name: str,
    db=None,
    override_instrument: Optional[str] = None,
) -> Optional[BotMarginConfig]:
    """Get the margin configuration for a specific bot.

    Loads from database if available, falls back to code defaults.

    Args:
        bot_name: The bot identifier (e.g., 'ANCHOR', 'AGAPE_BTC_PERP')
        db: Optional database connection for loading overrides
        override_instrument: Override the default instrument for this bot

    Returns:
        BotMarginConfig or None if bot not recognized
    """
    instrument = override_instrument or BOT_INSTRUMENT_MAP.get(bot_name)
    if not instrument:
        logger.warning(f"No instrument mapping for bot: {bot_name}")
        return None

    market_config = get_default_market_config(instrument)
    if not market_config:
        logger.warning(f"No market config for instrument: {instrument}")
        return None

    # Create bot config with defaults
    bot_config = BotMarginConfig(
        bot_name=bot_name,
        market_config=market_config,
    )

    # Load overrides from database if available
    if db:
        try:
            _load_bot_config_from_db(bot_config, db)
        except Exception as e:
            logger.warning(f"Failed to load margin config from DB for {bot_name}: {e}")

    return bot_config


def _load_bot_config_from_db(config: BotMarginConfig, db) -> None:
    """Load margin configuration overrides from the database.

    Reads from the `margin_bot_config` table if it exists.
    Falls back silently if table doesn't exist yet.
    """
    try:
        conn = db if hasattr(db, 'cursor') else None
        if conn is None:
            try:
                from database_adapter import get_connection
                conn = get_connection()
            except Exception:
                return

        cursor = conn.cursor()

        # Check if margin_bot_config table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'margin_bot_config'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            cursor.close()
            if not hasattr(db, 'cursor'):
                conn.close()
            return

        cursor.execute("""
            SELECT config_key, config_value
            FROM margin_bot_config
            WHERE bot_name = %s AND is_active = true
        """, (config.bot_name,))

        rows = cursor.fetchall()
        for row in rows:
            key, value = row[0], row[1]
            if hasattr(config, key):
                attr_type = type(getattr(config, key))
                try:
                    if attr_type == float:
                        setattr(config, key, float(value))
                    elif attr_type == int:
                        setattr(config, key, int(value))
                    elif attr_type == bool:
                        setattr(config, key, str(value).lower() in ("true", "1", "yes"))
                    elif attr_type == str:
                        setattr(config, key, str(value))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid config value for {config.bot_name}.{key}: {e}")

        cursor.close()
        if not hasattr(db, 'cursor'):
            conn.close()

    except Exception as e:
        logger.debug(f"Could not load margin config from DB: {e}")
