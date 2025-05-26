import logging
import os
import re
import time
import threading
import pythoncom
import win32com.client
import io
import struct
import ctypes
import numpy as np
import cv2
import hashlib
from ctypes import wintypes, windll, byref, c_int, c_uint, c_long, create_unicode_buffer
from urllib.request import urlopen, Request
from pathlib import Path
from contextlib import contextmanager

import keyboard
import win32gui
import win32con
import win32api
import win32clipboard
import win32process
from PIL import Image, ImageGrab, ImageStat, ImageChops, ImageFilter, ImageWin
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QMimeData, Qt, QRect, QThread, QCoreApplication, QMutex, QMutexLocker, QPoint, QBuffer
from PyQt5.QtGui import QImage, QPainter, QPen, QColor, QClipboard, QGuiApplication
from PyQt5.QtWidgets import QApplication, QWidget, QMessageBox, QDesktopWidget

from screen_capture import ScreenCapture

# Constants for Windows API
GWL_STYLE = -16
WS_BORDER = 0x00800000
WS_DLGFRAME = 0x00400000
WS_THICKFRAME = 0x00040000
WS_CAPTION = WS_BORDER | WS_DLGFRAME
WS_OVERLAPPED = 0x00000000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_OVERLAPPEDWINDOW = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX

# Window styles that might indicate a video player window
VIDEO_WINDOW_CLASSES = {
    'Chrome_WidgetWin_0',  # Chrome/Firefox browser
    'MozillaWindowClass',  # Firefox
    'MozillaCompositorWindowClass',  # Firefox (newer)
    'IEFrame',  # Internet Explorer
    'ApplicationFrameWindow',  # Edge
    'VLC',  # VLC Media Player
    'MPC-BE',  # MPC-BE Media Player
    'MPC-HC',  # MPC-HC Media Player
    'MediaPlayerClassicW',  # MPC-HC (newer)
    'WMPlayerApp',  # Windows Media Player
    'Win32WindowClass',  # Various media players
    'Qt5QWindowIcon',  # Various Qt-based media players
    'QWidget',  # Various Qt-based applications
    'Progman',  # Windows Desktop (fallback)
    'WorkerW',  # Windows Desktop (fallback)
    'CabinetWClass'  # Windows Explorer
}


class CaptureFrameOverlay(QWidget):
    """A transparent overlay widget that shows an outline around the captured area.
    
    Attributes:
        rect: The rectangle to highlight
        is_video: If True, draw a thicker border to indicate video capture
    """
    def __init__(self, rect, is_video=False, parent=None, settings=None):
        try:
            super().__init__(parent)
            self.rect = rect
            self.is_video = is_video
            self.settings = settings or {}
            
            # Get screen DPI scaling factor
            screen = QApplication.primaryScreen()
            self.dpr = screen.devicePixelRatio() or 1.0
            
            # Store original rect for painting
            self.original_rect = rect
            
            # Set up the overlay window properties
            self.setWindowFlags(
                Qt.FramelessWindowHint | 
                Qt.WindowStaysOnTopHint | 
                Qt.Tool | 
                Qt.X11BypassWindowManagerHint |
                Qt.WindowTransparentForInput
            )
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WA_DeleteOnClose, True)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            
            # Calculate screen geometry
            screens = QApplication.screens()
            virtual_rect = QRect()
            
            # Get the combined geometry of all screens in logical pixels
            for screen in screens:
                geometry = screen.geometry()
                virtual_rect = virtual_rect.united(geometry)
            
            logging.info(f"Virtual screen: {virtual_rect.x()},{virtual_rect.y()} {virtual_rect.width()}x{virtual_rect.height()}")
            logging.info(f"Capture frame: {self.original_rect.x()},{self.original_rect.y()} {self.original_rect.width()}x{self.original_rect.height()}")
            
            # Set the window geometry to cover all screens
            self.setGeometry(virtual_rect)
            
            # Set window opacity
            self.setWindowOpacity(1.0)
            
            # Use fixed 1000ms duration for consistent behavior
            frame_duration = 1000
            logging.debug(f"[ClipboardMonitor] Showing capture frame for {frame_duration}ms")
            
            # Set up a timer to automatically close the overlay
            self.close_timer = QTimer(self)
            self.close_timer.timeout.connect(self.close_safely)
            self.close_timer.setSingleShot(True)
            self.close_timer.start(frame_duration)
            
            # Safety timer - force close after duration + 1 second
            QTimer.singleShot(frame_duration + 1000, self.force_close)
            
            # Log the duration for debugging
            logging.debug(f"Capture frame will be shown for {frame_duration}ms")
            
            # Show the overlay
            self.show()
            self.raise_()
            self.activateWindow()
            
            logging.info(f"Created {'video ' if is_video else ''}capture frame overlay at {self.original_rect.x()},{self.original_rect.y()} size {self.original_rect.width()}x{self.original_rect.height()}")
            
        except Exception as e:
            logging.error(f"Error initializing CaptureFrameOverlay: {e}", exc_info=True)
    
    def close_safely(self):
        """Close the overlay safely."""
        try:
            if hasattr(self, 'close_timer') and self.close_timer and self.close_timer.isActive():
                self.close_timer.stop()
            self.close()
        except Exception as e:
            logging.error(f"Error closing overlay: {e}")
            self.force_close()
    
    def force_close(self):
        """Force close the overlay if it's still open."""
        try:
            if self.isVisible():
                logging.warning("Force closing capture frame overlay")
                self.close()
        except Exception as e:
            logging.error(f"Error force closing overlay: {e}")
    
    def paintEvent(self, event):
        """Draw a rectangle outline around the captured area with proper styling."""
        try:
            if not hasattr(self, 'original_rect') or self.original_rect.isNull():
                logging.warning("No valid rectangle to draw")
                return
                
            painter = QPainter(self)
            painter.setRenderHints(
                QPainter.Antialiasing | 
                QPainter.SmoothPixmapTransform |
                QPainter.HighQualityAntialiasing
            )
            
            # Get settings with defaults
            frame_color = QColor(self.settings.get('capture_frame_color', '#ADD8E6'))
            frame_opacity = self.settings.get('capture_frame_opacity', 200)
            frame_width = 4 if self.is_video else 2
            
            # Set the frame color and opacity
            frame_color.setAlpha(frame_opacity)
            
            # Get the rectangle in device coordinates
            rect = self.original_rect
            
            # Draw an outer glow effect (3 passes for smooth glow)
            for i in range(3, 0, -1):
                glow_color = QColor(frame_color)
                glow_color.setAlpha(frame_opacity // 3)  # Fainter glow
                glow_pen = QPen(glow_color)
                glow_pen.setWidth(frame_width + i * 3)
                glow_pen.setStyle(Qt.SolidLine)
                glow_pen.setCapStyle(Qt.RoundCap)
                glow_pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(glow_pen)
                painter.drawRoundedRect(rect.adjusted(-i, -i, i, i), 6, 6)
            
            # Draw the main frame
            pen = QPen(frame_color)
            pen.setWidth(frame_width)
            pen.setStyle(Qt.SolidLine)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            
            # Draw the main rectangle with rounded corners
            painter.drawRoundedRect(rect, 6, 6)
            
            # Draw a subtle inner highlight
            highlight = QPen(frame_color.lighter(150))
            highlight.setWidth(1)
            painter.setPen(highlight)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 5, 5)
            
            # Draw a subtle drop shadow
            shadow = QPen(QColor(0, 0, 0, 100))
            shadow.setWidth(1)
            painter.setPen(shadow)
            painter.drawRoundedRect(rect.adjusted(1, 1, 1, 1), 6, 6)
            
            # Draw corner indicators for better visibility
            corner_size = 20
            corner_pen = QPen(frame_color)
            corner_pen.setWidth(2)
            painter.setPen(corner_pen)
            
            # Top-left corner
            painter.drawLine(rect.topLeft(), rect.topLeft() + QPoint(corner_size, 0))
            painter.drawLine(rect.topLeft(), rect.topLeft() + QPoint(0, corner_size))
            
            # Top-right corner
            painter.drawLine(rect.topRight(), rect.topRight() - QPoint(corner_size, 0))
            painter.drawLine(rect.topRight(), rect.topRight() + QPoint(0, corner_size))
            
            # Bottom-left corner
            painter.drawLine(rect.bottomLeft(), rect.bottomLeft() + QPoint(corner_size, 0))
            painter.drawLine(rect.bottomLeft(), rect.bottomLeft() - QPoint(0, corner_size))
            
            # Bottom-right corner
            painter.drawLine(rect.bottomRight(), rect.bottomRight() - QPoint(corner_size, 0))
            painter.drawLine(rect.bottomRight(), rect.bottomRight() - QPoint(0, corner_size))
            
        except Exception as e:
            logging.error(f"Error in paintEvent: {e}", exc_info=True)


# Import mss for better multi-monitor screenshot support
try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    logging.warning("MSS library not available. Multi-monitor support may be limited.")
    logging.warning("To enable better multi-monitor support, install mss: pip install mss")

# Define necessary structures for Windows API calls
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION)
    ]

class ClipboardMonitor(QObject):
    """Monitors the clipboard for images and signals when one is found."""
    
    # Define signals as class variables
    new_image = pyqtSignal(object)
    image_captured = pyqtSignal(object)
    capture_frame_signal = pyqtSignal(QRect, bool)
    
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.screen_capture = ScreenCapture(settings)
        self.running = False
        self.last_image_hash = None
        self.last_web_url = None
        self.last_data = None
        self._keyboard_hook = None
        self.shift_timer = None
        self._cleanup_done = False
        
        # Initialize clipboard with proper cleanup
        self.clipboard = None
        self._init_clipboard()
        
        # Shift press tracking for double-shift feature
        self.shift_press_times = []
        self.shift_press_threshold = 0.3  # 300ms
        self.shift_released = True  # Track if shift was released since last press
        
        # Initialize settings
        self.draw_capture_frame = self.settings.get('draw_capture_frame', False)
        self.capture_overlay = None
        
        # Track clipboard content to avoid processing the same content multiple times
        self._last_clipboard_data = None
        self._last_clipboard_type = None
        
        # Initialize in a way that's safe for cleanup
        self._initialized = False
        try:
            # Connect the capture frame signal to the create_capture_overlay method
            self.capture_frame_signal.connect(self.create_capture_overlay)
            
            # Set up shift monitoring if enabled in settings
            if self.settings.get('double_shift_capture', False):
                self.setup_shift_monitoring()
            
            self._initialized = True
            logging.info("ClipboardMonitor initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing ClipboardMonitor: {e}", exc_info=True)
            raise
    
    def _init_clipboard(self):
        """Initialize clipboard with proper error handling."""
        try:
            self.clipboard = QApplication.clipboard()
            if self.clipboard:
                self.clipboard.dataChanged.connect(self._on_clipboard_changed)
        except Exception as e:
            logging.error(f"Failed to initialize clipboard: {e}", exc_info=True)
        
    def create_capture_overlay(self, rect, is_video=False):
        """Create a capture frame overlay at the specified rectangle.
        
        Args:
            rect: QRect specifying the area to highlight in logical pixels
            is_video: If True, indicates this is for video capture
        """
        try:
            # Check if capture frame is enabled in settings
            if not self.settings.get('draw_capture_frame', True):
                logging.info("Capture frame is disabled in settings")
                return
                
            # Ensure we're on the main thread
            if QThread.currentThread() != QApplication.instance().thread():
                logging.info("create_capture_overlay called from non-main thread, queuing call")
                QTimer.singleShot(0, lambda: self.create_capture_overlay(rect, is_video))
                return
                
            logging.info(f"Creating {'video ' if is_video else ''}capture overlay at {rect.x()},{rect.y()} {rect.width()}x{rect.height()}")
            
            # Close any existing overlay first
            if hasattr(self, 'capture_overlay') and self.capture_overlay:
                try:
                    logging.debug("Closing existing capture overlay")
                    self.capture_overlay.close()
                    self.capture_overlay.deleteLater()
                    self.capture_overlay = None
                except Exception as e:
                    logging.error(f"Error closing existing overlay: {e}", exc_info=True)
            
            # Ensure we have a valid rectangle
            if not rect.isValid() or rect.isEmpty():
                logging.error(f"Invalid rectangle provided for capture overlay: {rect}")
                return
                
            # Create and show the new overlay with settings
            self.capture_overlay = CaptureFrameOverlay(
                rect=rect,
                is_video=is_video,
                settings=self.settings
            )
            
            # Ensure the overlay is shown properly
            self.capture_overlay.show()
            self.capture_overlay.raise_()
            self.capture_overlay.activateWindow()
            
            # Force update
            self.capture_overlay.update()
            QApplication.processEvents()
            
            logging.info(f"Capture overlay created successfully at {rect.x()},{rect.y()}")
                
        except Exception as e:
            logging.error(f"Error in create_capture_overlay: {e}", exc_info=True)
    
    def start(self):
        """Start monitoring the clipboard for images"""
        if not self.running:
            self.running = True
            logging.info("Clipboard monitoring started")
            # Trigger initial clipboard check
            QTimer.singleShot(100, self._on_clipboard_changed)
            return True
        return False
        
    def stop(self):
        """Stop monitoring the clipboard"""
        if self.running:
            self.running = False
            self.clipboard.dataChanged.disconnect(self._on_clipboard_changed)
            logging.info("Clipboard monitoring stopped")
        self.cleanup()
        
    def _on_clipboard_changed(self):
        """Handle clipboard change events"""
        if not self.running or not self.settings.get("auto_refresh", True):
            return
            
        try:
            self.check_clipboard()
        except Exception as e:
            logging.error(f"Error processing clipboard content: {e}", exc_info=True)
            
    def check_clipboard(self):
        try:
            logging.debug_logger.info("Checking clipboard for new content")
            clipboard = QGuiApplication.clipboard()
            
            # Check for image data
            mime_data = clipboard.mimeData()
            
            if mime_data.hasImage():
                logging.debug_logger.info("Found image in clipboard")
                qimage = clipboard.image()
                
                if not qimage or qimage.isNull():
                    logging.debug_logger.warning("Clipboard image is null or invalid")
                    return
                
                # Check if the clipboard contains a GIF
                if hasattr(mime_data, 'formats') and 'image/gif' in mime_data.formats():
                    logging.debug_logger.info("Found GIF in clipboard, preserving format")
                    gif_data = mime_data.data('image/gif')
                    pil_image = Image.open(io.BytesIO(gif_data.data()))
                    pil_image.format = "GIF"
                else:
                    # For non-GIF images, convert to PNG
                    buffer = QBuffer()
                    buffer.open(QBuffer.ReadWrite)
                    qimage.save(buffer, "PNG")
                    pil_image = Image.open(io.BytesIO(buffer.data()))
                    pil_image.format = "PNG"
                
                # Set force refresh flag
                pil_image._force_refresh = True
                
                logging.debug_logger.info(f"Emitting clipboard image: {pil_image.size} {pil_image.mode} format: {getattr(pil_image, 'format', 'unknown')}")
                self.new_image.emit(pil_image)
                
            elif mime_data.hasUrls():
                logging.debug_logger.info("Found URLs in clipboard")
                urls = mime_data.urls()
                for url in urls:
                    if url.isLocalFile():
                        file_path = url.toLocalFile()
                        if self._is_image_file(file_path):
                            try:
                                # For GIFs, load with PIL to preserve animation
                                if file_path.lower().endswith('.gif'):
                                    with open(file_path, 'rb') as f:
                                        gif_data = f.read()
                                    image = Image.open(io.BytesIO(gif_data))
                                    image.format = 'GIF'
                                    # Store the raw data for later use in animation
                                    image._raw_gif_data = gif_data
                                else:
                                    image = Image.open(file_path)
                                    
                                image._force_refresh = True
                                logging.debug_logger.info(f"Emitting file image: {image.size} {image.mode} format: {getattr(image, 'format', 'unknown')}")
                                self.new_image.emit(image)
                                break
                            except Exception as e:
                                logging.debug_logger.error(f"Failed to load image file: {e}", exc_info=True)
                                
        except Exception as e:
            logging.debug_logger.error(f"Clipboard check error: {e}", exc_info=True)

            return
    
    def cleanup(self):
        """Clean up resources and prevent memory leaks."""
        if hasattr(self, '_cleanup_done') and self._cleanup_done:
            return
            
        try:
            # Stop any running operations
            self.running = False
            
            # Clean up clipboard
            if hasattr(self, 'clipboard') and self.clipboard:
                try:
                    self.clipboard.dataChanged.disconnect()
                except Exception as e:
                    logging.error(f"Error disconnecting clipboard signals: {e}", exc_info=True)
                self.clipboard = None
            
            # Clean up keyboard hooks
            if hasattr(self, '_keyboard_hook'):
                try:
                    keyboard.unhook(self._keyboard_hook)
                except Exception as e:
                    logging.error(f"Error cleaning up keyboard hook: {e}", exc_info=True)
                self._keyboard_hook = None
            
            # Clean up screen capture
            if hasattr(self, 'screen_capture'):
                try:
                    if hasattr(self.screen_capture, 'cleanup'):
                        self.screen_capture.cleanup()
                except Exception as e:
                    logging.error(f"Error cleaning up screen capture: {e}", exc_info=True)
                self.screen_capture = None
            
            # Clean up capture overlay
            if hasattr(self, 'capture_overlay') and self.capture_overlay:
                try:
                    self.capture_overlay.close()
                    self.capture_overlay.deleteLater()
                except Exception as e:
                    logging.error(f"Error cleaning up capture overlay: {e}", exc_info=True)
                self.capture_overlay = None
            
            # Clean up timers
            if hasattr(self, 'shift_timer') and self.shift_timer:
                try:
                    self.shift_timer.stop()
                    self.shift_timer.deleteLater()
                except Exception as e:
                    logging.error(f"Error cleaning up shift timer: {e}", exc_info=True)
                self.shift_timer = None
            
            # Clear signals
            if hasattr(self, 'capture_frame_signal'):
                try:
                    self.capture_frame_signal.disconnect()
                except Exception:
                    pass
            
            # Clear other attributes
            self._last_clipboard_data = None
            self._last_clipboard_type = None
            self.last_image_hash = None
            self.last_web_url = None
            self.last_data = None
            
            logging.info("Clipboard monitor cleaned up")
            
        except Exception as e:
            logging.error(f"Error during cleanup: {e}", exc_info=True)
        finally:
            self._cleanup_done = True
            # Force garbage collection
            import gc
            gc.collect()
    
    def _is_image_file(self, file_path):
        """Check if file is an image based on extension"""
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
        return os.path.splitext(file_path.lower())[1] in image_extensions
    
    def __del__(self):
        """Ensure cleanup happens even if object is garbage collected"""
        self.cleanup()

    def setup_shift_monitoring(self):
        """Set up keyboard monitoring for double Shift press."""
        try:
            logging.info("[DEBUG] Setting up shift monitoring...")
            
            # Unhook any existing hooks first to prevent duplicates
            try:
                keyboard.unhook_all()
                logging.debug("[DEBUG] Unhooked any existing keyboard hooks")
            except Exception as unhook_error:
                logging.error(f"[ERROR] Failed to unhook existing keyboard hooks: {unhook_error}")
            
            # Hook into keyboard events
            logging.debug("[DEBUG] Setting up shift press handler...")
            keyboard.on_press_key('shift', self.on_shift_press, suppress=False)
            
            logging.debug("[DEBUG] Setting up shift release handler...")
            keyboard.on_release_key('shift', self.on_shift_release, suppress=False)
            
            logging.info("[DEBUG] Shift monitoring setup complete")
            
        except Exception as e:
            logging.error(f"[CRITICAL] Error setting up shift monitoring: {e}", exc_info=True)
        finally:
            try:
                pythoncom.CoUninitialize()
            except:
                pass
            
    def on_shift_press(self, e):
        """Handle Shift key press event."""
        try:
            logging.info("[DEBUG] Shift key press event received")
            
            # Skip if disabled in settings
            if not self.settings.get("double_shift_capture", False):
                logging.info("[DEBUG] Double shift capture is disabled in settings")
                return
            
            current_time = time.time()
            logging.debug(f"[DEBUG] Current time: {current_time}")
            
            # Only count this press if shift was released since last press
            if not self.shift_released:
                logging.debug("[DEBUG] Shift was not released since last press, ignoring")
                return
                
            # Set flag to false until shift is released
            self.shift_released = False
            logging.debug("[DEBUG] Set shift_released to False")
            
            # Clean up old press times (older than threshold)
            prev_presses = len(self.shift_press_times)
            self.shift_press_times = [t for t in self.shift_press_times 
                                 if current_time - t < self.shift_press_threshold]
            
            logging.debug(f"[DEBUG] Press times before cleanup: {prev_presses}, after: {len(self.shift_press_times)}")
            
            # Add current press time
            self.shift_press_times.append(current_time)
            logging.debug(f"[DEBUG] Added press time. Total presses: {len(self.shift_press_times)}")
            
            # Check if we have at least 2 presses within threshold
            if len(self.shift_press_times) >= 2:
                # This is a double shift press
                time_since_first = current_time - self.shift_press_times[0]
                logging.info(f"[DEBUG] Double Shift detected! Time between presses: {time_since_first:.3f}s")
                
                # Clear press times to avoid triple detection
                self.shift_press_times = []
                logging.debug("[DEBUG] Cleared press times")
                
                # Ensure no modifier keys are stuck
                logging.debug("[DEBUG] Releasing modifier keys...")
                for key in ['ctrl', 'shift', 'alt']:
                    try:
                        keyboard.release(key)
                        logging.debug(f"[DEBUG] Released {key} key")
                    except Exception as key_error:
                        logging.error(f"[ERROR] Failed to release {key} key: {key_error}")
                
                # Handle double-shift screen capture
                self._handle_double_shift()
        except Exception as e:
            logging.error(f"[CRITICAL] Unhandled exception in on_shift_press: {e}", exc_info=True)
    
    def on_shift_release(self, e):
        """Handle Shift key release event."""
        try:
            self.shift_released = True
        except Exception as e:
            logging.error(f"Error in shift release handler: {e}")
    
    def _handle_double_shift(self):
        """Handle double-shift screen capture with improved reliability and error handling"""
        try:
            logging.info("Double-shift detected, capturing screen")
            
            # Check if capture frame is enabled in settings
            draw_frame = self.settings.get('draw_capture_frame', True)
            logging.info(f"Capture frame is {'enabled' if draw_frame else 'disabled'} in settings")
            
            try:
                # Get the screen capture
                qimage = self.screen_capture.capture_around_cursor()
                
                if qimage and not qimage.isNull():
                    # Add force refresh attribute to ensure the image is shown
                    qimage._force_refresh = True
                    
                    # Emit the captured image
                    self.image_captured.emit(qimage)
                    
                    # Show a brief notification if system_tray is available
                    try:
                        if hasattr(self, 'system_tray') and self.system_tray is not None:
                            self.system_tray.showMessage(
                                "Screen Captured",
                                "Screenshot captured successfully!",
                                QSystemTrayIcon.Information,
                                2000
                            )
                    except Exception as tray_error:
                        logging.error(f"Error showing system tray message: {tray_error}")
                    
                    # Log successful capture
                    logging.info(f"Captured image: {qimage.width()}x{qimage.height()} pixels, format: {qimage.format()}")
                    
                    # If there's a capture overlay, update it
                    if draw_frame and hasattr(self, 'capture_overlay') and self.capture_overlay:
                        try:
                            # Get screen that contains the cursor
                            cursor_pos = QGuiApplication.primaryScreen().cursor().pos()
                            screen = QGuiApplication.screenAt(cursor_pos)
                            if screen:
                                # Create a small rectangle around the cursor
                                rect = QRect(cursor_pos.x() - 50, cursor_pos.y() - 50, 100, 100)
                                self.create_capture_overlay(rect, False)
                        except Exception as e:
                            logging.error(f"Error creating capture frame: {e}")
                    
                    return True
                else:
                    error_msg = "Screen capture returned None or invalid image"
                    logging.error(error_msg)
                    
            except Exception as capture_error:
                error_msg = f"Error during screen capture: {capture_error}"
                logging.error(error_msg, exc_info=True)
            
            # Show error notification if system_tray is available
            try:
                if hasattr(self, 'system_tray') and self.system_tray is not None:
                    self.system_tray.showMessage(
                        "Capture Failed",
                        "Failed to capture screen. Check logs for details.",
                        QSystemTrayIcon.Critical,
                        3000
                    )
            except Exception as notify_error:
                logging.error(f"Error showing error notification: {notify_error}")
            
            return False
            
        except Exception as e:
            logging.error(f"Unexpected error in _handle_double_shift: {e}", exc_info=True)
            return False
                
        except Exception as e:
            logging.error(f"Error in _handle_double_shift: {e}", exc_info=True)
