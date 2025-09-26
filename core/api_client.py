# TradingVolatility.net API Client
import requests
import time
from typing import Dict, Optional, List

class TradingVolatilityAPI:
    def __init__(self, username: str = "", base_url: str = "https://stocks.tradingvolatility.net/api"):
        self.username = username
        self.base_url = base_url
        self.last_request_time = 0
        self.rate_limit_delay = 3  # 20 calls per minute = 3 seconds between calls
        
    def set_credentials(self, username: str):
        """Set API credentials"""
        self.username = username
        
    def _rate_limit(self):
        """Enforce rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        self.last_request_time = time.time()
        
    def get_net_gex(self, symbol: str) -> Dict:
        """Get net gamma exposure for a symbol"""
        try:
            self._rate_limit()
            
            url = f"{self.base_url}/netgamma"
            params = {
                'username': self.username,
                'ticker': symbol
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'data': data,
                    'net_gex': data.get('netGEX', 0),
                    'gamma_flip': data.get('zeroGamma', 0),
                    'call_walls': data.get('callWalls', []),
                    'put_walls': data.get('putWalls', [])
                }
            else:
                return {
                    'success': False,
                    'error': f'API request failed: {response.status_code}',
                    'net_gex': 0,
                    'gamma_flip': 0,
                    'call_walls': [],
                    'put_walls': []
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Request error: {str(e)}',
                'net_gex': 0,
                'gamma_flip': 0,
                'call_walls': [],
                'put_walls': []
            }
    
    def get_options_flow(self, symbol: str) -> Dict:
        """Get options flow data"""
        try:
            self._rate_limit()
            
            url = f"{self.base_url}/optionsflow"
            params = {
                'username': self.username,
                'ticker': symbol
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'API request failed: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Request error: {str(e)}'
            }
    
    def get_gex_profile(self, symbol: str) -> Dict:
        """Get complete GEX profile for a symbol"""
        try:
            self._rate_limit()
            
            url = f"{self.base_url}/gexprofile"
            params = {
                'username': self.username,
                'ticker': symbol
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'data': data,
                    'strikes': data.get('strikes', []),
                    'call_gex': data.get('callGEX', []),
                    'put_gex': data.get('putGEX', []),
                    'total_gex': data.get('totalGEX', [])
                }
            else:
                return {
                    'success': False,
                    'error': f'API request failed: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Request error: {str(e)}'
            }
            
    def scan_symbols(self, symbols: List[str]) -> Dict:
        """Scan multiple symbols for GEX data"""
        results = {}
        total_symbols = len(symbols)
        
        for i, symbol in enumerate(symbols):
            try:
                gex_data = self.get_net_gex(symbol)
                results[symbol] = gex_data
                
                # Progress tracking
                progress = (i + 1) / total_symbols
                print(f"Scanning progress: {progress:.1%} ({i+1}/{total_symbols})")
                
            except Exception as e:
                results[symbol] = {
                    'success': False,
                    'error': f'Scan error: {str(e)}'
                }
                
        return {
            'success': True,
            'total_scanned': len(results),
            'results': results
        }

def test_api_connection(username: str = "", base_url: str = "https://stocks.tradingvolatility.net/api") -> Dict:
    """Test API connection with credentials"""
    try:
        api = TradingVolatilityAPI(username, base_url)
        result = api.get_net_gex('SPY')
        
        if result['success']:
            return {
                'status': 'success',
                'message': 'API connection working successfully',
                'test_data': result['data'] if 'data' in result else None
            }
        else:
            return {
                'status': 'error', 
                'message': f"API test failed: {result['error']}"
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Connection test failed: {str(e)}'
        }

def get_api_limits() -> Dict:
    """Get current API rate limits"""
    return {
        'weekday_non_realtime': 20,  # calls per minute
        'weekday_realtime': 2,       # calls per minute  
        'weekend_options_volume': 1,  # calls per minute
        'weekend_other': 2           # calls per minute
    }

# Create default instance
default_api = TradingVolatilityAPI()
