
// WebRTC configuration with STUN and TURN servers
const rtcConfiguration = {
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
        { urls: 'stun:stun2.l.google.com:19302' },
        { urls: 'stun:stun.cloudflare.com:3478' },
        // Free TURN servers for NAT traversal
        { 
            urls: 'turn:openrelay.metered.ca:80',
            username: 'openrelayproject',
            credential: 'openrelayproject'
        },
        { 
            urls: 'turn:openrelay.metered.ca:443',
            username: 'openrelayproject',
            credential: 'openrelayproject'
        }
    ],
    iceCandidatePoolSize: 10
};

// Store active peer connections
const peerConnections = {};
let localStream = null;
let compositeCheckInterval = null;
let currentActiveStream = null; // Track currently active connection
let websocket = null;
let chatState = null;
let stateUpdateInterval = null;

// WebSocket connection for real-time state updates
function initializeWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    console.log('Attempting WebSocket connection to:', wsUrl);
    
    try {
        websocket = new WebSocket(wsUrl);
        
        websocket.onopen = function(event) {
            console.log('WebSocket connected');
            // Request initial state
            fetchChatState();
        };
        
        websocket.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                console.log('WebSocket message received:', data);
                
                if (data.type === 'state_update') {
                    updateChatState(data.state);
                }
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        websocket.onclose = function(event) {
            console.log('WebSocket disconnected:', event.code, event.reason);
            // Attempt to reconnect after 3 seconds
            setTimeout(() => {
                console.log('Attempting WebSocket reconnection...');
                initializeWebSocket();
            }, 3000);
        };
        
        websocket.onerror = function(error) {
            console.error('WebSocket error:', error);
        };
        
    } catch (error) {
        console.error('Failed to create WebSocket:', error);
        // Fall back to polling if WebSocket fails
        startStatePolling();
    }
}

// Fetch chat state from REST endpoint
async function fetchChatState() {
    try {
        const response = await fetch('/chat_state');
        if (response.ok) {
            const state = await response.json();
            updateChatState(state);
        } else {
            console.error('Failed to fetch chat state:', response.statusText);
        }
    } catch (error) {
        console.error('Error fetching chat state:', error);
    }
}

// Update chat state and UI
function updateChatState(newState) {
    chatState = newState;
    console.log('Chat state updated:', chatState);
    updateButtonStates();
}

// Update button states based on chat state
function updateButtonStates() {
    if (!chatState || !chatState.streams) {
        return;
    }
    
    // Update each button based on its stream state
    Object.keys(chatState.streams).forEach(streamName => {
        const streamInfo = chatState.streams[streamName];
        const button = document.querySelector(`[data-join-as="${streamName}"]`);
        
        if (button) {
            const connectionStatus = streamInfo.connected;
            
            // Remove all existing status classes
            button.classList.remove('connecting', 'connected', 'disconnected');
            
            // Apply appropriate styling based on connection status
            switch (connectionStatus) {
                case 'connecting':
                    button.classList.add('connecting');
                    button.style.backgroundColor = '#ffc107';
                    button.style.color = '#000';
                    button.title = `Connecting to ${streamName}...`;
                    break;
                case 'connected':
                    button.classList.add('connected');
                    button.style.backgroundColor = '#28a745';
                    button.style.color = 'white';
                    button.title = `Connected as ${streamName}`;
                    break;
                case 'disconnected':
                default:
                    button.classList.add('disconnected');
                    button.style.backgroundColor = '';
                    button.style.color = '';
                    button.title = `Connect as ${streamName}`;
                    break;
            }
            
            console.log(`Updated button ${streamName} to status: ${connectionStatus}`);
        }
    });
}

// Fallback polling if WebSocket fails
function startStatePolling() {
    console.log('Starting state polling fallback');
    
    if (stateUpdateInterval) {
        clearInterval(stateUpdateInterval);
    }
    
    // Poll every 2 seconds
    stateUpdateInterval = setInterval(fetchChatState, 2000);
    
    // Initial fetch
    fetchChatState();
}

// Stop state polling
function stopStatePolling() {
    if (stateUpdateInterval) {
        clearInterval(stateUpdateInterval);
        stateUpdateInterval = null;
    }
}

// Get user media (webcam and microphone)
async function getUserMedia() {
    if (!localStream) {
        try {
            localStream = await navigator.mediaDevices.getUserMedia({
                video: true,
                audio: true
            });
            console.log('Local media stream obtained');
        } catch (error) {
            console.error('Error accessing media devices:', error);
            throw error;
        }
    }
    return localStream;
}

// Check if media permissions are already granted
async function checkMediaPermissions() {
    if (!navigator.mediaDevices || !navigator.permissions) {
        return 'unknown';
    }
    
    try {
        const cameraPermission = await navigator.permissions.query({ name: 'camera' });
        const microphonePermission = await navigator.permissions.query({ name: 'microphone' });
        
        if (cameraPermission.state === 'granted' && microphonePermission.state === 'granted') {
            return 'granted';
        } else if (cameraPermission.state === 'denied' || microphonePermission.state === 'denied') {
            return 'denied';
        } else {
            return 'prompt';
        }
    } catch (error) {
        console.log('Could not check permissions:', error);
        return 'unknown';
    }
}

// Show permission status in UI
function showPermissionStatus(status, streamName) {
    const button = document.querySelector(`[data-join-as="${streamName}"]`);
    if (button) {
        const originalText = button.textContent;
        
        switch (status) {
            case 'requesting':
                button.textContent = '🎥 Requesting permissions...';
                button.style.backgroundColor = '#17a2b8';
                button.style.color = 'white';
                break;
            case 'granted':
                button.textContent = originalText;
                break;
            case 'denied':
                button.textContent = '❌ Camera access denied';
                button.style.backgroundColor = '#dc3545';
                button.style.color = 'white';
                setTimeout(() => {
                    button.textContent = originalText;
                    button.style.backgroundColor = '';
                    button.style.color = '';
                }, 3000);
                break;
        }
    }
}

// Create WebRTC peer connection and handle offer
async function handleWebRTCOffer(streamName, offerSdp) {
    try {
        // Parse the offer SDP
        const offer = JSON.parse(offerSdp);
        console.log('Processing WebRTC offer for', streamName);
        console.log('DEBUG: Offer SDP:', offer.sdp);
        console.log('DEBUG: Offer includes video:', offer.sdp.includes('m=video'));
        console.log('DEBUG: Offer includes audio:', offer.sdp.includes('m=audio'));

        // Create RTCPeerConnection
        const pc = new RTCPeerConnection(rtcConfiguration);
        peerConnections[streamName] = pc;

        // Get user media and add tracks to peer connection
        const stream = await getUserMedia();
        console.log('DEBUG: Got user media stream with tracks:', stream.getTracks().length);
        
        stream.getTracks().forEach((track, index) => {
            console.log(`DEBUG: Adding track ${index + 1}: ${track.kind} (${track.label})`);
            const sender = pc.addTrack(track, stream);
            console.log('DEBUG: Track added successfully, sender:', sender);
        });

        // Set up event handlers
        pc.onicecandidate = async (event) => {
            if (event.candidate) {
                console.log('ICE candidate generated:', event.candidate);
                console.log('Candidate type:', event.candidate.type);
                console.log('Candidate address:', event.candidate.address);
                
                // Send ICE candidate to server
                try {
                    await sendICECandidate(streamName, {
                        candidate: event.candidate.candidate,
                        sdpMLineIndex: event.candidate.sdpMLineIndex,
                        sdpMid: event.candidate.sdpMid
                    });
                } catch (error) {
                    console.error('Failed to send ICE candidate:', error);
                }
            } else {
                console.log('ICE gathering completed');
            }
        };

        pc.onicegatheringstatechange = () => {
            console.log('ICE gathering state:', pc.iceGatheringState);
        };

        pc.oniceconnectionstatechange = () => {
            console.log('ICE connection state:', pc.iceConnectionState);
            if (pc.iceConnectionState === 'failed') {
                console.error('ICE connection failed - likely NAT/firewall issue');
                console.log('Trying to restart ICE...');
                pc.restartIce();
            } else if (pc.iceConnectionState === 'connected') {
                console.log('ICE connection established successfully!');
            }
        };

        pc.onconnectionstatechange = () => {
            console.log(`Connection state for ${streamName}:`, pc.connectionState);
            updateConnectionStatus(streamName, pc.connectionState);
        };

        pc.ontrack = (event) => {
            console.log('Received remote track:', event.track.kind);
            console.log('Track details:', {
                kind: event.track.kind,
                id: event.track.id,
                label: event.track.label,
                readyState: event.track.readyState,
                muted: event.track.muted
            });
            
            // Show message that video is being displayed in OpenCV window on server
            if (event.track.kind === 'video') {
                displayOpenCVMessage(streamName);
            }
        };

        pc.ondatachannel = (event) => {
            const channel = event.channel;
            console.log('Data channel received:', channel.label);
            
            channel.onopen = () => {
                console.log('Data channel opened:', channel.label);
            };
            
            channel.onmessage = (event) => {
                console.log('Data channel message:', event.data);
            };
        };

        // Set the remote description (the offer)
        await pc.setRemoteDescription(new RTCSessionDescription(offer));
        console.log('DEBUG: Remote description set successfully');

        // Create and set local description (the answer)
        const answer = await pc.createAnswer();
        console.log('DEBUG: Created answer SDP:', answer.sdp);
        console.log('DEBUG: Answer includes video:', answer.sdp.includes('m=video'));
        console.log('DEBUG: Answer includes audio:', answer.sdp.includes('m=audio'));
        
        await pc.setLocalDescription(answer);
        console.log('DEBUG: Local description (answer) set successfully');

        // Send the answer back to the server
        await sendWebRTCAnswer(streamName, answer);

        // Start polling for server ICE candidates
        startICECandidatePolling(streamName, pc);

        // Display local video
        displayLocalStream(streamName, stream);

        return pc;
    } catch (error) {
        console.error('Error handling WebRTC offer:', error);
        throw error;
    }
}

// Send ICE candidate to server
async function sendICECandidate(streamName, candidateData) {
    try {
        const response = await fetch(`/ice_candidate/${streamName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(candidateData)
        });

        if (response.ok) {
            console.log('ICE candidate sent successfully');
        } else {
            console.error('Failed to send ICE candidate:', response.statusText);
        }
    } catch (error) {
        console.error('Error sending ICE candidate:', error);
        throw error;
    }
}

// Poll for server ICE candidates
async function startICECandidatePolling(streamName, pc) {
    const pollInterval = 1000; // Poll every second
    const maxPolls = 30; // Stop after 30 seconds
    let pollCount = 0;
    
    const poll = async () => {
        try {
            const response = await fetch(`/ice_candidates/${streamName}`);
            if (response.ok) {
                const data = await response.json();
                const candidates = data.candidates || [];
                
                // Add any new candidates to the peer connection
                for (const candidateData of candidates) {
                    try {
                        const candidate = new RTCIceCandidate({
                            candidate: candidateData.candidate,
                            sdpMLineIndex: candidateData.sdpMLineIndex,
                            sdpMid: candidateData.sdpMid
                        });
                        await pc.addIceCandidate(candidate);
                        console.log('Added server ICE candidate:', candidateData);
                    } catch (candidateError) {
                        console.warn('Failed to add server ICE candidate:', candidateError);
                    }
                }
            }
        } catch (error) {
            console.warn('Error polling for ICE candidates:', error);
        }
        
        pollCount++;
        if (pollCount < maxPolls && pc.iceConnectionState !== 'connected') {
            setTimeout(poll, pollInterval);
        }
    };
    
    // Start polling after a short delay
    setTimeout(poll, 500);
}

// Send WebRTC answer to the server
async function sendWebRTCAnswer(streamName, answer) {
    try {
        const answerData = {
            type: answer.type,
            sdp: answer.sdp
        };

        const response = await fetch(`/webrtc_answer/${streamName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(answerData)
        });

        if (response.ok) {
            console.log('WebRTC answer sent successfully');
        } else {
            console.error('Failed to send WebRTC answer:', response.statusText);
        }
    } catch (error) {
        console.error('Error sending WebRTC answer:', error);
        throw error;
    }
}

// Display local video stream
function displayLocalStream(streamName, stream) {
    const previewContainer = document.getElementById('local-stream-preview');
    
    // Remove existing video element if any
    const existingVideo = previewContainer.querySelector('video');
    if (existingVideo) {
        existingVideo.remove();
    }

    // Create video element
    const video = document.createElement('video');
    video.id = `local-${streamName}`;
    video.autoplay = true;
    video.muted = true; // Mute local video to prevent feedback
    video.playsInline = true;
    video.style.width = '100%';
    video.style.height = '100%';
    video.style.objectFit = 'cover';

    // Show the preview container and add video
    previewContainer.style.display = 'block';
    previewContainer.appendChild(video);

    // Set video source
    video.srcObject = stream;
    console.log('Local video stream displayed in toolbar preview for', streamName);
}

// Display message that video is being shown in OpenCV window on server
function displayOpenCVMessage(streamName) {
    const streamWindow = document.querySelector('.stream-window');
    
    if (!streamWindow) {
        console.error('Stream window not found');
        return;
    }
    
    // Clear the stream window for the OpenCV message
    streamWindow.innerHTML = '';
    
    // Create container for the message
    const container = document.createElement('div');
    container.id = `opencv-message-${streamName}`;
    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.justifyContent = 'center';
    container.style.height = '100%';
    container.style.textAlign = 'center';
    container.style.backgroundColor = '#1e1e1e';
    container.style.color = 'white';
    container.style.padding = '20px';
    
    // Create content
    const content = document.createElement('div');
    content.innerHTML = `
        <div style="max-width: 600px;">
            <h2 style="color: #4CAF50; margin-bottom: 20px;">
                🎥 Video Feed Active
            </h2>
            <p style="font-size: 18px; margin-bottom: 15px;">
                <strong>Stream:</strong> ${streamName}
            </p>
            <p style="font-size: 16px; margin-bottom: 15px;">
                Your video is being displayed in an OpenCV window on the server.
            </p>
            <p style="font-size: 14px; color: #888; margin-bottom: 20px;">
                Check the server console/desktop for the video display window.
            </p>
            <div style="background: #333; padding: 15px; border-radius: 5px; font-family: monospace; margin-top: 20px;">
                <p style="margin: 0; color: #0f0;">✓ WebRTC Connection: Established</p>
                <p style="margin: 5px 0 0 0; color: #0f0;">✓ Video Track: Received</p>
                <p style="margin: 5px 0 0 0; color: #0f0;">✓ OpenCV Display: Active</p>
            </div>
        </div>
    `;
    
    container.appendChild(content);
    streamWindow.appendChild(container);
    
    console.log(`OpenCV display message shown for ${streamName}`);
}

// Display remote video stream (deprecated - now using OpenCV)
function displayRemoteStream(streamName, stream) {
    // This function is no longer used since we're displaying video in OpenCV windows
    console.log(`Remote stream received for ${streamName}, but using OpenCV display instead`);
    displayOpenCVMessage(streamName);
}

// Update connection status in UI (now integrated with WebSocket state)
function updateConnectionStatus(streamName, connectionState) {
    const button = document.querySelector(`[data-join-as="${streamName}"]`);
    if (button) {
        // Remove existing status classes
        button.classList.remove('connecting', 'connected', 'disconnected');
        
        // Add status-specific class and update text
        switch (connectionState) {
            case 'connecting':
                button.classList.add('connecting');
                button.style.backgroundColor = '#ffc107';
                button.style.color = '#000';
                button.title = `Connecting to ${streamName}...`;
                break;
            case 'connected':
                button.classList.add('connected');
                button.style.backgroundColor = '#28a745';
                button.style.color = 'white';
                button.title = `Connected as ${streamName}`;
                break;
            case 'disconnected':
            case 'failed':
            case 'closed':
                button.classList.add('disconnected');
                button.style.backgroundColor = '';
                button.style.color = '';
                button.title = `Connect as ${streamName}`;
                break;
            default:
                button.style.backgroundColor = '';
                button.style.color = '';
                button.title = `Connect as ${streamName}`;
        }
    }
    
    // Trigger state refresh to keep in sync
    setTimeout(fetchChatState, 500);
}

// Stop camera and microphone
function stopCamera() {
    if (localStream) {
        console.log('Stopping camera and microphone...');
        
        // Stop all tracks (video and audio)
        localStream.getTracks().forEach(track => {
            console.log(`Stopping ${track.kind} track:`, track.label);
            track.stop();
        });
        
        // Clear the local stream reference
        localStream = null;
        console.log('Camera and microphone stopped');
    } else {
        console.log('No camera stream to stop');
    }
}

// Send close connection request to server
async function sendCloseConnection(streamName) {
    try {
        const response = await fetch(`/close_connection/${streamName}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            console.log(`Server connection closed for ${streamName}`);
        } else {
            console.error(`Failed to close server connection for ${streamName}`);
        }
    } catch (error) {
        console.error(`Error closing server connection for ${streamName}:`, error);
    }
}

// Close WebRTC connection
async function closeConnection(streamName) {
    if (peerConnections[streamName]) {
        peerConnections[streamName].close();
        delete peerConnections[streamName];
        console.log('Closed connection for', streamName);
    }

    // Clear current active stream if this was the active one
    if (currentActiveStream === streamName) {
        currentActiveStream = null;
        
        // Stop the camera when the active stream is closed
        stopCamera();
    }

    // Remove video from preview and hide if no active connections
    const previewContainer = document.getElementById('local-stream-preview');
    const localVideo = document.getElementById(`local-${streamName}`);
    if (localVideo) {
        localVideo.remove();
    }
    
    // Hide preview if no more local streams
    if (!previewContainer.querySelector('video')) {
        previewContainer.style.display = 'none';
    }

    // Remove mirror stream from main window
    const streamWindow = document.querySelector('.stream-window');
    const mirrorContainer = document.getElementById(`mirror-container-${streamName}`);
    if (mirrorContainer) {
        mirrorContainer.remove();
        console.log(`Removed mirror display for ${streamName}`);
    }
    
    // Clear stream window if no active connections
    if (streamWindow && !streamWindow.querySelector('video')) {
        streamWindow.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100%; text-align: center; color: #666;">
                <div>
                    <h3>No Active Connection</h3>
                    <p>Click a connection button to start mirroring</p>
                </div>
            </div>
        `;
    }

    updateConnectionStatus(streamName, 'disconnected');
}


// bind to data-join-as buttons click to manage connection requests
document.querySelectorAll('[data-join-as]').forEach(button => {
    console.log("Initializing connection binding for:", button);
    button.addEventListener('click', async () => {
        const streamName = button.getAttribute('data-join-as');
        try {
            // Terminate existing connection if switching to a different stream
            if (currentActiveStream && currentActiveStream !== streamName) {
                console.log(`Terminating existing connection: ${currentActiveStream}`);
                await closeConnection(currentActiveStream);
                await sendCloseConnection(currentActiveStream);
            }
            
            updateConnectionStatus(streamName, 'connecting');
            currentActiveStream = streamName;
            
            // Check current permission status
            const permissionStatus = await checkMediaPermissions();
            console.log('Current media permission status:', permissionStatus);
            
            // Handle different permission states
            if (permissionStatus === 'denied') {
                updateConnectionStatus(streamName, 'disconnected');
                showPermissionStatus('denied', streamName);
                alert('Camera and microphone access is blocked. Please enable permissions in your browser settings and refresh the page.');
                return;
            }
            
            // Show requesting status if we need to prompt for permissions
            if (permissionStatus === 'prompt' || permissionStatus === 'unknown') {
                showPermissionStatus('requesting', streamName);
            }
            
            // Request camera and microphone permissions
            console.log('Requesting camera and microphone permissions...');
            try {
                await getUserMedia();
                console.log('Camera and microphone permissions granted');
                showPermissionStatus('granted', streamName);
            } catch (mediaError) {
                console.error('Failed to get camera/microphone access:', mediaError);
                updateConnectionStatus(streamName, 'disconnected');
                showPermissionStatus('denied', streamName);
                
                let errorMessage = 'Failed to access camera/microphone. ';
                if (mediaError.name === 'NotAllowedError') {
                    errorMessage += 'Please allow camera and microphone access and try again.';
                } else if (mediaError.name === 'NotFoundError') {
                    errorMessage += 'No camera or microphone found.';
                } else if (mediaError.name === 'NotSupportedError') {
                    errorMessage += 'Camera/microphone not supported by this browser.';
                } else {
                    errorMessage += mediaError.message || 'Unknown error occurred.';
                }
                
                alert(errorMessage);
                return;
            }
            
            // Now proceed with WebRTC connection
            const response = await fetch(`/request_connection/${streamName}`, {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log(`Received offer SDP for ${streamName}:`, data.offer_sdp);
            
            // Handle the WebRTC offer and start streaming
            await handleWebRTCOffer(streamName, data.offer_sdp);
            
        } catch (error) {
            console.error('Error requesting connection:', error);
            updateConnectionStatus(streamName, 'disconnected');
            alert(`Failed to connect as ${streamName}: ${error.message}`);
        }
    });
});

// Stop button functionality - implemented from scratch
function initializeStopButton() {
    const stopButton = document.getElementById('stop');
    if (stopButton) {
        console.log('Stop button found, adding click handler');
        
        stopButton.addEventListener('click', async (event) => {
            event.preventDefault();
            console.log('STOP button clicked');
            
            if (currentActiveStream) {
                console.log(`Stopping active connection: ${currentActiveStream}`);
                
                try {
                    // Close the WebRTC connection (this will also stop the camera)
                    await closeConnection(currentActiveStream);
                    
                    // Notify the server
                    await sendCloseConnection(currentActiveStream);
                    
                    // Reset the current active stream
                    currentActiveStream = null;
                    
                    console.log('Connection and camera stopped successfully');
                    
                    // Visual feedback - briefly change button color
                    stopButton.style.backgroundColor = '#28a745';
                    stopButton.style.color = 'white';
                    setTimeout(() => {
                        stopButton.style.backgroundColor = '';
                        stopButton.style.color = '';
                    }, 1000);
                    
                } catch (error) {
                    console.error('Error stopping connection:', error);
                    
                    // Visual feedback for error
                    stopButton.style.backgroundColor = '#dc3545';
                    stopButton.style.color = 'white';
                    setTimeout(() => {
                        stopButton.style.backgroundColor = '';
                        stopButton.style.color = '';
                    }, 2000);
                }
            } else {
                console.log('No active connection to stop');
                
                // Visual feedback - briefly show info
                stopButton.style.backgroundColor = '#17a2b8';
                stopButton.style.color = 'white';
                setTimeout(() => {
                    stopButton.style.backgroundColor = '';
                    stopButton.style.color = '';
                }, 1000);
            }
        });
    } else {
        console.error('Stop button with ID "stop" not found');
    }
}

// Initialize everything when the page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded - initializing stop button and WebSocket');
    initializeStopButton();
    initializeWebSocket();
    
    // Initialize stream window with placeholder
    const streamWindow = document.querySelector('.stream-window');
    if (streamWindow) {
        streamWindow.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100%; text-align: center; color: #666;">
                <div>
                    <h3>WebRTC Mirror Server</h3>
                    <p>Click a connection button to start mirroring your video and audio</p>
                    <small>Your stream will be mirrored back to you in real-time</small>
                </div>
            </div>
        `;
    }
});

// Also initialize immediately if DOM is already loaded
if (document.readyState === 'loading') {
    // DOM is still loading, wait for DOMContentLoaded
    console.log('DOM is still loading, waiting...');
} else {
    // DOM is already loaded
    console.log('DOM already loaded - initializing stop button and WebSocket immediately');
    initializeStopButton();
    initializeWebSocket();
    
    // Initialize stream window with placeholder
    const streamWindow = document.querySelector('.stream-window');
    if (streamWindow) {
        streamWindow.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100%; text-align: center; color: #666;">
                <div>
                    <h3>WebRTC Mirror Server</h3>
                    <p>Click a connection button to start mirroring your video and audio</p>
                    <small>Your stream will be mirrored back to you in real-time</small>
                </div>
            </div>
        `;
    }
}
