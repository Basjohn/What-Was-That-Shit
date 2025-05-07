import logging
import sys
from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QMenu, QApplication, 
                           QAction, QFrame, QGraphicsDropShadowEffect)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QCursor, QColor
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QEvent, pyqtSignal, QTimer, QBuffer, QByteArray
from PIL import Image
import io
import struct

class ImageOverlay(QWidget):
    def paintEvent(self, event):
        """Ensure the overlay background is always cleared (fixes letterboxing/pillarboxing ghosting)."""
        painter = QPainter(self)
        color = QColor(30, 30, 33)  # Match your stylesheet background
        painter.fillRect(self.rect(), color)
        super().paintEvent(event)

    """A frameless, resizable overlay window that displays images copied to the clipboard."""
    
    # Signal to request opening settings
    settings_requested = pyqtSignal()
    
    def __init__(self, settings):
        # Use Qt.Tool flag to prevent the overlay from appearing in the taskbar
        # Always use WindowStaysOnTopHint as requested
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        
        # Store settings
        self.settings = settings
        
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
        
        # Track the current scaling factor (for mousewheel zoom)
        self.scale_factor = 1.0
        self.min_scale_factor = 0.2
        self.max_scale_factor = 3.0
        
        # Set background to dark grey for letterboxing/pillarboxing
        self.setStyleSheet("""
            QWidget {
                background-color: rgb(30, 30, 33);
            }
        """)
        
        # Add a stronger, more visible drop shadow around the entire overlay
        self.shadow_effect = QGraphicsDropShadowEffect()
        self.shadow_effect.setBlurRadius(20)  # Larger blur for more visibility
        self.shadow_effect.setColor(QColor(0, 0, 0, 220))  # Darker shadow
        self.shadow_effect.setOffset(0, 0)  # Centered shadow (appears around the entire window)
        self.setGraphicsEffect(self.shadow_effect)
        
        # Create image label (for displaying the image)
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: transparent; border: none;")
        
        # Set context menu policy
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # Set opacity from settings
        self.update_opacity(self.settings.get("opacity", 77))
        
        # Set clickthrough if enabled
        if self.settings.get("clickthrough", False):
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        # Load initial position and size from settings
        self._load_geometry_from_settings()
        
        # Set mouse tracking to handle resize cursors
        self.setMouseTracking(True)
        
        # Hide initially - will show when an image is set
        self.hide()
        
        # Install event filter to capture wheel events
        self.installEventFilter(self)
    
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
        try:
            # Get the current size
            current_width = self.width()
            current_height = self.height()
            
            # Calculate zoom factor based on wheel delta
            # Increase zoom sensitivity for better response
            zoom_factor = 1.0 + (event.angleDelta().y() / 1200.0)
            
            # Calculate new scale factor within bounds
            new_scale = self.scale_factor * zoom_factor
            new_scale = max(self.min_scale_factor, min(new_scale, self.max_scale_factor))
            
            # Calculate scale change since last time
            scale_change = new_scale / self.scale_factor
            
            # Only resize if change is significant enough
            if abs(scale_change - 1.0) > 0.01:
                # Save the old scale factor
                self.scale_factor = new_scale
                
                # Calculate new dimensions
                new_width = int(current_width * scale_change)
                new_height = int(current_height * scale_change)
                
                # Resize the window
                self.resize(new_width, new_height)
                
                # Check if we need to snap after resize
                self._snap_to_edges()
                
                # Update the image display to fit the new size
                if self.pixmap and self.settings.get("resize_image_to_fit", False):
                    self._apply_sized_pixmap()
                
                # Log the resize
                logging.debug(f"Wheel resize to {new_width}x{new_height}, scale factor: {self.scale_factor:.2f}")
                
            # Accept the event so it's not propagated further
            event.accept()
            return True
            
        except Exception as e:
            logging.error(f"Error in wheel event: {e}")
            event.accept()  # Still accept to prevent propagation
            return True
    
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
    
    def update_opacity(self, opacity_value):
        """Update window opacity based on settings."""
        # Store the normal opacity value
        self.current_opacity = opacity_value / 100.0
        
        # Only apply if not in full opacity mode
        if not self.is_full_opacity:
            self.setWindowOpacity(self.current_opacity)
    
    def set_image(self, pil_image):
        """Set the image to display in the overlay."""
        try:
            # Clear previous image data to prevent memory leaks
            if self.original_image:
                self.original_image = None
            
            if self.pixmap:
                self.pixmap = None
                
            # Clear animation data
            self.gif_frames = []
            self.frame_durations = []
            
            # Stop animation timer if running
            if self.animation_timer.isActive():
                self.animation_timer.stop()
                
            self.is_animated_gif = False
            self.animation_playing = False
            
            # Store the new image
            self.original_image = pil_image
            
            # Check if this is an animated GIF
            self._check_animated_gif()
            
            # Update the display
            self._update_image_display()
            
            # Show the overlay if not visible
            if not self.isVisible():
                # If we have a saved snap position, try to restore relative positioning
                if self.last_snapped_to:
                    self._restore_snap_position()
                
                self.show()
                
                # Don't steal focus
                active_window = QApplication.activeWindow()
                if active_window and active_window != self:
                    active_window.activateWindow()
        except Exception as e:
            logging.error(f"Error setting image in overlay: {e}")
    
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
        self.is_animated_gif = False
        self.gif_frames = []
        self.frame_durations = []
        self.current_frame = 0
        
        # Check if image is a GIF 
        try:
            if not self.original_image:
                return
                
            # Check if this is a GIF by format
            img_format = getattr(self.original_image, 'format', '')
            if not img_format or img_format.upper() != 'GIF':
                return
                
            logging.info(f"GIF image detected in overlay, analyzing...")
            
            # If we have raw GIF data, use that directly
            if hasattr(self.original_image, '_raw_gif_data') and self.original_image._raw_gif_data:
                logging.info("Using preserved raw GIF data")
                gif_data = self.original_image._raw_gif_data
                
                # Binary analysis to check for animation markers
                frame_markers = gif_data.count(b'\x21\xF9\x04')
                logging.info(f"GIF binary analysis found {frame_markers} animation markers")
                
                if frame_markers > 1:
                    # This is definitely an animated GIF
                    self.is_animated_gif = True
                    logging.info("Confirmed animated GIF")
                    
                    # We'll use the original image for the first frame
                    self.gif_frames = [self.original_image]
                    
                    # Set default duration
                    self.frame_durations = [100]  # Default 100ms
                    
                    # Flag for history saving
                    self.original_image.is_animated = True
            else:
                # No raw data available, try standard PIL methods
                logging.info("No raw GIF data available, using standard PIL analysis")
                
                # Try to detect animation using PIL
                try:
                    # Save and reload the image to ensure proper handling
                    buffer = io.BytesIO()
                    self.original_image.save(buffer, format='GIF')
                    buffer.seek(0)
                    
                    with Image.open(buffer) as gif:
                        try:
                            # Try to determine number of frames
                            frame_count = 0
                            while True:
                                try:
                                    gif.seek(frame_count)
                                    frame_count += 1
                                except EOFError:
                                    break
                                    
                            logging.info(f"PIL analysis found {frame_count} frames")
                            
                            if frame_count > 1:
                                self.is_animated_gif = True
                                self.original_image.is_animated = True
                                self.gif_frames = [self.original_image]
                                self.frame_durations = [100]
                        except Exception as e:
                            logging.error(f"Error counting GIF frames: {e}")
                except Exception as e:
                    logging.error(f"Error in PIL GIF analysis: {e}")
                    
            # Store the raw data for history saving if we confirmed animation
            if self.is_animated_gif and not hasattr(self.original_image, '_raw_gif_data'):
                buffer = io.BytesIO()
                self.original_image.save(buffer, format='GIF')
                self.original_image._raw_gif_data = buffer.getvalue()
                
        except Exception as e:
            logging.error(f"Error in _check_animated_gif: {e}")
    
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
                qimg = QImage(current_img.tobytes(), current_img.width, current_img.height, QImage.Format_RGBA8888)
            else:
                # Convert to RGBA
                rgba_img = current_img.convert('RGBA')
                qimg = QImage(rgba_img.tobytes(), rgba_img.width, rgba_img.height, QImage.Format_RGBA8888)
            
            self.pixmap = QPixmap.fromImage(qimg)
            
            # Apply the pixmap with proper sizing
            self._apply_sized_pixmap()
            
            # Update timer for next frame, using this frame's duration
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
            except Exception as e:
                logging.error(f"Error preparing animation: {e}")
        
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
        self.animation_timer.stop()
        self.animation_playing = False
        self.current_frame = 0
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging or resizing the window."""
        if event.button() == Qt.LeftButton:
            cursor_pos = event.pos()
            edge_size = self.edge_size
            
            # Get widget dimensions
            width = self.width()
            height = self.height()
            
            # Check if the cursor is near the edges
            on_left = cursor_pos.x() <= edge_size
            on_right = cursor_pos.x() >= width - edge_size
            on_top = cursor_pos.y() <= edge_size
            on_bottom = cursor_pos.y() >= height - edge_size
            
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
            else:
                self.resize_edge = None
            
            # Start resizing or dragging
            if self.resize_edge:
                self.resizing = True
                self.resize_start_pos = event.globalPos()
                self.resize_start_geometry = QRect(self.pos(), self.size())
                event.accept()
            else:
                self.dragging = True
                self.drag_position = event.pos()
                event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging, resizing, or updating cursor."""
        # If currently resizing
        if event.buttons() & Qt.LeftButton and self.resizing:
            self._handle_resize(event.globalPos())
            event.accept()
            return
        
        # If currently dragging
        if event.buttons() & Qt.LeftButton and self.dragging:
            self._handle_drag(event.pos())
            event.accept()
            return
        
        # Update cursor based on position for resize hints
        self._update_cursor(event.pos())
        
        super().mouseMoveEvent(event)
    
    def _update_cursor(self, pos):
        """Update the cursor based on position."""
        # Edge detection
        edge_size = self.edge_size
        rect = self.rect()
        
        # Check cursor position relative to edges
        on_left = pos.x() <= edge_size
        on_right = pos.x() >= rect.width() - edge_size
        on_top = pos.y() <= edge_size
        on_bottom = pos.y() >= rect.height() - edge_size
        
        # Set appropriate cursor
        if (on_top and on_left) or (on_bottom and on_right):
            self.setCursor(Qt.SizeFDiagCursor)
            self.cursor_on_edge = True
        elif (on_top and on_right) or (on_bottom and on_left):
            self.setCursor(Qt.SizeBDiagCursor)
            self.cursor_on_edge = True
        elif on_left or on_right:
            self.setCursor(Qt.SizeHorCursor)
            self.cursor_on_edge = True
        elif on_top or on_bottom:
            self.setCursor(Qt.SizeVerCursor)
            self.cursor_on_edge = True
        else:
            if self.cursor_on_edge:
                self.setCursor(Qt.ArrowCursor)
                self.cursor_on_edge = False
    
    def _handle_resize(self, global_pos):
        """Handle resizing based on which edge is being dragged."""
        if not self.resizing or not self.resize_edge or not self.resize_start_geometry:
            return
            
        delta = global_pos - self.resize_start_pos
        new_geometry = QRect(self.resize_start_geometry)
        
        # Apply resize based on edge
        if "left" in self.resize_edge:
            new_geometry.setLeft(self.resize_start_geometry.left() + delta.x())
        elif "right" in self.resize_edge:
            new_geometry.setRight(self.resize_start_geometry.right() + delta.x())
            
        if "top" in self.resize_edge:
            new_geometry.setTop(self.resize_start_geometry.top() + delta.y())
        elif "bottom" in self.resize_edge:
            new_geometry.setBottom(self.resize_start_geometry.bottom() + delta.y())
        
        # Enforce minimum size
        min_size = 100
        if new_geometry.width() < min_size:
            if "left" in self.resize_edge:
                new_geometry.setLeft(new_geometry.right() - min_size)
            else:
                new_geometry.setRight(new_geometry.left() + min_size)
                
        if new_geometry.height() < min_size:
            if "top" in self.resize_edge:
                new_geometry.setTop(new_geometry.bottom() - min_size)
            else:
                new_geometry.setBottom(new_geometry.top() + min_size)
        
        # Stay within screen bounds
        screen = QApplication.screenAt(global_pos)
        if screen:
            screen_geo = screen.geometry()
            
            # Ensure the window stays mostly visible on screen
            buffer = 50  # Minimum visible pixels
            
            # Left edge
            if new_geometry.left() > screen_geo.right() - buffer:
                new_geometry.moveLeft(screen_geo.right() - buffer)
            elif new_geometry.right() < screen_geo.left() + buffer:
                new_geometry.moveRight(screen_geo.left() + buffer)
                
            # Top edge
            if new_geometry.top() > screen_geo.bottom() - buffer:
                new_geometry.moveTop(screen_geo.bottom() - buffer)
            elif new_geometry.bottom() < screen_geo.top() + buffer:
                new_geometry.moveBottom(screen_geo.top() + buffer)
        
        # Apply the new geometry - do this directly for more responsive resizing
        self.setGeometry(new_geometry)
        
        # Save size to settings while resizing for smoother experience
        self.settings.update({
            "overlay_width": self.width(),
            "overlay_height": self.height(),
            "overlay_x": self.pos().x(),
            "overlay_y": self.pos().y()
        })
    
    def _handle_drag(self, local_pos):
        """Handle dragging the window."""
        self.move(self.mapToParent(local_pos - self.drag_position))
        self._snap_to_edges()
        
        # Save position to settings
        self.settings.update({
            "overlay_x": self.pos().x(),
            "overlay_y": self.pos().y()
        })
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release after dragging or resizing."""
        if event.button() == Qt.LeftButton:
            was_resizing = self.resizing
            was_dragging = self.dragging
            
            self.dragging = False
            self.resizing = False
            self.resize_edge = None
            
            # Update cursor based on new position
            if was_resizing or was_dragging:
                self._update_cursor(event.pos())
                
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
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
    
    def _snap_to_edges(self):
        """Snap window to screen edges and corners with moderate strength."""
        current_pos = self.pos()
        snap_distance = 20  # Moderate snap distance
        
        # Check all screens
        for i, screen in enumerate(QApplication.screens()):
            screen_geo = screen.geometry()
            
            # Window dimensions
            width = self.width()
            height = self.height()
            
            # Check corners first (stronger snapping)
            # Top-left corner
            if (abs(current_pos.x() - screen_geo.left()) < snap_distance and 
                abs(current_pos.y() - screen_geo.top()) < snap_distance):
                self.move(screen_geo.left(), screen_geo.top())
                self.last_snapped_to = ("top-left", i)
                return
                
            # Top-right corner
            if (abs(current_pos.x() + width - screen_geo.right()) < snap_distance and 
                abs(current_pos.y() - screen_geo.top()) < snap_distance):
                self.move(screen_geo.right() - width, screen_geo.top())
                self.last_snapped_to = ("top-right", i)
                return
                
            # Bottom-left corner
            if (abs(current_pos.x() - screen_geo.left()) < snap_distance and 
                abs(current_pos.y() + height - screen_geo.bottom()) < snap_distance):
                self.move(screen_geo.left(), screen_geo.bottom() - height)
                self.last_snapped_to = ("bottom-left", i)
                return
                
            # Bottom-right corner
            if (abs(current_pos.x() + width - screen_geo.right()) < snap_distance and 
                abs(current_pos.y() + height - screen_geo.bottom()) < snap_distance):
                self.move(screen_geo.right() - width, screen_geo.bottom() - height)
                self.last_snapped_to = ("bottom-right", i)
                return
            
            # Center of screen
            center_x = screen_geo.left() + screen_geo.width() // 2
            center_y = screen_geo.top() + screen_geo.height() // 2
            if (abs(current_pos.x() + width//2 - center_x) < snap_distance and
                abs(current_pos.y() + height//2 - center_y) < snap_distance):
                self.move(center_x - width//2, center_y - height//2)
                self.last_snapped_to = ("center", i)
                return
            
            # Edges (weaker snapping)
            # Left edge
            if abs(current_pos.x() - screen_geo.left()) < snap_distance:
                self.move(screen_geo.left(), current_pos.y())
                self.last_snapped_to = None  # Not a corner snap
                
            # Right edge
            elif abs(current_pos.x() + width - screen_geo.right()) < snap_distance:
                self.move(screen_geo.right() - width, current_pos.y())
                self.last_snapped_to = None
                
            # Top edge
            if abs(current_pos.y() - screen_geo.top()) < snap_distance:
                self.move(current_pos.x(), screen_geo.top())
                self.last_snapped_to = None
                
            # Bottom edge
            elif abs(current_pos.y() + height - screen_geo.bottom()) < snap_distance:
                self.move(current_pos.x(), screen_geo.bottom() - height)
                self.last_snapped_to = None
                
            # Check for monitor seams
            for j in range(i+1, len(QApplication.screens())):
                other_screen = QApplication.screens()[j]
                other_geo = other_screen.geometry()
                
                # Check horizontal seam
                if (screen_geo.right() == other_geo.left() or screen_geo.left() == other_geo.right()):
                    if max(screen_geo.top(), other_geo.top()) <= current_pos.y() <= min(screen_geo.bottom(), other_geo.bottom()):
                        # Snap to the seam
                        if abs(current_pos.x() - screen_geo.right()) < snap_distance:
                            self.move(screen_geo.right(), current_pos.y())
                            self.last_snapped_to = None
                            
                # Check vertical seam
                if (screen_geo.bottom() == other_geo.top() or screen_geo.top() == other_geo.bottom()):
                    if max(screen_geo.left(), other_geo.left()) <= current_pos.x() <= min(screen_geo.right(), other_geo.right()):
                        # Snap to the seam
                        if abs(current_pos.y() - screen_geo.bottom()) < snap_distance:
                            self.move(current_pos.x(), screen_geo.bottom())
                            self.last_snapped_to = None
        
        # Save the last snapped position to settings if it exists
        if self.last_snapped_to:
            self.settings.set("last_snapped_to", self.last_snapped_to)
    
    def _show_context_menu(self, position):
        """Show the right-click context menu."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #333337;
                color: white;
                border: 1px solid #444444;
            }
            QMenu::item {
                padding: 5px 30px 5px 20px;
            }
            QMenu::item:selected {
                background-color: #007BFF;
            }
        """)
        
        # Settings action
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)
        
        # Refresh action
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.refresh_image)
        menu.addAction(refresh_action)
        
        # GIF playback controls - only show if this is detected as a GIF
        if getattr(self.original_image, 'format', '').upper() == 'GIF':
            if self.animation_playing:
                pause_action = QAction("Pause", self)
                pause_action.triggered.connect(self._pause_animation)
                menu.addAction(pause_action)
            else:
                play_action = QAction("Play", self)
                play_action.triggered.connect(self._play_animation)
                menu.addAction(play_action)
        
        # Hide action
        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)
        
        # Opacity toggle action
        opacity_action = QAction("Toggle Full Opacity", self)
        opacity_action.triggered.connect(self._toggle_opacity)
        menu.addAction(opacity_action)
        
        # Reset size action
        reset_action = QAction("Reset Size", self)
        reset_action.triggered.connect(self._reset_size)
        menu.addAction(reset_action)
        
        # Show menu
        menu.exec_(self.mapToGlobal(position))
    
    def _reset_size(self):
        """Reset overlay to default size."""
        self.resize(500, 400)
        # Center on the current screen
        screen = QApplication.screenAt(self.mapToGlobal(QPoint(0, 0)))
        if screen:
            center_point = screen.geometry().center()
            self.move(center_point.x() - 250, center_point.y() - 200)
    
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
            self._update_image_display()
    
    def closeEvent(self, event):
        """Handle close event to properly clean up resources."""
        # Stop animation timer if running
        if self.animation_timer and self.animation_timer.isActive():
            self.animation_timer.stop()
            
        # Save window position before closing
        try:
            pos = self.pos()
            self.settings.set("overlay_position_x", pos.x())
            self.settings.set("overlay_position_y", pos.y())
            logging.info(f"Saved overlay position: {pos.x()}, {pos.y()}")
        except Exception as e:
            logging.error(f"Error saving overlay position: {e}")
            
        # Clear image data to free memory
        self.original_image = None
        self.pixmap = None
        self.gif_frames = []
        
        # Accept the close event
        event.accept()
    
    def apply_settings(self):
        """Apply current settings to the overlay."""
        # Apply opacity
        self.update_opacity(self.settings.get("opacity", 77))
        
        # Apply always on top
        flags = self.windowFlags()
        if self.settings.get("always_on_top", True):
            if not (flags & Qt.WindowStaysOnTopHint):
                self.setWindowFlags((flags | Qt.WindowStaysOnTopHint) | Qt.FramelessWindowHint | Qt.Tool)
                # Ensure mouse tracking is preserved
                self.setMouseTracking(True)
                if self.isVisible():
                    self.show()
        else:
            if (flags & Qt.WindowStaysOnTopHint):
                self.setWindowFlags((flags & ~Qt.WindowStaysOnTopHint) | Qt.FramelessWindowHint | Qt.Tool)
                # Ensure mouse tracking is preserved
                self.setMouseTracking(True)
                if self.isVisible():
                    self.show()
        
        # Apply clickthrough
        if self.settings.get("clickthrough", False):
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        else:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        
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
            # Get current widget size
            frame_width = self.width()
            frame_height = self.height()
            
            # Get pixmap dimensions
            img_width = self.pixmap.width()
            img_height = self.pixmap.height()
            
            # Calculate aspect ratios
            img_aspect = img_width / float(img_height)
            frame_aspect = frame_width / float(frame_height)
            
            # Calculate size to fit image within frame while maintaining aspect ratio
            if frame_aspect > img_aspect:  # Frame is wider than image (pillarboxing)
                # Height is the limiting factor
                new_height = frame_height
                new_width = int(new_height * img_aspect)
            else:  # Frame is taller than image (letterboxing)
                # Width is the limiting factor
                new_width = frame_width
                new_height = int(new_width / img_aspect)
                
            # Resize the pixmap
            scaled_pixmap = self.pixmap.scaled(new_width, new_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Center the image label in the widget
            x_offset = (frame_width - new_width) // 2
            y_offset = (frame_height - new_height) // 2
            
            # Update the image label size and position
            self.image_label.setGeometry(x_offset, y_offset, new_width, new_height)
            self.image_label.setPixmap(scaled_pixmap)
        
        except Exception as e:
            logging.error(f"Error applying sized pixmap: {e}")
