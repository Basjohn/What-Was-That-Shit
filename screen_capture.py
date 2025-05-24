
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt5.QtGui import QPainter, QColor, QPen, QScreen, QPixmap, QCursor
from PyQt5.QtCore import QRect, Qt, QTimer, QPoint, QObject, pyqtSignal, QThread, QDateTime, QTime
import logging

# --------------------------------------------------------------------- #
#  Screen Capture Frame Widget                                           #
# --------------------------------------------------------------------- #
# --------------------------------------------------------------------- #
class FrameWidget(QWidget):
    """A widget that draws a highly visible frame around the capture area."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set window flags - these are critical for proper display
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowStaysOnTopHint |
            Qt.X11BypassWindowManagerHint
        )
        
        # Set basic window attributes
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowStaysOnTopHint
        )
        
        # Enable transparency
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        # Enable click-through
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        
        # Set a fixed size to ensure visibility
        self.resize(300, 300)
        
        # Set style with thicker border and 80% opacity
        self.setStyleSheet("""
            background: transparent;
            border: 3px solid rgba(173, 216, 230, 0.8);
        """)
        
        # Log window creation
        logging.debug(f"FrameWidget created at ({self.x()}, {self.y()}) {self.width()}x{self.height()}")
        
    def paintEvent(self, event):
        """Draw the frame with corner indicators."""
        try:
            painter = QPainter(self)
            painter.setRenderHints(
                QPainter.Antialiasing |
                QPainter.SmoothPixmapTransform |
                QPainter.HighQualityAntialiasing
            )
            
            # Draw only the border with transparency
            border_width = 2
            pen = QPen(QColor(173, 216, 230), border_width)
            pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            
            # Draw the main border
            margin = 5
            border_rect = self.rect().adjusted(margin, margin, -margin, -margin)
            painter.drawRect(border_rect)
            
            # Draw corner indicators
            corner_length = 15
            
            # Top-left
            painter.drawLine(border_rect.topLeft(), border_rect.topLeft() + QPoint(corner_length, 0))
            painter.drawLine(border_rect.topLeft(), border_rect.topLeft() + QPoint(0, corner_length))
            
            # Top-right
            painter.drawLine(border_rect.topRight(), border_rect.topRight() - QPoint(corner_length, 0))
            painter.drawLine(border_rect.topRight(), border_rect.topRight() + QPoint(0, corner_length))
            
            # Bottom-left
            painter.drawLine(border_rect.bottomLeft(), border_rect.bottomLeft() + QPoint(corner_length, 0))
            painter.drawLine(border_rect.bottomLeft(), border_rect.bottomLeft() - QPoint(0, corner_length))
            
            # Bottom-right
            painter.drawLine(border_rect.bottomRight(), border_rect.bottomRight() - QPoint(corner_length, 0))
            painter.drawLine(border_rect.bottomRight(), border_rect.bottomRight() - QPoint(0, corner_length))
            
            painter.end()
            
        except Exception as e:
            logging.error(f"Error in FrameWidget.paintEvent: {e}", exc_info=True)
    
    def showEvent(self, event):
        """Ensure the frame is properly shown and stays on top."""
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()
        logging.debug(f"Frame shown at {self.geometry()}, visible: {self.isVisible()}")
        
        # Force update and ensure window is on top
        self.repaint()
        self.raise_()
        self.activateWindow()

# --------------------------------------------------------------------- #
class ScreenCapture(QObject):
    """Capture image around the cursor and flash a blue frame (thread‑safe)."""
    
    # Signal to show the capture frame
    capture_frame_signal = pyqtSignal(QRect, bool)  # rect, is_video

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        
        # Connect the signal to the handler
        self.capture_frame_signal.connect(self._show_capture_frame, Qt.QueuedConnection)
        self.capture_width = settings.get("capture_width", 2000)   # physical px
        self.capture_height = settings.get("capture_height", 1000)  # physical px

    # ------------------------------------------------------------------ #
    def capture_around_cursor(self):
        try:
            # Get cursor position and screen info
            cursor_pos = QCursor.pos()  # logical coords
            screen = QApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() or 1.0
            screen_geometry = screen.geometry()
            
            # Get capture dimensions from settings
            capture_width = self.settings.get('capture_width', 720)
            capture_height = self.settings.get('capture_height', 480)
            
            # Calculate capture rectangle centered on cursor (logical coords)
            x = max(0, cursor_pos.x() - capture_width // 2)
            y = max(0, cursor_pos.y() - capture_height // 2)
            
            # Ensure the capture rectangle stays within screen bounds
            if x + capture_width > screen_geometry.width():
                x = screen_geometry.width() - capture_width
            if y + capture_height > screen_geometry.height():
                y = screen_geometry.height() - capture_height
                
            # Ensure x and y are not negative
            x = max(0, x)
            y = max(0, y)
            
            # Create logical rect for the frame
            logical_rect = QRect(x, y, capture_width, capture_height)
            
            # Show the capture frame if enabled
            if self.settings.get('draw_capture_frame', True):
                self._flash_frame(logical_rect)
            
            # Calculate physical coordinates for capture
            phys_x = int(x * dpr)
            phys_y = int(y * dpr)
            phys_width = int(capture_width * dpr)
            phys_height = int(capture_height * dpr)
            
            # Capture the screen (using physical coordinates)
            pixmap = screen.grabWindow(0, phys_x, phys_y, phys_width, phys_height)
            
            # Convert to QImage and return
            return pixmap.toImage()
            
        except Exception as e:
            logging.error(f"Error capturing around cursor: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------ #
    def _show_capture_frame(self, rect: QRect, is_video: bool = False):
        """Show a frame around the captured area (thread‑safe)."""
        try:
            if not self.settings.get('draw_capture_frame', True):
                logging.debug("Capture frame disabled in settings")
                return
                
            logging.debug(f"Preparing to show capture frame at {rect}")
            
            # Create the frame widget with no parent for now
            frame = FrameWidget()
            
            # Calculate position and size with some padding
            padding = 10
            frame_rect = QRect(
                rect.x() - padding,
                rect.y() - padding,
                rect.width() + (padding * 2),
                rect.height() + (padding * 2)
            )
            
            # Set geometry before showing
            frame.setGeometry(frame_rect)
            
            # Set window properties
            frame.setWindowTitle("WWTS Capture Frame")
            frame.setWindowOpacity(1.0)
            
            # Show the window
            frame.show()
            
            # Force the window to be on top and active
            frame.setWindowState(frame.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
            frame.raise_()
            frame.activateWindow()
            
            # Force update and process events
            frame.repaint()
            QApplication.processEvents()
            
            # Log window properties
            logging.debug(f"Frame shown at {frame.geometry()}, visible: {frame.isVisible()}")
            logging.debug(f"Frame screen: {frame.screen().name() if frame.screen() else 'No screen'}")
            
            # Close the frame after a very short duration
            duration = 350  # 350 milliseconds
            QTimer.singleShot(duration, frame.deleteLater)
            
            # Keep a reference to prevent garbage collection
            self._current_frame = frame
            
            logging.info(f"Capture frame displayed for {duration}ms at {frame.geometry()}")
            
        except Exception as e:
            logging.error(f"Error in _show_capture_frame: {e}", exc_info=True)

    def _flash_frame(self, rect: QRect):
        """Show a blue frame around the captured area (thread‑safe)."""
        try:
            if not self.settings.get('draw_capture_frame', True):
                return
                
            if not rect.isValid() or rect.isEmpty():
                return
                
            # Use the same approach as _show_capture_frame
            self.capture_frame_signal.emit(rect, False)
        except Exception as e:
            logging.error(f"Error in _flash_frame: {e}", exc_info=True)


