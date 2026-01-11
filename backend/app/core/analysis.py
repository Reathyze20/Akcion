"""
Core AI Analysis Module

CRITICAL BUSINESS LOGIC: This module handles all interactions with the Gemini AI.
The prompts and analysis flow here directly impact investment decisions affecting
family financial security.

TESTING REQUIREMENTS:
- Any changes must be validated against known Mark Gomes transcripts
- Expected output: 100% stock mention capture rate
- Gomes scoring must remain consistent with manual analysis
"""

import json
import re
from typing import Dict, List, Optional
import google.generativeai as genai

from .prompts import (
    FIDUCIARY_ANALYST_PROMPT,
    GOOGLE_SEARCH_CONFIG,
    GEMINI_MODEL_NAME,
    get_analysis_prompt
)


class StockAnalyzer:
    """
    Handles AI-powered stock analysis using Gemini.
    
    This class encapsulates the entire analysis pipeline:
    1. Configure Gemini with API key
    2. Apply fiduciary system prompt
    3. Enable Google Search for real-time data
    4. Parse and validate JSON responses
    """
    
    def __init__(self, api_key: str):
        """
        Initialize the analyzer with Gemini API credentials.
        
        Args:
            api_key: Google Gemini API key
        """
        self.api_key = api_key
        genai.configure(api_key=api_key)
        
    def analyze_transcript(self, transcript: str) -> Optional[Dict]:
        """
        Analyze investment transcript and extract all stock mentions.
        
        This is the CORE analysis function. It:
        - Sends transcript to Gemini with fiduciary prompt
        - Enables Google Search for verification
        - Returns structured stock data following Gomes methodology
        
        Args:
            transcript: Investment video/document content
            
        Returns:
            Dictionary with structure:
            {
                "stocks": [
                    {
                        "ticker": str,
                        "company_name": str,
                        "sentiment": str,
                        "gomes_score": int,
                        "price_target": str,
                        "edge": str,
                        "catalysts": str,
                        "risks": str,
                        "status": str
                    }
                ]
            }
            Returns None if analysis fails
        """
        try:
            # Initialize model with:
            # 1. System instruction (fiduciary analyst persona)
            # 2. Google Search tools for real-time data
            model = genai.GenerativeModel(
                GEMINI_MODEL_NAME,
                tools=GOOGLE_SEARCH_CONFIG,
                system_instruction=FIDUCIARY_ANALYST_PROMPT
            )
            
            # Generate analysis prompt
            prompt = get_analysis_prompt(transcript)
            
            # Call Gemini API
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Clean up response (remove markdown code blocks if present)
            result_text = self._clean_json_response(result_text)
            
            # Parse JSON
            result = json.loads(result_text)
            
            return result
            
        except json.JSONDecodeError as e:
            raise ValueError(f"AI returned invalid JSON: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Analysis failed: {str(e)}")
    
    def _clean_json_response(self, text: str) -> str:
        """
        Remove markdown code fences from AI response.
        
        Gemini sometimes wraps JSON in ```json ... ``` blocks.
        This strips them to get pure JSON.
        """
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\n', '', text)
            text = re.sub(r'\n```$', '', text)
        return text


# ==============================================================================
# Convenience Function for Backward Compatibility
# ==============================================================================

def analyze_with_gemini(transcript: str, api_key: str) -> Optional[Dict]:
    """
    Legacy function signature for backward compatibility.
    
    This maintains the same interface as the original Streamlit app.
    
    Args:
        transcript: Investment content to analyze
        api_key: Gemini API key
        
    Returns:
        Analysis results dictionary or None on failure
    """
    try:
        analyzer = StockAnalyzer(api_key)
        return analyzer.analyze_transcript(transcript)
    except Exception:
        return None
