"""
FastAPI Development Server Launcher

Run this script to start the backend API server.
"""

import sys
import os

# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting Akcion FastAPI Backend...")
    print("📍 API Docs: http://localhost:8000/api/docs")
    print("📍 Health Check: http://localhost:8000/api/health")
    print("⏸️  Press Ctrl+C to stop")
    print()
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload on code changes
        log_level="info"
    )
