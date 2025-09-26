"""
Real TradingVolatility.net API Client
"""

import requests
import time
from typing import Dict, Optional
import json

class TradingVolatilityAPI:
    """API client for TradingVolatility.net"""
    
    def __init__(self):
        self.base_url = "https://stocks.tradingvolatility.net/api"
        self.username = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AlphaGEX-Trading-Platform/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
    def set_credentials(self, username: str):
        """Set API credentials"""
        self.username = username.strip()
        
    def get_net_gex(self, symbol: str) -> Dict:
        """Get net gamma exposure for a symbol"""
        if not self.username:
            return {"success": False, "error": "No API username configured"}
            
        try:
            # Real API endpoint for net GEX
            url = f"{self.base_url}/netgex"
            
            params = {
                'username': self.username,
                'symbol': symbol.upper()
            }
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse the response based on TradingVolatility.net format
                if 'error' in data:
                    return {"success": False, "error": data['error']}
                    
                return {
                    "success": True,
                    "symbol": symbol.upper(),
                    "net_gex": data.get('netGex', 0),
                    "gamma_flip": data.get('spotPrice', 0),  # Adjust based on actual API response
                    "timestamp": time.time(),
                    "raw_data": data
                }
                
            elif response.status_code == 401:
                return {"success": False, "error": "Invalid API credentials"}
            elif response.status_code == 429:
                return {"success": False, "error": "Rate limit exceeded"}
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}
                
        except requests.exceptions.Timeout:
            return {"success": False, "error": "API request timeout"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "Unable to connect to API"}
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid API response format"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def get_gex_profile(self, symbol: str) -> Dict:
        """Get complete GEX profile for a symbol"""
        if not self.username:
            return {"success": False, "error": "No API username configured"}
            
        try:
            url = f"{self.base_url}/gexprofile"
            
            params = {
                'username': self.username,
                'symbol': symbol.upper()
            }
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "symbol": symbol.upper(),
                    "profile_data": data,
                    "timestamp": time.time()
                }
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}

def test_api_connection(username: str) -> Dict:
    """Test API connection with real endpoint"""
    if not username or not username.strip():
        return {"status": "error", "message": "Username is required"}
        
    try:
        api = TradingVolatilityAPI()
        api.set_credentials(username)
        
        # Test with a simple API call (try SPY as test symbol)
        test_result = api.get_net_gex("SPY")
        
        if test_result.get("success", False):
            return {"status": "success", "message": "API connection successful"}
        else:
            error_msg = test_result.get("error", "Unknown error")
            return {"status": "error", "message": f"API test failed: {error_msg}"}
            
    except Exception as e:
        return {"status": "error", "message": f"Connection test error: {str(e)}"}
