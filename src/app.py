from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from src.conference_state import ConferenceStateSingleton
from pydantic import BaseModel
import logging
import json
import asyncio
import cv2
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)

app = FastAPI(title="DnD Chat WebRTC Video Display", description="A WebRTC server that displays client video feeds in OpenCV windows")

# Pydantic models for request/response
class WebRTCAnswer(BaseModel):
    type: str
    sdp: str

class ICECandidate(BaseModel):
    candidate: str
    sdpMLineIndex: int
    sdpMid: str

# Get the directory where this script is located
BASE_DIR = Path(__file__).resolve().parent.parent

# Custom static file serving with cache control
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if isinstance(response, FileResponse) and path.endswith('.js'):
            # Prevent caching of JavaScript files
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

# Mount the www folder as static files with cache control
app.mount("/static", NoCacheStaticFiles(directory=BASE_DIR / "www"), name="static")

@app.get("/")
async def read_index():
    """Serve the main index.html file"""
    index_path = BASE_DIR / "www" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    else:
        return {"message": "Index file not found"}
    

conference_state = ConferenceStateSingleton()

# Store active WebSocket connections
active_websockets = set()

async def broadcast_state_update():
    """Broadcast chat state to all connected WebSocket clients"""
    if not active_websockets:
        return
    
    try:
        state = conference_state.get_state()
        message = {
            "type": "state_update",
            "state": state.model_dump()
        }
        
        # Create a copy of the set to avoid issues with concurrent modification
        websockets_to_remove = set()
        
        for websocket in active_websockets.copy():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                websockets_to_remove.add(websocket)
        
        # Remove failed WebSocket connections
        active_websockets.difference_update(websockets_to_remove)
        
    except Exception as e:
        logger.error(f"Error in broadcast_state_update: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    logger.info(f"WebSocket connected. Total connections: {len(active_websockets)}")
    
    try:
        # Send initial state
        await broadcast_state_update()
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages (though we don't expect many from client)
                data = await websocket.receive_text()
                logger.info(f"WebSocket message received: {data}")
                
                # Parse message and handle if needed
                try:
                    message = json.loads(data)
                    if message.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    elif message.get("type") == "request_state":
                        await broadcast_state_update()
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received: {data}")
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        active_websockets.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(active_websockets)}")

@app.on_event("startup")
async def startup():
    """Initialize services on startup"""
    try:
        # Set up state change callback for WebSocket broadcasts
        conference_state.set_state_change_callback(broadcast_state_update)
        
        logger.info("WebRTC video display server initialized successfully")
        # Start periodic state broadcast
        asyncio.create_task(periodic_state_broadcast())
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

async def periodic_state_broadcast():
    """Periodically broadcast state updates"""
    while True:
        await asyncio.sleep(2)  # Broadcast every 2 seconds
        await broadcast_state_update()

@app.on_event("shutdown")
async def shutdown():
    """Clean up services on shutdown"""
    try:
        await conference_state.close_all_connections()
        logger.info("WebRTC video display server shut down successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

@app.get("/chat_state")
async def get_chat_state():
    return conference_state.get_state().model_dump()

@app.post("/request_connection/{stream_name}")
async def request_connection(stream_name: str):
    offer_sdp = await conference_state.request_connection(stream_name)
    return {"offer_sdp": offer_sdp}

@app.post("/webrtc_answer/{stream_name}")
async def handle_webrtc_answer(stream_name: str, answer: WebRTCAnswer):
    """Handle WebRTC answer from client"""
    try:
        answer_json = answer.model_dump_json()
        await conference_state.handle_webrtc_answer(stream_name, answer_json)
        return {"status": "success", "message": f"WebRTC answer processed for {stream_name}"}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}

@app.post("/close_connection/{stream_name}")
async def close_connection(stream_name: str):
    """Close WebRTC connection for a specific stream"""
    try:
        await conference_state.close_connection(stream_name)
        return {"status": "success", "message": f"Connection closed for {stream_name}"}
    except Exception as e:
        return {"status": "error", "message": f"Error closing connection: {str(e)}"}

@app.post("/close_all_connections")
async def close_all_connections():
    """Close all WebRTC connections"""
    try:
        await conference_state.close_all_connections()
        return {"status": "success", "message": "All connections closed"}
    except Exception as e:
        return {"status": "error", "message": f"Error closing connections: {str(e)}"}

@app.get("/ice_candidates/{stream_name}")
async def get_ice_candidates(stream_name: str):
    """Get ICE candidates for a specific stream"""
    try:
        candidates = conference_state.get_ice_candidates(stream_name)
        return {"status": "success", "candidates": candidates}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/ice_candidate/{stream_name}")
async def add_ice_candidate(stream_name: str, candidate: ICECandidate):
    """Add an ICE candidate for a specific stream"""
    try:
        await conference_state.add_ice_candidate(stream_name, candidate.model_dump())
        return {"status": "success", "message": "ICE candidate added"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
