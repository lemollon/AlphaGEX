"""
Volatility Surface Module for AlphaGEX

Provides institutional-grade volatility surface modeling:
- SVI (Stochastic Volatility Inspired) surface fitting
- IV interpolation for arbitrary strike/DTE
- Skew quantification (25-delta, ATM, risk reversal)
- Term structure analysis
- Volatility cone (historical IV percentiles)
- Arbitrage-free surface validation

This is CRITICAL infrastructure for:
- Accurate options pricing across all strikes
- Detecting IV mispricings
- Understanding market expectations
- Backtesting with realistic IV dynamics

Author: AlphaGEX
"""

import math
import numpy as np
from typing import Dict, List, Optional, Tuple, NamedTuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from scipy.optimize import minimize, least_squares
from scipy.interpolate import RectBivariateSpline, interp1d
from scipy.stats import norm
import warnings


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class IVPoint:
    """Single implied volatility observation"""
    strike: float
    expiration_days: int  # DTE
    iv: float
    delta: Optional[float] = None
    moneyness: Optional[float] = None  # K/S or log(K/F)
    bid_iv: Optional[float] = None
    ask_iv: Optional[float] = None
    volume: int = 0
    open_interest: int = 0

    def __post_init__(self):
        """Validate IV point"""
        if self.iv <= 0 or self.iv > 3.0:  # IV > 300% is suspicious
            warnings.warn(f"Suspicious IV value: {self.iv:.2%} at strike {self.strike}")


@dataclass
class SVIParams:
    """
    SVI (Stochastic Volatility Inspired) model parameters

    The SVI parameterization models total variance w(k) as:
    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

    where k = log(K/F) is log-moneyness

    Parameters:
        a: Level of variance (vertical shift)
        b: Slope of wings (smile steepness)
        rho: Skew (-1 to 1, negative = put skew)
        m: Horizontal shift (ATM location)
        sigma: Smoothness at ATM
    """
    a: float
    b: float
    rho: float
    m: float
    sigma: float

    def validate(self) -> bool:
        """Check butterfly arbitrage conditions"""
        # SVI no-arbitrage conditions (simplified)
        if self.b < 0:
            return False
        if abs(self.rho) >= 1:
            return False
        if self.sigma <= 0:
            return False
        if self.a + self.b * self.sigma * math.sqrt(1 - self.rho**2) < 0:
            return False
        return True


@dataclass
class SkewMetrics:
    """Volatility skew measurements"""
    atm_iv: float                    # ATM implied volatility
    skew_25d: float                  # 25-delta put IV - 25-delta call IV
    skew_10d: float                  # 10-delta put IV - 10-delta call IV
    risk_reversal_25d: float         # 25-delta call IV - 25-delta put IV (negative = put skew)
    butterfly_25d: float             # (25d call IV + 25d put IV) / 2 - ATM IV (smile curvature)
    put_skew_slope: float            # Rate of IV increase as puts go deeper OTM
    call_skew_slope: float           # Rate of IV increase as calls go deeper OTM
    skew_ratio: float                # Put skew / Call skew (>1 = more put skew)

    def is_normal_skew(self) -> bool:
        """Check if skew is in normal range for equity indices"""
        # Normal equity skew: puts more expensive than calls
        return -0.15 < self.risk_reversal_25d < 0.02


@dataclass
class TermStructure:
    """Volatility term structure data"""
    spot_iv: float                   # Front month IV
    term_ivs: Dict[int, float]       # DTE -> IV mapping
    slope: float                     # Term structure slope (positive = contango)
    is_inverted: bool                # True if backwardation
    vix_term_premium: float          # VIX vs realized vol spread

    def get_iv_at_dte(self, dte: int) -> float:
        """Interpolate IV at specific DTE"""
        dtes = sorted(self.term_ivs.keys())
        ivs = [self.term_ivs[d] for d in dtes]

        if dte <= dtes[0]:
            return ivs[0]
        if dte >= dtes[-1]:
            return ivs[-1]

        # Linear interpolation
        for i in range(len(dtes) - 1):
            if dtes[i] <= dte <= dtes[i + 1]:
                weight = (dte - dtes[i]) / (dtes[i + 1] - dtes[i])
                return ivs[i] + weight * (ivs[i + 1] - ivs[i])

        return self.spot_iv


# =============================================================================
# VOLATILITY SURFACE CLASS
# =============================================================================

class VolatilitySurface:
    """
    Institutional-grade volatility surface modeling

    Provides:
    - Surface fitting using SVI or polynomial models
    - IV interpolation for any strike/DTE
    - Skew and term structure analysis
    - Arbitrage-free validation

    Usage:
        surface = VolatilitySurface(spot_price=450.0, risk_free_rate=0.045)
        surface.add_iv_chain(chain_data)
        surface.fit()

        iv = surface.get_iv(strike=460, dte=30)
        skew = surface.get_skew_metrics(dte=30)
    """

    def __init__(self, spot_price: float, risk_free_rate: float = 0.045):
        """
        Initialize volatility surface

        Args:
            spot_price: Current underlying price
            risk_free_rate: Risk-free rate for forward calculation
        """
        self.spot = spot_price
        self.r = risk_free_rate

        # IV data storage: {dte: {strike: IVPoint}}
        self.iv_data: Dict[int, Dict[float, IVPoint]] = {}

        # Fitted parameters
        self.svi_params: Dict[int, SVIParams] = {}  # Per-expiration SVI fits
        self.surface_spline: Optional[RectBivariateSpline] = None

        # Surface state
        self.is_fitted = False
        self.fit_quality: Dict[str, float] = {}
        self.last_update = datetime.now()

    def add_iv_point(self, strike: float, dte: int, iv: float,
                     delta: Optional[float] = None,
                     bid_iv: Optional[float] = None,
                     ask_iv: Optional[float] = None,
                     volume: int = 0, oi: int = 0):
        """Add single IV observation"""
        if dte not in self.iv_data:
            self.iv_data[dte] = {}

        # Calculate moneyness
        forward = self.spot * math.exp(self.r * dte / 365.0)
        moneyness = math.log(strike / forward)

        point = IVPoint(
            strike=strike,
            expiration_days=dte,
            iv=iv,
            delta=delta,
            moneyness=moneyness,
            bid_iv=bid_iv,
            ask_iv=ask_iv,
            volume=volume,
            open_interest=oi
        )

        self.iv_data[dte][strike] = point
        self.is_fitted = False

    def add_iv_chain(self, chain_data: List[Dict], dte: int):
        """
        Add full options chain IV data

        Args:
            chain_data: List of option data dicts with keys:
                - strike: float
                - iv: float
                - delta: Optional[float]
                - bid_iv, ask_iv: Optional[float]
                - volume, open_interest: Optional[int]
            dte: Days to expiration for this chain
        """
        for opt in chain_data:
            self.add_iv_point(
                strike=opt['strike'],
                dte=dte,
                iv=opt['iv'],
                delta=opt.get('delta'),
                bid_iv=opt.get('bid_iv'),
                ask_iv=opt.get('ask_iv'),
                volume=opt.get('volume', 0),
                oi=opt.get('open_interest', 0)
            )

    def _fit_svi_slice(self, dte: int) -> Optional[SVIParams]:
        """
        Fit SVI model to single expiration slice

        The SVI model parameterizes total variance as:
        w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

        where k = log(K/F) is log-moneyness
        """
        if dte not in self.iv_data or len(self.iv_data[dte]) < 5:
            return None

        points = list(self.iv_data[dte].values())

        # Extract data
        k = np.array([p.moneyness for p in points])  # Log-moneyness
        t = dte / 365.0
        w = np.array([p.iv**2 * t for p in points])  # Total variance

        # Weights: prefer liquid strikes
        weights = np.array([max(1, p.volume + p.open_interest / 10) for p in points])
        weights = weights / weights.sum()

        def svi_variance(params, k):
            """SVI total variance function"""
            a, b, rho, m, sigma = params
            return a + b * (rho * (k - m) + np.sqrt((k - m)**2 + sigma**2))

        def objective(params):
            """Weighted sum of squared errors"""
            w_pred = svi_variance(params, k)
            return np.sum(weights * (w_pred - w)**2)

        # Initial guess
        atm_var = np.interp(0, k, w)
        x0 = [atm_var, 0.1, -0.3, 0.0, 0.1]

        # Bounds to ensure valid SVI parameters
        bounds = [
            (0, None),      # a >= 0
            (0.001, 1.0),   # 0 < b <= 1
            (-0.99, 0.99),  # -1 < rho < 1
            (-0.5, 0.5),    # m around 0
            (0.01, 0.5)     # sigma > 0
        ]

        try:
            result = minimize(objective, x0, method='L-BFGS-B', bounds=bounds)

            if result.success:
                params = SVIParams(*result.x)
                if params.validate():
                    return params
        except Exception:
            pass

        return None

    def fit(self, method: str = 'svi') -> bool:
        """
        Fit volatility surface to all data

        Args:
            method: 'svi' for SVI model, 'spline' for bivariate spline

        Returns:
            True if fit successful
        """
        if not self.iv_data:
            return False

        if method == 'svi':
            # Fit SVI to each expiration
            for dte in sorted(self.iv_data.keys()):
                params = self._fit_svi_slice(dte)
                if params:
                    self.svi_params[dte] = params

            if len(self.svi_params) >= 2:
                self.is_fitted = True
                self._calculate_fit_quality()
                return True

        elif method == 'spline':
            # Bivariate spline interpolation
            all_strikes = set()
            all_dtes = sorted(self.iv_data.keys())

            for dte_points in self.iv_data.values():
                all_strikes.update(dte_points.keys())

            strikes = sorted(all_strikes)

            if len(strikes) < 4 or len(all_dtes) < 2:
                return False

            # Build IV grid
            iv_grid = np.zeros((len(strikes), len(all_dtes)))

            for i, strike in enumerate(strikes):
                for j, dte in enumerate(all_dtes):
                    if strike in self.iv_data.get(dte, {}):
                        iv_grid[i, j] = self.iv_data[dte][strike].iv
                    else:
                        # Interpolate missing points
                        iv_grid[i, j] = self._interpolate_iv_linear(strike, dte)

            try:
                self.surface_spline = RectBivariateSpline(
                    strikes, all_dtes, iv_grid, kx=3, ky=3
                )
                self.is_fitted = True
                self._calculate_fit_quality()
                return True
            except Exception:
                return False

        return False

    def _interpolate_iv_linear(self, strike: float, dte: int) -> float:
        """Linear interpolation for missing IV points"""
        if dte in self.iv_data:
            strikes = sorted(self.iv_data[dte].keys())
            ivs = [self.iv_data[dte][k].iv for k in strikes]

            if strike <= strikes[0]:
                return ivs[0]
            if strike >= strikes[-1]:
                return ivs[-1]

            return np.interp(strike, strikes, ivs)

        # Interpolate across DTEs
        dtes = sorted(self.iv_data.keys())
        ivs = []

        for d in dtes:
            ivs.append(self._interpolate_iv_linear(strike, d) if strike not in self.iv_data.get(d, {})
                      else self.iv_data[d][strike].iv)

        return np.interp(dte, dtes, ivs)

    def _calculate_fit_quality(self):
        """Calculate fit quality metrics"""
        if not self.is_fitted:
            return

        total_error = 0
        n_points = 0

        for dte, strikes in self.iv_data.items():
            for strike, point in strikes.items():
                predicted_iv = self.get_iv(strike, dte)
                error = abs(predicted_iv - point.iv)
                total_error += error
                n_points += 1

        self.fit_quality['mae'] = total_error / n_points if n_points > 0 else float('inf')
        self.fit_quality['n_points'] = n_points
        self.fit_quality['n_expirations'] = len(self.iv_data)

    def get_iv(self, strike: float, dte: int) -> float:
        """
        Get implied volatility for any strike/DTE combination

        This is the main interpolation method - returns IV even for
        strikes/expirations not in the original data.

        Args:
            strike: Option strike price
            dte: Days to expiration

        Returns:
            Interpolated implied volatility
        """
        if not self.is_fitted:
            # Fall back to linear interpolation
            return self._interpolate_iv_linear(strike, dte)

        if self.surface_spline is not None:
            # Spline interpolation
            return float(self.surface_spline(strike, dte)[0, 0])

        # SVI interpolation
        if dte in self.svi_params:
            return self._svi_iv(strike, dte, self.svi_params[dte])

        # Interpolate between two nearest SVI fits
        dtes = sorted(self.svi_params.keys())

        if dte <= dtes[0]:
            return self._svi_iv(strike, dtes[0], self.svi_params[dtes[0]])
        if dte >= dtes[-1]:
            return self._svi_iv(strike, dtes[-1], self.svi_params[dtes[-1]])

        # Find bracketing expirations
        for i in range(len(dtes) - 1):
            if dtes[i] <= dte <= dtes[i + 1]:
                iv1 = self._svi_iv(strike, dtes[i], self.svi_params[dtes[i]])
                iv2 = self._svi_iv(strike, dtes[i + 1], self.svi_params[dtes[i + 1]])
                weight = (dte - dtes[i]) / (dtes[i + 1] - dtes[i])
                return iv1 + weight * (iv2 - iv1)

        return 0.20  # Default fallback

    def _svi_iv(self, strike: float, dte: int, params: SVIParams) -> float:
        """Calculate IV from SVI parameters"""
        t = dte / 365.0
        forward = self.spot * math.exp(self.r * t)
        k = math.log(strike / forward)

        # SVI total variance
        w = params.a + params.b * (
            params.rho * (k - params.m) +
            math.sqrt((k - params.m)**2 + params.sigma**2)
        )

        # Convert total variance to IV
        if w <= 0 or t <= 0:
            return 0.20

        return math.sqrt(w / t)

    def get_delta_strike(self, delta: float, dte: int, option_type: str = 'call') -> float:
        """
        Get strike price for target delta

        Args:
            delta: Target delta (0-1 for calls, -1 to 0 for puts)
            dte: Days to expiration
            option_type: 'call' or 'put'

        Returns:
            Strike price that achieves target delta
        """
        from utils.realistic_option_pricing import BlackScholesOption

        t = dte / 365.0

        # Binary search for strike
        low_strike = self.spot * 0.7
        high_strike = self.spot * 1.3

        target_delta = abs(delta)

        for _ in range(50):  # Max iterations
            mid_strike = (low_strike + high_strike) / 2
            iv = self.get_iv(mid_strike, dte)

            opt = BlackScholesOption(self.spot, mid_strike, t, self.r, iv, option_type)
            current_delta = abs(opt.delta())

            if abs(current_delta - target_delta) < 0.001:
                return mid_strike

            if option_type == 'call':
                if current_delta > target_delta:
                    low_strike = mid_strike
                else:
                    high_strike = mid_strike
            else:
                if current_delta > target_delta:
                    high_strike = mid_strike
                else:
                    low_strike = mid_strike

        return (low_strike + high_strike) / 2

    def get_skew_metrics(self, dte: int) -> SkewMetrics:
        """
        Calculate skew metrics for given expiration

        Args:
            dte: Days to expiration

        Returns:
            SkewMetrics with all skew measurements
        """
        # Get ATM IV
        atm_iv = self.get_iv(self.spot, dte)

        # Get delta-based strikes
        call_25d_strike = self.get_delta_strike(0.25, dte, 'call')
        put_25d_strike = self.get_delta_strike(-0.25, dte, 'put')
        call_10d_strike = self.get_delta_strike(0.10, dte, 'call')
        put_10d_strike = self.get_delta_strike(-0.10, dte, 'put')

        # Get IVs at delta strikes
        call_25d_iv = self.get_iv(call_25d_strike, dte)
        put_25d_iv = self.get_iv(put_25d_strike, dte)
        call_10d_iv = self.get_iv(call_10d_strike, dte)
        put_10d_iv = self.get_iv(put_10d_strike, dte)

        # Calculate metrics
        skew_25d = put_25d_iv - call_25d_iv
        skew_10d = put_10d_iv - call_10d_iv
        risk_reversal_25d = call_25d_iv - put_25d_iv  # Negative = put skew
        butterfly_25d = (call_25d_iv + put_25d_iv) / 2 - atm_iv

        # Calculate skew slopes
        put_skew_slope = (put_25d_iv - atm_iv) / (self.spot - put_25d_strike) if put_25d_strike != self.spot else 0
        call_skew_slope = (call_25d_iv - atm_iv) / (call_25d_strike - self.spot) if call_25d_strike != self.spot else 0

        skew_ratio = abs(put_skew_slope / call_skew_slope) if call_skew_slope != 0 else float('inf')

        return SkewMetrics(
            atm_iv=atm_iv,
            skew_25d=skew_25d,
            skew_10d=skew_10d,
            risk_reversal_25d=risk_reversal_25d,
            butterfly_25d=butterfly_25d,
            put_skew_slope=put_skew_slope,
            call_skew_slope=call_skew_slope,
            skew_ratio=skew_ratio
        )

    def get_term_structure(self) -> TermStructure:
        """
        Analyze volatility term structure

        Returns:
            TermStructure with term structure analysis
        """
        if not self.iv_data:
            return TermStructure(
                spot_iv=0.20,
                term_ivs={},
                slope=0.0,
                is_inverted=False,
                vix_term_premium=0.0
            )

        dtes = sorted(self.iv_data.keys())
        term_ivs = {}

        for dte in dtes:
            atm_iv = self.get_iv(self.spot, dte)
            term_ivs[dte] = atm_iv

        # Calculate slope (IV per day)
        if len(dtes) >= 2:
            ivs = [term_ivs[d] for d in dtes]
            slope = (ivs[-1] - ivs[0]) / (dtes[-1] - dtes[0])
        else:
            slope = 0.0

        spot_iv = term_ivs.get(dtes[0], 0.20)
        is_inverted = slope < 0  # Backwardation

        return TermStructure(
            spot_iv=spot_iv,
            term_ivs=term_ivs,
            slope=slope,
            is_inverted=is_inverted,
            vix_term_premium=0.0  # Would need VIX data to calculate
        )


# =============================================================================
# VOLATILITY CONE
# =============================================================================

class VolatilityCone:
    """
    Historical IV percentiles by DTE

    Shows where current IV sits relative to historical range
    at each expiration. Critical for identifying cheap/expensive options.
    """

    def __init__(self):
        self.historical_ivs: Dict[int, List[float]] = {}  # DTE -> list of historical ATM IVs

    def add_historical_iv(self, dte: int, iv: float):
        """Add historical IV observation"""
        if dte not in self.historical_ivs:
            self.historical_ivs[dte] = []
        self.historical_ivs[dte].append(iv)

    def get_percentile(self, dte: int, current_iv: float) -> float:
        """
        Get percentile rank of current IV

        Args:
            dte: Days to expiration
            current_iv: Current ATM IV at this DTE

        Returns:
            Percentile (0-100) of current IV vs history
        """
        if dte not in self.historical_ivs or len(self.historical_ivs[dte]) < 10:
            return 50.0  # Default to median if insufficient data

        historical = sorted(self.historical_ivs[dte])
        rank = sum(1 for iv in historical if iv < current_iv)
        return (rank / len(historical)) * 100

    def get_cone(self, dte: int) -> Dict[str, float]:
        """
        Get volatility cone at DTE

        Returns:
            Dict with min, 25th, median, 75th, max, current_pct
        """
        if dte not in self.historical_ivs or len(self.historical_ivs[dte]) < 10:
            return {
                'min': 0.10, 'p25': 0.15, 'median': 0.20,
                'p75': 0.25, 'max': 0.40, 'n_samples': 0
            }

        ivs = np.array(self.historical_ivs[dte])

        return {
            'min': float(np.min(ivs)),
            'p25': float(np.percentile(ivs, 25)),
            'median': float(np.median(ivs)),
            'p75': float(np.percentile(ivs, 75)),
            'max': float(np.max(ivs)),
            'n_samples': len(ivs)
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_surface_from_chain(spot: float, chains: Dict[int, List[Dict]],
                               risk_free_rate: float = 0.045) -> VolatilitySurface:
    """
    Create volatility surface from options chain data

    Args:
        spot: Current underlying price
        chains: Dict of {dte: [option_data]} where option_data has strike, iv, etc.
        risk_free_rate: Risk-free rate

    Returns:
        Fitted VolatilitySurface
    """
    surface = VolatilitySurface(spot, risk_free_rate)

    for dte, chain in chains.items():
        surface.add_iv_chain(chain, dte)

    surface.fit(method='svi')
    return surface


def estimate_iv_from_hv(realized_vol: float, vol_risk_premium: float = 0.03) -> float:
    """
    Estimate IV from historical volatility when no options data available

    Args:
        realized_vol: Historical/realized volatility
        vol_risk_premium: IV premium over HV (typically 2-5%)

    Returns:
        Estimated IV
    """
    return realized_vol + vol_risk_premium


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Volatility Surface Module - Test")
    print("=" * 70)

    # Create sample surface
    surface = VolatilitySurface(spot_price=450.0, risk_free_rate=0.045)

    # Add sample IV data (simulating SPY options)
    # 7 DTE chain
    chain_7dte = [
        {'strike': 440, 'iv': 0.22},
        {'strike': 445, 'iv': 0.19},
        {'strike': 450, 'iv': 0.18},  # ATM
        {'strike': 455, 'iv': 0.17},
        {'strike': 460, 'iv': 0.16},
    ]

    # 30 DTE chain
    chain_30dte = [
        {'strike': 430, 'iv': 0.23},
        {'strike': 440, 'iv': 0.20},
        {'strike': 450, 'iv': 0.18},  # ATM
        {'strike': 460, 'iv': 0.17},
        {'strike': 470, 'iv': 0.16},
    ]

    # 60 DTE chain
    chain_60dte = [
        {'strike': 420, 'iv': 0.24},
        {'strike': 440, 'iv': 0.21},
        {'strike': 450, 'iv': 0.19},  # ATM
        {'strike': 460, 'iv': 0.18},
        {'strike': 480, 'iv': 0.17},
    ]

    surface.add_iv_chain(chain_7dte, dte=7)
    surface.add_iv_chain(chain_30dte, dte=30)
    surface.add_iv_chain(chain_60dte, dte=60)

    # Fit surface
    print("\nFitting volatility surface...")
    success = surface.fit(method='spline')  # Use spline for small dataset
    print(f"Fit successful: {success}")

    # Test interpolation
    print("\n--- IV Interpolation ---")
    test_cases = [
        (450, 7),   # ATM, 7 DTE
        (450, 30),  # ATM, 30 DTE
        (455, 14),  # OTM call, interpolated DTE
        (440, 45),  # OTM put, interpolated DTE
    ]

    for strike, dte in test_cases:
        iv = surface.get_iv(strike, dte)
        print(f"Strike ${strike}, {dte} DTE: IV = {iv:.2%}")

    # Test skew metrics
    print("\n--- Skew Metrics (30 DTE) ---")
    skew = surface.get_skew_metrics(dte=30)
    print(f"ATM IV: {skew.atm_iv:.2%}")
    print(f"25-Delta Skew: {skew.skew_25d:.2%}")
    print(f"Risk Reversal: {skew.risk_reversal_25d:.2%}")
    print(f"Butterfly: {skew.butterfly_25d:.2%}")
    print(f"Normal Skew: {skew.is_normal_skew()}")

    # Test term structure
    print("\n--- Term Structure ---")
    term = surface.get_term_structure()
    print(f"Spot IV: {term.spot_iv:.2%}")
    print(f"Slope: {term.slope*1000:.4f} per day")
    print(f"Inverted (Backwardation): {term.is_inverted}")

    print("\n" + "=" * 70)
    print("Volatility Surface Module Ready for Integration")
    print("=" * 70)
