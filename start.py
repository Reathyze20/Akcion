"""
Akcion Full Stack Startup Script

Starts both the FastAPI backend and React frontend in parallel.
Run this from the project root directory.
"""

import subprocess
import sys
import os
import time
from pathlib import Path


def check_prerequisites():
    """Check if Python and Node.js are installed."""
    print("🔍 Checking prerequisites...")
    
    # Check Python
    try:
        result = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ Python: {result.stdout.strip()}")
    except Exception as e:
        print(f"❌ Python check failed: {e}")
        return False
    
    # Check Node.js
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ Node.js: {result.stdout.strip()}")
    except Exception as e:
        print(f"❌ Node.js check failed: {e}")
        print("   Please install Node.js from https://nodejs.org/")
        return False
    
    return True


def check_environment():
    """Check if .env files exist."""
    print("\n🔍 Checking environment configuration...")
    
    backend_env = Path("backend/.env")
    frontend_env = Path("frontend/.env")
    
    if not backend_env.exists():
        print("❌ backend/.env not found")
        print("   Run: copy backend\\.env.example backend\\.env")
        print("   Then edit backend/.env with your credentials")
        return False
    else:
        print("✅ backend/.env found")
    
    if not frontend_env.exists():
        print("❌ frontend/.env not found")
        print("   Run: copy frontend\\.env.example frontend\\.env")
        return False
    else:
        print("✅ frontend/.env found")
    
    return True


def install_dependencies():
    """Install dependencies for both backend and frontend."""
    print("\n📦 Installing dependencies...")
    
    # Backend dependencies
    print("\n🐍 Installing backend dependencies...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "backend/requirements.txt"],
            check=True
        )
        print("✅ Backend dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install backend dependencies: {e}")
        return False
    
    # Frontend dependencies
    print("\n📦 Installing frontend dependencies...")
    try:
        subprocess.run(
            ["npm", "install"],
            cwd="frontend",
            check=True
        )
        print("✅ Frontend dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install frontend dependencies: {e}")
        return False
    
    return True


def start_services():
    """Start both backend and frontend services."""
    print("\n🚀 Starting services...")
    print("=" * 60)
    print("Backend API will be at: http://localhost:8000")
    print("API Documentation:      http://localhost:8000/docs")
    print("Frontend will be at:    http://localhost:5173")
    print("=" * 60)
    print("\n⏳ Starting backend server...")
    
    # Start backend
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd="backend",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Wait a bit for backend to start
    time.sleep(3)
    
    print("✅ Backend server starting...")
    print("\n⏳ Starting frontend dev server...")
    
    # Start frontend
    frontend_process = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd="frontend",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    time.sleep(2)
    print("✅ Frontend dev server starting...")
    
    print("\n" + "=" * 60)
    print("🎉 AKCION is now running!")
    print("=" * 60)
    print("\n📊 Open your browser to: http://localhost:5173")
    print("\n💡 Tips:")
    print("   - Backend API docs: http://localhost:8000/docs")
    print("   - Backend health: http://localhost:8000/health")
    print("   - Press Ctrl+C to stop both servers")
    print("\n" + "=" * 60 + "\n")
    
    try:
        # Wait for processes
        backend_process.wait()
        frontend_process.wait()
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down services...")
        backend_process.terminate()
        frontend_process.terminate()
        try:
            backend_process.wait(timeout=5)
            frontend_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_process.kill()
            frontend_process.kill()
        print("✅ Services stopped")


def main():
    """Main startup routine."""
    print("🎯 AKCION Full Stack Startup")
    print("=" * 60)
    
    # Check if we're in the project root
    if not Path("backend").exists() or not Path("frontend").exists():
        print("❌ Error: Please run this script from the project root directory")
        print("   Expected structure: Akcion/backend/ and Akcion/frontend/")
        sys.exit(1)
    
    # Check prerequisites
    if not check_prerequisites():
        sys.exit(1)
    
    # Check environment
    if not check_environment():
        sys.exit(1)
    
    # Ask to install dependencies
    response = input("\n📦 Install/update dependencies? (y/n): ").strip().lower()
    if response == 'y':
        if not install_dependencies():
            sys.exit(1)
    
    # Start services
    print("\n" + "=" * 60)
    response = input("🚀 Ready to start services? (y/n): ").strip().lower()
    if response == 'y':
        start_services()
    else:
        print("👋 Startup cancelled")


if __name__ == "__main__":
    main()
