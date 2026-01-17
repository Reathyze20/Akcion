"""
Data Extraction Module

Handles fetching content from external sources:
- YouTube transcripts
- Google Docs
- Other document formats

Clean Code Principles Applied:
- Pure functions with no side effects
- Explicit error handling (no bare except)
- Single Responsibility per function
- Dependency on abstractions (constants module)

No UI dependencies - backend only.
"""

from __future__ import annotations

import logging
import re
from typing import Final

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from .constants import (
    ERROR_MESSAGES,
    REQUEST_TIMEOUT_SECONDS,
    TRANSCRIPT_LANGUAGES,
    URL_PATTERNS,
)


logger = logging.getLogger(__name__)


# ==============================================================================
# URL Pattern Compilation (Performance optimization)
# ==============================================================================

_YOUTUBE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(URL_PATTERNS.youtube_watch),
    re.compile(URL_PATTERNS.youtube_embed),
)

_GOOGLE_DOCS_PATTERN: Final[re.Pattern[str]] = re.compile(URL_PATTERNS.google_docs)


# ==============================================================================
# YouTube Transcript Extraction
# ==============================================================================

def extract_video_id(url: str) -> str | None:
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
        
    Example:
        >>> extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        "dQw4w9WgXcQ"
    """
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def get_youtube_transcript(video_id: str) -> str | None:
    """
    Fetch transcript for a YouTube video.
    
    Attempts to retrieve English transcripts first, then falls back to
    any available language.
    
    Args:
        video_id: YouTube video identifier
        
    Returns:
        Full transcript text or None if unavailable
        
    Note:
        Uses explicit exception handling per Clean Code guidelines.
        Each failure mode is logged for debugging.
    """
    transcript = _try_fetch_preferred_languages(video_id)
    if transcript:
        return transcript
    
    return _try_fetch_any_language(video_id)


def _try_fetch_preferred_languages(video_id: str) -> str | None:
    """
    Try to fetch transcript in preferred languages (English variants).
    
    Args:
        video_id: YouTube video identifier
        
    Returns:
        Transcript text or None if not available in preferred languages
    """
    for lang in TRANSCRIPT_LANGUAGES:
        try:
            transcript_data = YouTubeTranscriptApi.get_transcript(
                video_id, 
                languages=[lang]
            )
            return _join_transcript_segments(transcript_data)
        except (NoTranscriptFound, TranscriptsDisabled):
            logger.debug(f"No transcript in {lang} for video {video_id}")
            continue
        except VideoUnavailable:
            logger.warning(f"Video {video_id} is unavailable")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error fetching {lang} transcript: {e}")
            continue
    
    return None


def _try_fetch_any_language(video_id: str) -> str | None:
    """
    Fallback: try to fetch transcript in any available language.
    
    Args:
        video_id: YouTube video identifier
        
    Returns:
        Transcript text or None if no transcripts available
    """
    try:
        transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
        return _join_transcript_segments(transcript_data)
    except (NoTranscriptFound, TranscriptsDisabled) as e:
        logger.info(f"No transcripts available for video {video_id}: {e}")
        return None
    except VideoUnavailable:
        logger.warning(f"Video {video_id} is unavailable")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch any transcript for {video_id}: {e}")
        return None


def _join_transcript_segments(transcript_data: list[dict[str, str]]) -> str:
    """
    Join transcript segments into a single string.
    
    Args:
        transcript_data: List of segment dictionaries with 'text' key
        
    Returns:
        Space-joined transcript text
    """
    return " ".join(item["text"] for item in transcript_data)


# ==============================================================================
# Google Docs Extraction
# ==============================================================================

def extract_google_doc_id(url: str) -> str | None:
    """
    Extract document ID from Google Docs URL.
    
    Args:
        url: Google Docs sharing URL
        
    Returns:
        Document ID or None if invalid format
        
    Example:
        >>> extract_google_doc_id("https://docs.google.com/document/d/abc123/edit")
        "abc123"
    """
    match = _GOOGLE_DOCS_PATTERN.search(url)
    if match:
        return match.group(1)
    return None


def get_google_doc_content(doc_url: str) -> str:
    """
    Fetch plain text content from a publicly shared Google Doc.
    
    REQUIREMENTS:
    - Document must be shared with "Anyone with the link can view"
    - Link sharing must be enabled
    
    Args:
        doc_url: Full Google Docs URL
        
    Returns:
        Document text content
        
    Raises:
        ValueError: If URL is invalid or document is empty
        PermissionError: If document is not accessible
        TimeoutError: If request times out
        RuntimeError: For other network/HTTP errors
    """
    doc_id = extract_google_doc_id(doc_url)
    if not doc_id:
        raise ValueError(ERROR_MESSAGES.INVALID_GOOGLE_DOCS_URL)
    
    export_url = _build_google_docs_export_url(doc_id)
    return _fetch_document_content(export_url)


def _build_google_docs_export_url(doc_id: str) -> str:
    """
    Build the export URL for fetching Google Doc as plain text.
    
    Args:
        doc_id: Google Docs document ID
        
    Returns:
        Full export URL
    """
    return f"https://docs.google.com/document/d/{doc_id}/export?format=txt"


def _fetch_document_content(export_url: str) -> str:
    """
    Fetch document content from Google Docs export URL.
    
    Args:
        export_url: Google Docs export URL
        
    Returns:
        Document text content
        
    Raises:
        PermissionError: If access denied (401/403)
        TimeoutError: If request times out
        RuntimeError: For other HTTP/network errors
        ValueError: If document is empty
    """
    try:
        response = requests.get(export_url, timeout=REQUEST_TIMEOUT_SECONDS)
        return _process_document_response(response)
        
    except requests.exceptions.Timeout:
        raise TimeoutError(ERROR_MESSAGES.REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error: {e}")


def _process_document_response(response: requests.Response) -> str:
    """
    Process HTTP response from Google Docs export.
    
    Args:
        response: HTTP response object
        
    Returns:
        Document text content
        
    Raises:
        PermissionError: If access denied
        RuntimeError: For other HTTP errors
        ValueError: If document is empty
    """
    if response.status_code == 200:
        content = response.text.strip()
        if not content:
            raise ValueError(ERROR_MESSAGES.EMPTY_DOCUMENT)
        return content
    
    if response.status_code in (401, 403):
        raise PermissionError(ERROR_MESSAGES.DOCUMENT_ACCESS_DENIED)
    
    raise RuntimeError(f"HTTP {response.status_code}: Failed to fetch document")
