"""
Real TradingVolatility.net API Client
Based on official API documentation
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
            'Accept': 'application/json',
            'User-Agent': 'AlphaGEX-Trading-Platform/1.0'
        })
        
    def set_credentials(self, username: str):
        """Set API credentials"""
        self.username = username.strip()
        
    def get_net_gex(self, symbol: str) -> Dict:
        """Get gamma exposure data for a symbol"""
        if not self.username:
            return {"success": False, "error": "No API username configured"}
            
        try:
            # Based on API docs: /gex/gamma endpoint
            url = f"{self.base_url}/gex/gamma"
            
            params = {
                'username': self.username,
                'ticker': symbol.upper(),
                'format': 'json',
                'exp': '1'  # Combined expiry data
            }
            
            print(f"API Request: {url} with params: {params}")
            
            response = self.session.get(url, params=params, timeout=30)
            
            print(f"API Response Status: {response.status_code}")
            print(f"API Response Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"API Response Data: {data}")
                    
                    # Check if response contains error
                    if isinstance(data, dict) and 'error' in data:
                        return {"success": False, "error": data['error']}
                    
                    # Parse TradingVolatility.net response format
                    symbol_data = data.get(symbol.upper(), {})
                    
                    if not symbol_data:
                        return {"success": False, "error": f"No data found for symbol {symbol}"}
                    
                    # Calculate net GEX from gamma array
                    gamma_array = symbol_data.get('gamma_array', [])
                    net_gex = sum(float(item.get('gamma', 0)) for item in gamma_array if isinstance(item, dict))
                    
                    # Get current price and other data
                    current_price = float(symbol_data.get('price', 0))
                    
                    # Find gamma flip point (where gamma changes from negative to positive)
                    gamma_flip = current_price  # Default to current price
                    for item in gamma_array:
                        if isinstance(item, dict) and float(item.get('gamma', 0)) > 0:
                            gamma_flip = float(item.get('strike', current_price))
                            break
                    
                    return {
                        "success": True,
                        "symbol": symbol.upper(),
                        "net_gex": net_gex,
                        "gamma_flip": gamma_flip,
                        "current_price": current_price,
                        "collection_date": symbol_data.get('collection_date', ''),
                        "gamma_array": gamma_array,
                        "timestamp": time.time()
                    }
                    
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
                    print(f"Response text: {response.text[:500]}")
                    return {"success": False, "error": f"Invalid JSON response: {str(e)}"}
                    
            elif response.status_code == 401:
                return {"success": False, "error": "Invalid API credentials - check your username"}
            elif response.status_code == 403:
                return {"success": False, "error": "Access forbidden - subscription may be required"}
            elif response.status_code == 429:
                return {"success": False, "error": "Rate limit exceeded - try again later"}
            else:
                print(f"API Error Response: {response.text[:500]}")
                return {"success": False, "error": f"API error {response.status_code}: {response.text[:200]}"}
                
        except requests.exceptions.Timeout:
            return {"success": False, "error": "API request timeout - server may be busy"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "Unable to connect to TradingVolatility.net API"}
        except Exception as e:
            print(f"Unexpected API error: {e}")
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def get_gex_levels(self, symbol: str) -> Dict:
        """Get GEX levels for a symbol"""
        if not self.username:
            return {"success": False, "error": "No API username configured"}
            
        try:
            # Based on API docs: /gex/levels endpoint
            url = f"{self.base_url}/gex/levels"
            
            params = {
                'username': self.username,
                'ticker': symbol.upper(),
                'format': 'json'
            }
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "symbol": symbol.upper(),
                    "levels_data": data,
                    "timestamp": time.time()
                }
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_gex_history(self, symbol: str, start_date: str = None, end_date: str = None) -> Dict:
        """Get historical GEX data"""
        if not self.username:
            return {"success": False, "error": "No API username configured"}
            
        try:
            # Based on API docs: /gex/history endpoint
            url = f"{self.base_url}/gex/history"
            
            params = {
                'username': self.username,
                'ticker': symbol.upper(),
                'format': 'json'
            }
            
            if start_date:
                params['start'] = start_date
            if end_date:
                params['end'] = end_date
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "symbol": symbol.upper(),
                    "history_data": data,
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
        
        print(f"Testing API connection for username: {username}")
        
        # Test with SPY as it's commonly available
        test_result = api.get_net_gex("SPY")
        
        print(f"Test result: {test_result}")
        
        if test_result.get("success", False):
            return {"status": "success", "message": "API connection successful - data retrieved"}
        else:
            error_msg = test_result.get("error", "Unknown error")
            return {"status": "error", "message": f"API test failed: {error_msg}"}
            
    except Exception as e:
        print(f"Connection test exception: {e}")
        return {"status": "error", "message": f"Connection test error: {str(e)}"}
