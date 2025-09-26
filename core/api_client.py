# TradingVolatility.net API Client
import requests
import time
from typing import Dict, Optional

class APIClient:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "https://stocks.tradingvolatility.net/api"
        self.last_request_time = 0
        self.rate_limit_delay = 3  # 20 calls per minute = 3 seconds between calls
        
    def set_api_key(self, api_key: str):
        self.api_key = api_key
        
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
                'apikey': self.api_key,
                'ticker': symbol
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'API request failed: {response.status_code}'}
                
        except Exception as e:
            return {'error': f'Request error: {str(e)}'}
    
    def get_options_flow(self, symbol: str) -> Dict:
        """Get options flow data"""
        try:
            self._rate_limit()
            
            url = f"{self.base_url}/optionsflow"
            params = {
                'apikey': self.api_key,
                'ticker': symbol
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'API request failed: {response.status_code}'}
                
        except Exception as e:
            return {'error': f'Request error: {str(e)}'}
            
    def test_connection(self) -> Dict:
        """Test API connection"""
        try:
            result = self.get_net_gex('SPY')
            if 'error' not in result:
                return {'status': 'success', 'message': 'API connection working'}
            else:
                return {'status': 'error', 'message': result['error']}
        except Exception as e:
            return {'status': 'error', 'message': f'Connection test failed: {str(e)}'}

# Create default instance
api_client = APIClient()
