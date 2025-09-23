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
        lines = cv2
