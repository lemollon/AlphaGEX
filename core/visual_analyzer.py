"""
GammaHunter Visual Analyzer
===========================
Chart image analysis and pattern recognition for GEX profiles.
"""

try:
    import cv2
except ImportError:
    print("OpenCV not available - visual analysis will be limited")
    cv2 = None

import numpy as np
import pandas as pd
from PIL import Image
import streamlit as st
from typing import Dict, List, Optional, Tuple
import requests
from io import BytesIO
import matplotlib.pyplot as plt
import plotly.graph_objects as go

class VisualIntelligenceCoordinator:
    """
    Coordinates visual analysis of GEX charts and market data
    """
    
    def __init__(self):
        self.supported_formats = ['.png', '.jpg', '.jpeg', '.gif', '.bmp']
        self.chart_patterns = {
            'gamma_stack': 'Concentrated gamma at single strike',
            'gamma_wall': 'Strong resistance/support level',
            'gamma_ramp': 'Gradual gamma build-up',
            'gamma_squeeze': 'Negative gamma environment'
        }
        self.opencv_available = cv2 is not None
        
    def analyze_chart_image(self, image_source) -> Dict:
        """
        Main function to analyze uploaded or URL-based chart images
        """
        if not self.opencv_available:
            return self._fallback_analysis("OpenCV not available")
            
        try:
            # Load image
            image = self._load_image(image_source)
            if image is None:
                return self._fallback_analysis("Failed to load image")
                
            # Convert to OpenCV format
            cv_image = self._pil_to_cv2(image)
            
            # Detect chart elements
            chart_analysis = self._detect_chart_elements(cv_image)
            
            # Identify GEX patterns
            gex_patterns = self._identify_gex_patterns(cv_image, chart_analysis)
            
            # Calculate confidence scores
            confidence = self._calculate_visual_confidence(chart_analysis, gex_patterns)
            
            # Generate insights
            insights = self._generate_visual_insights(gex_patterns, confidence)
            
            return {
                'success': True,
                'chart_type': chart_analysis.get('chart_type', 'Unknown'),
                'patterns_detected': gex_patterns,
                'confidence': confidence,
                'insights': insights,
                'gamma_levels': chart_analysis.get('gamma_levels', []),
                'price_levels': chart_analysis.get('price_levels', []),
                'analysis_quality': self._assess_image_quality(cv_image)
            }
            
        except Exception as e:
            return self._fallback_analysis(f"Analysis error: {str(e)}")
    
    def process_gex_data_visually(self, gex_data: Dict) -> Dict:
        """
        Process numerical GEX data and create visual insights
        """
        try:
            insights = []
            recommendations = []
            
            # Extract key metrics
            net_gex = gex_data.get('net_gex', 0)
            gamma_flip = gex_data.get('gamma_flip', 0)
            call_walls = gex_data.get('call_walls', [])
            put_walls = gex_data.get('put_walls', [])
            
            # Analyze GEX regime
            if net_gex < -1000000000:  # Highly negative
                insights.append("🔥 Extremely negative GEX - squeeze setup likely")
                recommendations.append("Consider long calls above gamma flip")
            elif net_gex > 2000000000:  # Highly positive
                insights.append("🛡️ High positive GEX - range-bound environment")
                recommendations.append("Consider iron condor or premium selling")
            else:
                insights.append("📊 Moderate GEX - mixed signals")
                recommendations.append("Wait for clearer directional bias")
            
            # Analyze walls
            if call_walls:
                strongest_call = max(call_walls, key=lambda x: x.get('strength', 0))
                insights.append(f"🔴 Strong call wall at ${strongest_call.get('strike', 'N/A')}")
                
            if put_walls:
                strongest_put = max(put_walls, key=lambda x: x.get('strength', 0))
                insights.append(f"🟢 Strong put wall at ${strongest_put.get('strike', 'N/A')}")
            
            return {
                'success': True,
                'insights': insights,
                'recommendations': recommendations,
                'visual_score': self._calculate_setup_score(gex_data),
                'key_levels': {
                    'gamma_flip': gamma_flip,
                    'resistance': [w['strike'] for w in call_walls[:3]],
                    'support': [w['strike'] for w in put_walls[:3]]
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'insights': [],
                'recommendations': []
            }
    
    def _load_image(self, image_source) -> Optional[Image.Image]:
        """Load image from file upload or URL"""
        try:
            if isinstance(image_source, str):  # URL
                response = requests.get(image_source, timeout=10)
                image = Image.open(BytesIO(response.content))
            else:  # Uploaded file
                image = Image.open(image_source)
                
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
                
            return image
            
        except Exception as e:
            st.error(f"Failed to load image: {str(e)}")
            return None
    
    def _pil_to_cv2(self, pil_image: Image.Image) -> np.ndarray:
        """Convert PIL image to OpenCV format"""
        if not self.opencv_available:
            return np.array(pil_image)
        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    
    def _detect_chart_elements(self, cv_image: np.ndarray) -> Dict:
        """Detect chart elements using OpenCV"""
        if not self.opencv_available:
            return {'chart_type': 'GEX_PROFILE', 'gamma_spikes': []}
            
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            
            # Detect edges
            edges = cv2.Canny(gray, 50, 150, apertureSize=3, L2gradient=True)
            
            # Find contours for potential gamma spikes
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            gamma_spikes = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 500:  # Filter small noise
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = h / w if w > 0 else 0
                    
                    # Look for tall, narrow shapes (potential gamma spikes)
                    if aspect_ratio > 2 and h > 50:
                        gamma_spikes.append({
                            'x': x + w/2,
                            'y': y,
                            'height': h,
                            'width': w,
                            'area': area
                        })
            
            return {
                'chart_type': 'GEX_PROFILE',
                'gamma_spikes': gamma_spikes,
                'image_dimensions': cv_image.shape
            }
            
        except Exception as e:
            return {'chart_type': 'Unknown', 'gamma_spikes': []}
    
    def _identify_gex_patterns(self, cv_image: np.ndarray, chart_analysis: Dict) -> List[Dict]:
        """Identify GEX patterns from chart elements"""
        patterns = []
        gamma_spikes = chart_analysis.get('gamma_spikes', [])
        
        if not gamma_spikes:
            return patterns
        
        # Sort spikes by height to find the strongest
        gamma_spikes.sort(key=lambda x: x['height'], reverse=True)
        
        # Detect gamma walls (tall spikes)
        for spike in gamma_spikes[:5]:  # Top 5 spikes
            if spike['height'] > 100:  # Significant height
                pattern_type = 'call_wall' if spike['y'] < cv_image.shape[0] / 2 else 'put_wall'
                patterns.append({
                    'type': pattern_type,
                    'strength': spike['height'] * spike['area'] / 10000,
                    'location': spike['x'],
                    'confidence': min(0.9, spike['height'] / 200)
                })
        
        return patterns
    
    def _calculate_visual_confidence(self, chart_analysis: Dict, patterns: List[Dict]) -> float:
        """Calculate confidence in visual analysis"""
        if not patterns:
            return 0.3
        
        pattern_confidences = [p['confidence'] for p in patterns]
        return np.mean(pattern_confidences)
    
    def _generate_visual_insights(self, patterns: List[Dict], confidence: float) -> List[str]:
        """Generate insights from visual patterns"""
        insights = []
        
        if confidence < 0.4:
            insights.append("⚠️ Low confidence analysis")
            return insights
        
        call_walls = [p for p in patterns if p['type'] == 'call_wall']
        put_walls = [p for p in patterns if p['type'] == 'put_wall']
        
        if call_walls:
            insights.append("🔴 Call resistance detected")
        if put_walls:
            insights.append("🟢 Put support detected")
        
        if not call_walls and not put_walls:
            insights.append("📊 Balanced profile detected")
            
        return insights
    
    def _assess_image_quality(self, cv_image: np.ndarray) -> Dict:
        """Assess image quality for analysis"""
        if not self.opencv_available:
            return {'quality_score': 0.5}
            
        try:
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            return {'quality_score': min(1.0, sharpness / 1000)}
        except:
            return {'quality_score': 0.5}
    
    def _calculate_setup_score(self, gex_data: Dict) -> float:
        """Calculate numerical score for setup quality"""
        score = 0.5  # Base score
        
        net_gex = abs(gex_data.get('net_gex', 0))
        if net_gex > 1000000000:  # 1B+
            score += 0.3
        elif net_gex > 500000000:  # 500M+
            score += 0.2
        
        call_walls = len(gex_data.get('call_walls', []))
        put_walls = len(gex_data.get('put_walls', []))
        
        if call_walls > 0 or put_walls > 0:
            score += 0.2
            
        return min(1.0, score)
    
    def _fallback_analysis(self, error_msg: str) -> Dict:
        """Fallback when visual analysis fails"""
        return {
            'success': False,
            'chart_type': 'Unknown',
            'patterns_detected': [],
            'confidence': 0.0,
            'insights': [f"❌ {error_msg}"],
            'gamma_levels': [],
            'price_levels': [],
            'analysis_quality': {'quality_score': 0.0}
        }
    
    def create_sample_chart(self, symbol: str = "SPY") -> go.Figure:
        """Create sample GEX chart"""
        strikes = np.arange(400, 500, 5)
        call_gex = np.random.exponential(100, len(strikes))
        put_gex = -np.random.exponential(80, len(strikes))
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=strikes,
            y=call_gex,
            name='Call GEX',
            marker_color='red',
            opacity=0.7
        ))
        
        fig.add_trace(go.Bar(
            x=strikes,
            y=put_gex,
            name='Put GEX',
            marker_color='green',
            opacity=0.7
        ))
        
        fig.update_layout(
            title=f"{symbol} GEX Profile",
            xaxis_title="Strike Price",
            yaxis_title="Gamma Exposure ($M)",
            height=500
        )
        
        return fig

# Create default instance
visual_coordinator = VisualIntelligenceCoordinator()
