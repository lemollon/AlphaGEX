"""
GammaHunter Visual Analyzer
==========================

Chart image analysis and pattern recognition for gamma exposure profiles.
"""

import cv2
import numpy as np
from PIL import Image, ImageEnhance
from io import BytesIO
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from config import VISUAL_CONFIDENCE_THRESHOLD, SUPPORTED_IMAGE_FORMATS, IMAGE_MAX_SIZE_MB
from core.logger import log_error, log_decision

@dataclass
class ChartElement:
    element_type: str  # 'gamma_stack', 'wall', 'flip_point', 'price_line'
    coordinates: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    properties: Dict[str, Any]

@dataclass
class VisualAnalysis:
    chart_type: str
    detected_elements: List[ChartElement]
    extracted_data: Dict[str, Any]
    analysis_confidence: float
    recommendations: List[str]

class ImagePreprocessor:
    """Image preprocessing for better chart analysis"""
    
    def preprocess_image(self, image_data: bytes) -> Optional[np.ndarray]:
        """Preprocess image for analysis"""
        try:
            # Check file size
            if len(image_data) > IMAGE_MAX_SIZE_MB * 1024 * 1024:
                raise ValueError(f"Image too large (max {IMAGE_MAX_SIZE_MB}MB)")
            
            # Convert to PIL Image
            image = Image.open(BytesIO(image_data))
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Enhance for better detection
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.2)
            
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.1)
            
            # Convert to OpenCV format
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            return cv_image
            
        except Exception as e:
            log_error("image_preprocessing", e)
            return None
    
    def detect_chart_type(self, image: np.ndarray) -> str:
        """Detect chart type from image"""
        
        # Simple heuristics for chart type detection
        # In production, would use more sophisticated methods
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Look for characteristic patterns
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Count rectangular regions (potential gamma bars)
        rectangular_count = 0
        for contour in contours:
            approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
            if len(approx) == 4:  # Rectangle
                rectangular_count += 1
        
        if rectangular_count > 10:
            return 'gex_profile'
        else:
            return 'unknown'

class GEXChartAnalyzer:
    """Specialized GEX profile chart analyzer"""
    
    def __init__(self):
        self.preprocessor = ImagePreprocessor()
    
    def analyze_gex_chart(self, image_data: bytes) -> VisualAnalysis:
        """Analyze GEX profile chart"""
        
        try:
            processed_image = self.preprocessor.preprocess_image(image_data)
            if processed_image is None:
                raise ValueError("Failed to preprocess image")
            
            detected_elements = self._detect_chart_elements(processed_image)
            extracted_data = self._extract_gex_data(processed_image, detected_elements)
            confidence = self._calculate_confidence(detected_elements)
            recommendations = self._generate_recommendations(extracted_data, detected_elements)
            
            return VisualAnalysis(
                chart_type='gex_profile',
                detected_elements=detected_elements,
                extracted_data=extracted_data,
                analysis_confidence=confidence,
                recommendations=recommendations
            )
            
        except Exception as e:
            log_error("gex_chart_analysis", e)
            return VisualAnalysis(
                chart_type='unknown',
                detected_elements=[],
                extracted_data={},
                analysis_confidence=0,
                recommendations=["Image analysis failed - check image quality"]
            )
    
    def _detect_chart_elements(self, image: np.ndarray) -> List[ChartElement]:
        """Detect key elements in GEX chart"""
        
        elements = []
        
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Detect horizontal lines (gamma walls)
            horizontal_lines = self._detect_horizontal_lines(gray)
            for line in horizontal_lines:
                elements.append(ChartElement(
                    element_type='potential_wall',
                    coordinates=line,
                    confidence=75.0,
                    properties={'line_length': line[2] - line[0]}
                ))
            
            # Detect vertical lines (price levels)
            vertical_lines = self._detect_vertical_lines(gray)
            for line in vertical_lines:
                elements.append(ChartElement(
                    element_type='price_line',
                    coordinates=line,
                    confidence=70.0,
                    properties={'line_height': line[3] - line[1]}
                ))
            
            # Detect gamma stacks (rectangular regions)
            gamma_stacks = self._detect_gamma_stacks(image)
            elements.extend(gamma_stacks)
            
        except Exception as e:
            log_error("element_detection", e)
        
        return elements
    
    def _detect_horizontal_lines(self, gray_image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect horizontal lines (potential gamma walls)"""
        
        edges = cv2.Canny(gray_image, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=100, maxLineGap=10)
        
        horizontal_lines = []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                if angle < 10 or angle > 170:  # Nearly horizontal
                    horizontal_lines.append((x1, y1, x2, y2))
        
        return horizontal_lines
    
    def _detect_vertical_lines(self, gray_image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect vertical lines (price levels)"""
        
        edges = cv2.Canny(gray_image, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80, minLineLength=50, maxLineGap=10)
        
        vertical_lines = []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                if 80 < angle < 100:  # Nearly vertical
                    vertical_lines.append((x1, y1, x2, y2))
        
        return vertical_lines
    
    def _detect_gamma_stacks(self, image: np.ndarray) -> List[ChartElement]:
        """Detect rectangular regions (potential gamma stacks)"""
        
        stacks = []
        
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
            
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = cv2.contourArea(contour)
                
                if (area > 1000 and w > 20 and h > 20 and area / (w * h) > 0.3):
                    confidence = min(90, 50 + (area / 5000) * 20)
                    
                    element = ChartElement(
                        element_type='gamma_stack',
                        coordinates=(x, y, x + w, y + h),
                        confidence=confidence,
                        properties={
                            'area': area,
                            'aspect_ratio': w / h,
                            'width': w,
                            'height': h
                        }
                    )
                    stacks.append(element)
            
            return stacks[:10]  # Limit to top 10
            
        except Exception as e:
            log_error("gamma_stack_detection", e)
            return []
    
    def _extract_gex_data(self, image: np.ndarray, elements: List[ChartElement]) -> Dict[str, Any]:
        """Extract numerical GEX data from chart"""
        
        extracted_data = {
            'estimated_net_gex': 0,
            'estimated_flip_point': 0,
            'detected_walls': len([e for e in elements if e.element_type == 'potential_wall']),
            'detected_stacks': len([e for e in elements if e.element_type == 'gamma_stack']),
            'chart_dimensions': image.shape[:2],
            'extraction_method': 'pattern_recognition'
        }
        
        # Find dominant stack
        gamma_stacks = [e for e in elements if e.element_type == 'gamma_stack']
        if gamma_stacks:
            largest_stack = max(gamma_stacks, key=lambda x: x.properties.get('area', 0))
            extracted_data['dominant_stack_position'] = {
                'x_ratio': (largest_stack.coordinates[0] + largest_stack.coordinates[2]) / 2 / image.shape[1],
                'y_ratio': (largest_stack.coordinates[1] + largest_stack.coordinates[3]) / 2 / image.shape[0],
                'size_score': largest_stack.properties.get('area', 0)
            }
        
        return extracted_data
    
    def _calculate_confidence(self, elements: List[ChartElement]) -> float:
        """Calculate overall analysis confidence"""
        
        if not elements:
            return 0
        
        element_count_score = min(40, len(elements) * 8)
        avg_element_confidence = sum(e.confidence for e in elements) / len(elements)
        gamma_stack_bonus = 20 if any(e.element_type == 'gamma_stack' for e in elements) else 0
        
        return min(95, element_count_score + avg_element_confidence * 0.4 + gamma_stack_bonus)
    
    def _generate_recommendations(self, extracted_data: Dict[str, Any], 
                                elements: List[ChartElement]) -> List[str]:
        """Generate recommendations based on visual analysis"""
        
        recommendations = []
        
        stack_count = extracted_data.get('detected_stacks', 0)
        if stack_count > 0:
            recommendations.append(f"Detected {stack_count} potential gamma stacks")
        
        wall_count = extracted_data.get('detected_walls', 0)
        if wall_count >= 2:
            recommendations.append(f"Found {wall_count} potential gamma walls")
        
        if 'dominant_stack_position' in extracted_data:
            pos = extracted_data['dominant_stack_position']
            if pos['x_ratio'] < 0.5:
                recommendations.append("Large gamma concentration on left side of chart")
            else:
                recommendations.append("Large gamma concentration on right side of chart")
        
        if not recommendations:
            recommendations.append("Chart pattern unclear - validate with API data")
        
        return recommendations

class VisualIntelligenceCoordinator:
    """Main coordinator for visual intelligence"""
    
    def __init__(self, behavioral_engine=None):
        self.gex_analyzer = GEXChartAnalyzer()
        self.behavioral_engine = behavioral_engine
    
    def analyze_chart_image(self, image_data: bytes, symbol: str = None,
                          api_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Complete chart image analysis with API validation"""
        
        try:
            # Visual analysis
            visual_analysis = self.gex_analyzer.analyze_gex_chart(image_data)
            
            # Validate against API data if available
            validation_results = {}
            if api_data and symbol:
                validation_results = self._validate_against_api(visual_analysis, api_data)
            
            # Generate integrated insights
            integrated_insights = self._generate_integrated_insights(
                visual_analysis, validation_results, symbol
            )
            
            overall_confidence = self._calculate_overall_confidence(
                visual_analysis, validation_results
            )
            
            # Log the analysis
            log_decision(
                decision_type="visual_analysis",
                confidence_score=overall_confidence,
                reasoning_steps=visual_analysis.recommendations,
                supporting_evidence=[f"Detected {len(visual_analysis.detected_elements)} elements"],
                contrary_evidence=["Visual analysis has numerical limitations"],
                final_recommendation=f"Visual analysis complete: {overall_confidence:.0f}% confidence"
            )
            
            return {
                "visual_analysis": visual_analysis,
                "validation_results": validation_results,
                "integrated_insights": integrated_insights,
                "overall_confidence": overall_confidence,
                "recommendations": self._prioritize_recommendations(visual_analysis, validation_results)
            }
            
        except Exception as e:
            error_id = log_error("visual_analysis_coordinator", e)
            return {
                "error": f"Visual analysis failed: {str(e)}",
                "error_id": error_id,
                "overall_confidence": 0,
                "recommendations": ["Visual analysis unavailable - use API data only"]
            }
    
    def _validate_against_api(self, visual_analysis: VisualAnalysis, 
                            api_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate visual analysis against API data"""
        
        validation = {
            "agreement_score": 0,
            "discrepancies": [],
            "confirmations": [],
            "data_quality": "unknown"
        }
        
        try:
            detected_stacks = visual_analysis.extracted_data.get('detected_stacks', 0)
            detected_walls = visual_analysis.extracted_data.get('detected_walls', 0)
            
            api_net_gex = api_data.get('net_gex', 0)
            api_strikes = api_data.get('strikes', [])
            
            agreement_points = 0
            
            # Validate stack detection
            large_negative_gex = api_net_gex < -500_000_000
            if large_negative_gex and detected_stacks > 0:
                validation["confirmations"].append("Visual stacks match negative GEX")
                agreement_points += 25
            elif not large_negative_gex and detected_stacks == 0:
                validation["confirmations"].append("No stacks matches moderate GEX")
                agreement_points += 15
            
            # Validate wall detection
            significant_strikes = len([s for s in api_strikes if abs(s.get('gex', 0)) > 100_000_000])
            if detected_walls > 0 and significant_strikes > 0:
                validation["confirmations"].append(f"Visual walls match {significant_strikes} API strikes")
                agreement_points += 25
            
            # Data quality assessment
            if len(api_strikes) > 10:
                validation["data_quality"] = "good"
                agreement_points += 10
            elif len(api_strikes) > 5:
                validation["data_quality"] = "moderate"
                agreement_points += 5
            
            validation["agreement_score"] = min(100, agreement_points)
            
        except Exception as e:
            log_error("api_validation", e)
        
        return validation
    
    def _generate_integrated_insights(self, visual_analysis: VisualAnalysis,
                                    validation_results: Dict[str, Any],
                                    symbol: str) -> List[str]:
        """Generate insights combining visual and API analysis"""
        
        insights = []
        agreement_score = validation_results.get('agreement_score', 0)
        
        if agreement_score > 70:
            insights.append("Visual and API analysis strongly agree")
            insights.extend(visual_analysis.recommendations)
        elif agreement_score > 40:
            insights.append("Moderate agreement between visual and API analysis")
            insights.append("Recommend combining both sources")
        else:
            insights.append("Visual and API analysis differ significantly")
            insights.append("Prioritize API data for numerical accuracy")
        
        if symbol in ['SPY', 'QQQ', 'IWM']:
            insights.append(f"For {symbol}: Focus on major gamma levels")
        
        return insights
    
    def _calculate_overall_confidence(self, visual_analysis: VisualAnalysis,
                                    validation_results: Dict[str, Any]) -> float:
        """Calculate overall confidence"""
        
        visual_confidence = visual_analysis.analysis_confidence
        
        if not validation_results:
            return visual_confidence * 0.7
        
        agreement_score = validation_results.get('agreement_score', 0)
        return min(95, (visual_confidence * 0.6) + (agreement_score * 0.4))
    
    def _prioritize_recommendations(self, visual_analysis: VisualAnalysis,
                                  validation_results: Dict[str, Any]) -> List[str]:
        """Prioritize recommendations"""
        
        prioritized = []
        
        if visual_analysis.analysis_confidence > VISUAL_CONFIDENCE_THRESHOLD:
            prioritized.extend(visual_analysis.recommendations)
        
        if validation_results.get('agreement_score', 0) > 60:
            prioritized.append("Visual analysis confirmed by API data")
        elif validation_results.get('discrepancies'):
            prioritized.append("Discrepancies detected - verify manually")
        
        prioritized.extend([
            "Always validate visual analysis with API data",
            "Use visual patterns for context, API for precision"
        ])
        
        return prioritized
