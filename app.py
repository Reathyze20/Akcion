"""
Akcion - Investment Video Analysis Application
Analyze YouTube investment videos and track stock mentions with AI
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import re
import json
from typing import Dict, List, Optional
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import requests

# ============================================================================
# DATABASE SETUP - PostgreSQL with SQLAlchemy
# ============================================================================

Base = declarative_base()

# Global variables for database connection
engine = None
Session = None
db_error = None

class Stock(Base):
    """SQLAlchemy model for stocks table"""
    __tablename__ = 'stocks'
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())
    ticker = Column(String(20), nullable=False)
    company_name = Column(String(200))
    source_type = Column(String(50))  # YouTube, WhatsApp, Google Docs, etc.
    speaker = Column(String(100))  # Mark Gomes, etc.
    sentiment = Column(String(50))
    gomes_score = Column(Integer)
    price_target = Column(Text)  # Changed to Text to handle long descriptions
    edge = Column(Text)  # Information Arbitrage
    catalysts = Column(Text)
    risks = Column(Text)
    raw_notes = Column(Text)
    time_horizon = Column(String(100))  # Increased from 50
    conviction_score = Column(Integer)

def init_database():
    """Initialize PostgreSQL connection and create tables"""
    global engine, Session, db_error
    
    try:
        # Get connection string from Streamlit secrets
        if "postgres" not in st.secrets or "url" not in st.secrets["postgres"]:
            db_error = "⚠️ Database not configured. Please add 'postgres.url' to .streamlit/secrets.toml"
            return False
        
        conn_str = st.secrets["postgres"]["url"]
        
        # Create engine
        engine = create_engine(conn_str, pool_pre_ping=True)
        
        # Create session factory
        Session = sessionmaker(bind=engine)
        
        # Create tables if they don't exist
        Base.metadata.create_all(engine)
        
        db_error = None
        return True
        
    except Exception as e:
        db_error = f"❌ Database connection failed: {str(e)}"
        engine = None
        Session = None
        return False

def save_analysis(source_id: str, source_type: str, stocks: List[Dict], speaker: str = "Mark Gomes"):
    """Save analysis to PostgreSQL database"""
    global Session
    
    if not Session:
        st.error("Database not connected")
        return
    
    session = Session()
    try:
        # Insert each stock
        for stock_data in stocks:
            stock = Stock(
                ticker=stock_data.get("ticker", ""),
                company_name=stock_data.get("company_name", stock_data.get("name", "")),
                source_type=source_type,
                speaker=speaker,
                sentiment=stock_data.get("sentiment", ""),
                gomes_score=stock_data.get("gomes_score", 5),
                price_target=stock_data.get("price_target", ""),
                edge=stock_data.get("edge", ""),
                catalysts=stock_data.get("catalysts", ""),
                risks=stock_data.get("risks", ""),
                raw_notes=stock_data.get("note", stock_data.get("status", "")),
                time_horizon=stock_data.get("horizon", "Long-term"),
                conviction_score=stock_data.get("conviction_score", stock_data.get("gomes_score", 5))
            )
            session.add(stock)
        
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        st.error(f"Error saving to database: {str(e)}")
    finally:
        session.close()

# ============================================================================
# YOUTUBE & AI FUNCTIONS
# ============================================================================

def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)',
        r'youtube\.com\/embed\/([\w-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def extract_google_doc_id(url: str) -> Optional[str]:
    """Extract Google Docs document ID from URL"""
    patterns = [
        r'docs\.google\.com/document/d/([a-zA-Z0-9-_]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_google_doc_content(doc_url: str) -> Optional[str]:
    """Fetch content from a publicly shared Google Doc"""
    try:
        doc_id = extract_google_doc_id(doc_url)
        if not doc_id:
            st.error("❌ Invalid Google Docs URL")
            return None
        
        # Try to access as plain text export
        export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
        
        response = requests.get(export_url, timeout=10)
        
        if response.status_code == 200:
            content = response.text.strip()
            if content:
                return content
            else:
                st.error("❌ Document is empty")
                return None
        else:
            st.error("❌ Cannot access document. Please ensure:\n1. Document is set to 'Anyone with the link can view'\n2. Link sharing is enabled")
            st.info("💡 To share: Open your Google Doc → Click 'Share' → Change to 'Anyone with the link' → Copy link")
            return None
            
    except requests.exceptions.Timeout:
        st.error("❌ Request timeout. Please check your internet connection.")
        return None
    except Exception as e:
        st.error(f"❌ Error fetching Google Doc: {str(e)}")
        st.info("💡 Make sure your document is publicly accessible (Anyone with the link can view)")
        return None

def get_transcript(video_id: str) -> Optional[str]:
    """Fetch YouTube transcript"""
    try:
        # Try to get transcript - try multiple language codes
        languages_to_try = ['en', 'en-US', 'en-GB']
        
        for lang in languages_to_try:
            try:
                transcript_data = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
                full_transcript = " ".join([item["text"] for item in transcript_data])
                return full_transcript
            except:
                continue
        
        # If English fails, try to get any available transcript
        try:
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            full_transcript = " ".join([item["text"] for item in transcript_data])
            return full_transcript
        except:
            pass
            
        st.error("No transcript available for this video. Please try a video with captions/subtitles enabled.")
        return None
        
    except Exception as e:
        st.error(f"Error fetching transcript: {str(e)}")
        return None

def analyze_with_gemini(transcript: str, api_key: str) -> Optional[Dict]:
    """Send transcript to Gemini for stock analysis"""
    try:
        genai.configure(api_key=api_key)
        
        # System instruction - Defines AI "personality" that knows what's at stake
        safety_system_prompt = """
ROLE: You are a Fiduciary Senior Financial Analyst acting as a guardian for a client with a serious health condition (Multiple Sclerosis).
CONTEXT: The client relies on these insights for family financial security. Mistakes or missed opportunities cause significant stress, which impacts the client's health.

YOUR MISSION:
1.  **Analyze Mark Gomes' Transcripts:** You are analyzing informal speech. He speaks fast and uses slang.
2.  **AGGRESSIVE EXTRACTION:** You MUST extract EVERY stock mentioned, even if discussed briefly. If he says "Geodrill", you find the ticker (GEO.TO). If he says "Tech Precision", you find (TPCS). Do not filter out stocks just because the discussion is short.
3.  **Apply "The Rules":** For every stock, evaluate:
    * **Information Arbitrage:** What is the hidden "Edge"?
    * **Catalysts:** Specific dates/events.
    * **Risks:** Be brutally honest. If it's a gamble, say it.
4.  **Scoring:** Assign a 'Gomes Score' (1-10).
    * 10 = "Table Pounding Buy" (High Conviction, Clear Edge, Low Risk).
    * 1 = "Avoid" or "Sell".

OUTPUT FORMAT:
Return PURE JSON only. No markdown formatting, no introductory text.
Structure:
{
  "stocks": [
    {
      "ticker": "XYZ",
      "company_name": "Example Corp",
      "sentiment": "Bullish/Bearish/Neutral",
      "gomes_score": 8,
      "price_target": "Start buying at $5, sell at $10",
      "edge": "Market misses the new contract...",
      "catalysts": "Earnings on Feb 14th...",
      "risks": "Low liquidity, CEO history...",
      "status": "New Idea / Update"
    }
  ]
}
"""
        
        # Google Search tools configuration
        tools_config = [
            {
                "google_search_retrieval": {
                    "dynamic_retrieval_config": {
                        "mode": "dynamic",
                        "dynamic_threshold": 0.6,
                    }
                }
            }
        ]
        
        # Initialize model with Google Search capability and system instruction
        model = genai.GenerativeModel(
            'gemini-3-pro-preview',
            tools=tools_config,  # Enable Google Search for real-time data
            system_instruction=safety_system_prompt
        )
        
        prompt = """Analyze this investment video transcript and extract ALL stock mentions.

Transcript:

""" + transcript[:30000]  # Increased limit
        
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = re.sub(r'^```(?:json)?\n', '', result_text)
            result_text = re.sub(r'\n```$', '', result_text)
        
        result = json.loads(result_text)
        return result
        
    except Exception as e:
        st.error(f"Error analyzing with Gemini: {str(e)}")
        return None

# ============================================================================
# DATA RETRIEVAL FUNCTIONS
# ============================================================================

def get_portfolio_master() -> pd.DataFrame:
    """Get consolidated view of latest mentions for each ticker with Gomes data"""
    global engine
    
    if not engine:
        return pd.DataFrame()
    
    query = """
        SELECT 
            ticker,
            company_name,
            sentiment,
            price_target,
            time_horizon,
            conviction_score,
            raw_notes as key_note,
            edge,
            catalysts,
            risks,
            gomes_score,
            speaker,
            source_type,
            created_at,
            id
        FROM stocks
        ORDER BY gomes_score DESC NULLS LAST, created_at DESC
    """
    try:
        df = pd.read_sql_query(query, engine)
        return df
    except Exception as e:
        st.error(f"Error loading portfolio: {str(e)}")
        return pd.DataFrame()

def get_ticker_history(ticker: str) -> pd.DataFrame:
    """Get all historical mentions of a specific ticker"""
    global engine
    
    if not engine:
        return pd.DataFrame()
    
    query = """
        SELECT 
            source_type as title,
            created_at as analysis_date,
            sentiment,
            price_target,
            time_horizon,
            conviction_score,
            gomes_score,
            edge,
            catalysts,
            risks,
            raw_notes as key_note
        FROM stocks
        WHERE ticker = :ticker
        ORDER BY created_at DESC
    """
    try:
        df = pd.read_sql_query(query, engine, params={"ticker": ticker})
        return df
    except Exception as e:
        st.error(f"Error loading history: {str(e)}")
        return pd.DataFrame()

# ============================================================================
# UI DISPLAY FUNCTIONS
# ============================================================================

def display_compact_grid_card(stock: Dict, col):
    """Display stock in compact grid card format - similar to the screenshot"""
    analysis = stock.get("analysis", {})
    gomes_score = analysis.get("rules_fit_score", 0)
    risks = analysis.get("risks", "")
    sentiment = stock.get("sentiment", "Neutral")
    edge = analysis.get("arbitrage_edge", "")
    catalysts = analysis.get("catalysts", "")
    
    # Color coding
    if sentiment == "Bullish":
        sentiment_color = "#28a745"
        sentiment_text = "BULLISH"
    elif sentiment == "Bearish":
        sentiment_color = "#dc3545"
        sentiment_text = "BEARISH"
    else:
        sentiment_color = "#6c757d"
        sentiment_text = "NEUTRAL"
    
    with col:
        st.markdown(f"""
        <div style="background: #1a1f2e; border: 1px solid #30363d; border-radius: 8px; padding: 16px; height: 380px; display: flex; flex-direction: column;">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                <div>
                    <h3 style="margin: 0; color: #2962FF; font-size: 1.3rem;">{stock.get('ticker', 'N/A')}</h3>
                    <p style="margin: 4px 0 0 0; color: #8b949e; font-size: 0.75rem;">({stock.get('company_name', 'Unknown')[:25]})</p>
                </div>
                <div style="text-align: right;">
                    <div style="background: {sentiment_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; margin-bottom: 6px;">
                        {sentiment_text}
                    </div>
                    <div style="background: #2962FF; color: white; padding: 4px 10px; border-radius: 20px; font-size: 0.85rem; font-weight: 700;">
                        {gomes_score}/10
                    </div>
                </div>
            </div>
            
            <div style="background: #0d1117; padding: 8px; border-radius: 6px; margin-bottom: 8px; font-size: 0.7rem;">
                <div style="color: #58a6ff; font-weight: 600; margin-bottom: 4px;">💎 THE EDGE</div>
                <div style="color: #c9d1d9; line-height: 1.3;">{edge[:120]}{"..." if len(edge) > 120 else ""}</div>
            </div>
            
            <div style="background: #0d1117; padding: 8px; border-radius: 6px; margin-bottom: 8px; font-size: 0.7rem;">
                <div style="color: #58a6ff; font-weight: 600; margin-bottom: 4px;">📊 CATALYSTS</div>
                <div style="color: #c9d1d9; line-height: 1.3;">{catalysts[:100]}{"..." if len(catalysts) > 100 else ""}</div>
            </div>
            
            <div style="background: #2d1515; padding: 8px; border-radius: 6px; font-size: 0.7rem;">
                <div style="color: #f85149; font-weight: 600; margin-bottom: 4px;">⚠️ RISKS</div>
                <div style="color: #f85149; line-height: 1.3;">{risks[:100] if risks else "No major risks noted"}{"..." if len(risks) > 100 else ""}</div>
            </div>
            
            <div style="margin-top: auto; padding-top: 8px; border-top: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #58a6ff; font-size: 0.7rem;">✓ Web Check: Verified</span>
                <span style="color: #8b949e; font-size: 0.7rem;">Gomes Score: {gomes_score}/10</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

def display_stock_card(stock: Dict):
    """Display a single stock analysis in compact Bloomberg Terminal style"""
    analysis = stock.get("analysis", {})
    gomes_score = analysis.get("rules_fit_score", 0)
    risks = analysis.get("risks", "")
    sentiment = stock.get("sentiment", "Neutral")
    
    # Color coding
    if sentiment == "Bullish":
        border_color = "#28a745"
        sentiment_badge = f'<span style="background: #28a745; padding: 2px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; color: white;">● BULLISH</span>'
    elif sentiment == "Bearish":
        border_color = "#dc3545"
        sentiment_badge = f'<span style="background: #dc3545; padding: 2px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; color: white;">● BEARISH</span>'
    else:
        border_color = "#6c757d"
        sentiment_badge = f'<span style="background: #6c757d; padding: 2px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; color: white;">● NEUTRAL</span>'
    
    # Compact container with border
    with st.container():
        st.markdown(f"""
        <div style="border: 1px solid #30363d; border-left: 3px solid {border_color}; 
                    background: #0d1117; padding: 12px 16px; border-radius: 6px; margin-bottom: 8px;">
        </div>
        """, unsafe_allow_html=True)
        
        # TOP ROW: Ticker, Company, Target, Sentiment, Score
        col1, col2, col3, col4 = st.columns([1.5, 2.5, 1.5, 1.5])
        
        with col1:
            st.markdown(f"### {stock.get('ticker', 'N/A')}")
            st.caption(stock.get('company_name', 'Unknown')[:30])
        
        with col2:
            st.markdown(f"**🎯 Target:** {stock.get('price_target', 'N/A')[:50]}")
            st.caption(f"⏱️ {stock.get('time_horizon', 'N/A')} | 💪 Conviction: {stock.get('conviction_score', 0)}/10")
        
        with col3:
            st.markdown(sentiment_badge, unsafe_allow_html=True)
        
        with col4:
            # Gomes Score with progress bar
            score_pct = int((gomes_score / 10) * 100) if gomes_score else 0
            st.markdown(f"**⭐ Gomes Score**")
            st.progress(score_pct / 100)
            st.caption(f"{gomes_score}/10")
        
        # BOTTOM ROW: Edge, Catalysts, Risks (3 columns)
        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        
        with c1:
            st.markdown("**🎯 THE EDGE**")
            edge_text = analysis.get("arbitrage_edge", "Not specified")
            st.markdown(f'<div style="font-size: 0.85rem; line-height: 1.4; color: #c9d1d9;">{edge_text[:200]}{"..." if len(edge_text) > 200 else ""}</div>', unsafe_allow_html=True)
        
        with c2:
            st.markdown("**🚀 CATALYSTS**")
            catalysts_text = analysis.get("catalysts", "Not specified")
            # Convert to bullet points if semicolon-separated
            if ';' in catalysts_text:
                bullets = catalysts_text.split(';')
                for bullet in bullets[:3]:  # Limit to 3 bullets
                    st.markdown(f'<div style="font-size: 0.8rem; color: #58a6ff;">• {bullet.strip()[:80]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="font-size: 0.85rem; color: #58a6ff;">{catalysts_text[:150]}{"..." if len(catalysts_text) > 150 else ""}</div>', unsafe_allow_html=True)
        
        with c3:
            st.markdown("**⚠️ RISKS**")
            if risks and len(risks) > 10:
                st.markdown(f'<div style="font-size: 0.85rem; line-height: 1.4; color: #f85149; font-weight: 500;">⚠️ {risks[:200]}{"..." if len(risks) > 200 else ""}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="font-size: 0.85rem; color: #8b949e;">No significant risks mentioned</div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

def display_portfolio_dataframe(df: pd.DataFrame):
    """Display portfolio with styled dataframe and Gomes columns"""
    if df.empty:
        st.info("📦 No stocks analyzed yet. Start with 'New Analysis'!")
        return
    
    # Prepare display
    display_df = df.copy()
    
    # Add risk indicator
    display_df["risk"] = display_df["risks"].apply(
        lambda x: "⚠️" if (x and len(str(x)) > 10) else "✅"
    )
    
    # Convert Gomes score to percentage for progress bar
    display_df["gomes_pct"] = (display_df["gomes_score"].fillna(0) / 10 * 100).astype(int)
    
    # Column configuration
    column_config = {
        "risk": st.column_config.TextColumn(
            "⚠️",
            width="small",
            help="Risk indicator"
        ),
        "ticker": st.column_config.TextColumn(
            "Ticker",
            width="small"
        ),
        "company_name": st.column_config.TextColumn(
            "Company",
            width="medium"
        ),
        "sentiment": st.column_config.TextColumn(
            "Sentiment",
            width="small"
        ),
        "gomes_pct": st.column_config.ProgressColumn(
            "⭐ Gomes Score",
            help="How well it fits The Rules",
            min_value=0,
            max_value=100,
            format="%d%%"
        ),
        "conviction_score": st.column_config.ProgressColumn(
            "Conviction",
            min_value=0,
            max_value=10,
            format="%d/10"
        ),
        "edge": st.column_config.TextColumn(
            "🎯 The Edge",
            width="large"
        ),
        "catalysts": st.column_config.TextColumn(
            "🚀 Catalysts",
            width="medium"
        ),
        "price_target": st.column_config.TextColumn(
            "Target",
            width="small"
        ),
        "analysis_date": st.column_config.DatetimeColumn(
            "Date",
            width="small",
            format="MMM DD, YYYY"
        )
    }
    
    # Select columns
    display_columns = [
        "risk", "ticker", "company_name", "sentiment",
        "gomes_pct", "conviction_score", "edge",
        "catalysts", "price_target", "analysis_date"
    ]
    
    # Filter existing columns
    display_columns = [c for c in display_columns if c in display_df.columns]
    
    st.dataframe(
        display_df[display_columns],
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=600
    )

def style_sentiment(val):
    """Apply color to sentiment column"""
    if val == "Bullish":
        return "background-color: #d4edda; color: #155724; font-weight: bold;"
    elif val == "Bearish":
        return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
    else:
        return "background-color: #e2e3e5; color: #383d41; font-weight: bold;"

def display_styled_dataframe(df: pd.DataFrame, show_video_info: bool = False):
    """Display dataframe with professional styling"""
    if df.empty:
        st.info("No data to display")
        return
    
    # Prepare display columns
    display_df = df.copy()
    
    # Configure columns
    column_config = {
        "ticker": st.column_config.TextColumn(
            "Ticker",
            width="small",
            help="Stock ticker symbol"
        ),
        "company_name": st.column_config.TextColumn(
            "Company",
            width="medium"
        ),
        "sentiment": st.column_config.TextColumn(
            "Sentiment",
            width="small"
        ),
        "price_target": st.column_config.TextColumn(
            "Price Target",
            width="small"
        ),
        "time_horizon": st.column_config.TextColumn(
            "Horizon",
            width="small"
        ),
        "conviction_score": st.column_config.ProgressColumn(
            "Conviction",
            help="Confidence level (1-10)",
            min_value=0,
            max_value=10,
            format="%d/10",
            width="small"
        ),
        "key_note": st.column_config.TextColumn(
            "Key Reasoning",
            width="large"
        )
    }
    
    if show_video_info:
        column_config["video_title"] = st.column_config.TextColumn(
            "Video",
            width="medium"
        )
        column_config["analysis_date"] = st.column_config.TextColumn(
            "Date",
            width="small"
        )
    
    # Hide index and ID columns
    columns_to_display = [col for col in display_df.columns if col != 'id']
    
    # Apply styling with pandas styler
    styled_df = display_df[columns_to_display].style.applymap(
        style_sentiment, 
        subset=['sentiment']
    )
    
    st.dataframe(
        styled_df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True
    )

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    st.set_page_config(
        page_title="Akcion",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Premium Dark Fintech CSS
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
    
    /* ============ GLOBAL RESETS & BASE ============ */
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }
    
    /* Remove Streamlit branding */
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header {visibility: hidden !important;}
    
    /* Main app background - Deep dark blue/grey */
    .stApp {
        background-color: #0E1117 !important;
        background-image: radial-gradient(circle at 10% 20%, rgba(41, 98, 255, 0.05) 0%, transparent 20%),
                          radial-gradient(circle at 90% 80%, rgba(0, 229, 255, 0.03) 0%, transparent 20%);
    }
    
    /* Main content area */
    .main .block-container {
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        max-width: 1400px !important;
    }
    
    /* ============ SIDEBAR PREMIUM STYLING ============ */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0A0E1A 0%, #0E1117 100%) !important;
        border-right: 1px solid #30363D !important;
    }
    
    [data-testid="stSidebar"] > div:first-child {
        background: transparent !important;
    }
    
    /* Sidebar AKCION logo - Massive & Gradient */
    .sidebar-logo {
        font-size: 3.8rem !important;
        font-weight: 900 !important;
        background: linear-gradient(135deg, #2962FF 0%, #00E5FF 50%, #7C4DFF 100%) !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        text-align: center !important;
        margin: 30px 0 20px 0 !important;
        letter-spacing: 6px !important;
        text-shadow: 0 0 30px rgba(41, 98, 255, 0.3) !important;
    }
    
    /* Sidebar text */
    [data-testid="stSidebar"] * {
        color: #C9D1D9 !important;
    }
    
    /* Sidebar input fields */
    [data-testid="stSidebar"] input {
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
        color: #C9D1D9 !important;
        border-radius: 8px !important;
    }
    
    [data-testid="stSidebar"] input:focus {
        border-color: #2962FF !important;
        box-shadow: 0 0 0 3px rgba(41, 98, 255, 0.2) !important;
    }
    
    /* ============ PREMIUM CARD CONTAINERS ============ */
    .content-card {
        background: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 16px !important;
        padding: 32px !important;
        margin: 20px 0 !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4), 
                    0 2px 8px rgba(0, 0, 0, 0.3),
                    inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    }
    
    /* Hero header inside cards */
    .hero-title {
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        color: #FFFFFF !important;
        margin-bottom: 8px !important;
        letter-spacing: -0.5px !important;
    }
    
    .hero-subtitle {
        font-size: 1rem !important;
        color: #8B949E !important;
        margin-bottom: 32px !important;
        font-weight: 400 !important;
    }
    
    /* ============ RADIO BUTTONS AS MODERN CHIPS ============ */
    /* Hide default radio buttons */
    [data-testid="stRadio"] > div {
        flex-direction: row !important;
        gap: 12px !important;
        background: transparent !important;
    }
    
    [data-testid="stRadio"] > div > label {
        background: #1C2128 !important;
        border: 2px solid #30363D !important;
        border-radius: 10px !important;
        padding: 12px 24px !important;
        cursor: pointer !important;
        transition: all 0.3s ease !important;
        color: #C9D1D9 !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        min-width: 140px !important;
        text-align: center !important;
    }
    
    [data-testid="stRadio"] > div > label:hover {
        border-color: #2962FF !important;
        background: #242B35 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(41, 98, 255, 0.2) !important;
        color: #E6EDF3 !important;
    }
    
    /* Hide the radio circle completely */
    [data-testid="stRadio"] > div > label > div[role="radio"] {
        display: none !important;
    }
    
    /* Selected radio chip - solid blue like button */
    [data-testid="stRadio"] > div > label[data-checked="true"],
    [data-testid="stRadio"] > div > label:has(input:checked) {
        background: #2962FF !important;
        border-color: #2962FF !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 16px rgba(41, 98, 255, 0.5) !important;
    }
    
    /* ============ TEXT INPUTS - MODERN SEARCH BAR STYLE ============ */
    input[type="text"], input[type="url"], textarea {
        background-color: #0D1117 !important;
        border: 2px solid #30363D !important;
        border-radius: 12px !important;
        color: #E6EDF3 !important;
        padding: 14px 20px !important;
        font-size: 0.95rem !important;
        transition: all 0.3s ease !important;
        min-height: 48px !important;
    }
    
    input[type="text"]:focus, input[type="url"]:focus, textarea:focus {
        border-color: #2962FF !important;
        box-shadow: 0 0 0 4px rgba(41, 98, 255, 0.15),
                    0 0 20px rgba(41, 98, 255, 0.2) !important;
        outline: none !important;
        background-color: #161B22 !important;
    }
    
    input::placeholder, textarea::placeholder {
        color: #8B949E !important;
        font-weight: 500 !important;
        opacity: 1 !important;
    }
    
    /* ============ BUTTONS - SOLID ELECTRIC BLUE ============ */
    .stButton > button {
        background: #2962FF !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 14px 32px !important;
        font-size: 1.05rem !important;
        font-weight: 800 !important;
        letter-spacing: 1.5px !important;
        text-transform: uppercase !important;
        text-shadow: 0 2px 8px rgba(0, 0, 0, 0.5), 0 1px 3px rgba(0, 0, 0, 0.8) !important;
        box-shadow: 0 4px 16px rgba(41, 98, 255, 0.4) !important;
        transition: all 0.3s ease !important;
        cursor: pointer !important;
        min-height: 52px !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-3px) !important;
        background: #3D73FF !important;
        box-shadow: 0 8px 24px rgba(41, 98, 255, 0.6),
                    0 0 30px rgba(41, 98, 255, 0.3) !important;
    }
    
    .stButton > button:active {
        transform: translateY(-1px) !important;
    }
    
    /* ============ METRICS & STATS ============ */
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
        font-weight: 700 !important;
        color: #FFFFFF !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: #8B949E !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
    }
    
    [data-testid="stMetricDelta"] {
        font-weight: 600 !important;
    }
    
    /* Metric containers */
    [data-testid="metric-container"] {
        background: #1C2128 !important;
        border: 1px solid #30363D !important;
        border-radius: 12px !important;
        padding: 20px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
    }
    
    /* ============ STOCK CARDS - PREMIUM DEPTH ============ */
    .stock-card {
        background: linear-gradient(135deg, #1C2128 0%, #161B22 100%) !important;
        border: 1px solid #30363D !important;
        border-radius: 14px !important;
        padding: 24px !important;
        margin: 16px 0 !important;
        border-left: 4px solid !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4),
                    inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
        transition: all 0.3s ease !important;
    }
    
    .stock-card:hover {
        transform: translateY(-4px) !important;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5),
                    0 0 20px rgba(41, 98, 255, 0.1) !important;
    }
    
    /* ============ DATAFRAME STYLING ============ */
    [data-testid="stDataFrame"] {
        background: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }
    
    /* DataFrame headers */
    .stDataFrame thead tr th {
        background: #1C2128 !important;
        color: #C9D1D9 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #2962FF !important;
        padding: 14px !important;
    }
    
    /* DataFrame rows */
    .stDataFrame tbody tr {
        border-bottom: 1px solid #21262D !important;
    }
    
    .stDataFrame tbody tr:hover {
        background: #1C2128 !important;
    }
    
    /* ============ SELECTBOX & SLIDER ============ */
    [data-testid="stSelectbox"] > div > div {
        background-color: #161B22 !important;
        border: 2px solid #30363D !important;
        border-radius: 10px !important;
    }
    
    [data-testid="stSelectbox"] > div > div:hover {
        border-color: #2962FF !important;
    }
    
    /* Slider */
    .stSlider > div > div > div {
        background: #2962FF !important;
    }
    
    .stSlider [data-testid="stThumbValue"] {
        background: #2962FF !important;
        color: white !important;
    }
    
    /* ============ EXPANDER ============ */
    .streamlit-expanderHeader {
        background: #1C2128 !important;
        border: 1px solid #30363D !important;
        border-radius: 10px !important;
        color: #C9D1D9 !important;
        font-weight: 600 !important;
    }
    
    .streamlit-expanderHeader:hover {
        border-color: #2962FF !important;
    }
    
    .streamlit-expanderContent {
        background: #161B22 !important;
        border: 1px solid #30363D !important;
        border-top: none !important;
        border-radius: 0 0 10px 10px !important;
    }
    
    /* ============ FILE UPLOADER ============ */
    [data-testid="stFileUploader"] {
        background: #1C2128 !important;
        border: 2px dashed #30363D !important;
        border-radius: 12px !important;
        padding: 20px !important;
    }
    
    [data-testid="stFileUploader"]:hover {
        border-color: #2962FF !important;
        background: #1C2533 !important;
    }
    
    /* ============ TYPOGRAPHY HIERARCHY ============ */
    h1 {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        letter-spacing: -0.5px !important;
        font-size: 2.5rem !important;
    }
    
    h2 {
        color: #FFFFFF !important;
        font-weight: 600 !important;
        font-size: 1.8rem !important;
    }
    
    h3 {
        color: #C9D1D9 !important;
        font-weight: 600 !important;
        font-size: 1.3rem !important;
        margin-top: 24px !important;
    }
    
    p, span, div {
        color: #8B949E !important;
    }
    
    /* Labels */
    label {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5) !important;
    }
    
    /* ============ SENTIMENT BADGES ============ */
    .sentiment-bullish {
        background: linear-gradient(135deg, #10B981 0%, #059669 100%) !important;
        color: white !important;
        padding: 6px 16px !important;
        border-radius: 20px !important;
        font-weight: 700 !important;
        display: inline-block !important;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3) !important;
    }
    
    .sentiment-bearish {
        background: linear-gradient(135deg, #EF4444 0%, #DC2626 100%) !important;
        color: white !important;
        padding: 6px 16px !important;
        border-radius: 20px !important;
        font-weight: 700 !important;
        display: inline-block !important;
        box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3) !important;
    }
    
    .sentiment-neutral {
        background: linear-gradient(135deg, #6B7280 0%, #4B5563 100%) !important;
        color: white !important;
        padding: 6px 16px !important;
        border-radius: 20px !important;
        font-weight: 700 !important;
        display: inline-block !important;
        box-shadow: 0 4px 12px rgba(107, 114, 128, 0.3) !important;
    }
    
    /* ============ SCROLLBAR ============ */
    ::-webkit-scrollbar {
        width: 12px !important;
        height: 12px !important;
    }
    
    ::-webkit-scrollbar-track {
        background: #0E1117 !important;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #30363D !important;
        border-radius: 6px !important;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #2962FF !important;
    }
    
    /* ============ SPINNER ============ */
    .stSpinner > div {
        border-top-color: #2962FF !important;
    }
    
    /* ============ INFO/SUCCESS/WARNING/ERROR BOXES ============ */
    .stAlert {
        border-radius: 10px !important;
        border-left-width: 4px !important;
    }
    
    </style>
    """, unsafe_allow_html=True)

    
    # Initialize session state for navigation at the very beginning
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "New Analysis"
    
    # Initialize database
    init_database()
    
    # Sidebar with premium AKCION gradient logo
    st.sidebar.markdown('<div class="sidebar-logo">AKCION</div>', unsafe_allow_html=True)
    st.sidebar.markdown("---")
    
    # Database connection status
    if db_error:
        st.sidebar.error(f"⚠️ Database Connection Issue\n\n{db_error}")
    elif engine:
        st.sidebar.success("✅ PostgreSQL Connected")
    
    st.sidebar.markdown("---")
    
    # Default API key
    DEFAULT_API_KEY = "AIzaSyBvA9ZrWGCVytm-PltCUgoGm3H1e_DX9BY"
    
    api_key = st.sidebar.text_input(
        "🔑 Gemini API Key",
        value=DEFAULT_API_KEY,
        type="password",
        help="Enter your Google Gemini API key"
    )
    
    st.sidebar.markdown("---")
    
    # Navigation menu - sync with session state
    st.sidebar.markdown("### 📊 Navigation")
    
    page = st.sidebar.radio(
        "Navigation Menu",
        ["New Analysis", "Portfolio View"],
        index=0 if st.session_state.current_page == "New Analysis" else 1,
        label_visibility="collapsed",
        key="sidebar_nav"
    )
    
    # Update session state when sidebar changes
    if page != st.session_state.current_page:
        st.session_state.current_page = page
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📖 The Gomes Rules")
    st.sidebar.markdown("""
    <div style="font-size: 0.9rem; line-height: 1.6;">
    1. 🎯 <b>Information Arbitrage</b><br/>
    &nbsp;&nbsp;&nbsp;Know what others don't<br/><br/>
    2. 📈 <b>Asymmetric Upside</b><br/>
    &nbsp;&nbsp;&nbsp;Limited downside, huge upside<br/><br/>
    3. 🚀 <b>Clear Catalysts</b><br/>
    &nbsp;&nbsp;&nbsp;Specific upcoming events<br/><br/>
    4. ⚠️ <b>Risk Awareness</b><br/>
    &nbsp;&nbsp;&nbsp;Eyes wide open
    </div>
    """, unsafe_allow_html=True)
    
    # Main content
    st.markdown('<h1 class="main-title">AKCION</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Mark Gomes Investment Analysis Dashboard</p>', unsafe_allow_html=True)
    
    # Navigation tabs at top of page (for when sidebar is hidden)
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("🔬 New Analysis", key="nav_new_analysis", type="primary" if st.session_state.current_page == "New Analysis" else "secondary", use_container_width=True):
            st.session_state.current_page = "New Analysis"
            st.rerun()
    with col2:
        if st.button("📊 Portfolio View", key="nav_portfolio", type="primary" if st.session_state.current_page == "Portfolio View" else "secondary", use_container_width=True):
            st.session_state.current_page = "Portfolio View"
            st.rerun()
    
    # Use session state for page selection
    page = st.session_state.current_page
    
    st.markdown("---")
    
    # Route based on sidebar selection
    if page == "New Analysis":
    
        # ================================================================
        # NEW ANALYSIS PAGE
        # ================================================================
        
        # Premium card container for main content
        st.markdown('<div class="content-card">', unsafe_allow_html=True)
        st.markdown('<div class="hero-title">🔬 Investment Analysis</div>', unsafe_allow_html=True)
        st.markdown('<div class="hero-subtitle">Analyze videos, transcripts, and documents using the Mark Gomes methodology</div>', unsafe_allow_html=True)
        
        # Input method selection
        input_method = st.radio(
            "Choose input method:",
            ["YouTube URL", "Google Docs Link", "Paste Transcript", "Upload File"],
            horizontal=True,
            label_visibility="collapsed"
        )
        
        transcript = None
        video_id = "manual_input"
        
        if input_method == "YouTube URL":
            col1, col2 = st.columns([3, 1])
            
            with col1:
                video_url = st.text_input(
                    "YouTube Video URL",
                    placeholder="https://www.youtube.com/watch?v=..."
                )
            
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)  # Spacing
                analyze_button = st.button("🔍 Analyze Video", type="primary", use_container_width=True)
            
            if analyze_button:
                if not api_key:
                    st.error("⚠️ Please enter your Gemini API Key in the sidebar")
                elif not video_url:
                    st.error("⚠️ Please enter a YouTube video URL")
                else:
                    # Extract video ID
                    video_id = extract_video_id(video_url)
                    if not video_id:
                        st.error("❌ Invalid YouTube URL")
                    else:
                        with st.spinner("🔄 Fetching transcript..."):
                            transcript = get_transcript(video_id)
                        
                        if not transcript:
                            st.info("💡 Tip: If the video doesn't have transcripts, use 'Paste Transcript' option instead")
        
        elif input_method == "Google Docs Link":  # Google Docs
            st.markdown("**📄 Paste your Google Docs link**")
            st.caption("Make sure the document is shared as 'Anyone with the link can view'")
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                doc_url = st.text_input(
                    "Google Docs URL",
                    placeholder="https://docs.google.com/document/d/..."
                )
            
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                analyze_button = st.button("🔍 Analyze Doc", type="primary", use_container_width=True)
            
            if analyze_button:
                if not api_key:
                    st.error("⚠️ Please enter your Gemini API Key in the sidebar")
                elif not doc_url:
                    st.error("⚠️ Please enter a Google Docs URL")
                else:
                    with st.spinner("📥 Fetching document from Google Docs..."):
                        transcript = get_google_doc_content(doc_url)
                    
                    if transcript:
                        st.success(f"✅ Document loaded ({len(transcript):,} characters)")
                        video_id = extract_google_doc_id(doc_url) or "google_doc"
        
        elif input_method == "Paste Transcript":  # Paste Transcript
            transcript_text = st.text_area(
                "Paste Video Transcript",
                height=200,
                placeholder="Paste the video transcript here..."
            )
            
            analyze_button = st.button("🔍 Analyze Transcript", type="primary", use_container_width=True)
            
            if analyze_button:
                if not api_key:
                    st.error("⚠️ Please enter your Gemini API Key in the sidebar")
                elif not transcript_text:
                    st.error("⚠️ Please paste a transcript")
                else:
                    transcript = transcript_text
                    st.success(f"✅ Transcript loaded ({len(transcript)} characters)")
        
        else:  # Upload File
            st.markdown("**Upload a transcript file (from Google Docs or any text file)**")
            uploaded_file = st.file_uploader(
                "Choose a file",
                type=["txt", "docx", "doc"],
                help="Supports .txt and .docx files exported from Google Docs"
            )
            
            analyze_button = st.button("🔍 Analyze File", type="primary", use_container_width=True)
            
            if analyze_button:
                if not api_key:
                    st.error("⚠️ Please enter your Gemini API Key in the sidebar")
                elif not uploaded_file:
                    st.error("⚠️ Please upload a file")
                else:
                    try:
                        # Read the file content
                        if uploaded_file.name.endswith('.txt'):
                            # Read text file
                            transcript = uploaded_file.read().decode('utf-8')
                        elif uploaded_file.name.endswith(('.docx', '.doc')):
                            # Try to read docx file (basic text extraction)
                            try:
                                import docx
                                doc = docx.Document(uploaded_file)
                                transcript = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                            except ImportError:
                                st.warning("⚠️ python-docx not installed. Reading as plain text...")
                                transcript = uploaded_file.read().decode('utf-8', errors='ignore')
                        else:
                            transcript = uploaded_file.read().decode('utf-8', errors='ignore')
                        
                        if transcript:
                            st.success(f"✅ File uploaded: {uploaded_file.name} ({len(transcript):,} characters)")
                        else:
                            st.error("❌ File is empty or couldn't be read")
                            transcript = None
                    except Exception as e:
                        st.error(f"❌ Error reading file: {str(e)}")
                        transcript = None
        
        # Process transcript if available
        if transcript and analyze_button:
            with st.spinner("🤖 Analyzing with Gemini Pro..."):
                result = analyze_with_gemini(transcript, api_key)
            
            if result and "stocks" in result:
                stocks = result["stocks"]
                
                if len(stocks) == 0:
                    st.warning("No stock mentions found in this transcript.")
                else:
                    st.success(f"✅ Found {len(stocks)} stock mention(s)")
                    
                    # Save to database
                    save_analysis(video_id, "YouTube", stocks, speaker="Mark Gomes")
                    
                    # Display results as cards
                    st.markdown("---")
                    st.markdown("### 📊 Analysis Results")
                    st.caption("Stocks analyzed using the Gomes methodology")
                    
                    for stock in stocks:
                        display_stock_card(stock)
                    
                    st.success("💾 Analysis saved to database")
        
        # Close content card
        st.markdown('</div>', unsafe_allow_html=True)
    
    else:  # Portfolio View
        # ================================================================
        # PORTFOLIO VIEW PAGE
        # ================================================================
        
        # Premium card container
        st.markdown('<div class="content-card">', unsafe_allow_html=True)
        st.markdown('<div class="hero-title">📊 Portfolio Master</div>', unsafe_allow_html=True)
        st.markdown('<div class="hero-subtitle">All analyzed stocks with Gomes methodology insights</div>', unsafe_allow_html=True)
        
        # Get master portfolio data
        portfolio_df = get_portfolio_master()
        
        if portfolio_df.empty:
            st.info("📭 No stocks analyzed yet. Start with 'New Analysis'!")
        else:
            # Stats overview
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Stocks", len(portfolio_df))
            with col2:
                bullish_count = len(portfolio_df[portfolio_df["sentiment"] == "Bullish"])
                st.metric("Bullish", bullish_count)
            with col3:
                avg_gomes = portfolio_df["gomes_score"].mean()
                st.metric("Avg Gomes Score", f"{avg_gomes:.1f}/10" if not pd.isna(avg_gomes) else "N/A")
            with col4:
                high_conviction = len(portfolio_df[portfolio_df["conviction_score"] >= 8])
                st.metric("High Conviction (8+)", high_conviction)
            
            st.markdown("---")
            
            # Filters
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            
            with col1:
                sentiment_filter = st.selectbox(
                    "📊 Filter by Sentiment",
                    options=["All", "Bullish", "Bearish", "Neutral"]
                )
            
            with col2:
                unique_tickers = sorted(portfolio_df["ticker"].unique().tolist())
                ticker_filter = st.selectbox(
                    "🔍 Filter by Ticker",
                    options=["All"] + unique_tickers
                )
            
            with col3:
                min_gomes = st.slider(
                    "⭐ Min Gomes Score",
                    min_value=0,
                    max_value=10,
                    value=0
                )
            
            with col4:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔄 Refresh", use_container_width=True):
                    st.rerun()
            
            # Apply filters
            filtered_df = portfolio_df.copy()
            
            if sentiment_filter != "All":
                filtered_df = filtered_df[filtered_df["sentiment"] == sentiment_filter]
            
            if ticker_filter != "All":
                filtered_df = filtered_df[filtered_df["ticker"] == ticker_filter]
            
            if min_gomes > 0:
                filtered_df = filtered_df[filtered_df["gomes_score"] >= min_gomes]
            
            # View toggle
            view_mode = st.radio(
                "View Mode",
                options=["🎴 Grid View", "📊 List View", "📋 Data Table"],
                horizontal=True,
                label_visibility="collapsed"
            )
            
            # Display master table or cards
            st.markdown("### 📈 Master Stock List")
            st.caption(f"Showing {len(filtered_df)} of {len(portfolio_df)} stocks (sorted by Gomes Score)")
            
            if view_mode == "🎴 Grid View":
                # Display in 3-column grid like the screenshot
                rows = [filtered_df.iloc[i:i+3] for i in range(0, len(filtered_df), 3)]
                
                for row_stocks in rows:
                    cols = st.columns(3)
                    for idx, (_, row) in enumerate(row_stocks.iterrows()):
                        stock_dict = {
                            "ticker": row.get("ticker", "N/A"),
                            "company_name": row.get("company_name", "Unknown"),
                            "sentiment": row.get("sentiment", "Neutral"),
                            "price_target": row.get("price_target", "N/A"),
                            "time_horizon": row.get("time_horizon", "N/A"),
                            "conviction_score": row.get("conviction_score", 0),
                            "analysis": {
                                "rules_fit_score": row.get("gomes_score", 0),
                                "arbitrage_edge": row.get("edge", "Not specified"),
                                "catalysts": row.get("catalysts", "Not specified"),
                                "risks": row.get("risks", "")
                            }
                        }
                        display_compact_grid_card(stock_dict, cols[idx])
                    st.markdown("<br>", unsafe_allow_html=True)
            
            elif view_mode == "📊 List View":
                # Convert DataFrame rows to stock dictionaries for card display
                for idx, row in filtered_df.iterrows():
                    stock_dict = {
                        "ticker": row.get("ticker", "N/A"),
                        "company_name": row.get("company_name", "Unknown"),
                        "sentiment": row.get("sentiment", "Neutral"),
                        "price_target": row.get("price_target", "N/A"),
                        "time_horizon": row.get("time_horizon", "N/A"),
                        "conviction_score": row.get("conviction_score", 0),
                        "analysis": {
                            "rules_fit_score": row.get("gomes_score", 0),
                            "arbitrage_edge": row.get("edge", "Not specified"),
                            "catalysts": row.get("catalysts", "Not specified"),
                            "risks": row.get("risks", "")
                        }
                    }
                    display_stock_card(stock_dict)
            else:
                display_portfolio_dataframe(filtered_df)
            
            # Ticker history section
            st.markdown("---")
            st.markdown("### 📜 Historical Tracking")
            
            if unique_tickers:
                selected_ticker = st.selectbox(
                    "Select a ticker to view history",
                    options=unique_tickers,
                    key="history_ticker"
                )
                
                if selected_ticker:
                    history_df = get_ticker_history(selected_ticker)
                    
                    if not history_df.empty:
                        st.markdown(f"#### {selected_ticker} - All Mentions ({len(history_df)} total)")
                        
                        # Show trend chart if multiple entries
                        if len(history_df) > 1 and 'gomes_score' in history_df.columns:
                            col1, col2 = st.columns(2)
                            with col1:
                                if history_df['gomes_score'].notna().any():
                                    st.line_chart(history_df.set_index("analysis_date")["gomes_score"])
                                    st.caption("Gomes Score Trend")
                            with col2:
                                if history_df['conviction_score'].notna().any():
                                    st.line_chart(history_df.set_index("analysis_date")["conviction_score"])
                                    st.caption("Conviction Score Trend")
                        
                        # Display history table
                        st.dataframe(
                            history_df,
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.info(f"No history found for {selected_ticker}")
        
        # Close content card
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
