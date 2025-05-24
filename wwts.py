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
import psutil

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
        self.app_icon = None
        
        # Try to load icon from file system (development)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'icons', 'WWTS.ico')
        
        # For PyInstaller bundle, check if we're running in a bundle
        if getattr(sys, 'frozen', False):
            # Running in a bundle
            bundle_dir = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
            icon_path = os.path.join(bundle_dir, 'resources', 'icons', 'WWTS.ico')
        
        if os.path.exists(icon_path):
            try:
                self.app_icon = QIcon(icon_path)
                self.app.setWindowIcon(self.app_icon)
            except Exception as e:
                logging.error(f"Failed to load icon from {icon_path}: {e}")
        
        # Fallback to a blank icon if loading failed
        if self.app_icon is None:
            logging.warning("Using blank application icon")
            self.app_icon = QIcon()
        
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
        """Setup the application logger with minimal verbosity for production."""
        # Set root logger to only show errors and above
        logging.basicConfig(
            level=logging.ERROR,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                # Only log errors to file, no console output by default
                logging.FileHandler(
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wwts.log'),
                    mode='w',  # Overwrite log file on each run
                    encoding='utf-8'
                )
            ]
        )
        # Disable debug logging for PIL and other verbose libraries
        logging.getLogger('PIL').setLevel(logging.WARNING)
        logging.getLogger('PIL.PngImagePlugin').setLevel(logging.WARNING)
        logging.getLogger('PIL.Image').setLevel(logging.WARNING)
        logging.getLogger('PIL.TiffImagePlugin').setLevel(logging.WARNING)
    
    def _init_history_manager(self):
        """Initialize the history manager if save_history is enabled."""
        if self.settings.get("save_history", False):
            # Ensure the folder exists
            os.makedirs(self.settings.history_folder, exist_ok=True)
            
            # Create the history manager
            self.history_manager = HistoryManager(self.settings.history_folder)
            return True
        return False
    
    def init_overlay(self):
        """Initialize the image overlay."""
        from overlay import ImageOverlay
        self.overlay = ImageOverlay(self.settings)
        self.overlay.setWindowTitle("What Was That Shit?!")
        if hasattr(self, 'app_icon'):
            self.overlay.setWindowIcon(self.app_icon)
        
        # Store a reference to this app instance in the overlay
        self.overlay.app_instance = self
        
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
            logging.info("Initializing clipboard monitoring...")
            
            # Import the ClipboardMonitor class here to ensure any errors are caught
            try:
                from clipboard_monitor import ClipboardMonitor
                logging.info("Successfully imported ClipboardMonitor")
            except ImportError as ie:
                logging.error(f"Failed to import ClipboardMonitor: {ie}")
                raise
                
            # Create clipboard monitor if it doesn't exist
            if not self.clipboard_monitor:
                logging.info("Creating ClipboardMonitor instance...")
                try:
                    self.clipboard_monitor = ClipboardMonitor(self.settings)
                    logging.info("ClipboardMonitor instance created successfully")
                    
                    # Connect signals with error handling
                    try:
                        logging.info("Connecting new_image signal...")
                        self.clipboard_monitor.new_image.connect(self.on_new_image)
                        logging.info("Connected new_image signal")
                        
                        logging.info("Connecting image_captured signal...")
                        self.clipboard_monitor.image_captured.connect(self.on_direct_capture)
                        logging.info("Connected image_captured signal")
                        
                        logging.info("Clipboard monitor signals connected successfully")
                    except Exception as sig_err:
                        logging.error(f"Error connecting clipboard monitor signals: {sig_err}", exc_info=True)
                        raise
                        
                except Exception as create_err:
                    logging.error(f"Failed to create ClipboardMonitor: {create_err}", exc_info=True)
                    self.clipboard_monitor = None
                    raise
            else:
                logging.warning("Clipboard monitor already exists")
            
        except Exception as e:
            logging.error(f"Error initializing clipboard monitoring: {e}", exc_info=True)
            # Explicitly set to None to make it clear it failed
            self.clipboard_monitor = None
            # Re-raise to allow upper levels to handle the error
            raise
    
    def connect_signals(self):
        """Connect signals to slots (unused - signals are connected where components are initialized)"""
        pass
    
    def start(self):
        """Start the application"""
        # Start clipboard monitoring if it was initialized successfully
        if self.clipboard_monitor is not None:
            try:
                self.clipboard_monitor.start()
                logging.info("Clipboard monitoring started successfully")
            except Exception as e:
                logging.error(f"Error starting clipboard monitor: {e}")
        else:
            logging.warning("Clipboard monitor was not initialized, some features may not work")
        
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
        
        # Show the overlay on launch, even if it's empty
        if not self.overlay.isVisible():
            self.overlay.show()
            self.overlay.raise_()
            self.overlay.activateWindow()
        
        # Start the application event loop
        return self.app.exec_()
    
    def check_overlay_settings_request(self):
        """Check if the overlay requested to open settings"""
        # This is no longer needed since we're using signals
        pass
    
    def on_new_image(self, image):
        """Handle new image from clipboard monitor
        
        Args:
            image: The image to display (with _force_refresh attribute)
        """
        if not image:
            logging.warning("Received None image in on_new_image")
            return
            
        logging.info("Processing new clipboard image")
        
        # Get force refresh flag from image object (default to False if not set)
        force = getattr(image, '_force_refresh', False)
        
        try:
            # Save to history if enabled - always save even if auto-refresh is disabled
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
                            logging.info(f"Image saved to history: {file_path}")
                        else:
                            logging.warning(f"Cannot save to history: received non-Image object: {type(image)}")
                    except Exception as save_error:
                        logging.error(f"Error saving image to history: {save_error}")
            
            # Only update the overlay if auto-refresh is enabled or we're forcing
            if force or self.settings.get("auto_refresh", True):
                logging.info("Updating overlay with new image")
                
                # Make sure we're on the main thread
                self.app.processEvents()
                
                # Send image to overlay
                self.overlay.set_image(image, force=force)
                
                # Ensure overlay is visible
                if not self.overlay.isVisible():
                    self.overlay.show()
                    self.overlay.raise_()
                    self.overlay.activateWindow()
            else:
                logging.info("Skipping overlay update: auto-refresh is disabled")
                
        except Exception as e:
            logging.error(f"Error handling clipboard image: {e}", exc_info=True)
    
    def on_direct_capture(self, qimage, force=False):
        """Handle direct image capture from double-shift."""
        try:
            logging.debug_logger.info("=== Starting Direct Capture Processing ===")
            
            if not qimage or qimage.isNull():
                logging.debug_logger.error("Direct capture received null/empty QImage")
                return

            logging.debug_logger.info(f"QImage details:")
            logging.debug_logger.info(f"- Size: {qimage.size()}")
            logging.debug_logger.info(f"- Format: {qimage.format()}")
            logging.debug_logger.info(f"- Depth: {qimage.depth()}")
            logging.debug_logger.info(f"- Has alpha: {qimage.hasAlphaChannel()}")
            logging.debug_logger.info(f"- Is null: {qimage.isNull()}")
            
            # Memory check before processing
            process = psutil.Process(os.getpid())
            mem_before = process.memory_info().rss / 1024 / 1024
            logging.debug_logger.info(f"Memory before processing: {mem_before:.2f} MB")

            # Check auto-refresh setting if not forcing
            if not force and not self.settings.get("auto_refresh", True):
                logging.info("Skipping direct capture: auto-refresh is disabled")
                return

            try:
                # Convert QImage to PIL Image for saving
                buffer = QBuffer()
                buffer.open(QBuffer.ReadWrite)
                if not qimage.save(buffer, "PNG"):
                    logging.debug_logger.error("Failed to save QImage to buffer")
                    return
                buffer_data = buffer.data()
                logging.debug_logger.info(f"Buffer size: {len(buffer_data)} bytes")
                
                pil_image = Image.open(io.BytesIO(buffer_data))
                logging.debug_logger.info(f"Converted to PIL Image:")
                logging.debug_logger.info(f"- Size: {pil_image.size}")
                logging.debug_logger.info(f"- Mode: {pil_image.mode}")
                logging.debug_logger.info(f"- Format: {pil_image.format}")
            except Exception as conv_error:
                logging.debug_logger.error(f"Image conversion error: {conv_error}", exc_info=True)
                return

            # Save to history if enabled
            if self.settings.get("save_history", False):
                # Ensure history manager is initialized
                if not self.history_manager:
                    if not self._init_history_manager():
                        logging.error("Failed to initialize history manager")
                
                if self.history_manager:
                    try:
                        pil_image.format = "PNG"
                        file_path = self.history_manager.save_image(pil_image, "png")
                        logging.info(f"Direct capture saved to history: {file_path}")
                    except Exception as save_error:
                        logging.error(f"Error saving direct capture to history: {save_error}")

            # Before setting image to overlay
            logging.debug_logger.info("Attempting to set image to overlay...")
            self.overlay.set_qimage(qimage)
            logging.debug_logger.info("Successfully set image to overlay")

            # Ensure overlay is visible
            if not self.overlay.isVisible():
                self.overlay.show()
                self.overlay.raise_()
                self.overlay.activateWindow()

            # Memory check after processing
            mem_after = process.memory_info().rss / 1024 / 1024
            logging.debug_logger.info(f"Memory after processing: {mem_after:.2f} MB")
            logging.debug_logger.info(f"Memory delta: {mem_after - mem_before:.2f} MB")
            logging.debug_logger.info("=== Direct Capture Processing Complete ===")

        except Exception as e:
            logging.debug_logger.error(f"Direct capture processing error: {str(e)}")
            logging.debug_logger.error(f"Traceback:", exc_info=True)
            return
    
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
    
    def force_check_clipboard(self):
        """Force a clipboard check regardless of auto-refresh setting."""
        logging.warning("force_check_clipboard called in WWTSApp")
        logging.warning(f"clipboard_monitor: {self.clipboard_monitor}")
        logging.warning(f"clipboard_monitor type: {type(self.clipboard_monitor) if self.clipboard_monitor else 'None'}")
        
        if self.clipboard_monitor:
            logging.warning("Calling clipboard_monitor.force_check_clipboard")
            try:
                # Force the overlay to be visible before checking clipboard
                if self.overlay:
                    self.overlay.show()
                    self.overlay.raise_()
                    self.overlay.activateWindow()
                
                # Force a clipboard check
                self.clipboard_monitor.force_check_clipboard()
                logging.warning("Successfully called clipboard_monitor.force_check_clipboard")
                
                # Ensure the overlay is visible after the clipboard check
                if self.overlay and not self.overlay.isVisible():
                    self.overlay.show()
                    self.overlay.raise_()
                    self.overlay.activateWindow()
                    
            except Exception as e:
                logging.error(f"Error in clipboard_monitor.force_check_clipboard: {e}", exc_info=True)
        else:
            logging.warning("clipboard_monitor is None")
    
    def exit_app(self):
        """Exit the application"""
        logging.warning("Application exit requested")
        
        try:
            # Stop clipboard monitoring
            if self.clipboard_monitor:
                logging.warning("Stopping clipboard monitor")
                try:
                    self.clipboard_monitor.stop()
                except Exception as e:
                    logging.error(f"Error stopping clipboard monitor: {e}")
                self.clipboard_monitor = None
            
            # Hide overlay
            if self.overlay:
                logging.warning("Closing overlay")
                try:
                    self.overlay.close()
                    self.overlay.deleteLater()
                except Exception as e:
                    logging.error(f"Error closing overlay: {e}")
                self.overlay = None
                
            # Close settings window if it exists and is visible
            if self.settings_window:
                logging.warning("Closing settings window")
                try:
                    if self.settings_window.isVisible():
                        self.settings_window.close()
                    self.settings_window.deleteLater()
                except Exception as e:
                    logging.error(f"Error closing settings window: {e}")
                self.settings_window = None
            
            # Clean up system tray
            if self.system_tray:
                logging.warning("Cleaning up system tray")
                try:
                    self.system_tray.cleanup()
                except Exception as e:
                    logging.error(f"Error cleaning up system tray: {e}")
                self.system_tray = None
            
            # Stop timer
            if self.check_timer:
                logging.warning("Stopping timer")
                try:
                    self.check_timer.stop()
                    self.check_timer.timeout.disconnect()
                except Exception as e:
                    logging.error(f"Error stopping timer: {e}")
                self.check_timer = None
            
            # Process any pending events
            self.app.processEvents()
            
            # Exit application
            logging.warning("Exiting application")
            self.app.quit()
            
        except Exception as e:
            logging.critical(f"Error during application exit: {e}", exc_info=True)
            # Force exit if we get here

def setup_excepthook():
    """Setup a global exception hook to catch all unhandled exceptions."""
    def handle_exception(exc_type, exc_value, exc_traceback):
        """Handle unhandled exceptions by logging them and showing an error message."""
        # Skip keyboard interrupt to allow normal interrupt handling
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
            
        # Log the error to a file with minimal verbosity
        error_msg = f"Unhandled exception: {exc_value}"
        logging.error(error_msg)
        
        # Show a simple error message to user if possible
        try:
            app = QApplication.instance()
            if app is not None:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle("Application Error")
                msg.setText("An unexpected error occurred. The application may become unstable.")
                msg.setInformativeText(str(exc_value))
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
        except Exception:
            pass  # If we can't show the error, just continue
    
    # Set the exception handler
    sys.excepthook = handle_exception

if __name__ == "__main__":
    import time
    import traceback
    
    # Set up global exception handling
    setup_excepthook()
    
    try:
        # Create logs directory
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Create two separate loggers
        main_logger = logging.getLogger('main')
        debug_logger = logging.getLogger('debug')
        
        # Configure main logger (warnings and above)
        main_logger.setLevel(logging.WARNING)
        main_handler = logging.FileHandler(os.path.join(log_dir, 'wwts.log'))
        main_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        main_logger.addHandler(main_handler)
        
        # Configure debug logger (all levels)
        debug_logger.setLevel(logging.DEBUG)
        debug_handler = logging.FileHandler(os.path.join(log_dir, 'wwts_debug.log'))
        debug_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        debug_logger.addHandler(debug_handler)
        
        # Add console handler for immediate feedback
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        debug_logger.addHandler(console_handler)
        
        # Set the loggers as module-level variables
        logging.main_logger = main_logger
        logging.debug_logger = debug_logger
        
        # Initial logging
        main_logger.warning("=== Application Starting ===")
        debug_logger.info("=== Debug Log Initialized ===")
        
        logging.debug_logger.info(f"Python version: {sys.version}")
        logging.debug_logger.info(f"Working directory: {os.getcwd()}")
        logging.debug_logger.info(f"Script directory: {os.path.dirname(os.path.abspath(__file__))}")
        
        # Log environment variables that might affect the application
        logging.debug_logger.debug("Environment variables:")
        for var in ['PATH', 'PYTHONPATH', 'QT_DEBUG_PLUGINS']:
            logging.debug_logger.debug(f"  {var} = {os.environ.get(var, 'Not set')}")
        
        # Create and start the application
        logging.debug_logger.info("Creating WWTSApp instance...")
        app = WWTSApp()
        logging.debug_logger.info("Starting application...")
        exit_code = app.start()
        logging.debug_logger.info(f"Application exited with code {exit_code}")
        sys.exit(exit_code)
        
    except Exception as e:
        logging.main_logger.critical(f"Fatal error during application startup: {e}", exc_info=True)
        # Try to log the full traceback to file
        try:
            with open('wwts_startup_error.log', 'w') as f:
                traceback.print_exc(file=f)
        except Exception as log_err:
            print(f"Failed to write startup error log: {log_err}")
        sys.exit(1)
