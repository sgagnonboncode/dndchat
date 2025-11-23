#!/usr/bin/env python3
"""
Startup script for the DnD Chat FastAPI server
"""

from src.app import app

import uvicorn
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
)