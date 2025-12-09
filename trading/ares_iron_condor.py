"""
ARES - Aggressive Iron Condor Trading Bot
==========================================

Named after the Greek God of War - aggressive and relentless.

TARGET: 10% Monthly Returns via Daily Iron Condor Trading

THE MATH FOR 10% MONTHLY:
=========================
- 20 trading days/month
- Need ~0.5% per day to compound to 10% monthly
- Iron Condor at 1 SD collects ~$3-5 on $10 wide spread
- Win rate at 1 SD: ~68% for BOTH sides to be profitable
- With 10% risk per trade and compounding, this achieves the target

AGGRESSIVE PARAMETERS:
=====================
- Trade EVERY weekday (Mon-Fri)
- Iron Condor: Bull Put + Bear Call simultaneously
- 10% risk per trade (aggressive Kelly)
- 1 SD strikes (balanced risk/reward)
- NO stop loss - let options expire (defined risk)
- Compound daily - reinvest gains immediately

Usage:
    from trading.ares_iron_condor import ARESTrader
    ares = ARESTrader(initial_capital=100_000)
    ares.run_daily_cycle()
"""

import os
import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo

# Import Tradier for execution
try:
    from data.tradier_data_fetcher import (
        TradierDataFetcher,
        OrderSide,
        OrderType,
        OrderDuration,
        OptionContract
    )
    TRADIER_AVAILABLE = True
except ImportError:
    TRADIER_AVAILABLE = False
    TradierDataFetcher = None

# Import decision logger
try:
    from trading.decision_logger import (
        DecisionLogger, TradeDecision, DecisionType,
        DataSource, TradeLeg, MarketContext, DecisionReasoning, BotName
    )
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False
    DecisionLogger = None

logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Trading execution mode"""
    PAPER = "paper"       # Sandbox/Paper trading
    LIVE = "live"         # Live trading with real money
    BACKTEST = "backtest" # Backtesting mode (no execution)


@dataclass
class IronCondorPosition:
    """Represents an open Iron Condor position"""
    position_id: str
    open_date: str
    expiration: str

    # Strikes
    put_long_strike: float
    put_short_strike: float
    call_short_strike: float
    call_long_strike: float

    # Credits received
    put_credit: float
    call_credit: float
    total_credit: float

    # Position details
    contracts: int
    spread_width: float
    max_loss: float

    # Order IDs from broker
    put_spread_order_id: str = ""
    call_spread_order_id: str = ""

    # Status
    status: str = "open"  # open, closed, expired
    close_date: str = ""
    close_price: float = 0
    realized_pnl: float = 0

    # Market data at entry
    underlying_price_at_entry: float = 0
    vix_at_entry: float = 0
    expected_move: float = 0


@dataclass
class ARESConfig:
    """Configuration for ARES trading bot"""
    # Risk parameters
    risk_per_trade_pct: float = 10.0     # 10% of capital per trade
    spread_width: float = 10.0            # $10 wide spreads (SPX)
    spread_width_spy: float = 2.0         # $2 wide spreads (SPY for sandbox)
    sd_multiplier: float = 1.0            # 1 SD strikes

    # Execution parameters
    ticker: str = "SPX"                   # Trade SPX in production
    sandbox_ticker: str = "SPY"           # Trade SPY in sandbox (better data)
    use_0dte: bool = True                 # Use 0DTE options
    max_contracts: int = 1000             # Max contracts per trade
    min_credit_per_spread: float = 1.50   # Minimum credit to accept (SPX)
    min_credit_per_spread_spy: float = 0.15  # Minimum credit (SPY ~1/10)

    # Trade management
    use_stop_loss: bool = False           # NO stop loss (defined risk)
    profit_target_pct: float = 50         # Take profit at 50% of max

    # Trading schedule
    trade_every_day: bool = True          # Trade Mon-Fri
    entry_time_start: str = "09:45"       # Entry window start
    entry_time_end: str = "10:30"         # Entry window end


class ARESTrader:
    """
    ARES - Aggressive Iron Condor Trading Bot

    Executes daily 0DTE Iron Condors targeting 10% monthly returns.
    Uses Tradier sandbox for paper trading, can switch to live.
    """

    def __init__(
        self,
        mode: TradingMode = TradingMode.PAPER,
        initial_capital: float = 100_000,
        config: ARESConfig = None
    ):
        """
        Initialize ARES trader.

        Args:
            mode: Trading mode (PAPER, LIVE, or BACKTEST)
            initial_capital: Starting capital for position sizing
            config: Optional custom configuration
        """
        self.mode = mode
        self.capital = initial_capital
        self.config = config or ARESConfig()

        self.tz = ZoneInfo("America/New_York")

        # Initialize Tradier client
        self.tradier = None
        if TRADIER_AVAILABLE and mode != TradingMode.BACKTEST:
            try:
                # Use sandbox for PAPER mode
                sandbox = (mode == TradingMode.PAPER)
                self.tradier = TradierDataFetcher(sandbox=sandbox)
                logger.info(f"ARES: Tradier client initialized ({'SANDBOX' if sandbox else 'LIVE'})")
            except Exception as e:
                logger.warning(f"ARES: Failed to initialize Tradier: {e}")

        # Decision logger
        self.decision_logger = None
        if LOGGER_AVAILABLE:
            self.decision_logger = DecisionLogger()

        # State tracking
        self.open_positions: List[IronCondorPosition] = []
        self.closed_positions: List[IronCondorPosition] = []
        self.daily_trade_executed: Dict[str, bool] = {}  # date -> traded

        # Performance tracking
        self.total_pnl = 0
        self.high_water_mark = initial_capital
        self.trade_count = 0
        self.win_count = 0

        # Position ID counter
        self._position_counter = 0

        if mode == TradingMode.LIVE:
            logger.warning("ARES: LIVE TRADING MODE - Real money at risk!")

        logger.info(f"ARES initialized: mode={mode.value}, capital=${initial_capital:,.0f}")
        logger.info(f"  Trading ticker: {self.get_trading_ticker()}")
        logger.info(f"  Risk per trade: {self.config.risk_per_trade_pct}%")
        logger.info(f"  Spread width: ${self.get_spread_width()}")
        logger.info(f"  SD multiplier: {self.config.sd_multiplier}")

    def _generate_position_id(self) -> str:
        """Generate unique position ID"""
        self._position_counter += 1
        now = datetime.now(self.tz)
        return f"ARES-{now.strftime('%Y%m%d')}-{self._position_counter:04d}"

    def get_trading_ticker(self) -> str:
        """
        Get the ticker to trade based on mode.

        Sandbox mode uses SPY (better data availability in Tradier sandbox).
        Production mode uses SPX for higher premium.
        """
        if self.mode == TradingMode.PAPER:
            return self.config.sandbox_ticker  # SPY
        return self.config.ticker  # SPX

    def get_spread_width(self) -> float:
        """
        Get spread width based on mode.

        SPY spreads are $2 wide (vs $10 for SPX) because SPY is ~1/10 of SPX.
        """
        if self.mode == TradingMode.PAPER:
            return self.config.spread_width_spy  # $2 for SPY
        return self.config.spread_width  # $10 for SPX

    def get_min_credit(self) -> float:
        """
        Get minimum credit required based on mode.

        SPY credits are ~1/10 of SPX credits.
        """
        if self.mode == TradingMode.PAPER:
            return self.config.min_credit_per_spread_spy
        return self.config.min_credit_per_spread

    def get_current_market_data(self) -> Optional[Dict]:
        """
        Get current market data for the trading ticker (SPX or SPY).

        Returns:
            Dict with underlying price, VIX, expected move
        """
        if not self.tradier:
            logger.warning("ARES: Tradier not available for market data")
            return None

        try:
            # Get the appropriate ticker for current mode
            ticker = self.get_trading_ticker()
            underlying_price = None

            if ticker == "SPY":
                # Sandbox mode - use SPY directly
                quote = self.tradier.get_quote("SPY")
                if quote and quote.get('last'):
                    underlying_price = float(quote['last'])
                else:
                    logger.warning("ARES: Could not get SPY quote")
                    return None
            else:
                # Production mode - use SPX
                quote = self.tradier.get_quote("$SPX.X")
                if not quote or not quote.get('last'):
                    # Fallback to SPY * 10 estimate
                    spy_quote = self.tradier.get_quote("SPY")
                    if spy_quote and spy_quote.get('last'):
                        underlying_price = float(spy_quote['last']) * 10
                        logger.info("ARES: Using SPY*10 as SPX proxy")
                    else:
                        logger.warning("ARES: Could not get SPX or SPY quote")
                        return None
                else:
                    underlying_price = float(quote['last'])

            # Get VIX for expected move calculation
            vix = 15.0  # Default if not available
            vix_quote = self.tradier.get_quote("$VIX.X")
            if vix_quote and vix_quote.get('last'):
                vix = float(vix_quote['last'])
            else:
                # Try alternate symbol
                vix_quote = self.tradier.get_quote("VIX")
                if vix_quote and vix_quote.get('last'):
                    vix = float(vix_quote['last'])
                else:
                    logger.info("ARES: VIX not available, using default 15.0")

            # Calculate expected move (1 SD for 0DTE)
            iv = vix / 100
            expected_move = underlying_price * iv * math.sqrt(1/252)

            return {
                'ticker': ticker,
                'underlying_price': underlying_price,
                'vix': vix,
                'expected_move': expected_move,
                'timestamp': datetime.now(self.tz).isoformat()
            }

        except Exception as e:
            logger.error(f"ARES: Error getting market data: {e}")
            return None

    def find_iron_condor_strikes(
        self,
        underlying_price: float,
        expected_move: float,
        expiration: str
    ) -> Optional[Dict]:
        """
        Find optimal Iron Condor strikes at 1 SD from current price.

        Args:
            underlying_price: Current price (SPX or SPY)
            expected_move: Expected move (1 SD)
            expiration: Expiration date (YYYY-MM-DD)

        Returns:
            Dict with strikes and credits, or None if not found
        """
        if not self.tradier:
            return None

        try:
            # Get options chain - use appropriate symbol for mode
            ticker = self.get_trading_ticker()
            spread_width = self.get_spread_width()
            min_credit = self.get_min_credit()

            # Determine options symbol
            if ticker == "SPY":
                symbol = "SPY"  # SPY options
            elif ticker == "SPX":
                symbol = "SPXW"  # Weekly SPX options
            else:
                symbol = ticker

            chain = self.tradier.get_option_chain(symbol, expiration, greeks=True)

            if not chain or not chain.chains or expiration not in chain.chains:
                logger.warning(f"ARES: No options chain for {symbol} exp {expiration}")
                return None

            contracts = chain.chains[expiration]
            if not contracts:
                return None

            # Target strikes at SD distance
            # For SPY, round to $1 strikes; for SPX, round to $5 strikes
            sd = self.config.sd_multiplier
            strike_rounding = 1 if ticker == "SPY" else 5
            put_target = round((underlying_price - sd * expected_move) / strike_rounding) * strike_rounding
            call_target = round((underlying_price + sd * expected_move) / strike_rounding) * strike_rounding

            # Filter puts and calls
            otm_puts = [c for c in contracts
                       if c.option_type == 'put'
                       and c.strike < underlying_price
                       and c.bid > 0]

            otm_calls = [c for c in contracts
                        if c.option_type == 'call'
                        and c.strike > underlying_price
                        and c.bid > 0]

            if not otm_puts or not otm_calls:
                logger.warning("ARES: Insufficient options available")
                return None

            # Find short put (sell)
            short_put = min(otm_puts, key=lambda x: abs(x.strike - put_target))

            # Find long put (buy) - spread_width below short
            long_put_strike = short_put.strike - spread_width
            long_put_candidates = [c for c in contracts
                                  if c.option_type == 'put'
                                  and abs(c.strike - long_put_strike) < (0.5 if ticker == "SPY" else 1)
                                  and c.ask > 0]

            if not long_put_candidates:
                logger.warning(f"ARES: No long put at strike {long_put_strike}")
                return None

            long_put = min(long_put_candidates, key=lambda x: abs(x.strike - long_put_strike))

            # Find short call (sell)
            short_call = min(otm_calls, key=lambda x: abs(x.strike - call_target))

            # Find long call (buy) - spread_width above short
            long_call_strike = short_call.strike + spread_width
            long_call_candidates = [c for c in contracts
                                   if c.option_type == 'call'
                                   and abs(c.strike - long_call_strike) < (0.5 if ticker == "SPY" else 1)
                                   and c.ask > 0]

            if not long_call_candidates:
                logger.warning(f"ARES: No long call at strike {long_call_strike}")
                return None

            long_call = min(long_call_candidates, key=lambda x: abs(x.strike - long_call_strike))

            # Calculate credits
            put_credit = short_put.bid - long_put.ask
            call_credit = short_call.bid - long_call.ask
            total_credit = put_credit + call_credit

            # Validate credit
            if total_credit < min_credit:
                logger.info(f"ARES: Credit too low: ${total_credit:.2f} < ${min_credit:.2f}")
                return None

            return {
                'put_long_strike': long_put.strike,
                'put_short_strike': short_put.strike,
                'call_short_strike': short_call.strike,
                'call_long_strike': long_call.strike,
                'put_credit': put_credit,
                'call_credit': call_credit,
                'total_credit': total_credit,
                'put_long_symbol': long_put.symbol,
                'put_short_symbol': short_put.symbol,
                'call_short_symbol': short_call.symbol,
                'call_long_symbol': long_call.symbol,
            }

        except Exception as e:
            logger.error(f"ARES: Error finding strikes: {e}")
            return None

    def calculate_position_size(self, max_loss_per_spread: float) -> int:
        """
        Calculate position size based on risk budget.

        Args:
            max_loss_per_spread: Maximum loss per spread ($)

        Returns:
            Number of contracts to trade
        """
        # Risk budget: X% of current capital
        risk_budget = self.capital * (self.config.risk_per_trade_pct / 100)

        # Max loss is spread width minus credit received (per contract * 100)
        max_loss_dollars = max_loss_per_spread * 100

        # Calculate contracts
        contracts = int(risk_budget / max_loss_dollars)
        contracts = max(1, min(contracts, self.config.max_contracts))

        return contracts

    def execute_iron_condor(
        self,
        ic_strikes: Dict,
        contracts: int,
        expiration: str,
        market_data: Dict
    ) -> Optional[IronCondorPosition]:
        """
        Execute Iron Condor order via Tradier.

        Args:
            ic_strikes: Strike data from find_iron_condor_strikes
            contracts: Number of contracts
            expiration: Expiration date
            market_data: Current market data

        Returns:
            IronCondorPosition if successful, None otherwise
        """
        if not self.tradier:
            logger.warning("ARES: Cannot execute - Tradier not available")
            return None

        try:
            # Execute Iron Condor as a single order
            ticker = self.get_trading_ticker()
            spread_width = self.get_spread_width()

            result = self.tradier.place_iron_condor(
                symbol=ticker,
                expiration=expiration,
                put_long=ic_strikes['put_long_strike'],
                put_short=ic_strikes['put_short_strike'],
                call_short=ic_strikes['call_short_strike'],
                call_long=ic_strikes['call_long_strike'],
                quantity=contracts,
                limit_price=ic_strikes['total_credit']
            )

            # Check for Tradier API errors
            if 'errors' in result:
                error_msg = result.get('errors', {}).get('error', 'Unknown error')
                logger.error(f"ARES: Tradier API error: {error_msg}")
                logger.error(f"ARES: Full response: {result}")
                return None

            order_info = result.get('order', {}) or {}
            order_id = str(order_info.get('id', ''))
            order_status = order_info.get('status', '')

            # Validate order was actually placed
            if not order_id:
                logger.error(f"ARES: Order not placed - no order ID returned")
                logger.error(f"ARES: Full response: {result}")
                return None

            logger.info(f"ARES: Iron Condor order placed on {ticker} - ID: {order_id}, Status: {order_status}")

            # Create position record
            max_loss = spread_width - ic_strikes['total_credit']

            position = IronCondorPosition(
                position_id=self._generate_position_id(),
                open_date=datetime.now(self.tz).strftime('%Y-%m-%d'),
                expiration=expiration,
                put_long_strike=ic_strikes['put_long_strike'],
                put_short_strike=ic_strikes['put_short_strike'],
                call_short_strike=ic_strikes['call_short_strike'],
                call_long_strike=ic_strikes['call_long_strike'],
                put_credit=ic_strikes['put_credit'],
                call_credit=ic_strikes['call_credit'],
                total_credit=ic_strikes['total_credit'],
                contracts=contracts,
                spread_width=spread_width,
                max_loss=max_loss,
                put_spread_order_id=order_id,
                call_spread_order_id=order_id,
                underlying_price_at_entry=market_data['underlying_price'],
                vix_at_entry=market_data['vix'],
                expected_move=market_data['expected_move']
            )

            self.open_positions.append(position)
            self.trade_count += 1

            # Log decision
            self._log_entry_decision(position, market_data)

            return position

        except Exception as e:
            logger.error(f"ARES: Error executing Iron Condor: {e}")
            return None

    def _log_entry_decision(self, position: IronCondorPosition, market_data: Dict):
        """Log entry decision with full transparency"""
        if not self.decision_logger or not LOGGER_AVAILABLE:
            return

        try:
            # Create trade legs
            legs = [
                TradeLeg(
                    leg_id=1,
                    action="BUY",
                    option_type="put",
                    strike=position.put_long_strike,
                    expiration=position.expiration,
                    contracts=position.contracts
                ),
                TradeLeg(
                    leg_id=2,
                    action="SELL",
                    option_type="put",
                    strike=position.put_short_strike,
                    expiration=position.expiration,
                    entry_price=position.put_credit,
                    contracts=position.contracts
                ),
                TradeLeg(
                    leg_id=3,
                    action="SELL",
                    option_type="call",
                    strike=position.call_short_strike,
                    expiration=position.expiration,
                    entry_price=position.call_credit,
                    contracts=position.contracts
                ),
                TradeLeg(
                    leg_id=4,
                    action="BUY",
                    option_type="call",
                    strike=position.call_long_strike,
                    expiration=position.expiration,
                    contracts=position.contracts
                )
            ]

            decision = TradeDecision(
                decision_id=position.position_id,
                timestamp=datetime.now(self.tz).isoformat(),
                decision_type=DecisionType.ENTRY_SIGNAL,
                bot_name=BotName.ARES,
                what=f"SELL Iron Condor {position.contracts}x {position.put_short_strike}P/{position.call_short_strike}C @ ${position.total_credit:.2f}",
                why=f"1 SD Iron Condor for daily premium collection. VIX: {market_data['vix']:.1f}",
                action="SELL",
                symbol=self.config.ticker,
                strategy="aggressive_iron_condor",
                legs=legs,
                underlying_price_at_entry=market_data['underlying_price'],
                market_context=MarketContext(
                    timestamp=datetime.now(self.tz).isoformat(),
                    spot_price=market_data['underlying_price'],
                    spot_source=DataSource.TRADIER_LIVE,
                    vix=market_data['vix']
                ),
                reasoning=DecisionReasoning(
                    primary_reason="Daily aggressive Iron Condor for 10% monthly target",
                    supporting_factors=[
                        f"VIX at {market_data['vix']:.1f}",
                        f"1 SD expected move: ${market_data['expected_move']:.0f}",
                        f"Credit received: ${position.total_credit:.2f}",
                    ],
                    risk_factors=[
                        f"Max loss: ${position.max_loss * 100 * position.contracts:,.0f}",
                        "No stop loss - letting theta work"
                    ]
                ),
                position_size_dollars=position.total_credit * 100 * position.contracts,
                position_size_contracts=position.contracts,
                max_risk_dollars=position.max_loss * 100 * position.contracts
            )

            self.decision_logger.log_decision(decision)

        except Exception as e:
            logger.error(f"ARES: Error logging decision: {e}")

    def get_todays_expiration(self) -> Optional[str]:
        """Get today's expiration for 0DTE trading"""
        now = datetime.now(self.tz)
        ticker = self.get_trading_ticker()

        # For 0DTE, use today's date
        if self.config.use_0dte:
            return now.strftime('%Y-%m-%d')

        # Otherwise find nearest weekly expiration
        if not self.tradier:
            return None

        try:
            expirations = self.tradier.get_option_expirations(ticker)
            if expirations:
                return expirations[0]
        except Exception as e:
            logger.error(f"ARES: Error getting expirations for {ticker}: {e}")

        return None

    def is_trading_window(self) -> bool:
        """Check if we're in the trading entry window"""
        now = datetime.now(self.tz)

        # Check if weekday
        if now.weekday() >= 5:  # Saturday or Sunday
            return False

        # Parse entry window times
        start_parts = self.config.entry_time_start.split(':')
        end_parts = self.config.entry_time_end.split(':')

        start_time = now.replace(
            hour=int(start_parts[0]),
            minute=int(start_parts[1]),
            second=0,
            microsecond=0
        )
        end_time = now.replace(
            hour=int(end_parts[0]),
            minute=int(end_parts[1]),
            second=0,
            microsecond=0
        )

        return start_time <= now <= end_time

    def should_trade_today(self) -> bool:
        """Check if we should open a new trade today"""
        today = datetime.now(self.tz).strftime('%Y-%m-%d')

        # Already traded today?
        if self.daily_trade_executed.get(today, False):
            logger.info("ARES: Already traded today")
            return False

        # Have any open positions expiring today?
        for pos in self.open_positions:
            if pos.expiration == today:
                logger.info(f"ARES: Already have position {pos.position_id} expiring today")
                return False

        return True

    def run_daily_cycle(self) -> Dict:
        """
        Run the daily ARES trading cycle.

        This should be called during market hours (ideally 10:00 AM ET).

        Returns:
            Dict with cycle results
        """
        now = datetime.now(self.tz)
        today = now.strftime('%Y-%m-%d')

        logger.info(f"=" * 60)
        logger.info(f"ARES Daily Cycle - {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"Mode: {self.mode.value.upper()}")
        logger.info(f"Capital: ${self.capital:,.2f}")
        logger.info(f"=" * 60)

        result = {
            'date': today,
            'timestamp': now.isoformat(),
            'actions': [],
            'new_position': None,
            'capital': self.capital,
            'open_positions': len(self.open_positions)
        }

        # Check if in trading window
        if not self.is_trading_window():
            logger.info("ARES: Outside trading window")
            result['actions'].append("Outside trading window")
            return result

        # Check if should trade today
        if not self.should_trade_today():
            result['actions'].append("Already traded today or position exists")
            return result

        # Get market data
        market_data = self.get_current_market_data()
        if not market_data:
            logger.warning("ARES: Could not get market data")
            result['actions'].append("Failed to get market data")
            return result

        result['market_data'] = market_data

        logger.info(f"  Underlying: ${market_data['underlying_price']:,.2f}")
        logger.info(f"  VIX: {market_data['vix']:.1f}")
        logger.info(f"  Expected Move (1 SD): ${market_data['expected_move']:.2f}")

        # Get expiration
        expiration = self.get_todays_expiration()
        if not expiration:
            logger.warning("ARES: Could not get expiration date")
            result['actions'].append("Failed to get expiration")
            return result

        # Find Iron Condor strikes
        ic_strikes = self.find_iron_condor_strikes(
            market_data['underlying_price'],
            market_data['expected_move'],
            expiration
        )

        if not ic_strikes:
            logger.info("ARES: Could not find suitable Iron Condor strikes")
            result['actions'].append("No suitable strikes found")
            return result

        logger.info(f"  IC Strikes: {ic_strikes['put_long_strike']}/{ic_strikes['put_short_strike']}P - "
                   f"{ic_strikes['call_short_strike']}/{ic_strikes['call_long_strike']}C")
        logger.info(f"  Credit: ${ic_strikes['total_credit']:.2f}")

        # Calculate position size
        max_loss = self.config.spread_width - ic_strikes['total_credit']
        contracts = self.calculate_position_size(max_loss)

        logger.info(f"  Contracts: {contracts}")
        logger.info(f"  Total Premium: ${ic_strikes['total_credit'] * 100 * contracts:,.2f}")
        logger.info(f"  Max Risk: ${max_loss * 100 * contracts:,.2f}")

        # Execute the trade
        position = self.execute_iron_condor(ic_strikes, contracts, expiration, market_data)

        if position:
            self.daily_trade_executed[today] = True
            result['new_position'] = {
                'position_id': position.position_id,
                'strikes': f"{position.put_long_strike}/{position.put_short_strike}P - "
                          f"{position.call_short_strike}/{position.call_long_strike}C",
                'contracts': position.contracts,
                'credit': position.total_credit,
                'max_loss': position.max_loss
            }
            result['actions'].append(f"Opened position {position.position_id}")
            logger.info(f"ARES: Position {position.position_id} opened successfully")
        else:
            result['actions'].append("Failed to execute Iron Condor")

        result['open_positions'] = len(self.open_positions)

        logger.info(f"=" * 60)

        return result

    def get_status(self) -> Dict:
        """Get current ARES status"""
        now = datetime.now(self.tz)
        today = now.strftime('%Y-%m-%d')

        return {
            'mode': self.mode.value,
            'capital': self.capital,
            'total_pnl': self.total_pnl,
            'trade_count': self.trade_count,
            'win_rate': (self.win_count / self.trade_count * 100) if self.trade_count > 0 else 0,
            'open_positions': len(self.open_positions),
            'closed_positions': len(self.closed_positions),
            'traded_today': self.daily_trade_executed.get(today, False),
            'in_trading_window': self.is_trading_window(),
            'high_water_mark': self.high_water_mark,
            'current_time': now.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'config': {
                'risk_per_trade': self.config.risk_per_trade_pct,
                'spread_width': self.get_spread_width(),
                'sd_multiplier': self.config.sd_multiplier,
                'ticker': self.get_trading_ticker(),
                'production_ticker': self.config.ticker,
                'sandbox_ticker': self.config.sandbox_ticker
            }
        }


# Convenience function to get ARES logger
def get_ares_logger() -> DecisionLogger:
    """Get decision logger for ARES bot"""
    if LOGGER_AVAILABLE:
        return DecisionLogger()
    return None


# CLI for testing
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description='ARES Iron Condor Bot')
    parser.add_argument('--mode', choices=['paper', 'live', 'backtest'],
                       default='paper', help='Trading mode')
    parser.add_argument('--capital', type=float, default=100_000,
                       help='Initial capital')
    parser.add_argument('--status', action='store_true',
                       help='Show status only')
    parser.add_argument('--run', action='store_true',
                       help='Run daily cycle')

    args = parser.parse_args()

    # Create trader
    mode = TradingMode[args.mode.upper()]
    ares = ARESTrader(mode=mode, initial_capital=args.capital)

    if args.status:
        status = ares.get_status()
        print("\nARES STATUS")
        print("=" * 40)
        for key, value in status.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for k, v in value.items():
                    print(f"  {k}: {v}")
            else:
                print(f"{key}: {value}")

    elif args.run:
        result = ares.run_daily_cycle()
        print("\nARES DAILY CYCLE RESULT")
        print("=" * 40)
        for key, value in result.items():
            print(f"{key}: {value}")

    else:
        print("Use --status or --run to interact with ARES")
        print(f"\nCurrent status: {ares.get_status()['mode']} mode")
