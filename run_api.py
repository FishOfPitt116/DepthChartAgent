"""
API server entry point.

Usage:
    python run_api.py
    uvicorn depth_chart_agent.api.app:app --reload   # alternative
"""

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    uvicorn.run(
        "depth_chart_agent.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
