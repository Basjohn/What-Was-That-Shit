import logging
import sys
import os
import time
from pathlib import Path
from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QMenu, QApplication, 
                           QAction, QFrame, QCheckBox, QMessageBox, QHBoxLayout, 
                           QPushButton, QWidgetAction, QSizePolicy)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QCursor, QColor, QPen, QKeyEvent
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QEvent, pyqtSignal, QTimer, QBuffer, QByteArray, QSettings
from PIL import Image, ImageOps
import io
import struct

# Import the history database
from history_db import HistoryDB

class ImageOverlay(QWidget):
    """A frameless, resizable overlay window that displays images copied to the clipboard."""
    
    # Signal to request opening settings
    settings_requested = pyqtSignal()
    
    # Signal emitted when navigation occurs
    navigation_occurred = pyqtSignal(str)  # 'next' or 'prev'
    
    def __init__(self, settings):
        # Set window flags for overlay behavior (no taskbar icon)
        super().__init__(None, 
                        Qt.Window |
                        Qt.FramelessWindowHint | 
                        Qt.WindowStaysOnTopHint |
                        Qt.Tool)  # Add Tool flag to prevent taskbar presence
        
        # Set window attributes for better performance
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_Hover, True)
        
        # Optimize for performance
        self.setAttribute(Qt.WA_AcceptTouchEvents, False)
        self.setAttribute(Qt.WA_AlwaysStackOnTop, True)
        self.setAttribute(Qt.WA_NoChildEventsForParent, True)
        self.setAttribute(Qt.WA_NoChildEventsFromChildren, True)
        
        # Enable high DPI scaling
        self.setAttribute(Qt.WA_AcceptTouchEvents, False)
        
        # Store settings first
        self.settings = settings
        self.settings_window = None  # Will be set by SettingsWindow
        
        # Track if we've loaded the initial image
        self._initial_image_loaded = False
        
        # Track clickthrough state
        self._last_clickthrough = False
        
        # Set up context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # Set initial clickthrough state
        self._update_clickthrough()
        
        # Image handling
        self.original_image = None
        self.pixmap = None
        
        # GIF animation support
        self.is_animated_gif = False
        self.gif_frames = []
        self.current_frame = 0
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._update_gif_frame)
        self.animation_playing = False
        self.frame_durations = []
        
        # State tracking
        self.dragging = False
        self.drag_position = QPoint(0, 0)
        self.resizing = False
        self.resize_edge = None
        self.resize_start_pos = None
        self.resize_start_geometry = None
        self.cursor_on_edge = False
        self.last_snapped_to = None
        self.edge_size = 12  # Make resize handles even larger
        self.current_opacity = self.settings.get("opacity", 77) / 100.0  # Track current opacity
        self.is_full_opacity = False  # Track if we're at full opacity
        
        # Navigation state
        self.current_file_path = None
        self.nav_history = []
        self.nav_history_index = -1
        
        # Initialize history database
        try:
            self.history_db = HistoryDB()  # This will automatically call _init_db()
            logging.info("History database initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize history database: {e}")
            # Create a dummy history_db to prevent None errors
            self.history_db = type('DummyDB', (), {'add_image': lambda *args, **kwargs: None,
                                               'get_current_image': lambda *args, **kwargs: None,
                                               'get_adjacent_image': lambda *args, **kwargs: None})()
        
        # Image cache for smoother navigation
        self.image_cache = {}
        self.cache_size = 3  # Current, previous, and next image
        self.current_cache_key = None
        
        # Navigation debounce
        self.last_nav_time = 0
        self.nav_debounce_ms = 300  # 300ms debounce for navigation
        
        # Track the current scaling factor (for mousewheel zoom)
        self.scale_factor = 1.0
        self.min_scale_factor = 0.2
        self.max_scale_factor = 3.0
        
        # Background and border now handled in paintEvent
        
        # Create image label (for displaying the image)
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: transparent; border: none;")
        
        # Set up context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._init_context_menu()  # Initialize the context menu
        
        # Set opacity from settings
        self.update_opacity(self.settings.get("opacity", 77))
        
        # Clickthrough is now handled in the event method
        
        # Load initial position and size from settings
        self._load_geometry_from_settings()
        
        # Set mouse tracking to handle resize cursors
        self.setMouseTracking(True)
        
        # Hide initially - will show when an image is set
        self.hide()
        
        # Install event filter to capture wheel events
        self.installEventFilter(self)

        self._current_image_path = None  # Add this attribute
    
    def _update_clickthrough(self):
        """Update the clickthrough state based on settings."""
        try:
            clickthrough = self.settings.get("clickthrough", False)
            self._last_clickthrough = clickthrough
            
            # Update window attributes for clickthrough
            self.setAttribute(Qt.WA_TransparentForMouseEvents, clickthrough)
            self.setAttribute(Qt.WA_ShowWithoutActivating, clickthrough)
            
            # On Windows, set additional window flags for proper clickthrough
            if sys.platform == 'win32' and hasattr(self, 'windowHandle') and self.windowHandle() is not None:
                try:
                    import ctypes
                    
                    # Constants for Windows API
                    GWL_EXSTYLE = -20
                    WS_EX_LAYERED = 0x00080000
                    WS_EX_TRANSPARENT = 0x00000020
                    
                    # Get window handle - ensure window is created first
                    if not self.testAttribute(Qt.WA_WState_Created):
                        self.createWinId()
                    
                    hwnd = int(self.windowHandle().winId())
                    
                    # Get current extended style
                    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    
                    if clickthrough:
                        # Add the transparent and layered styles
                        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
                    else:
                        # Remove the transparent and layered styles
                        style &= ~(WS_EX_LAYERED | WS_EX_TRANSPARENT)
                    
                    # Apply the new style
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
                    
                except Exception as e:
                    logging.error(f"Error setting Windows clickthrough: {e}", exc_info=True)
            
            # Update window flags for Qt
            self._update_clickthrough_state(clickthrough)
            
            # Force window update
            self.update()
            
            logging.debug(f"Clickthrough updated: {clickthrough}")
        except Exception as e:
            logging.error(f"Error in _update_clickthrough: {e}", exc_info=True)
    
    def event(self, event):
        """Custom event handling to support clickthrough while preserving functionality."""
        # Update clickthrough state if settings have changed
        if hasattr(self, '_last_clickthrough') and self._last_clickthrough != self.settings.get("clickthrough", False):
            self._update_clickthrough()
        
        clickthrough = self.settings.get("clickthrough", False)
        self._last_clickthrough = clickthrough
        
        # For mouse press events
        if event.type() == QEvent.MouseButtonPress:
            pos = event.pos()
            margin = self.edge_size
            rect = self.rect()
            
            # Check if we're near an edge for resizing
            near_edge = (pos.x() <= margin or 
                        pos.x() >= rect.width() - margin or
                        pos.y() <= margin or 
                        pos.y() >= rect.height() - margin)
            
            # If we're in clickthrough mode and not near an edge, ignore the event
            if clickthrough and not near_edge:
                event.ignore()
                return False
                
            # If we're near an edge, temporarily disable clickthrough
            if near_edge and clickthrough:
                self._update_clickthrough_state(False)
        
        # For mouse move events during drag/resize
        elif event.type() == QEvent.MouseMove and (self.dragging or self.resizing):
            pass  # Let the normal event handling take care of this
            
        # For mouse release events
        elif event.type() == QEvent.MouseButtonRelease:
            # Restore clickthrough state if needed
            if clickthrough and not (self.dragging or self.resizing):
                self._update_clickthrough_state(True)
        
        # Let the parent class handle the event
        return super().event(event)
        
    def _update_clickthrough_state(self, enable):
        """Helper method to update clickthrough state with proper window flags."""
        try:
            # Store current geometry and state
            geometry = self.geometry()
            was_visible = self.isVisible()
            
            # Update window flags
            flags = self.windowFlags()
            if enable:
                flags |= Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
            else:
                flags &= ~(Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
            
            # Apply new flags
            self.setWindowFlags(flags)
            
            # Restore geometry and visibility
            self.setGeometry(geometry)
            if was_visible:
                self.show()
                
            # Force update of window attributes
            self.setAttribute(Qt.WA_TransparentForMouseEvents, enable)
            
            # Update the settings to persist the state
            self.settings.set("clickthrough", enable)
            
            # Ensure the context menu is updated
            self._update_context_menu()
            
        except Exception as e:
            logging.error(f"Error updating clickthrough state: {e}", exc_info=True)
            
    def _show_context_menu(self, position):
        """Show the context menu at the given position."""
        try:
            menu = QMenu(self)
            
            # Add clickthrough toggle action
            clickthrough_action = QAction("Clickthrough", self, checkable=True)
            clickthrough_action.setChecked(self.settings.get("clickthrough", False))
            clickthrough_action.triggered.connect(self._toggle_clickthrough)
            menu.addAction(clickthrough_action)
            
            # Add separator
            menu.addSeparator()
            
            # Add settings action
            settings_action = QAction("Settings", self)
            settings_action.triggered.connect(self.settings_requested.emit)
            menu.addAction(settings_action)
            
            # Show the menu at the cursor position
            menu.exec_(self.mapToGlobal(position))
        except Exception as e:
            logging.error(f"Error showing context menu: {e}", exc_info=True)
        
    def _toggle_clickthrough(self):
        """Toggle clickthrough state and save settings immediately."""
        try:
            current_state = self.settings.get("clickthrough", False)
            new_state = not current_state
            
            # Update settings first
            self.settings.set("clickthrough", new_state)
            
            # Then update the window state
            self._update_clickthrough_state(new_state)
            
            # Force save settings to disk
            if hasattr(self.settings, 'save'):
                self.settings.save()
                
        except Exception as e:
            logging.error(f"Error toggling clickthrough: {e}", exc_info=True)
    
    def _update_context_menu(self):
        """Update the context menu state based on current settings."""
        # This method is kept for future use if needed
        pass

    def eventFilter(self, obj, event):
        """Filter events to ensure wheel events are captured."""
        if event.type() == QEvent.Wheel and obj is self:
            # Only process wheel events if scroll wheel resize is enabled
            if self.settings.get("scroll_wheel_resize", True):
                # Handle the wheel event for zooming
                self.wheelEvent(event)
                # Return True to indicate that the event was handled
                return True
        # For other events, call the parent class handler
        return super().eventFilter(obj, event)
    
    def wheelEvent(self, event):
        """Handle mouse wheel events for resizing the overlay."""
        # Only process wheel events if scroll wheel resize is enabled
        if not self.settings.get("scroll_wheel_resize", True):
            event.ignore()
            return
            
        try:
            # Get the current size
            current_width = self.width()
            current_height = self.height()
            
            # Calculate zoom factor based on wheel delta
            zoom_factor = 1.0 + (event.angleDelta().y() / 1200.0)
            
            # Calculate new scale factor within bounds
            new_scale = self.scale_factor * zoom_factor
            new_scale = max(self.min_scale_factor, min(new_scale, self.max_scale_factor))
            
            # Calculate scale change since last time
            scale_change = new_scale / (self.scale_factor or 1.0)
            
            # Only resize if change is significant enough
            if abs(scale_change - 1.0) > 0.01:
                # Save the old scale factor
                self.scale_factor = new_scale
                
                # Calculate new dimensions
                new_width = int(current_width * scale_change)
                new_height = int(current_height * scale_change)
                
                # Ensure minimum size
                min_size = 100
                new_width = max(min_size, new_width)
                new_height = max(min_size, new_height)
                
                # Resize the window
                self.resize(new_width, new_height)
                
                # Check if we need to snap after resize
                self._snap_to_edges()
                
                # Update the image display to fit the new size
                if self.pixmap and self.settings.get("resize_image_to_fit", False):
                    self._apply_sized_pixmap()
                
                # Log the resize
                logging.debug(f"Wheel resize to {new_width}x{new_height}, scale factor: {self.scale_factor:.2f}")
            
            # Accept the event to prevent further propagation
            event.accept()
            
        except Exception as e:
            logging.error(f"Error in wheel event: {e}", exc_info=True)
            event.ignore()
    
    def showEvent(self, event):
        """Handle show event to load the most recent image when the overlay is shown."""
        super().showEvent(event)
        
        # Only load the initial image once
        if not getattr(self, '_initial_image_loaded', False):
            self._load_most_recent_image()
    
    def _load_most_recent_image(self):
        """Load the most recent image from the history directory."""
        try:
            # Get the history folder from settings
            history_dir = Path(getattr(self.settings, 'history_folder', 'History'))
            if not history_dir.exists():
                logging.warning(f"History directory not found: {history_dir}")
                return
                
            # Find all image files in the history directory
            all_images = []
            for ext in ('*.png', '*.jpg', '*.jpeg', '*.gif'):
                all_images.extend(history_dir.rglob(ext))
                
            if not all_images:
                logging.warning("No images found in history directory")
                return
                
            # Sort by modification time (newest first)
            all_images.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Load the most recent image
            most_recent = all_images[0]
            image = Image.open(str(most_recent))
            self.set_image(image, file_path=str(most_recent))
            self._current_image_path = str(most_recent)
            
            # If it's a GIF, start playing it
            if str(most_recent).lower().endswith('.gif'):
                self._check_animated_gif()
                if self.is_animated_gif and not self.animation_playing:
                    self._play_animation()
                    
        except Exception as e:
            logging.error(f"Error loading most recent image: {e}", exc_info=True)
    
    def _load_geometry_from_settings(self):
        """Load position and size from settings."""
        width = self.settings.get("overlay_width", 500)
        height = self.settings.get("overlay_height", 400)
        
        # Try to load the saved position first
        x = self.settings.get("overlay_position_x", None)
        y = self.settings.get("overlay_position_y", None)
        
        # If no saved position, use the default values
        if x is None or y is None:
            x = self.settings.get("overlay_x", 100)
            y = self.settings.get("overlay_y", 100)
            logging.info("Using default overlay position")
        else:
            logging.info(f"Restored overlay position: {x}, {y}")
        
        # Load last snapped position if available
        self.last_snapped_to = self.settings.get("last_snapped_to", None)
        
        self.resize(width, height)
        self.move(x, y)
    
    def resizeEvent(self, event):
        """Handle resize events."""
        super().resizeEvent(event)
        
        # Update the displayed image to fit the new size with letterboxing/pillarboxing
        self._update_image_display()
        
        # Save size to settings
        self.settings.update({
            "overlay_width": self.width(),
            "overlay_height": self.height()
        })
    
    def paintEvent(self, event):
        """Custom paint event to draw background and border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        
        # Fill the background with dark grey
        background_color = QColor(30, 30, 33)
        painter.fillRect(self.rect(), background_color)
        
        # Determine border color based on theme
        theme = self.settings.get("theme", "dark") if hasattr(self, 'settings') else "dark"
        border_color = QColor(255, 255, 255) if theme == "dark" else QColor(0, 0, 0)
        
        # Draw border if enabled in settings
        if self.settings.get("show_border", True):
            pen = QPen(border_color, 2)
            pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        # Draw a solid 3px border
        border_rect = self.rect().adjusted(3, 3, -3, -3)  # Adjust border inwards
        pen = QPen(border_color, 3, Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRect(border_rect)

        # Adjust image label to fit within border
        if self.image_label:
            self.image_label.setGeometry(border_rect)

        super().paintEvent(event)

    def update_opacity(self, opacity_value):
        """Update window opacity based on settings."""
        # Store the normal opacity value
        self.current_opacity = opacity_value / 100.0
        
        # Only apply if not in full opacity mode
        if not self.is_full_opacity:
            self.setWindowOpacity(self.current_opacity)
    
    def set_image(self, pil_image, force=False, file_path=None):
        """Set the image to display in the overlay.
        
        Args:
            pil_image: The PIL image to display
            force: If True, bypass the auto-refresh check (used for manual refreshes)
            file_path: Optional path to the image file for history tracking
        """
        # Only check auto_refresh if this isn't a forced update
        if not force and not self.settings.get("auto_refresh", True):
            logging.info("Auto-refresh is disabled. Skipping image update.")
            return
            
        # Mark that we've loaded the initial image
        self._initial_image_loaded = True

        try:
            # Store the file path before doing anything else
            if file_path and os.path.exists(file_path):
                self.current_file_path = file_path
                self._update_navigation_history(file_path)
                logging.info(f"Set file path to: {file_path}")
            elif hasattr(pil_image, 'filename') and pil_image.filename and os.path.exists(pil_image.filename):
                self.current_file_path = pil_image.filename
                self._update_navigation_history(pil_image.filename)
                logging.info(f"Set file path from image: {pil_image.filename}")
            
            # Clear previous animation state
            if hasattr(self, 'animation_timer') and self.animation_timer.isActive():
                self.animation_timer.stop()
            
            # Clear animation data
            self.is_animated_gif = False
            self.animation_playing = False
            self.gif_frames = []
            self.frame_durations = []
            self.current_frame = 0
            
            # Clear previous image data to prevent memory leaks
            if hasattr(self, 'pixmap') and self.pixmap:
                self.pixmap = None
            
            # Store the new image
            self.original_image = pil_image
            
            # Check if this is a GIF
            is_gif = False
            if hasattr(pil_image, 'format') and pil_image.format:
                is_gif = pil_image.format.upper() == 'GIF'
                logging.info(f"Image format: {pil_image.format}, is_gif: {is_gif}")
            
            # If we have a file path and it's a GIF, try to load it directly
            if is_gif and hasattr(self, 'current_file_path') and self.current_file_path and self.current_file_path.lower().endswith('.gif'):
                logging.info("Attempting to load GIF directly from file...")
                if self._check_animated_gif():
                    logging.info("Successfully loaded animated GIF from file")
            # Otherwise, check if the image itself is an animated GIF
            elif is_gif:
                logging.info("Checking if image is an animated GIF...")
                self._check_animated_gif()
            
            # Update the display
            self._update_image_display()
            
            # Show the overlay if not visible
            if not self.isVisible():
                # If we have a saved snap position, try to restore relative positioning
                if hasattr(self, 'last_snapped_to') and self.last_snapped_to:
                    self._restore_snap_position()
                
                self.show()
                
                # Don't steal focus
                active_window = QApplication.activeWindow()
                if active_window and active_window != self:
                    active_window.activateWindow()

        except Exception as e:
            logging.error(f"Error setting image in overlay: {e}", exc_info=True)
    
    def set_qimage(self, qimage):
        """Set the image to display directly from a QImage."""
        try:
            if qimage and not qimage.isNull():
                # Store QImage as pixmap
                self.pixmap = QPixmap.fromImage(qimage)
                
                # Store as PIL image as well for consistency with other functions
                # Convert QImage to bytes
                byte_array = QByteArray()
                buffer = QBuffer(byte_array)
                buffer.open(QBuffer.WriteOnly)
                qimage.save(buffer, "PNG")
                buffer.close()
                
                # Convert bytes to PIL Image
                pil_image = Image.open(io.BytesIO(byte_array.data()))
                pil_image.format = "PNG"  # Set format explicitly
                self.original_image = pil_image
                
                # Reset animation if there was any
                self._stop_animation()
                self.is_animated_gif = False
                
                # Reset cached values to ensure full refresh
                self.scale_factor = 1.0
                
                # Apply the image to the display
                self._update_image_display()
                
                # Show window if hidden
                self.show()
                self.raise_()
                
                # Force garbage collection to help with switching between image types
                import gc
                gc.collect()
                
                return True
        except Exception as e:
            logging.error(f"Error setting QImage: {e}")
            return False
    
    def _restore_snap_position(self):
        """Restore snap position relative to monitor edges."""
        if not self.last_snapped_to:
            return
            
        try:
            snap_type, monitor_index = self.last_snapped_to
            
            # Get all screens
            screens = QApplication.screens()
            if not screens or monitor_index >= len(screens):
                return
                
            screen = screens[monitor_index]
            screen_geo = screen.geometry()
            
            # Current geometry
            width = self.width()
            height = self.height()
            
            # Calculate new position based on snap type
            if snap_type == "top-left":
                self.move(screen_geo.left(), screen_geo.top())
            elif snap_type == "top-right":
                self.move(screen_geo.right() - width, screen_geo.top())
            elif snap_type == "bottom-left":
                self.move(screen_geo.left(), screen_geo.bottom() - height)
            elif snap_type == "bottom-right":
                self.move(screen_geo.right() - width, screen_geo.bottom() - height)
            elif snap_type == "center":
                self.move(
                    screen_geo.left() + (screen_geo.width() - width) // 2,
                    screen_geo.top() + (screen_geo.height() - height) // 2
                )
        except Exception as e:
            logging.error(f"Error restoring snap position: {e}")
    
    def _update_image_display(self):
        """Update the displayed image with proper letterboxing/pillarboxing."""
        if not self.original_image:
            return
            
        try:
            # Calculate border adjustment
            border_width = 6  # 3px border on each side
            display_width = self.width() - border_width * 2
            display_height = self.height() - border_width * 2

            # For GIF animations, use the first frame for display when not playing
            display_image = self.original_image
            if self.is_animated_gif and self.gif_frames and not self.animation_playing:
                display_image = self.gif_frames[0]
            
            # Get the original image dimensions
            img_width, img_height = display_image.size
            
            # If resize_image_to_fit is true, create a QPixmap from the original image
            if self.settings.get("resize_image_to_fit", False):
                # Convert PIL Image to QPixmap
                if display_image.mode == 'RGBA':
                    qimg = QImage(display_image.tobytes(), img_width, img_height, QImage.Format_RGBA8888)
                else:
                    # Convert to RGBA
                    rgba_image = display_image.convert('RGBA')
                    qimg = QImage(rgba_image.tobytes(), img_width, img_height, QImage.Format_RGBA8888)
                
                self.pixmap = QPixmap.fromImage(qimg)
                
                # Apply with letterboxing/pillarboxing
                self._apply_sized_pixmap()
            else:
                # No resize - set window to image size
                self.resize(img_width, img_height)
                
                # Convert PIL Image to QPixmap
                if display_image.mode == 'RGBA':
                    qimg = QImage(display_image.tobytes(), img_width, img_height, QImage.Format_RGBA8888)
                else:
                    # Convert to RGBA
                    rgba_image = display_image.convert('RGBA')
                    qimg = QImage(rgba_image.tobytes(), img_width, img_height, QImage.Format_RGBA8888)
                
                self.pixmap = QPixmap.fromImage(qimg)
                self.image_label.setPixmap(self.pixmap)
        except Exception as e:
            logging.error(f"Error updating image display: {e}")
    
    def _check_animated_gif(self):
        """Check if the current image is an animated GIF and extract frames if it is."""
        try:
            # Reset animation state
            self.is_animated_gif = False
            self.animation_playing = False
            
            # Stop any running animation
            if hasattr(self, 'animation_timer') and self.animation_timer.isActive():
                self.animation_timer.stop()
            
            # Clear existing frames
            self.gif_frames = []
            self.frame_durations = []
            self.current_frame = 0
            
            # Initialize animation timer if it doesn't exist
            if not hasattr(self, 'animation_timer'):
                self.animation_timer = QTimer(self)
                self.animation_timer.timeout.connect(self._update_gif_frame)
            
            # Check if we have an image to work with
            if not self.original_image:
                logging.warning("No image available to check for animation")
                return False
            
            # Check if we have a file path to load the GIF directly
            if hasattr(self, 'current_file_path') and self.current_file_path and self.current_file_path.lower().endswith('.gif'):
                try:
                    # Try to load the GIF directly from file
                    with Image.open(self.current_file_path) as img:
                        # Check if it's actually animated
                        try:
                            # Try to seek to the second frame
                            img.seek(1)
                            is_animated = True
                            logging.info("GIF is animated (found multiple frames)")
                            # Load all frames
                            return self._load_gif_frames()
                        except EOFError:
                            logging.info("GIF has only one frame")
                            return False
                except Exception as e:
                    logging.error(f"Error checking GIF animation: {str(e)}", exc_info=True)
                    return False
            
            # Fallback to checking the image format
            img_format = getattr(self.original_image, 'format', '')
            if not img_format or img_format.upper() != 'GIF':
                return False
                
            # If we have raw data, use that
            if hasattr(self.original_image, '_raw_gif_data') and self.original_image._raw_gif_data:
                try:
                    buffer = io.BytesIO(self.original_image._raw_gif_data)
                    with Image.open(buffer) as img:
                        try:
                            img.seek(1)  # Try to seek to second frame
                            is_animated = True
                            logging.info("GIF is animated (found multiple frames in raw data)")
                            return self._load_gif_frames()
                        except EOFError:
                            logging.info("GIF has only one frame in raw data")
                            return False
                except Exception as e:
                    logging.error(f"Error checking raw GIF data: {str(e)}", exc_info=True)
            
            return False
                
        except Exception as e:
            logging.error(f"Error in _check_animated_gif: {str(e)}", exc_info=True)
            return False
    
    def _load_gif_frames(self):
        """Load all frames from the current GIF."""
        try:
            if not hasattr(self, 'original_image') or not self.original_image:
                logging.warning("No image available to load GIF frames from")
                return False
                
            # Clear any existing frames
            self.gif_frames = []
            self.frame_durations = []
            self.current_frame = 0
            
            # First try to load directly from file if we have a path
            if hasattr(self, 'current_file_path') and self.current_file_path and os.path.exists(self.current_file_path):
                try:
                    with Image.open(self.current_file_path) as gif:
                        frames = []
                        durations = []
                        frame_count = 0
                        
                        try:
                            while True:
                                gif.seek(frame_count)
                                # Convert to RGBA to ensure consistent format
                                frame = gif.convert('RGBA')
                                frames.append(frame.copy())
                                duration = gif.info.get('duration', 100)
                                durations.append(max(20, duration))
                                frame_count += 1
                        except EOFError:
                            pass
                            
                        if frame_count <= 1:
                            logging.warning("GIF has only one frame, not animated")
                            return False
                            
                        # Store the frames and durations
                        self.gif_frames = frames
                        self.frame_durations = durations
                        self.is_animated_gif = True
                        logging.info(f"Successfully loaded {frame_count} GIF frames from file")
                        
                        # Start playing automatically
                        self._play_animation()
                        return True
                        
                except Exception as e:
                    logging.error(f"Error loading GIF from file: {str(e)}", exc_info=True)
            
            # Fallback to using the image data we have
            try:
                # Create a fresh copy of the image to work with
                img = self.original_image
                
                # If we have raw GIF data, use that
                if hasattr(img, '_raw_gif_data') and img._raw_gif_data:
                    buffer = io.BytesIO(img._raw_gif_data)
                else:
                    # Otherwise, try to save as GIF
                    buffer = io.BytesIO()
                    img.save(buffer, format='GIF', save_all=True, append_images=[], loop=0)
                    buffer.seek(0)
                
                # Open the GIF using the buffer
                with Image.open(buffer) as gif:
                    # Extract all frames
                    frames = []
                    durations = []
                    frame_count = 0
                    
                    try:
                        while True:
                            try:
                                gif.seek(frame_count)
                                # Convert to RGBA to ensure consistent format
                                frame = gif.convert('RGBA')
                                frames.append(frame.copy())
                                duration = gif.info.get('duration', 100)  # Default to 100ms if no duration
                                durations.append(max(20, duration))  # Minimum 20ms to avoid too fast
                                frame_count += 1
                            except EOFError:
                                break
                        
                        if frame_count <= 1:
                            logging.warning("GIF has only one frame, not animated")
                            return False
                            
                        # Store the frames and durations
                        self.gif_frames = frames
                        self.frame_durations = durations
                        self.is_animated_gif = True
                        logging.info(f"Successfully loaded {frame_count} GIF frames from image data")
                        
                        # Start playing automatically
                        self._play_animation()
                        return True
                        
                    except Exception as e:
                        logging.error(f"Error extracting GIF frames: {str(e)}", exc_info=True)
                        return False
                        
            except Exception as e:
                logging.error(f"Error preparing GIF for frame extraction: {str(e)}", exc_info=True)
                return False
                
        except Exception as e:
            logging.error(f"Error in _load_gif_frames: {str(e)}", exc_info=True)
            return False
    
    def _update_gif_frame(self):
        """Update the display with the next frame of the animated GIF."""
        if not self.is_animated_gif or not self.gif_frames:
            self._stop_animation()
            return
        
        try:
            # Move to the next frame
            self.current_frame = (self.current_frame + 1) % len(self.gif_frames)
            
            # Set the current frame as the image to display
            current_img = self.gif_frames[self.current_frame]
            
            # Convert PIL Image to QPixmap
            if current_img.mode == 'RGBA':
                qimg = QImage(current_img.tobytes(), current_img.width, current_img.height, 
                            current_img.width * 4, QImage.Format_RGBA8888)
            else:
                # Convert to RGBA
                rgba_img = current_img.convert('RGBA')
                qimg = QImage(rgba_img.tobytes(), rgba_img.width, rgba_img.height,
                            rgba_img.width * 4, QImage.Format_RGBA8888)
            
            # Convert to QPixmap and update display
            self.pixmap = QPixmap.fromImage(qimg)
            self._apply_sized_pixmap()
            
            # Force update the display
            self.update()
            
            # Schedule next frame update
            if self.frame_durations and self.current_frame < len(self.frame_durations):
                frame_duration = self.frame_durations[self.current_frame]
                self.animation_timer.setInterval(frame_duration)
                
        except Exception as e:
            logging.error(f"Error updating GIF frame: {e}")
            self._stop_animation()
    
    def _play_animation(self):
        """Begin or resume playing the GIF animation."""
        # For any GIF, try to play it whether we've detected animation or not
        if getattr(self.original_image, 'format', '').upper() != 'GIF':
            return
            
        logging.info("Play button clicked for GIF")
        
        # If we haven't loaded animation frames yet or only have one frame, try to load them
        if not self.is_animated_gif or not self.gif_frames or len(self.gif_frames) <= 1:
            logging.info("Attempting to load animation frames directly from GIF data")
            try:
                # Use the raw data if available
                if hasattr(self.original_image, '_raw_gif_data') and self.original_image._raw_gif_data:
                    # Load from raw data
                    buffer = io.BytesIO(self.original_image._raw_gif_data)
                    gif = Image.open(buffer)
                    
                    # Try to count frames
                    frame_count = 0
                    frames = []
                    durations = []
                    
                    try:
                        # Load all frames
                        while True:
                            try:
                                gif.seek(frame_count)
                                frames.append(gif.copy())
                                duration = gif.info.get('duration', 100)
                                durations.append(max(20, duration))
                                frame_count += 1
                            except EOFError:
                                # End of animation
                                break
                        
                        logging.info(f"Loaded {frame_count} frames from GIF")
                        
                        if frame_count > 1:
                            # We have animation frames
                            self.gif_frames = frames
                            self.frame_durations = durations
                            self.is_animated_gif = True
                            self.original_image.is_animated = True
                        else:
                            logging.warning("GIF has only one frame, not animated")
                    except Exception as e:
                        logging.error(f"Error extracting frames: {e}")
                else:
                    # No raw data, try to create animation from the image
                    logging.info("No raw data, creating animation from the current image")
                    
                    # Save the image to a temporary buffer in GIF format
                    buffer = io.BytesIO()
                    self.original_image.save(buffer, format='GIF')
                    buffer.seek(0)
                    
                    # Try to load as animated GIF
                    gif = Image.open(buffer)
                    frame_count = 0
                    frames = []
                    durations = []
                    
                    try:
                        # Count frames
                        while True:
                            try:
                                gif.seek(frame_count)
                                frames.append(gif.copy())
                                duration = gif.info.get('duration', 100)
                                durations.append(max(20, duration))
                                frame_count += 1
                            except EOFError:
                                break
                        
                        logging.info(f"Created {frame_count} frames from GIF")
                        
                        if frame_count > 1:
                            # We have animation frames
                            self.gif_frames = frames
                            self.frame_durations = durations
                            self.is_animated_gif = True
                            self.original_image.is_animated = True
                        else:
                            # Can't animate
                            logging.warning("Couldn't create animation, using static frame")
                            self.gif_frames = [self.original_image]
                            self.frame_durations = [100]
                            self.is_animated_gif = True
                    except Exception as e:
                        logging.error(f"Error creating animation: {e}")
                        # Fall back to static image
                        self.gif_frames = [self.original_image]
                        self.frame_durations = [100]
                        self.is_animated_gif = False
            except Exception as e:
                logging.error(f"Error preparing animation: {e}")
                # Fall back to static image
                self.is_animated_gif = False
        
        # Start the animation if we have frames
        if self.is_animated_gif and self.gif_frames:
            if not self.animation_playing:
                self.animation_playing = True
                self.current_frame = 0
                
                # Start with the first frame's duration
                initial_duration = self.frame_durations[0] if self.frame_durations else 100
                self.animation_timer.setInterval(initial_duration)
                self.animation_timer.start()
                logging.info("Started GIF animation playback")
        else:
            logging.warning("Cannot play animation: no frames available")
    
    def _pause_animation(self):
        """Pause the GIF animation."""
        if self.animation_playing:
            self.animation_timer.stop()
            self.animation_playing = False
            logging.info("Paused GIF animation playback")
    
    def _stop_animation(self):
        """Stop the GIF animation completely and reset to first frame."""
        if hasattr(self, 'animation_timer') and self.animation_timer.isActive():
            self.animation_timer.stop()
        self.animation_playing = False
        self.current_frame = 0
        logging.info("Stopped GIF animation")
        
    def cleanup_resources(self):
        """Clean up any resources used by the overlay."""
        try:
            # Stop any running animations
            if hasattr(self, 'animation_timer') and self.animation_timer.isActive():
                self.animation_timer.stop()
                
            # Clear animation data
            if hasattr(self, 'is_animated_gif'):
                self.is_animated_gif = False
            if hasattr(self, 'animation_playing'):
                self.animation_playing = False
                
            # Clear frames and force garbage collection
            if hasattr(self, 'gif_frames'):
                self.gif_frames = []
            if hasattr(self, 'frame_durations'):
                self.frame_durations = []
                
            # Clear current frame
            if hasattr(self, 'current_frame'):
                self.current_frame = 0
                
            # Force garbage collection
            import gc
            gc.collect()
            
        except Exception as e:
            logging.error(f"Error during resource cleanup: {e}")
    
    def clear_display(self):
        """Clear the current display and release resources."""
        try:
            # Clear the current image
            if hasattr(self, 'original_image'):
                self.original_image = None
            if hasattr(self, 'pixmap'):
                self.pixmap = None
                
            # Clear the label
            if hasattr(self, 'image_label'):
                self.image_label.clear()
                
            # Force update the display
            self.update()
            QApplication.processEvents()
            
        except Exception as e:
            logging.error(f"Error clearing display: {e}")

    def _update_cursor(self, pos):
        """Update the cursor based on the mouse position within the window."""
        edge_size = 10
        width = self.width()
        height = self.height()
        
        # Check if near edges
        near_left = pos.x() <= edge_size
        near_right = pos.x() >= width - edge_size
        near_top = pos.y() <= edge_size
        near_bottom = pos.y() >= height - edge_size
        
        # Set cursor based on edge
        if near_left and near_top or near_right and near_bottom:
            self.setCursor(Qt.SizeFDiagCursor)
        elif near_left and near_bottom or near_right and near_top:
            self.setCursor(Qt.SizeBDiagCursor)
        elif near_left or near_right:
            self.setCursor(Qt.SizeHorCursor)
        elif near_top or near_bottom:
            self.setCursor(Qt.SizeVerCursor)
        else:
            # Show hand cursor when over the overlay but not near edges
            self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event):
        """Handle mouse press for dragging or resizing the window."""
        # Check if we should handle the event based on clickthrough settings
        if self.settings.get("clickthrough", False):
            # If clickthrough is enabled, we only handle events near the edges
            margin = self.edge_size
            pos = event.pos()
            rect = self.rect()
            
            # Check if we're near an edge
            near_edge = (pos.x() <= margin or 
                        pos.x() >= rect.width() - margin or
                        pos.y() <= margin or 
                        pos.y() >= rect.height() - margin)
            
            if near_edge:
                # Temporarily disable clickthrough for resizing/dragging
                self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                # Process the event normally
                event.accept()
            else:
                # Let the click pass through
                event.ignore()
                return
        
        if event.button() == Qt.LeftButton:
            cursor_pos = event.pos()
            
            # Check if we're near any edge for resizing
            on_left = cursor_pos.x() <= self.edge_size
            on_right = cursor_pos.x() >= self.width() - self.edge_size
            on_top = cursor_pos.y() <= self.edge_size
            on_bottom = cursor_pos.y() >= self.height() - self.edge_size
            
            # Determine resize direction
            if on_left and on_top:
                self.resize_edge = "top-left"
                self.setCursor(Qt.SizeFDiagCursor)
            elif on_right and on_top:
                self.resize_edge = "top-right"
                self.setCursor(Qt.SizeBDiagCursor)
            elif on_left and on_bottom:
                self.resize_edge = "bottom-left"
                self.setCursor(Qt.SizeBDiagCursor)
            elif on_right and on_bottom:
                self.resize_edge = "bottom-right"
                self.setCursor(Qt.SizeFDiagCursor)
            elif on_left:
                self.resize_edge = "left"
                self.setCursor(Qt.SizeHorCursor)
            elif on_right:
                self.resize_edge = "right"
                self.setCursor(Qt.SizeHorCursor)
            elif on_top:
                self.resize_edge = "top"
                self.setCursor(Qt.SizeVerCursor)
            elif on_bottom:
                self.resize_edge = "bottom"
                self.setCursor(Qt.SizeVerCursor)
            
            # Start resizing or dragging
            if self.resize_edge:
                self.resizing = True
                self.resize_start_pos = event.globalPos()
                self.resize_start_geometry = QRect(self.pos(), self.size())
                event.accept()
            else:
                # Only start dragging if we're not in clickthrough mode or if we're near an edge
                if not self.settings.get("clickthrough", False) or \
                   (on_left or on_right or on_top or on_bottom):
                    self.dragging = True
                    self.setCursor(Qt.ClosedHandCursor)  # Change to closed hand when dragging
                    self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                    event.accept()
                else:
                    # Let the click pass through
                    event.ignore()
                    return
        
        # For right-clicks or other buttons, let the parent handle them
        super().mousePressEvent(event)

    def _constrain_resize_geometry(self, geometry):
        """Constrain resize geometry to stay within screen bounds."""
        try:
            # Get the screen that contains the center of the window
            screen = QApplication.screenAt(geometry.center()) or QApplication.primaryScreen()
            if not screen:
                return geometry
                
            screen_rect = screen.geometry()
            
            # Ensure width and height are within bounds
            width = min(max(geometry.width(), 100), screen_rect.width())
            height = min(max(geometry.height(), 100), screen_rect.height())
            
            # Calculate new position to stay within screen bounds
            x = max(screen_rect.left(), min(geometry.x(), screen_rect.right() - width + 1))
            y = max(screen_rect.top(), min(geometry.y(), screen_rect.bottom() - height + 1))
            
            return QRect(x, y, width, height)
            
        except Exception as e:
            logging.error(f"Error in _constrain_resize_geometry: {e}", exc_info=True)
            return geometry
    
    def _handle_resize(self, global_pos):
        """Handle resizing based on which edge is being dragged."""
        if not self.resizing or not self.resize_edge or not self.resize_start_geometry:
            return
        
        # Disable updates temporarily to reduce flickering
        self.setUpdatesEnabled(False)
        
        try:
            delta = global_pos - self.resize_start_pos
            new_geometry = QRect(self.resize_start_geometry)
            
            # Apply resize based on edge
            if self.resize_edge == "top-left":
                new_geometry.setTopLeft(self.resize_start_geometry.topLeft() + delta)
            elif self.resize_edge == "top-right":
                new_geometry.setTopRight(self.resize_start_geometry.topRight() + delta)
            elif self.resize_edge == "bottom-left":
                new_geometry.setBottomLeft(self.resize_start_geometry.bottomLeft() + delta)
            elif self.resize_edge == "bottom-right":
                new_geometry.setBottomRight(self.resize_start_geometry.bottomRight() + delta)
            elif self.resize_edge == "left":
                new_geometry.setLeft(self.resize_start_geometry.left() + delta.x())
            elif self.resize_edge == "right":
                new_geometry.setRight(self.resize_start_geometry.right() + delta.x())
            elif self.resize_edge == "top":
                new_geometry.setTop(self.resize_start_geometry.top() + delta.y())
            elif self.resize_edge == "bottom":
                new_geometry.setBottom(self.resize_start_geometry.bottom() + delta.y())
            
            # Constrain the new geometry to stay within screen bounds
            constrained_geometry = self._constrain_resize_geometry(new_geometry)
            
            # Apply the constrained geometry
            self.setGeometry(constrained_geometry)
        finally:
            # Re-enable updates
            self.setUpdatesEnabled(True)
        
        # Save size to settings while resizing for smoother experience
        self.settings.set("overlay_width", self.width())
        self.settings.set("overlay_height", self.height())
        self.settings.set("overlay_position_x", self.pos().x())
        self.settings.set("overlay_position_y", self.pos().y())

    def _ensure_in_bounds(self):
        """Ensure the window is within screen bounds."""
        try:
            # Get current geometry
            geometry = self.geometry()
            
            # Get the screen that contains the center of the window
            screen = QApplication.screenAt(geometry.center()) or QApplication.primaryScreen()
            if not screen:
                return
                
            screen_rect = screen.geometry()
            
            # Calculate new position to stay within screen bounds
            new_x = max(screen_rect.left(), min(geometry.x(), screen_rect.right() - geometry.width() + 1))
            new_y = max(screen_rect.top(), min(geometry.y(), screen_rect.bottom() - geometry.height() + 1))
            
            # Move window if needed
            if new_x != geometry.x() or new_y != geometry.y():
                self.move(new_x, new_y)
                return True
                
        except Exception as e:
            logging.error(f"Error in _ensure_in_bounds: {e}", exc_info=True)
        return False

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging, resizing, or updating cursor."""
        # Initialize state tracking variables
        was_resizing = self.resizing
        was_dragging = self.dragging
        
        # If clickthrough is enabled and we're not resizing or dragging, handle cursor updates
        if self.settings.get("clickthrough", False) and not (was_resizing or was_dragging):
            # Only process cursor updates if we're near the edge
            pos = event.pos()
            margin = self.edge_size
            rect = self.rect()
            
            # Check if we're near an edge
            near_edge = (pos.x() <= margin or 
                        pos.x() >= rect.width() - margin or
                        pos.y() <= margin or 
                        pos.y() >= rect.height() - margin)
            
            if not near_edge:
                # If not near edge, ignore the event to allow clickthrough
                event.ignore()
                return
        
        # Handle resizing
        if event.buttons() & Qt.LeftButton and self.resizing:
            self._handle_resize(event.globalPos())
            event.accept()
            return
        
        # Handle dragging
        if event.buttons() & Qt.LeftButton and self.dragging:
            # Calculate new position
            new_pos = event.globalPos() - self.drag_position
            
            # Move the window
            self.move(new_pos)
            
            # Update settings with new position
            self.settings.set("overlay_position_x", new_pos.x())
            self.settings.set("overlay_position_y", new_pos.y())
            
            # Snap to edges if enabled, otherwise ensure we're in bounds
            if self.settings.get("snap_to_edges", True):
                if not self._snap_to_edges():
                    self._ensure_in_bounds()
            else:
                self._ensure_in_bounds()
                
            event.accept()
            return
        
        # Save settings if we were resizing or dragging
        if was_resizing:
            self.settings.set("overlay_width", self.width())
            self.settings.set("overlay_height", self.height())
        elif was_dragging:
            pos = self.pos()
            self.settings.set("overlay_position_x", pos.x())
            self.settings.set("overlay_position_y", pos.y())
            if self.settings.get("snap_to_edges", True):
                self._snap_to_edges()
        
        # Update cursor based on new position
        self._update_cursor(event.pos())
        # Restore open hand cursor if not near edges
        if not (self.dragging or self.resizing):
            self.setCursor(Qt.OpenHandCursor)
        
        # Only accept the event if we were resizing or dragging
        # Otherwise, let it pass through if clickthrough is enabled
        if was_resizing or was_dragging or not self.settings.get("clickthrough", False):
            event.accept()
        else:
            event.ignore()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release after dragging or resizing."""
        if self.resizing:
            self.resizing = False
            self.resize_edge = None
            self.unsetCursor()
            
            # Save final size to settings
            self.settings.set("overlay_width", self.width())
            self.settings.set("overlay_height", self.height())
            
            # Snap to edges if enabled
            if self.settings.get("snap_to_edges", True):
                self._snap_to_edges()
                
            event.accept()
        elif self.dragging:
            self.dragging = False
            self.unsetCursor()
            
            # Save final position to settings
            pos = self.pos()
            self.settings.set("overlay_position_x", pos.x())
            self.settings.set("overlay_position_y", pos.y())
            
            # Snap to edges if enabled
            if self.settings.get("snap_to_edges", True):
                self._snap_to_edges()
                
            event.accept()
        else:
            # Reset cursor and update based on new position
            self.unsetCursor()
            self._update_cursor(event.pos())
            
            # Handle clickthrough for mouse release
            if not self.settings.get("clickthrough", False):
                event.accept()
            else:
                event.ignore()
                
            super().mouseReleaseEvent(event)
    
    def keyPressEvent(self, event):
        """Handle key press events."""
        try:
            # Close on Escape key
            if event.key() == Qt.Key_Escape:
                self.hide()
                return
            # Toggle GIF playback with down arrow
            elif event.key() == Qt.Key_Down and self.isVisible() and hasattr(self, 'original_image') and getattr(self.original_image, 'format', '').upper() == 'GIF':
                if self.animation_playing:
                    self._pause_animation()
                else:
                    self._play_animation()
                return
            # Navigation with arrow keys
            elif event.key() == Qt.Key_Left:
                self.navigate_history('prev')
                return
            elif event.key() == Qt.Key_Right:
                self.navigate_history('next')
                return
            # Toggle always on top on T key
            elif event.key() == Qt.Key_T:
                current = self.windowFlags() & Qt.WindowStaysOnTopHint
                self.setWindowFlag(Qt.WindowStaysOnTopHint, not current)
                self.show()
            # Toggle full opacity on F key
            elif event.key() == Qt.Key_F:
                self._toggle_opacity()
            # Refresh image on R key
            elif event.key() == Qt.Key_R:
                self.refresh_image()
            # Open settings on S key
            elif event.key() == Qt.Key_S:
                self._open_settings()
            # Reset size on D key
            elif event.key() == Qt.Key_D:
                self._reset_size()
            else:
                super().keyPressEvent(event)
                
        except Exception as e:
            logging.error(f"Error in keyPressEvent: {e}", exc_info=True)
    
    def navigate_history(self, direction):
        """Navigate through history images using file system."""
        try:
            # Stop any currently playing animation
            if hasattr(self, 'animation_timer') and self.animation_timer.isActive():
                self.animation_timer.stop()
                self.animation_playing = False

            current_path = getattr(self, '_current_image_path', None) or getattr(self, 'current_file_path', None)
            
            # Get the history folder from settings
            if hasattr(self, 'app_instance') and hasattr(self.app_instance, 'settings'):
                history_dir = Path(self.app_instance.settings.history_folder)
            else:
                history_dir = Path('History')  # Fallback default
                
            if not history_dir.exists():
                logging.warning(f"History directory not found: {history_dir}")
                return

            # Find all image files in the history directory
            all_images = []
            for ext in ('*.png', '*.jpg', '*.jpeg', '*.gif'):
                all_images.extend(history_dir.rglob(ext))
                
            if not all_images:
                logging.warning("No images found in history directory")
                return
                
            # Sort by filename (which includes the timestamp)
            all_images.sort(key=lambda x: x.name)
            
            if not current_path:
                # If no current image, load the first one
                next_path = all_images[0]
            else:
                try:
                    current_path = Path(current_path)
                    if not current_path.exists():
                        logging.warning(f"Current image not found: {current_path}")
                        current_path = None
                except Exception as e:
                    logging.error(f"Error with current path: {e}")
                    current_path = None
            
            if not current_path:
                # If we still don't have a valid current path, use the first image
                next_path = all_images[0]
            else:
                # Find current image in the list
                try:
                    current_idx = next((i for i, p in enumerate(all_images) 
                                      if p.name == current_path.name), -1)
                    
                    if current_idx == -1:
                        logging.warning(f"Current image not found in history: {current_path.name}")
                        next_path = all_images[0]  # Fall back to first image
                    else:
                        # Get next or previous image
                        if direction == 'prev':
                            next_idx = max(0, current_idx - 1)
                        else:  # 'next'
                            next_idx = min(len(all_images) - 1, current_idx + 1)
                        
                        # If we're at the boundary, wrap around
                        if next_idx == current_idx:
                            next_idx = 0 if direction == 'next' else len(all_images) - 1
                            
                        next_path = all_images[next_idx]
                        
                except Exception as e:
                    logging.error(f"Error during navigation: {e}", exc_info=True)
                    return

            # Load and display the image
            try:
                # Clear any existing animation state
                self.is_animated_gif = False
                self.gif_frames = []
                self.frame_durations = []
                self.current_frame = 0
                
                # Open the image and set it
                image = Image.open(str(next_path))
                self.set_image(image, file_path=str(next_path))
                self._current_image_path = str(next_path)
                
                # Force check for animated GIF and start playing if it is one
                if str(next_path).lower().endswith('.gif'):
                    self._check_animated_gif()
                    if self.is_animated_gif and not self.animation_playing:
                        self._play_animation()
                        
            except Exception as e:
                logging.error(f"Failed to load image during navigation: {e}", exc_info=True)

        except Exception as e:
            logging.error(f"Error in navigation: {e}", exc_info=True)
    
    def _navigate_to_adjacent(self, direction):
        """Navigate to the next or previous image in history.
        
        Args:
            direction: 'next' or 'prev'
        """
        if not self.history_db or not self.current_file_path:
            return
            
        try:
            # First check if we have the requested image in cache
            cache_key = f"{direction}:{self.current_file_path}"
            if cache_key in self.image_cache:
                cached_image = self.image_cache[cache_key]
                if hasattr(cached_image, '_raw_gif_data'):
                    # For GIFs, we need to re-create the buffer
                    gif_buffer = io.BytesIO(cached_image._raw_gif_data)
                    cached_image = Image.open(gif_buffer)
                    cached_image._raw_gif_data = gif_buffer.getvalue()
                
                # Use the cached image
                self.set_image(cached_image, file_path=self.current_file_path)
                logging.info(f"Using cached {direction} image: {self.current_file_path}")
                
                # Update cache key
                old_cache_key = f"current:{self.current_file_path}"
                if old_cache_key in self.image_cache:
                    del self.image_cache[old_cache_key]
                self.image_cache[old_cache_key] = cached_image
                self.current_cache_key = old_cache_key
                
                # Preload adjacent images in the background
                QTimer.singleShot(100, lambda: self._preload_adjacent_images(self.current_file_path))
                return
                
            # If not in cache, proceed with normal navigation
            conn = self.history_db._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM images WHERE file_path = ?', (str(self.current_file_path),))
            current = cursor.fetchone()
            
            if not current:
                logging.warning("Current image not found in history database")
                return
                
            current_id = current['id']
            
            # Get adjacent image
            adjacent = self.history_db.get_adjacent_image(current_id, direction)
            if not adjacent:
                logging.info(f"No {direction} image found")
                return
                
            # Load and display the adjacent image
            file_path = Path(adjacent['file_path'])
            if not file_path.exists():
                logging.error(f"Image file not found: {file_path}")
                return
                
            try:
                # Check if we have this image in cache
                cached_key = f"current:{file_path}"
                if cached_key in self.image_cache:
                    image = self.image_cache[cached_key]
                    if hasattr(image, '_raw_gif_data'):
                        gif_buffer = io.BytesIO(image._raw_gif_data)
                        image = Image.open(gif_buffer)
                        image._raw_gif_data = gif_buffer.getvalue()
                else:
                    # For GIFs, we need to handle them specially to preserve animation
                    if file_path.suffix.lower() == '.gif':
                        with open(file_path, 'rb') as f:
                            gif_data = f.read()
                        gif_buffer = io.BytesIO(gif_data)
                        image = Image.open(gif_buffer)
                        image._raw_gif_data = gif_data
                    else:
                        image = Image.open(file_path)
                
                # Set the image in the overlay
                self.set_image(image, file_path=file_path)
                logging.info(f"Navigated to {direction} image: {file_path}")
                
                # Update navigation history
                if direction == 'next':
                    if self.nav_history and self.nav_history_index < len(self.nav_history) - 1:
                        self.nav_history = self.nav_history[:self.nav_history_index + 1]
                    self.nav_history_index += 1
                    self.nav_history.append(str(file_path))
                else:  # prev
                    if self.nav_history_index > 0:
                        self.nav_history_index -= 1
                
                # Preload adjacent images in the background
                QTimer.singleShot(100, lambda: self._preload_adjacent_images(str(file_path)))
                
            except Exception as load_error:
                logging.error(f"Error loading {direction} image: {load_error}", exc_info=True)
                return
        finally:
            if 'conn' in locals():
                conn.close()
            
    def _clear_cache(self):
        """Clear the image cache and free up memory."""
        for key in list(self.image_cache.keys()):
            if key != self.current_cache_key and key in self.image_cache:
                del self.image_cache[key]
    
    def _preload_adjacent_images(self, file_path):
        """Preload the previous and next images for smoother navigation."""
        if not file_path or not self.history_db:
            return
            
        try:
            # Get current image ID
            cursor = self.history_db._get_connection().cursor()
            cursor.execute('SELECT id FROM images WHERE file_path = ?', (str(file_path),))
            current = cursor.fetchone()
            
            if not current:
                return
                
            current_id = current['id']
            
            # Preload next and previous images
            for direction in ['next', 'prev']:
                try:
                    adjacent = self.history_db.get_adjacent_image(current_id, direction)
                    if not adjacent or not os.path.exists(adjacent['file_path']):
                        continue
                        
                    cache_key = f"{direction}:{adjacent['file_path']}"
                    if cache_key not in self.image_cache:
                        try:
                            if adjacent['file_path'].lower().endswith('.gif'):
                                with open(adjacent['file_path'], 'rb') as f:
                                    gif_data = f.read()
                                gif_buffer = io.BytesIO(gif_data)
                                image = Image.open(gif_buffer)
                                image._raw_gif_data = gif_data
                            else:
                                image = Image.open(adjacent['file_path'])
                            
                            # Store in cache
                            self.image_cache[cache_key] = image
                            
                            # Enforce cache size limit
                            if len(self.image_cache) > self.cache_size:
                                self._clear_cache()
                                
                        except Exception as e:
                            logging.error(f"Error preloading {direction} image: {e}")
                except Exception as e:
                    logging.error(f"Error getting {direction} image for preloading: {e}")
                    
        except Exception as e:
            logging.error(f"Error in _preload_adjacent_images: {e}")
    
    def _update_navigation_history(self, file_path):
        """Update the navigation history with the current file."""
        if not self.history_db or not file_path:
            return
            
        try:
            # Add the image to the database
            img = Image.open(file_path)
            img_id = self.history_db.add_image(
                file_path=file_path,
                is_temporary='_T' in os.path.basename(file_path),
                width=img.width,
                height=img.height
            )
            
            if img_id:
                # Set as current position
                self.history_db.set_current_image(img_id)
                
                # Update in-memory history
                if file_path in self.nav_history:
                    self.nav_history.remove(file_path)
                self.nav_history.append(file_path)
                self.nav_history_index = len(self.nav_history) - 1
                
                # Preload adjacent images in a separate thread to avoid UI lag
                QTimer.singleShot(100, lambda: self._preload_adjacent_images(file_path))
                
        except Exception as e:
            logging.error(f"Error updating navigation history: {e}")
            
    def mouseDoubleClickEvent(self, event):
        """Handle double-click to toggle opacity."""
        if event.button() == Qt.LeftButton:
            self._toggle_opacity()
            event.accept()
        super().mouseDoubleClickEvent(event)
    
    def _toggle_opacity(self):
        """Toggle between user-set opacity and 100%."""
        if self.is_full_opacity:
            # Return to user setting
            self.current_opacity = self.settings.get("opacity", 77) / 100.0
            self.is_full_opacity = False
        else:
            # Go to full opacity
            self.current_opacity = 1.0
            self.is_full_opacity = True
            
        # Apply opacity
        self.setWindowOpacity(self.current_opacity)
    
    def _init_history_db(self):
        """Initialize the history database connection."""
        try:
            self.history_db = HistoryDB()
            logging.info("History database initialized")
        except Exception as e:
            logging.error(f"Failed to initialize history database: {e}")
            self.history_db = None
            
    def navigate(self, direction):
        """Navigate to the next or previous image.
        
        Args:
            direction: 'next' or 'prev'
        """
        try:
            # Update navigation buttons after navigation
            self._update_nav_buttons_style()
            # First try using the history database if available
            if hasattr(self, 'history_db') and self.history_db and self.current_file_path:
                try:
                    # Get current image ID
                    current_id = self.history_db.get_current_image()
                    if current_id:
                        # Get next/previous image
                        adjacent = self.history_db.get_adjacent_image(current_id['id'], direction)
                        if adjacent and os.path.exists(adjacent['file_path']):
                            # Load and display the image
                            img = Image.open(adjacent['file_path'])
                            self.set_image(img, file_path=adjacent['file_path'])
                            self.history_db.set_current_image(adjacent['id'])
                            return
                except Exception as e:
                    logging.warning(f"Error navigating with history_db: {e}")
            
            # Fall back to file system based navigation
            self.navigate_history(direction)
            
        except Exception as e:
            logging.error(f"Error in navigation: {e}", exc_info=True)
    
    def can_go_back(self):
        """Check if there's a previous image to navigate to."""
        if not self.history_db or not self.current_file_path:
            return False
        try:
            current_id = self.history_db.get_current_image()
            if not current_id:
                return False
            return bool(self.history_db.get_adjacent_image(current_id['id'], 'prev'))
        except Exception as e:
            logging.error(f"Error checking if can go back: {e}")
            return False
    
    def can_go_forward(self):
        """Check if there's a next image to navigate to."""
        if not self.history_db or not self.current_file_path:
            return False
        try:
            current_id = self.history_db.get_current_image()
            if not current_id:
                return False
            return bool(self.history_db.get_adjacent_image(current_id['id'], 'next'))
        except Exception as e:
            logging.error(f"Error checking if can go forward: {e}")
            return False
    
    def _open_in_folder(self):
        """Open the current image's location in File Explorer with the file selected."""
        if self.current_file_path and os.path.isfile(self.current_file_path):
            try:
                # Use os.startfile to open the folder and select the file
                import subprocess
                # This command works on Windows to open the folder and select the file
                subprocess.Popen(f'explorer /select,"{self.current_file_path}"')
            except Exception as e:
                logging.error(f"Error opening file location: {e}")
    
    def _update_nav_buttons_style(self):
        """Update the navigation buttons style based on navigation availability."""
        if hasattr(self, 'nav_prev_btn') and hasattr(self, 'nav_next_btn'):
            can_go_prev = self.can_go_back()
            can_go_next = self.can_go_forward()
            
            # Update previous button
            self.nav_prev_btn.setProperty("canNavigate", can_go_prev)
            self.nav_prev_btn.setEnabled(can_go_prev)
            
            # Update next button
            self.nav_next_btn.setProperty("canNavigate", can_go_next)
            self.nav_next_btn.setEnabled(can_go_next)
            
            # Force style update
            self.nav_prev_btn.style().unpolish(self.nav_prev_btn)
            self.nav_prev_btn.style().polish(self.nav_prev_btn)
            self.nav_next_btn.style().unpolish(self.nav_next_btn)
            self.nav_next_btn.style().polish(self.nav_next_btn)
    
    def _init_context_menu(self):
        """Initialize the context menu components."""
        # Create the navigation widget
        nav_widget = QWidget()
        nav_widget.setObjectName("navWidget")
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(2, 2, 2, 2)
        nav_layout.setSpacing(6)
        
        # Add navigation label
        self.nav_label = QLabel("NAVI")
        self.nav_label.setObjectName("navLabel")
        nav_layout.addWidget(self.nav_label)
        
        # Add separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        nav_layout.addWidget(sep)
        
        # Navigation buttons
        self.nav_prev_btn = QPushButton("<")
        self.nav_prev_btn.setObjectName("navPrevBtn")
        self.nav_prev_btn.setFixedSize(28, 22)
        self.nav_prev_btn.clicked.connect(lambda: self.navigate('prev'))
        nav_layout.addWidget(self.nav_prev_btn)
        
        self.nav_next_btn = QPushButton(">")
        self.nav_next_btn.setObjectName("navNextBtn")
        self.nav_next_btn.setFixedSize(28, 22)
        self.nav_next_btn.clicked.connect(lambda: self.navigate('next'))
        nav_layout.addWidget(self.nav_next_btn)
        
        # Create the main menu
        self.context_menu = QMenu(self)
        
        # Add navigation widget to menu
        nav_action = QWidgetAction(self.context_menu)
        nav_action.setDefaultWidget(nav_widget)
        self.context_menu.addAction(nav_action)
        self.context_menu.addSeparator()
        
        # Create menu actions
        self.open_folder_action = QAction("Open in Folder", self)
        self.open_folder_action.triggered.connect(self._open_in_folder)
        
        self.refresh_action = QAction("Refresh Image", self)
        self.refresh_action.triggered.connect(self.refresh_image)
        
        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self._open_settings)
        
        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self._exit_application)
        
        # Add common actions to menu
        self.context_menu.addAction(self.open_folder_action)
        self.context_menu.addAction(self.refresh_action)
        
        # Add GIF control action (will be shown/hidden as needed)
        self.gif_control_action = QAction("", self)  # Will be updated in _update_gif_control
        self.gif_control_action.setVisible(False)
        self.context_menu.addAction(self.gif_control_action)
        
        # Add other common actions
        self.opacity_action = QAction("Toggle Full Opacity", self)
        self.opacity_action.triggered.connect(self._toggle_opacity)
        self.context_menu.addAction(self.opacity_action)
        
        self.reset_action = QAction("Reset Size", self)
        self.reset_action.triggered.connect(self._reset_size)
        self.context_menu.addAction(self.reset_action)
        
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.settings_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.exit_action)
        
        # Set menu style
        self._update_menu_style()
    
    def _update_gif_control(self):
        """Update the GIF control action based on current state."""
        is_gif = getattr(self.original_image, 'format', '').upper() == 'GIF'
        if is_gif:
            if self.animation_playing:
                self.gif_control_action.setText("Stop GIF  ▼")
                self.gif_control_action.triggered.disconnect()
                self.gif_control_action.triggered.connect(self._pause_animation)
            else:
                self.gif_control_action.setText("Start GIF  ▼")
                self.gif_control_action.triggered.disconnect()
                self.gif_control_action.triggered.connect(self._play_animation)
        self.gif_control_action.setVisible(is_gif)
    
    def _update_menu_style(self):
        """Update the menu style based on current theme."""
        is_dark_theme = self.settings.get("theme", "dark").lower() == "dark"
        
        if is_dark_theme:
            menu_style = """
                QMenu {
                    background-color: #2d2d2d;
                    color: white;
                    border: 1px solid #6e6e6e;
                    padding: 2px;
                }
                QMenu::item {
                    padding: 5px 25px 5px 20px;
                    background-color: transparent;
                }
                QMenu::item:selected {
                    background-color: #3e3e3e;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #555555;
                    margin: 2px 5px;
                }
                QMenu::item:disabled {
                    color: #6e6e6e;
                }
                #navLabel {
                    font-weight: 500;
                    font-size: 10pt;
                    padding: 2px 6px;
                    color: #ffffff;
                    background: transparent;
                    border: 1px solid #6e6e6e;
                    border-radius: 3px;
                    margin-right: 4px;
                }
                QPushButton {
                    border: none;
                    border-radius: 3px;
                    padding: 0;
                    min-width: 20px;
                    max-width: 20px;
                    height: 20px;
                    background: #2d2d2d;
                    color: #555555;
                    font-weight: 500;
                    font-size: 9pt;
                    margin: 0;
                }
                QPushButton[canNavigate="true"] {
                    color: #ffffff;
                }
                QPushButton:disabled {
                    color: #555555;
                    background: #2d2d2d;
                }
                QPushButton[canNavigate="true"]:hover:!disabled {
                    background: #3c3c3c;
                    color: #ffffff;
                }
                QWidget#navWidget {
                    background-color: #252526;
                    border: none;
                    border-bottom: 1px solid #3f3f46;
                    padding: 2px 6px;
                }"""
        else:
            menu_style = """
                QMenu {
                    background-color: #f5f5f5;
                    color: black;
                    border: 1px solid #6e6e6e;
                    padding: 2px;
                }
                QMenu::item {
                    padding: 5px 25px 5px 20px;
                }
                QMenu::item:selected {
                    background-color: #e6e6e6;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #d6d6d6;
                    margin: 2px 5px;
                }
                QMenu::item:disabled {
                    color: #a0a0a0;
                }
                #navLabel {
                    font-weight: 500;
                    font-size: 10pt;
                    padding: 2px 6px;
                    color: #1e1e1e;
                    background: transparent;
                    border: 1px solid #d4d4d4;
                    border-radius: 3px;
                    margin-right: 4px;
                }
                QPushButton {
                    border: 1px solid #d4d4d4;
                    border-radius: 3px;
                    padding: 0;
                    min-width: 20px;
                    max-width: 20px;
                    height: 20px;
                    background: #ffffff;
                    color: #1e1e1e;
                    font-weight: 500;
                    font-size: 9pt;
                    margin: 0;
                }
                QPushButton:disabled {
                    color: #b0b0b0;
                    background: #f0f0f0;
                    border-color: #e0e0e0;
                }
                QPushButton:hover:!disabled {
                    background: #e8e8e8;
                }
                QWidget#navWidget {
                    background-color: #f3f3f3;
                    border: none;
                    border-bottom: 1px solid #d6d6d6;
                    padding: 2px 6px;
                }"""
        
        self.context_menu.setStyleSheet(menu_style)
    
    def _show_context_menu(self, position):
        """Show the right-click context menu."""
        # Update navigation state
        can_go_prev = self.can_go_back()
        can_go_next = self.can_go_forward()
        
        # Update previous button state
        self.nav_prev_btn.setEnabled(can_go_prev)
        self.nav_prev_btn.setProperty("canNavigate", str(can_go_prev).lower())
        self.nav_prev_btn.style().unpolish(self.nav_prev_btn)
        self.nav_prev_btn.style().polish(self.nav_prev_btn)
        
        # Update next button state
        self.nav_next_btn.setEnabled(can_go_next)
        self.nav_next_btn.setProperty("canNavigate", str(can_go_next).lower())
        self.nav_next_btn.style().unpolish(self.nav_next_btn)
        self.nav_next_btn.style().polish(self.nav_next_btn)
        
        # Force update the navigation label
        self.nav_label.setText("NAVI")
        
        # Update menu items
        self.open_folder_action.setEnabled(bool(self.current_file_path and os.path.isfile(self.current_file_path)))
        
        # Update GIF control if needed
        self._update_gif_control()
        
        # Update opacity action text
        self.opacity_action.setText("Toggle Full Opacity")
        
        # Update styles
        self._update_menu_style()
        
        # Force a style update for the navigation widget
        self.context_menu.style().unpolish(self.context_menu)
        self.context_menu.style().polish(self.context_menu)
        
        # Show the menu
        self.context_menu.exec_(self.mapToGlobal(position))
    
    def _exit_application(self):
        """Exit the application."""
        if hasattr(self, 'app_instance') and hasattr(self.app_instance, 'exit_app'):
            self.app_instance.exit_app()
        else:
            QApplication.quit()
    
    def _reset_size(self):
        """Reset overlay to default size."""
        self.resize(500, 400)
        # Center on the current screen
        screen = QApplication.screenAt(self.mapToGlobal(QPoint(0, 0)))
        if screen:
            center_point = screen.geometry().center()
            self.move(center_point.x() - 250, center_point.y() - 200)
    
    def _toggle_auto_refresh(self):
        """Toggle auto-refresh setting and update the settings."""
        current = self.settings.get("auto_refresh", True)
        new_value = not current
        self.settings.set("auto_refresh", new_value)
        logging.info(f"Auto-Refresh {'enabled' if new_value else 'disabled'}")
        
        # Update the settings window UI if it exists
        if hasattr(self, 'settings_window') and self.settings_window:
            try:
                # Directly access the checkbox through the settings window reference
                if hasattr(self.settings_window, 'auto_refresh_checkbox'):
                    # Block signals to prevent recursive updates
                    self.settings_window.auto_refresh_checkbox.blockSignals(True)
                    self.settings_window.auto_refresh_checkbox.setChecked(new_value)
                    self.settings_window.auto_refresh_checkbox.blockSignals(False)
                else:
                    # Fallback to find by object name if direct attribute access fails
                    for widget in self.settings_window.findChildren(QCheckBox):
                        if widget.objectName() == "autoRefreshCheckbox":
                            widget.blockSignals(True)
                            widget.setChecked(new_value)
                            widget.blockSignals(False)
                            break
                        break
            except Exception as e:
                logging.error(f"Error updating settings window UI: {e}")
    
    def _open_settings(self):
        """Signal to open settings window."""
        self.settings_requested.emit()
    
    def _set_always_on_top(self, checked):
        """Set the always-on-top state from menu action."""
        self.settings.set("always_on_top", checked)
        
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags((flags | Qt.WindowStaysOnTopHint) | Qt.FramelessWindowHint | Qt.Tool)
        else:
            self.setWindowFlags((flags & ~Qt.WindowStaysOnTopHint) | Qt.FramelessWindowHint | Qt.Tool)
        
        # Preserve mouse tracking after changing flags
        self.setMouseTracking(True)
        self.show()
    
    def refresh_image(self):
        """Refresh the current image display."""
        if self.original_image:
            # If we have a file path, reload from disk to get any changes
            if self.current_file_path and os.path.exists(self.current_file_path):
                try:
                    img = Image.open(self.current_file_path)
                    self.original_image = img
                    # Update the display
                    self._update_image_display()
                    return
                except Exception as e:
                    logging.error(f"Error refreshing image from {self.current_file_path}: {e}")
            
            # Fall back to just updating the display with the current image
            self._update_image_display()
        
        # If we have an app instance, force a clipboard check with force=True
        if hasattr(self, 'app_instance') and self.app_instance:
            try:
                # Store current auto_refresh setting
                auto_refresh = self.settings.get("auto_refresh", True)
                
                try:
                    # Temporarily enable auto-refresh to ensure the image updates
                    self.settings.set("auto_refresh", True)
                    
                    # Force a clipboard check with force=True
                    if hasattr(self.app_instance, 'clipboard_monitor') and self.app_instance.clipboard_monitor:
                        logging.info("Calling force_check_clipboard on clipboard_monitor")
                        self.app_instance.clipboard_monitor.force_check_clipboard()
                    else:
                        logging.warning("clipboard_monitor not available, trying app's force_check_clipboard")
                        self.app_instance.force_check_clipboard()
                    
                    # Make sure the overlay is visible
                    if not self.isVisible():
                        logging.info("Overlay not visible, showing it")
                        self.show()
                        self.raise_()
                        self.activateWindow()
                    
                    # Force an immediate update of the display
                    if self.original_image:
                        self._update_image_display()
                    
                    return
                    
                finally:
                    # Restore the original auto_refresh setting
                    self.settings.set("auto_refresh", auto_refresh)
                    
            except Exception as e:
                logging.error(f"Error during manual refresh: {e}", exc_info=True)
        
        # Fallback to just updating the current image if available
        if self.original_image:
            logging.info("Falling back to updating current image display")
            self._update_image_display()
        else:
            logging.warning("No app_instance available, cannot perform refresh")
    
    def closeEvent(self, event):
        """Handle close event to properly clean up resources."""
        try:
            # Clean up all resources
            self.cleanup_resources()
            self.clear_display()
            
            # Save window position before closing
            try:
                pos = self.pos()
                self.settings.set("overlay_position_x", pos.x())
                self.settings.set("overlay_position_y", pos.y())
                logging.info(f"Saved overlay position: {pos.x()}, {pos.y()}")
            except Exception as e:
                logging.error(f"Error saving overlay position: {e}")
                
            # Force garbage collection
            import gc
            gc.collect()
            
        except Exception as e:
            logging.error(f"Error during close: {e}")
        finally:
            # Always accept the close event
            event.accept()
    
    def apply_settings(self, settings=None):
        """Apply current settings to the overlay.
        
        Args:
            settings: Optional settings object. If provided, updates the overlay's settings.
        """
        # Update settings if provided
        if settings is not None:
            self.settings = settings
            
        # Apply opacity
        self.update_opacity(self.settings.get("opacity", 77))
        
        # Apply always on top
        flags = self.windowFlags()
        if self.settings.get("always_on_top", True):
            if not (flags & Qt.WindowStaysOnTopHint):
                self.setWindowFlags((flags | Qt.WindowStaysOnTopHint) | Qt.FramelessWindowHint | Qt.Tool)
                # Ensure mouse tracking is preserved
                self.setMouseTracking(True)
                self.show()
        else:
            if flags & Qt.WindowStaysOnTopHint:
                self.setWindowFlags((flags & ~Qt.WindowStaysOnTopHint) | Qt.FramelessWindowHint | Qt.Tool)
                # Ensure mouse tracking is preserved
                self.setMouseTracking(True)
                if self.isVisible():
                    self.show()
        
        # Update clickthrough state
        self._update_clickthrough()
        
        # Apply border and background color based on theme
        theme = self.settings.get("theme", "dark")
        if theme == "light":
            self.setStyleSheet("background-color: #E0E0E0; border: 10px solid red;")
        else:
            self.setStyleSheet("background-color: #252525; border: 10px solid red;")
        
        # Show window after changing flags
        self.show()
    
    def _apply_sized_pixmap(self):
        """Apply the current pixmap with proper letterboxing/pillarboxing."""
        if not self.pixmap or self.width() <= 10 or self.height() <= 10:
            return
        
        try:
            # Border adjustment
            border_width = 6  # 3px border on each side
            frame_width = self.width() - border_width * 2
            frame_height = self.height() - border_width * 2
            
            # Get pixmap dimensions
            img_width = self.pixmap.width()
            img_height = self.pixmap.height()
            
            # Calculate aspect ratios
            img_aspect = img_width / float(img_height)
            frame_aspect = frame_width / float(frame_height)
            
            # Determine scaling strategy
            if self.settings.get("resize_image_to_fit", False):
                # Fit image within frame
                if img_aspect > frame_aspect:
                    # Image is wider relative to frame
                    new_width = frame_width
                    new_height = int(frame_width / img_aspect)
                else:
                    # Image is taller relative to frame
                    new_height = frame_height
                    new_width = int(frame_height * img_aspect)
            else:
                # Maintain original image size
                new_width = min(img_width, frame_width)
                new_height = min(img_height, frame_height)
            
            # Resize the pixmap
            scaled_pixmap = self.pixmap.scaled(new_width, new_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Center the image label in the widget with border adjustment
            x_offset = border_width + (frame_width - new_width) // 2
            y_offset = border_width + (frame_height - new_height) // 2
            
            # Update the image label size and position
            self.image_label.setGeometry(x_offset, y_offset, new_width, new_height)
            self.image_label.setPixmap(scaled_pixmap)
        
        except Exception as e:
            logging.error(f"Error applying sized pixmap: {e}")
    
    def _constrain_to_monitors(self, pos, size):
        """Ensure the window stays within monitor bounds, using full screen geometry."""
        # Get the screen containing the current position
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if not screen:
            return pos
            
        # Use full screen geometry (includes taskbar area)
        screen_geo = screen.geometry()
        
        # Calculate the right and bottom edges
        right_edge = screen_geo.right() - size.width() + 1
        bottom_edge = screen_geo.bottom() - size.height() + 1
        
        # Constrain the position to be within the screen bounds
        x = max(screen_geo.left(), min(pos.x(), right_edge))
        y = max(screen_geo.top(), min(pos.y(), bottom_edge))
        
        return QPoint(x, y)
    
    def _handle_drag(self, pos):
        """Handle window dragging with monitor boundary constraints."""
        if not hasattr(self, '_drag_start_pos') or not hasattr(self, '_drag_window_pos'):
            return
            
        # Calculate new position based on drag delta
        delta = self.mapToGlobal(pos) - self._drag_start_pos
        new_pos = self._drag_window_pos + delta
        
        # Constrain to monitor bounds
        constrained_pos = self._constrain_to_monitors(
            new_pos, 
            QSize(self.width(), self.height())
        )
        
        # Apply the constrained position
        self.move(constrained_pos)

    def _get_screen_geometry(self, pos=None):
        """Get the geometry of the screen containing the given position or the current window.
        Uses full screen geometry (ignores taskbar)."""
        screen = QApplication.screenAt(pos if pos is not None else self.mapToGlobal(self.rect().center()))
        if not screen and QApplication.screens():
            screen = QApplication.primaryScreen()
        return screen.geometry() if screen else QRect()  # Use geometry() instead of availableGeometry() to ignore taskbar
    
    def _get_all_screens_geometry(self):
        """Get the combined geometry of all screens."""
        screens = QApplication.screens()
        if not screens:
            return QRect()
            
        # Get the virtual geometry that encompasses all screens
        min_x = min(screen.geometry().left() for screen in screens)
        min_y = min(screen.geometry().top() for screen in screens)
        max_x = max(screen.geometry().right() for screen in screens)
        max_y = max(screen.geometry().bottom() for screen in screens)
        
        return QRect(QPoint(min_x, min_y), QPoint(max_x, max_y))
    
    def _get_screen_edges(self):
        """Get all screen edges and corners for snapping."""
        edges = []
        corners = []
        
        # Get all screens
        screens = QApplication.screens()
        if not screens:
            return [], []
        
        # Get the combined geometry of all screens
        combined = QRect()
        for screen in screens:
            combined = combined.united(screen.geometry())
        
        # Add screen edges (excluding outer edges of the combined area)
        for screen in screens:
            geo = screen.geometry()
            
            # Left edge
            if geo.left() > combined.left():
                edges.append((geo.left(), 'vertical'))
            # Right edge
            if geo.right() < combined.right():
                edges.append((geo.right(), 'vertical'))
            # Top edge
            if geo.top() > combined.top():
                edges.append((geo.top(), 'horizontal'))
            # Bottom edge
            if geo.bottom() < combined.bottom():
                edges.append((geo.bottom(), 'horizontal'))
            
            # Add corners
            corners.append((geo.topLeft(), 'topleft'))
            corners.append((geo.topRight(), 'topright'))
            corners.append((geo.bottomLeft(), 'bottomleft'))
            corners.append((geo.bottomRight(), 'bottomright'))
        
        # Add outer edges of the combined area
        edges.append((combined.left(), 'vertical'))
        edges.append((combined.right(), 'vertical'))
        edges.append((combined.top(), 'horizontal'))
        edges.append((combined.bottom(), 'horizontal'))
        
        return edges, corners

    def _snap_to_edges(self):
        """Snap the window to screen edges and corners with stronger snapping."""
        try:
            geometry = self.geometry()
            center = geometry.center()
            
            # Get all screen edges and corners
            edges, corners = self._get_screen_edges()
            
            # Snap distances (increased for stronger snapping)
            edge_snap = 30      # Increased from 20
            corner_snap = 25    # Increased from 15
            
            # Initialize new position
            new_x, new_y = geometry.x(), geometry.y()
            snapped = False
            
            # Check for corner snapping first (strongest snap)
            for pos, corner_type in corners:
                dist = ((center.x() - pos.x()) ** 2 + (center.y() - pos.y()) ** 2) ** 0.5
                if dist <= corner_snap:
                    if corner_type == 'topleft':
                        new_x, new_y = pos.x(), pos.y()
                    elif corner_type == 'topright':
                        new_x, new_y = pos.x() - geometry.width() + 1, pos.y()
                    elif corner_type == 'bottomleft':
                        new_x, new_y = pos.x(), pos.y() - geometry.height() + 1
                    else:  # bottomright
                        new_x, new_y = pos.x() - geometry.width() + 1, pos.y() - geometry.height() + 1
                    snapped = True
                    break
            
            # If not snapped to a corner, check edges
            if not snapped:
                for edge_pos, edge_type in edges:
                    if edge_type == 'vertical':
                        # Check left and right edges
                        if abs(geometry.left() - edge_pos) <= edge_snap:
                            new_x = edge_pos
                            snapped = True
                        elif abs(geometry.right() - edge_pos) <= edge_snap:
                            new_x = edge_pos - geometry.width() + 1
                            snapped = True
                    else:  # horizontal
                        # Check top and bottom edges
                        if abs(geometry.top() - edge_pos) <= edge_snap:
                            new_y = edge_pos
                            snapped = True
                        elif abs(geometry.bottom() - edge_pos) <= edge_snap:
                            new_y = edge_pos - geometry.height() + 1
                            snapped = True
            
            # Apply the new position if snapped
            if snapped and (new_x != geometry.x() or new_y != geometry.y()):
                # Ensure we stay within screen bounds
                screen = QApplication.screenAt(QPoint(new_x, new_y)) or QApplication.primaryScreen()
                if screen:
                    screen_rect = screen.geometry()
                    new_x = max(screen_rect.left(), min(new_x, screen_rect.right() - geometry.width() + 1))
                    new_y = max(screen_rect.top(), min(new_y, screen_rect.bottom() - geometry.height() + 1))
                    
                    self.move(new_x, new_y)
                    return True
                
        except Exception as e:
            logging.error(f"Error in _snap_to_edges: {e}", exc_info=True)
            
        return False
        
    def _get_combined_screen_geometry(self):
        """Get the combined geometry of all screens (legacy support)."""
        return self._get_all_screens_geometry()
    