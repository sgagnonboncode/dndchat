from enum import StrEnum
from pydantic import BaseModel, computed_field
from src.conventions import StreamNames
from src.opencv_display import OpenCVDisplayManager
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer, RTCIceCandidate
import asyncio
import json
import logging
from typing import Optional, Dict, List

# Configure logging for this module
logger = logging.getLogger(__name__)

class ConnectionStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


class StreamDefinition(BaseModel):

    name: str
    connected:ConnectionStatus = ConnectionStatus.DISCONNECTED

    @computed_field
    @property
    def is_board(self) -> bool:
        return self.name == StreamNames.BOARD
    
class ChatStatus(BaseModel):
    streams: dict[str, StreamDefinition]


class ConferenceStateSingleton():
    
    def __init__(self):
        self.chat_status = ChatStatus(streams={})
        self.peer_connections: dict[str, RTCPeerConnection] = {}
        self.opencv_display_manager = OpenCVDisplayManager()  # Manage OpenCV windows
        self.ice_candidates: Dict[str, List] = {}  # Store ICE candidates for each connection
        self.state_change_callback = None  # Callback for state changes
        
        for stream_name in StreamNames:
            self.chat_status.streams[stream_name] = StreamDefinition(name=stream_name)
    
    def set_state_change_callback(self, callback):
        """Set callback function to be called when state changes"""
        self.state_change_callback = callback
    
    async def notify_state_change(self):
        """Notify about state changes"""
        if self.state_change_callback:
            try:
                await self.state_change_callback()
            except Exception as e:
                print(f"Error in state change callback: {e}")
    
    def get_state(self) -> ChatStatus:
        return self.chat_status
    
    async def generate_webrtc_offer(self, stream_name: str) -> str:
        if stream_name not in StreamNames:
            raise ValueError(f"Invalid stream name: {stream_name}")
        
        # Configure ICE servers for NAT traversal
        ice_servers = [
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun2.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun.cloudflare.com:3478"]),
            # Free TURN server for NAT traversal
            RTCIceServer(
                urls=["turn:openrelay.metered.ca:80"],
                username="openrelayproject",
                credential="openrelayproject"
            ),
            RTCIceServer(
                urls=["turn:openrelay.metered.ca:443"],
                username="openrelayproject",
                credential="openrelayproject"
            ),
        ]
        
        configuration = RTCConfiguration(iceServers=ice_servers)
        
        # Create a new RTCPeerConnection with ICE server configuration
        pc = RTCPeerConnection(configuration=configuration)
        self.peer_connections[stream_name] = pc
      
        # Set up event handlers
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state for {stream_name}: {pc.connectionState}")
            if pc.connectionState == "connected":
                self.chat_status.streams[stream_name].connected = ConnectionStatus.CONNECTED
                print(f"Stream {stream_name} is now connected")
                print(f"Peer connection transceivers: {len(pc.getTransceivers())}")
                for i, transceiver in enumerate(pc.getTransceivers()):
                    print(f"Transceiver {i}: direction={transceiver.direction}, mid={transceiver.mid}")
                    if transceiver.receiver and transceiver.receiver.track:
                        track = transceiver.receiver.track
                        print(f"  Receiver track: kind={track.kind}, id={track.id}")
            elif pc.connectionState in ["disconnected", "failed", "closed"]:
                self.chat_status.streams[stream_name].connected = ConnectionStatus.DISCONNECTED
                # Clean up OpenCV windows for this stream
                self.opencv_display_manager.close_window(stream_name)
                print(f"Stream {stream_name} is now disconnected")
            
            # Notify about state change
            await self.notify_state_change()

        
        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            print(f"ICE connection state for {stream_name}: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed":
                print(f"ICE connection failed for {stream_name} - likely NAT/firewall issue")
                
        @pc.on("icegatheringstatechange")
        async def on_icegatheringstatechange():
            print(f"ICE gathering state for {stream_name}: {pc.iceGatheringState}")
        
        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                print(f"ICE candidate for {stream_name}: {candidate}")
                # Store ICE candidate for this stream
                if stream_name not in self.ice_candidates:
                    self.ice_candidates[stream_name] = []
                self.ice_candidates[stream_name].append({
                    "candidate": candidate.candidate,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                    "sdpMid": candidate.sdpMid
                })
            else:
                print(f"ICE gathering completed for {stream_name}")
        
        @pc.on("track")
        def on_track(track):
            print(f"DEBUG: Track received for {stream_name}: {track.kind}")
            print(f"DEBUG: Track details - id: {track.id}, ready_state: {track.readyState}")
            logger.info(f"Track received for {stream_name}: {track.kind}")
            
            # Only handle video tracks for OpenCV display
            if track.kind == 'video':
                print(f"DEBUG: Processing video track for {stream_name}")
                print(f"Setting up OpenCV display for {stream_name}")
                self.opencv_display_manager.create_video_window(stream_name, track)
                
            elif track.kind == 'audio':
                print(f"DEBUG: Processing audio track for {stream_name}")
                print(f"Audio track received for {stream_name} (audio not displayed)")
            
            # Set up track event handlers
            @track.on("ended")
            def on_ended():
                print(f"DEBUG: Track {track.kind} ended for {stream_name}")
                # Close OpenCV window if it was a video track
                if track.kind == 'video':
                    self.opencv_display_manager.close_window(stream_name)

        # Add transceivers to indicate we want to receive video and audio
        # This tells the client that the server is ready to receive media tracks
        pc.addTransceiver("video", direction="recvonly")
        pc.addTransceiver("audio", direction="recvonly")
        print(f"DEBUG: Added video and audio transceivers for {stream_name}")
        
        # Add a data channel for communication
        data_channel = pc.createDataChannel(f"{stream_name}_data")
        
        @data_channel.on("open")
        def on_open():
            print(f"Data channel opened for {stream_name}")
            # Send a welcome message
            data_channel.send(f"Welcome to mirror session for {stream_name}")
        
        @data_channel.on("message")
        def on_message(message):
            print(f"Message received on {stream_name}: {message}")
            # Echo the message back
            data_channel.send(f"Echo: {message}")
        
        # Create the offer
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        print(f"DEBUG: Created offer for {stream_name}")
        print(f"DEBUG: Offer SDP includes video: {'m=video' in offer.sdp}")
        print(f"DEBUG: Offer SDP includes audio: {'m=audio' in offer.sdp}")
        
        # Return the offer as JSON
        offer_dict = {
            "type": offer.type,
            "sdp": offer.sdp
        }
        
        return json.dumps(offer_dict)
   
    async def request_connection(self, stream_name: str) -> str:
        if stream_name not in StreamNames:
            raise ValueError(f"Invalid stream name: {stream_name}")
    
        if self.chat_status.streams[stream_name].connected == ConnectionStatus.CONNECTED:
            print("TODO: FORCE DISCONNECT TO RESET CONNECTION")
            # For now, close the existing connection
            if stream_name in self.peer_connections:
                await self.peer_connections[stream_name].close()
                del self.peer_connections[stream_name]
            self.chat_status.streams[stream_name].connected = ConnectionStatus.DISCONNECTED
        
        # Set status to connecting
        self.chat_status.streams[stream_name].connected = ConnectionStatus.CONNECTING
        print(f"Connection requested for stream {stream_name}")
        
        # Notify about state change
        await self.notify_state_change()
        
        # Generate and return the WebRTC offer
        return await self.generate_webrtc_offer(stream_name)
    
    async def handle_webrtc_answer(self, stream_name: str, answer_json: str) -> None:
        if stream_name not in StreamNames:
            raise ValueError(f"Invalid stream name: {stream_name}")
            
        if stream_name not in self.peer_connections:
            raise ValueError(f"No peer connection found for stream: {stream_name}")
        
        pc = self.peer_connections[stream_name]
        answer_dict = json.loads(answer_json)
        
        # Create RTCSessionDescription from the answer
        answer = RTCSessionDescription(
            sdp=answer_dict["sdp"],
            type=answer_dict["type"]
        )
        
        # Set the remote description
        await pc.setRemoteDescription(answer)
        print(f"WebRTC answer processed for stream {stream_name}")
        print(f"Mirror setup complete for {stream_name}")
    
    async def close_connection(self, stream_name: str) -> None:
        """Close the WebRTC connection for a specific stream.
        
        Args:
            stream_name: The name of the stream to close
        """
        if stream_name in self.peer_connections:
            await self.peer_connections[stream_name].close()
            del self.peer_connections[stream_name]
        
        # Clean up OpenCV windows
        self.opencv_display_manager.close_window(stream_name)
            
        if stream_name in self.chat_status.streams:
            self.chat_status.streams[stream_name].connected = ConnectionStatus.DISCONNECTED
            
        print(f"Connection closed for stream {stream_name}")
        
        # Notify about state change
        await self.notify_state_change()
    
    async def close_all_connections(self) -> None:
        """Close all active WebRTC connections."""
        for stream_name in list(self.peer_connections.keys()):
            await self.close_connection(stream_name)
            
        print("All connections closed")
    
    def get_display_status(self) -> dict:
        """Get information about active OpenCV display windows"""
        return {
            "active_connections": list(self.peer_connections.keys()),
            "opencv_windows": self.opencv_display_manager.get_active_windows(),
            "connection_states": {
                stream_name: stream_info.connected.value
                for stream_name, stream_info in self.chat_status.streams.items()
            }
        }
    
    def get_ice_candidates(self, stream_name: str) -> List[dict]:
        """Get ICE candidates for a specific stream"""
        return self.ice_candidates.get(stream_name, [])
    
    async def add_ice_candidate(self, stream_name: str, candidate_data: dict) -> None:
        """Add an ICE candidate to a peer connection"""
        if stream_name not in self.peer_connections:
            raise ValueError(f"No peer connection found for stream: {stream_name}")
        
        pc = self.peer_connections[stream_name]
        
        try:
            # Parse the candidate string to extract components
            candidate_line = candidate_data["candidate"]
            sdp_mline_index = candidate_data.get("sdpMLineIndex", 0)
            sdp_mid = candidate_data.get("sdpMid")
            
            # aiortc expects ICE candidates to be added via the SDP
            # We need to create a proper RTCIceCandidate object
            if candidate_line and candidate_line.startswith("candidate:"):
                # Parse the candidate line to extract required fields
                parts = candidate_line.split()
                if len(parts) >= 8:
                    foundation = parts[0].split(":")[1]  # Remove "candidate:" prefix
                    component = int(parts[1])
                    protocol = parts[2].upper()
                    priority = int(parts[3])
                    ip = parts[4]
                    port = int(parts[5])
                    typ = parts[7]  # candidate type
                    
                    # Create RTCIceCandidate with required parameters
                    ice_candidate = RTCIceCandidate(
                        component=component,
                        foundation=foundation,
                        ip=ip,
                        port=port,
                        priority=priority,
                        protocol=protocol,
                        type=typ
                    )
                    
                    # Set additional attributes
                    ice_candidate.sdpMLineIndex = sdp_mline_index
                    ice_candidate.sdpMid = sdp_mid
                    
                    # Add the candidate to the peer connection
                    await pc.addIceCandidate(ice_candidate)
                    print(f"Successfully added ICE candidate for {stream_name}: {typ} {ip}:{port}")
                else:
                    print(f"Invalid candidate format for {stream_name}: {candidate_line}")
            else:
                # Null candidate indicates end of candidates
                await pc.addIceCandidate(None)
                print(f"Added null ICE candidate (end of candidates) for {stream_name}")
                
        except Exception as e:
            print(f"Error adding ICE candidate for {stream_name}: {e}")
            print(f"Candidate data: {candidate_data}")
            # Don't raise the exception to avoid breaking the connection
    