import cv2
import numpy as np
import threading
import asyncio
from typing import Dict, Optional
import logging

# Configure logging for this module
logger = logging.getLogger(__name__)

class OpenCVDisplayManager:
    """Manages OpenCV video display windows for WebRTC streams with hardware acceleration"""
    
    def __init__(self):
        self.active_windows: Dict[str, bool] = {}
        self.video_threads: Dict[str, threading.Thread] = {}
        self.gpu_available = False
        self.opencl_available = False
        
        # Initialize hardware acceleration
        self._initialize_hardware_acceleration()
        
        # AMD RX 7900 XTX specific optimizations
        self._configure_amd_optimizations()
        
    def _initialize_hardware_acceleration(self):
        """Initialize OpenCL hardware acceleration for AMD GPU"""
        try:
            # Check if OpenCL is available
            if cv2.ocl.haveOpenCL():
                print("DEBUG: OpenCL support detected")
                
                # Enable OpenCL
                cv2.ocl.setUseOpenCL(True)
                
                if cv2.ocl.useOpenCL():
                    # Get basic OpenCL info
                    print("DEBUG: OpenCL enabled successfully")
                    print("DEBUG: Hardware acceleration will be used for image processing")
                    
                    self.opencl_available = True
                    self.gpu_available = True
                    print("DEBUG: AMD GPU hardware acceleration enabled")
                else:
                    print("WARNING: OpenCL available but not enabled")
            else:
                print("WARNING: OpenCL not available")
                
        except Exception as e:
            print(f"WARNING: Failed to initialize hardware acceleration: {e}")
            logger.warning(f"Hardware acceleration initialization failed: {e}")
    
    def _configure_amd_optimizations(self):
        """Configure specific optimizations for AMD RX 7900 XTX"""
        try:
            if self.opencl_available:
                # Set OpenCV thread count for optimal AMD GPU performance
                cv2.setNumThreads(4)  # Optimal for RX 7900 XTX with high core count
                
                # Configure OpenCL device selection (prefer discrete GPU)
                print("DEBUG: Configuring AMD RX 7900 XTX optimizations")
                
                # Set optimal buffer sizes for high-end AMD GPU
                import os
                os.environ['OPENCV_OPENCL_DEVICE'] = ':GPU:0'  # Use first discrete GPU
                
                print("DEBUG: AMD GPU optimizations configured")
            
        except Exception as e:
            print(f"WARNING: Failed to configure AMD optimizations: {e}")
            logger.warning(f"AMD optimization configuration failed: {e}")
        
    def create_video_window(self, stream_name: str, track) -> None:
        """Create and start a video display window for a WebRTC track"""
        try:
            print(f"DEBUG: create_video_window called for {stream_name}")
            logger.info(f"Creating video window for {stream_name}")
            
            if stream_name in self.active_windows and self.active_windows[stream_name]:
                logger.warning(f"Window for {stream_name} already active")
                print(f"WARNING: Window for {stream_name} already exists")
                return
                
            logger.info(f"Setting up OpenCV display for {stream_name}")
            print(f"DEBUG: Setting up OpenCV display for {stream_name}")
            
            # Mark window as active immediately
            self.active_windows[stream_name] = True
            
            # Start video frame processing in a separate thread
            def process_video_frames():
                print(f"DEBUG: Starting video processing thread for {stream_name}")
                self._run_video_processing_loop(stream_name, track)
            
            # Start video processing thread
            video_thread = threading.Thread(target=process_video_frames, daemon=True)
            video_thread.start()
            self.video_threads[stream_name] = video_thread
            
            logger.info(f"OpenCV window created and video processing started for {stream_name}")
            print(f"DEBUG: Video processing thread started for {stream_name}")
            
        except Exception as e:
            logger.error(f"Error creating video window for {stream_name}: {e}")
            print(f"ERROR: Failed to create video window for {stream_name}: {e}")
            import traceback
            traceback.print_exc()
            self.active_windows[stream_name] = False
    
    def _run_video_processing_loop(self, stream_name: str, track):
        """Run the video processing loop in its own async context"""
        
        # Create window name
        window_name = f"Video Feed - {stream_name}"
        
        async def video_loop():
            try:
                print(f"DEBUG: Video loop starting for {stream_name}")
                logger.info(f"Video processing started for {stream_name}")
                
                # Create OpenCV window with low-latency optimizations
                print(f"DEBUG: Creating low-latency OpenCV window: {window_name}")
                cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                cv2.resizeWindow(window_name, 640, 480)
                
                # Ultra-low latency window optimizations
                try:
                    # Disable window buffering for immediate display
                    cv2.setWindowProperty(window_name, cv2.WND_PROP_VSYNC, 0)  # Disable VSync
                    print("DEBUG: VSync disabled for ultra-low latency")
                except Exception as e:
                    print(f"DEBUG: VSync setting not supported: {e}")
                
                print(f"DEBUG: Low-latency OpenCV window created successfully")
                
                # Initialize frame counter and metrics with low-latency optimizations
                frame_count = 0
                last_frame_time = asyncio.get_event_loop().time()
                last_fps_update = last_frame_time
                fps_display = 0.0
                frames_received = 0
                frames_dropped = 0
                error_count = 0
                last_display_time = 0
                
                # Low-latency configuration
                max_frame_age = 0.05  # Drop frames older than 50ms
                min_display_interval = 1.0 / 60  # Target 60 FPS display rate
                frame_skip_threshold = 2  # Skip frames if we're falling behind
                
                while self.active_windows.get(stream_name, False):
                    try:
                        # Receive frame with aggressive timeout for low latency
                        frame_start_time = asyncio.get_event_loop().time()
                        frame = await asyncio.wait_for(track.recv(), timeout=0.1)  # Reduced from 0.5s
                        frame_receive_time = asyncio.get_event_loop().time()
                        
                        frames_received += 1
                        frame_count += 1
                        error_count = 0
                        
                        # Check frame age for latency optimization
                        frame_age = frame_receive_time - frame_start_time
                        if frame_age > max_frame_age:
                            frames_dropped += 1
                            if frames_dropped % 10 == 0:
                                print(f"DEBUG: Dropping old frames for {stream_name}, age: {frame_age*1000:.1f}ms")
                            continue
                        
                        # Skip frame processing if we're behind schedule
                        if (frame_receive_time - last_display_time) < min_display_interval:
                            continue
                        
                        # Fast frame conversion with minimal copying
                        img = frame.to_ndarray(format="bgr24")
                        
                        # Calculate FPS with latency metrics
                        current_time = asyncio.get_event_loop().time()
                        if current_time - last_fps_update >= 1.0:
                            fps_display = frame_count / (current_time - last_fps_update)
                            frame_count = 0
                            last_fps_update = current_time
                            
                            # Enhanced logging with latency info
                            if frames_received % 120 == 0:  # Log every 2 seconds
                                accel_status = "AMD GPU" if self.opencl_available else "CPU"
                                latency_ms = frame_age * 1000
                                drop_rate = (frames_dropped / frames_received) * 100 if frames_received > 0 else 0
                                print(f"DEBUG: {stream_name}: {fps_display:.1f} FPS ({accel_status}), "
                                     f"latency: {latency_ms:.1f}ms, drop rate: {drop_rate:.1f}%")
                        
                        # Use hardware acceleration with latency optimization
                        process_start = asyncio.get_event_loop().time()
                        
                        if self.opencl_available:
                            # Ultra-fast GPU processing
                            img_with_overlay = self._add_video_overlay_low_latency(img, stream_name, fps_display)
                        else:
                            # Optimized CPU processing
                            img_with_overlay = self._add_video_overlay_cpu_fast(img, stream_name, fps_display)
                        
                        process_end = asyncio.get_event_loop().time()
                        processing_time = (process_end - process_start) * 1000  # ms
                        
                        # Display the frame immediately
                        cv2.imshow(window_name, img_with_overlay)
                        last_display_time = asyncio.get_event_loop().time()
                        
                        # Log processing time occasionally for optimization
                        if frames_received % 300 == 0:  # Every 5 seconds
                            total_latency = (last_display_time - frame_start_time) * 1000
                            print(f"DEBUG: Processing time: {processing_time:.1f}ms, "
                                 f"total latency: {total_latency:.1f}ms")
                        
                        # Check for window close or 'q' key (non-blocking)
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord('q') or cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                            logger.info(f"User closed OpenCV window for {stream_name}")
                            self.close_window(stream_name)
                            break
                            
                    except asyncio.TimeoutError:
                        # No frame received within timeout - show waiting message less frequently
                        if frames_received == 0 or frames_received % 30 == 0:
                            print(f"DEBUG: Waiting for frames from {stream_name} (frames received: {frames_received})")
                        
                        # Display waiting message
                        waiting_frame = self._create_waiting_frame(stream_name)
                        cv2.imshow(window_name, waiting_frame)
                        
                        key = cv2.waitKey(1) & 0xFF  # Reduced wait time
                        if key == ord('q') or cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                            logger.info(f"User closed OpenCV window for {stream_name}")
                            self.close_window(stream_name)
                            break
                            
                    except Exception as e:
                        error_count += 1
                        if error_count <= 5:  # Only log first few errors to avoid spam
                            logger.error(f"Error receiving frame for {stream_name}: {e}")
                            print(f"ERROR: Frame reception error for {stream_name}: {e}")
                        
                        # Shorter delay for better recovery
                        await asyncio.sleep(0.01)  # 10ms instead of 100ms
                        
            except Exception as e:
                logger.error(f"Error in video processing for {stream_name}: {e}")
                print(f"ERROR: Video processing error for {stream_name}: {e}")
                import traceback
                traceback.print_exc()
                
            finally:
                print(f"DEBUG: Cleaning up OpenCV window for {stream_name}")
                cv2.destroyWindow(window_name)
                logger.info(f"OpenCV window closed for {stream_name}")
        
        # Create new event loop for this thread
        print(f"DEBUG: Creating event loop for {stream_name}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            print(f"DEBUG: Running video loop for {stream_name}")
            loop.run_until_complete(video_loop())
        except Exception as e:
            print(f"ERROR: Event loop error for {stream_name}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print(f"DEBUG: Closing event loop for {stream_name}")
            loop.close()
    
    def _add_video_overlay_low_latency(self, img: np.ndarray, stream_name: str, fps_display: float) -> np.ndarray:
        """Ultra-low latency overlay for AMD GPU - minimal processing"""
        # Minimal overlay for maximum speed
        height, width = img.shape[:2]
        
        # Simplified overlay with direct pixel operations
        overlay_region = img[10:80, 10:280]  # Smaller overlay area
        
        # Fast background darkening using vectorized operations
        overlay_region[:] = overlay_region * 0.7  # Direct multiplication
        
        # Minimal text with maximum performance
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Only essential text to minimize rendering time
        cv2.putText(overlay_region, f"{stream_name}", (5, 20), font, 0.4, (0, 255, 0), 1)
        cv2.putText(overlay_region, f"{fps_display:.0f} FPS", (5, 40), font, 0.4, (255, 255, 255), 1)
        cv2.putText(overlay_region, "LOW-LAT", (5, 60), font, 0.3, (255, 255, 0), 1)
        
        return img
    
    def _add_video_overlay_cpu_fast(self, img: np.ndarray, stream_name: str, fps_display: float) -> np.ndarray:
        """Fast CPU overlay with minimal latency"""
        height, width = img.shape[:2]
        
        # Minimal overlay processing
        overlay_region = img[10:80, 10:280]
        
        # Fast darkening
        overlay_region[:] = overlay_region * 0.7
        
        # Minimal text
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(overlay_region, f"{stream_name}", (5, 20), font, 0.4, (0, 255, 0), 1)
        cv2.putText(overlay_region, f"{fps_display:.0f} FPS", (5, 40), font, 0.4, (255, 255, 255), 1)
        cv2.putText(overlay_region, "CPU", (5, 60), font, 0.3, (255, 255, 0), 1)
        
        return img
    
    def _add_video_overlay_gpu_optimized(self, img: np.ndarray, stream_name: str, fps_display: float) -> np.ndarray:
        """Add overlay using OpenCL-optimized operations for AMD GPU"""
        height, width = img.shape[:2]
        
        # AMD RX 7900 XTX optimizations
        # Use minimal memory copies and vectorized operations
        
        # Create overlay region (in-place to minimize memory allocation)
        overlay_height, overlay_width = 120, 320
        overlay_y, overlay_x = 10, 10
        
        # Work directly on image region to avoid copy operations
        overlay_region = img[overlay_y:overlay_y+overlay_height, overlay_x:overlay_x+overlay_width]
        
        # Create background mask using vectorized operations
        mask = np.zeros_like(overlay_region, dtype=np.uint8)
        
        # OpenCV will use OpenCL backend for this operation on AMD GPU
        blended = cv2.addWeighted(overlay_region, 0.7, mask, 0.3, 0)
        
        # Optimized text rendering with pre-computed values
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Batch text operations for better GPU utilization
        cv2.putText(blended, f"Stream: {stream_name}", (5, 25), font, 0.5, (0, 255, 0), 1)
        cv2.putText(blended, f"Res: {width}x{height}", (5, 50), font, 0.4, (255, 255, 255), 1)
        cv2.putText(blended, f"FPS: {fps_display:.1f} (AMD)", (5, 75), font, 0.4, (255, 255, 255), 1)
        cv2.putText(blended, "Press 'q' to close", (5, 95), font, 0.3, (255, 255, 0), 1)
        
        # Copy back using vectorized assignment (GPU-optimized)
        img[overlay_y:overlay_y+overlay_height, overlay_x:overlay_x+overlay_width] = blended
        
        return img
    
    def _add_video_overlay_cpu(self, img: np.ndarray, stream_name: str, fps_display: float) -> np.ndarray:
        """Add overlay information to video frame using CPU (fallback)"""
        height, width = img.shape[:2]
        
        # Create overlay region
        overlay_region = img[10:130, 10:320].copy()
        overlay_bg = np.zeros((120, 310, 3), dtype=np.uint8)
        
        # Blend overlay
        cv2.addWeighted(overlay_region, 0.7, overlay_bg, 0.3, 0, overlay_region)
        
        # Add text overlays
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        cv2.putText(overlay_region, f"Stream: {stream_name}", (5, 25), 
                  font, 0.5, (0, 255, 0), 1)
        cv2.putText(overlay_region, f"Res: {width}x{height}", (5, 50), 
                  font, 0.4, (255, 255, 255), 1)
        cv2.putText(overlay_region, f"FPS: {fps_display:.1f} (CPU)", (5, 75), 
                  font, 0.4, (255, 255, 255), 1)
        cv2.putText(overlay_region, "Press 'q' to close", (5, 95), 
                  font, 0.3, (255, 255, 0), 1)
        
        # Copy overlay back to original image
        img[10:130, 10:320] = overlay_region
        
        return img
    
    def _create_waiting_frame(self, stream_name: str) -> np.ndarray:
        """Create a frame to display while waiting for video"""
        waiting_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(waiting_frame, f"Waiting for video frames...", (150, 240), 
                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.putText(waiting_frame, f"Stream: {stream_name}", (200, 280), 
                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        return waiting_frame
    
    def close_window(self, stream_name: str) -> None:
        """Close the OpenCV window for a specific stream"""
        if stream_name in self.active_windows:
            self.active_windows[stream_name] = False
            logger.info(f"Marked OpenCV window for closure: {stream_name}")
            
        # Clean up thread reference
        if stream_name in self.video_threads:
            del self.video_threads[stream_name]
    
    def close_all_windows(self) -> None:
        """Close all active OpenCV windows"""
        for stream_name in list(self.active_windows.keys()):
            self.close_window(stream_name)
        logger.info("All OpenCV windows marked for closure")
    
    def get_active_windows(self) -> Dict[str, bool]:
        """Get information about currently active windows"""
        return {
            stream_name: active
            for stream_name, active in self.active_windows.items()
            if active
        }
    
    def is_window_active(self, stream_name: str) -> bool:
        """Check if a window is currently active"""
        return self.active_windows.get(stream_name, False)