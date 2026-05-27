"""
Single-command launcher for the ORB Dashboard.
Run: python run.py
"""
import subprocess
import sys
import os

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("=" * 60)
    print("  ORB Trading Alert Dashboard")
    print("  30-Min Opening Range Breakout Strategy")
    print("=" * 60)
    print()
    print("  Stocks: BSE.NS | SUZLON.NS | IFCI.NS | HFCL.NS | TMCV.NS")
    print("  Market Hours: 9:15 AM – 3:30 PM IST (Mon-Fri)")
    print()
    print("  Dashboard → http://localhost:8000")
    print("  API Docs  → http://localhost:8000/docs")
    print()
    print("  Press Ctrl+C to stop")
    print("=" * 60)
    print()

    cmd = [
        sys.executable, "-m", "uvicorn",
        "backend.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload",
        "--log-level", "info"
    ]
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
