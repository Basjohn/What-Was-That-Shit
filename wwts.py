import sys
import os
import logging
import ctypes
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QSystemTrayIcon
from PyQt5.QtCore import Qt, QStandardPaths, QTimer, QBuffer
from PyQt5.QtGui import QIcon, QPixmap, QImage
from PIL import Image, ImageGrab
import io

# Local modules
from settings import Settings
from settings_window import SettingsWindow
from overlay import ImageOverlay
from clipboard_monitor import ClipboardMonitor
from system_tray import SystemTrayManager
from history import HistoryManager

class WWTSApp:
    def __init__(self):
        # Make app DPI aware to ensure proper scaling
        try:
            # Enable Windows DPI awareness
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception as e:
            logging.warning(f"Failed to set DPI awareness: {e}")
        
        # Setup logger
        self.setup_logger()
        
        # Initialize settings
        self.settings = Settings()
        
        # Ensure settings file exists
        if not os.path.exists(self.settings.settings_file):
            logging.warning("Settings file not found, creating with defaults")
            self.settings.save_settings()
        
        # History folder will be created by the Settings class 
        # and will always be at the executable's location
        logging.warning(f"Using history folder: {self.settings.history_folder}")
        
        # Initialize history manager if needed
        self.history_manager = None
        self._init_history_manager()
        
        # Create QApplication instance
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("What Was That Shit?!")
        self.app.setOrganizationName("WWTS")
        self.app.setQuitOnLastWindowClosed(False)  # Allow app to run with no visible windows
        
        # Set application icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'icons', 'WWTS.ico')
        if os.path.exists(icon_path):
            self.app_icon = QIcon(icon_path)
            self.app.setWindowIcon(self.app_icon)
        
        # Initialize variables
        self.overlay = None
        self.settings_window = None
        self.clipboard_monitor = None
        self.system_tray = None
        
        # Initialize components
        self.init_overlay()
        self.init_settings_window()
        self.init_systray()
        
        # Initialize clipboard monitor
        self.init_monitoring()
        
        # Timer to check for overlay settings request
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_overlay_settings_request)
        self.check_timer.start(500)  # Check every 500ms
        
    def setup_logger(self):
        """Setup the application logger."""
        logging.basicConfig(
            level=logging.WARNING,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wwts.log')),
                logging.StreamHandler()
            ]
        )
        logging.warning("Logger initialized")
    
    def _init_history_manager(self):
        """Initialize the history manager if save_history is enabled."""
        if self.settings.get("save_history", False):
            # Ensure the folder exists
            os.makedirs(self.settings.history_folder, exist_ok=True)
            logging.warning(f"Using history folder: {self.settings.history_folder}")
            
            # Create the history manager
            self.history_manager = HistoryManager(self.settings.history_folder)
            return True
        return False
    
    def init_overlay(self):
        """Initialize the image overlay."""
        self.overlay = ImageOverlay(self.settings)
        
        # Connect overlay settings request signal
        self.overlay.settings_requested.connect(self.show_settings)
        
    def init_settings_window(self):
        """Initialize the settings window."""
        self.settings_window = SettingsWindow(self.settings, self.overlay)
        self.settings_window.setWindowIcon(self.app_icon)
        self.settings_window.finished.connect(self.on_settings_closed)
    
    def init_systray(self):
        """Initialize the system tray."""
        tray_icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'icons', 'WWTS.ico')
        self.system_tray = SystemTrayManager(tray_icon_path if os.path.exists(tray_icon_path) else None)
        
        # Connect system tray signals
        self.system_tray.settings_requested.connect(self.show_settings)
        self.system_tray.history_requested.connect(self.show_history)
        self.system_tray.overlay_focus_requested.connect(self.focus_overlay)
        self.system_tray.exit_requested.connect(self.exit_app)
    
    def init_monitoring(self):
        """Initialize clipboard monitoring."""
        try:
            # Create clipboard monitor if it doesn't exist
            if not self.clipboard_monitor:
                self.clipboard_monitor = ClipboardMonitor(self.settings)
                
                # Connect signal
                self.clipboard_monitor.new_image.connect(self.on_new_image)
                
                # Connect the direct capture signal
                self.clipboard_monitor.image_captured.connect(self.on_direct_capture)
                
                # Start monitoring
                self.clipboard_monitor.start()
                logging.warning("Clipboard monitoring started")
            
        except Exception as e:
            logging.error(f"Error initializing clipboard monitoring: {e}")
    
    def connect_signals(self):
        """Connect signals to slots (unused - signals are connected where components are initialized)"""
        pass
    
    def start(self):
        """Start the application"""
        # Start clipboard monitoring
        self.clipboard_monitor.start()
        
        # Show settings window if not starting minimized
        if not self.settings.get("minimize_on_startup", False):
            self.settings_window.show()
            self.settings_window.raise_()
            self.settings_window.activateWindow()
        else:
            # Notify user the app started minimized
            self.system_tray.show_message(
                "What Was That Shit?!",
                "Application is running in the system tray",
                QSystemTrayIcon.Information
            )
        
        # Start the application event loop
        return self.app.exec_()
    
    def check_overlay_settings_request(self):
        """Check if the overlay requested to open settings"""
        # This is no longer needed since we're using signals
        pass
    
    def on_new_image(self, image):
        """Handle new image from clipboard monitor"""
        logging.warning("New clipboard image detected")
        
        # Check if we have a valid image
        if not image:
            logging.warning("Received empty image from clipboard monitor")
            return
        
        try:
            # Save to history if enabled
            if self.settings.get("save_history", False):
                # Ensure history manager is initialized
                if not self.history_manager:
                    if not self._init_history_manager():
                        logging.error("Failed to initialize history manager")
                
                if self.history_manager:
                    try:
                        # Ensure we're passing a PIL Image object and specify the format
                        if isinstance(image, Image.Image):
                            file_type = image.format if image.format else 'PNG'
                            file_path = self.history_manager.save_image(image, file_type.lower())
                            logging.warning(f"Image saved to history: {file_path}")
                        else:
                            logging.warning(f"Cannot save to history: received non-Image object: {type(image)}")
                    except Exception as save_error:
                        logging.error(f"Error saving image to history: {save_error}")
            
            # Send to overlay - don't refresh if auto-refresh is disabled
            if self.settings.get("auto_refresh", True) or not self.overlay.isVisible():
                logging.warning("Setting new image to overlay")
                
                # Make sure we're on the main thread
                self.app.processEvents()
                
                # Send image to overlay
                self.overlay.set_image(image)
        except Exception as e:
            logging.error(f"Error handling clipboard image: {e}")
    
    def on_direct_capture(self, qimage):
        """Handle direct image capture from double-shift."""
        try:
            if qimage and not qimage.isNull():
                logging.warning("Received direct capture image")
                
                # Make sure we're on the main thread
                self.app.processEvents()
                
                # Save to history if enabled
                if self.settings.get("save_history", False):
                    # Ensure history manager is initialized
                    if not self.history_manager:
                        if not self._init_history_manager():
                            logging.error("Failed to initialize history manager")
                    
                    if self.history_manager:
                        try:
                            # Convert QImage to PIL Image for saving
                            buffer = QBuffer()
                            buffer.open(QBuffer.ReadWrite)
                            qimage.save(buffer, "PNG")
                            pil_image = Image.open(io.BytesIO(buffer.data()))
                            pil_image.format = "PNG"
                            
                            # Save the image
                            file_path = self.history_manager.save_image(pil_image, "png")
                            logging.warning(f"Direct capture saved to history: {file_path}")
                        except Exception as save_error:
                            logging.error(f"Error saving direct capture to history: {save_error}")
                
                # Send QImage directly to overlay
                self.overlay.set_qimage(qimage)
                
                # Ensure overlay is visible
                if not self.overlay.isVisible():
                    self.overlay.show()
                    self.overlay.raise_()
        except Exception as e:
            logging.error(f"Error handling direct capture: {e}")
    
    def on_settings_closed(self):
        """Handle settings updated from settings window"""
        # Update history manager if history setting changed
        if self.settings.get("save_history", False) and not self.history_manager:
            self._init_history_manager()
        
        # Apply settings to overlay
        if self.overlay:
            self.overlay.apply_settings(self.settings)
    
    def show_settings(self):
        """Show the settings window."""
        if not hasattr(self, 'settings_window') or not self.settings_window.isVisible():
            # Create a new settings window if it doesn't exist or isn't visible
            self.settings_window = SettingsWindow(self.settings, self.overlay)
            self.settings_window.setWindowIcon(self.app_icon)
            self.settings_window.finished.connect(self.on_settings_closed)
            self.settings_window.show()
        else:
            # Bring existing window to front
            self.settings_window.activateWindow()
    
    def show_history(self):
        """Show the history browser window"""
        # Get the history folder path (always relative to the app)
        history_folder = self.settings.history_folder
            
        # Create the folder if it doesn't exist
        if not os.path.exists(history_folder):
            try:
                os.makedirs(history_folder)
                logging.warning(f"Created History folder: {history_folder}")
            except Exception as e:
                self.system_tray.show_message(
                    "History",
                    f"Could not create History folder: {e}",
                    QSystemTrayIcon.Warning
                )
                return
        
        # Open the folder in file explorer
        try:
            if os.name == 'nt':  # Windows
                os.startfile(history_folder)
            elif os.name == 'posix':  # macOS and Linux
                import subprocess
                subprocess.Popen(['open', history_folder])
        except Exception as e:
            self.system_tray.show_message(
                "History", 
                f"Could not open History folder: {e}",
                QSystemTrayIcon.Warning
            )
    
    def focus_overlay(self):
        """Bring overlay window to front"""
        if self.overlay:
            # Make sure the overlay is visible
            if not self.overlay.isVisible():
                self.overlay.show()
            
            # Ensure it stays on top (don't toggle - we always want always-on-top)
            self.overlay.show()
            self.overlay.raise_()
            self.overlay.activateWindow()
        else:
            self.system_tray.show_message(
                "Overlay",
                "No image overlay is currently available",
                QSystemTrayIcon.Information
            )
    
    def exit_app(self):
        """Exit the application"""
        logging.warning("Application exit requested")
        
        # Stop clipboard monitoring
        if self.clipboard_monitor:
            logging.warning("Stopping clipboard monitor")
            self.clipboard_monitor.stop()
            self.clipboard_monitor = None
        
        # Hide windows
        if self.overlay:
            logging.warning("Closing overlay")
            self.overlay.close()
            self.overlay.deleteLater()
            self.overlay = None
            
        if self.settings_window:
            logging.warning("Closing settings window")
            self.settings_window.close()
            self.settings_window.deleteLater()
            self.settings_window = None
        
        # Clean up system tray
        if self.system_tray:
            logging.warning("Cleaning up system tray")
            self.system_tray.cleanup()
            self.system_tray = None
        
        # Stop timer
        if self.check_timer:
            logging.warning("Stopping timer")
            self.check_timer.stop()
            self.check_timer = None
        
        # Process any pending events
        self.app.processEvents()
        
        # Exit application
        logging.warning("Exiting application")
        self.app.quit()

if __name__ == "__main__":
    app = WWTSApp()
    sys.exit(app.start())
