"""
Data Extraction Module

Handles fetching content from external sources:
- YouTube transcripts
- Google Docs
- Other document formats

Pure functions with no UI dependencies.
"""

import re
import requests
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi


# ==============================================================================
# YouTube Transcript Extraction
# ==============================================================================

def extract_video_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats.
    
    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    
    Args:
        url: YouTube video URL
        
    Returns:
        Video ID string or None if not found
    """
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)',
        r'youtube\.com\/embed\/([\w-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_youtube_transcript(video_id: str) -> Optional[str]:
    """
    Fetch transcript for a YouTube video.
    
    Attempts to retrieve English transcripts first, then falls back to
    any available language.
    
    Args:
        video_id: YouTube video identifier
        
    Returns:
        Full transcript text or None if unavailable
    """
    try:
        # Try English variants first
        languages_to_try = ['en', 'en-US', 'en-GB']
        
        for lang in languages_to_try:
            try:
                transcript_data = YouTubeTranscriptApi.get_transcript(
                    video_id, 
                    languages=[lang]
                )
                full_transcript = " ".join([item["text"] for item in transcript_data])
                return full_transcript
            except:
                continue
        
        # Fallback: try any available language
        try:
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            full_transcript = " ".join([item["text"] for item in transcript_data])
            return full_transcript
        except:
            return None
            
    except Exception:
        return None


# ==============================================================================
# Google Docs Extraction
# ==============================================================================

def extract_google_doc_id(url: str) -> Optional[str]:
    """
    Extract document ID from Google Docs URL.
    
    Args:
        url: Google Docs sharing URL
        
    Returns:
        Document ID or None if invalid
    """
    pattern = r'docs\.google\.com/document/d/([a-zA-Z0-9-_]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None


def get_google_doc_content(doc_url: str) -> Optional[str]:
    """
    Fetch plain text content from a publicly shared Google Doc.
    
    REQUIREMENTS:
    - Document must be shared with "Anyone with the link can view"
    - Link sharing must be enabled
    
    Args:
        doc_url: Full Google Docs URL
        
    Returns:
        Document text content or None on failure
        
    Raises:
        ValueError: If URL is invalid
        PermissionError: If document is not accessible
        TimeoutError: If request times out
    """
    doc_id = extract_google_doc_id(doc_url)
    if not doc_id:
        raise ValueError("Invalid Google Docs URL format")
    
    # Export URL for plain text
    export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    
    try:
        response = requests.get(export_url, timeout=10)
        
        if response.status_code == 200:
            content = response.text.strip()
            if content:
                return content
            else:
                raise ValueError("Document is empty")
        elif response.status_code == 403 or response.status_code == 401:
            raise PermissionError(
                "Cannot access document. Ensure it's shared as 'Anyone with the link can view'"
            )
        else:
            raise RuntimeError(f"HTTP {response.status_code}: Failed to fetch document")
            
    except requests.exceptions.Timeout:
        raise TimeoutError("Request timeout - check internet connection")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error: {str(e)}")
