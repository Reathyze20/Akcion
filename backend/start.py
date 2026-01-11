"""
Backend Startup Script

Quick script to install dependencies and start the FastAPI server.
Run this from the backend directory.
"""

import subprocess
import sys
import os


def main():
    """Install dependencies and start the FastAPI server."""
    print("🚀 Akcion Backend Startup")
    print("=" * 50)
    
    # Check if we're in the backend directory
    if not os.path.exists("app"):
        print("❌ Error: Please run this script from the backend directory")
        print("   Expected structure: backend/app/")
        sys.exit(1)
    
    # Check if .env file exists
    if not os.path.exists(".env"):
        print("⚠️  Warning: .env file not found")
        print("   Copy .env.example to .env and configure your settings")
        if os.path.exists(".env.example"):
            print("   Run: copy .env.example .env")
        sys.exit(1)
    
    print("\n📦 Installing dependencies...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True
        )
        print("✅ Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        sys.exit(1)
    
    print("\n🔥 Starting FastAPI server...")
    print("   API will be available at: http://localhost:8000")
    print("   API Documentation: http://localhost:8000/docs")
    print("   Press Ctrl+C to stop the server")
    print("=" * 50)
    print()
    
    try:
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
            check=True
        )
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
