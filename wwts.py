import sys
import os
import logging
import ctypes
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QSystemTrayIcon, QMessageBox
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
        logging.info("Initializing WWTS application...")

        try:
            logging.info("Setting up DPI awareness...")
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            logging.info("DPI awareness set successfully")
        except Exception as e:
            logging.warning(f"Failed to set DPI awareness: {e}")
            
        try:
            # Initialize the application components
            self.app = QApplication(sys.argv)
            self.app.setQuitOnLastWindowClosed(False)
            
            # Set up logging first
            self.setup_logger()
            
            # Initialize settings
            self.settings = Settings()
            
            # Initialize history folder path
            self.history_folder = self.settings.history_folder
            
            # Initialize history manager
            self.history_manager = None
            if self.settings.get("save_history", False):
                self._init_history_manager()
            
            # Initialize components
            self.clipboard_monitor = None
            self.check_timer = None
            
            # Set up icon
            possible_icon_paths = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'icons', 'WWTS.ico'),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'WWTS.ico'),
                'WWTS.ico'
            ]
            
            self.app_icon = None
            for path in possible_icon_paths:
                if os.path.exists(path):
                    self.app_icon = QIcon(path)
                    break
            
            if not self.app_icon:
                self.app_icon = self.app.style().standardIcon(self.app.style().SP_ComputerIcon)
            
            # Initialize components
            self.init_overlay()
            self.init_settings_window()
            self.init_systray()
            self.init_monitoring()
            
        except Exception as e:
            logging.critical(f"Failed to initialize WWTS application: {e}", exc_info=True)
            raise
            
    def toggle_setting(self, key, value):
        """Update setting live and save instantly."""
        self.settings[key] = value
        self.settings.save_settings()
        
    def setup_logger(self):
        """Setup the application logger with appropriate verbosity."""
        # Set up logging to both file and console
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wwts.log')
        
        # Clear existing handlers
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # Set up logging to file
        file_handler = logging.FileHandler(
            log_file,
            mode='a',  # Append to log file
            encoding='utf-8',
            delay=True  # Open the file only when needed
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Set up console logging
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Create formatters and add them to the handlers
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        
        file_handler.setFormatter(file_formatter)
        console_handler.setFormatter(console_formatter)
        
        # Add handlers to the root logger
        logging.basicConfig(
            level=logging.DEBUG,
            handlers=[file_handler, console_handler]
        )
        
        # Set up module-specific log levels
        log_levels = {
            'PIL': logging.WARNING,
            'PIL.PngImagePlugin': logging.ERROR,
            'PIL.Image': logging.WARNING,
            'PIL.TiffImagePlugin': logging.ERROR,
            'PyQt5': logging.WARNING,
            'matplotlib': logging.ERROR,
            'clipboard_monitor': logging.DEBUG,
            'screen_capture': logging.DEBUG,
            'wwts': logging.DEBUG
        }
        
        for name, level in log_levels.items():
            logger = logging.getLogger(name)
            logger.setLevel(level)
            logger.propagate = True
            
        logging.info("Logger configured successfully")
        logging.info(f"Log file: {os.path.abspath(log_file)}")
    
    def _init_history_manager(self):
        """Initialize the history manager if save_history is enabled."""
        if self.settings.get("save_history", False):
            try:
                # Create the history manager with the fixed history folder
                self.history_manager = HistoryManager(self.history_folder)
                logging.info(f"History manager initialized with folder: {self.history_folder}")
                return True
            except Exception as e:
                logging.error(f"Failed to initialize history manager: {e}")
                return False
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
        
        # Hide the overlay if in sneaky bitch mode
        if self.settings.get("sneaky_bitch_mode", False):
            self.overlay.hide()
        
    def init_settings_window(self):
        """Initialize the settings window."""
        self.settings_window = SettingsWindow(self.settings, self.overlay)
        self.settings_window.setWindowIcon(self.app_icon)
        self.settings_window.finished.connect(self.on_settings_closed)
    
    def init_systray(self):
        """Initialize the system tray."""
        # Try multiple possible locations for the icon
        possible_icon_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'icons', 'WWTS.ico'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'WWTS.ico'),
            'WWTS.ico'
        ]
        
        # Find the first valid icon path
        tray_icon_path = None
        for path in possible_icon_paths:
            if os.path.exists(path):
                tray_icon_path = path
                logging.info(f"Found icon at: {tray_icon_path}")
                break
                
        if tray_icon_path is None:
            logging.warning("Could not find icon file in any of the expected locations")
            logging.warning(f"Searched in: {possible_icon_paths}")
        else:
            logging.info(f"Using icon from: {tray_icon_path}")
            
        self.system_tray = SystemTrayManager(tray_icon_path)
        
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
                    self.clipboard_monitor.system_tray = self.system_tray
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
                # Apply the new image to the overlay
                self.overlay.set_image(image, force=force)
                
                # Save to history if enabled
                if self.settings.get("save_history", False) and self.history_manager:
                    try:
                        if hasattr(image, 'toImage'):
                            self.history_manager.add_image(image)
                    except Exception as e:
                        logging.error(f"Error saving to history: {e}")
                
                # Update the overlay but respect sneaky bitch mode
                if not self.settings.get("sneaky_bitch_mode", False):
                    logging.info("Sneaky Bitch Mode: Off - Showing overlay for clipboard capture")
                    if self.overlay.isHidden():
                        self.overlay.show()
                        self.overlay.raise_()
                        self.overlay.activateWindow()
                else:
                    logging.info("Sneaky Bitch Mode: On - Keeping overlay hidden for clipboard capture")
                    # Still update the overlay but ensure it's hidden
                    if self.overlay.isVisible():
                        self.overlay.hide()
        except Exception as e:
            logging.error(f"Error in on_new_image: {e}", exc_info=True)
    
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

            # Update the overlay with the new image but respect sneaky bitch mode
            if not self.settings.get("sneaky_bitch_mode", False):
                logging.info("Sneaky Bitch Mode: Off - Showing overlay after direct capture")
                if not self.overlay.isVisible():
                    self.overlay.show()
                    self.overlay.raise_()
                    self.overlay.activateWindow()
            else:
                logging.info("Sneaky Bitch Mode: On - Keeping overlay hidden after direct capture")
                # Still update the overlay but ensure it's hidden
                if self.overlay.isVisible():
                    self.overlay.hide()

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
            # Disable sneaky bitch mode when focusing from system tray
            if self.settings.get("sneaky_bitch_mode", False):
                self.settings.set("sneaky_bitch_mode", False)
                self.settings.save_settings()
                if hasattr(self.overlay, 'sneaky_bitch_action'):
                    self.overlay.sneaky_bitch_action.setChecked(False)
            
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
        """Exit the application and clean up all resources."""
        try:
            # Stop clipboard monitoring first to prevent new operations
            if self.clipboard_monitor:
                try:
                    self.clipboard_monitor.stop()
                except Exception as e:
                    logging.error(f"Error stopping clipboard monitor: {e}", exc_info=True)
                finally:
                    self.clipboard_monitor = None
            
            # Stop any timers to prevent callbacks during cleanup
            if hasattr(self, 'check_timer') and self.check_timer:
                try:
                    self.check_timer.stop()
                    self.check_timer.timeout.disconnect()
                except Exception as e:
                    logging.error(f"Error stopping timer: {e}", exc_info=True)
                finally:
                    self.check_timer = None
            
            # Clean up overlay
            if hasattr(self, 'overlay') and self.overlay:
                try:
                    # Clean up any resources in the overlay
                    if hasattr(self.overlay, 'cleanup_resources'):
                        self.overlay.cleanup_resources()
                    self.overlay.close()
                    self.overlay.deleteLater()
                except Exception as e:
                    logging.error(f"Error closing overlay: {e}", exc_info=True)
                finally:
                    self.overlay = None
            
            # Clean up settings window
            if hasattr(self, 'settings_window') and self.settings_window:
                try:
                    if self.settings_window.isVisible():
                        self.settings_window.close()
                    self.settings_window.deleteLater()
                except Exception as e:
                    logging.error(f"Error closing settings window: {e}", exc_info=True)
                finally:
                    self.settings_window = None
            
            # Clean up system tray
            if hasattr(self, 'system_tray') and self.system_tray:
                try:
                    self.system_tray.cleanup()
                except Exception as e:
                    logging.error(f"Error cleaning up system tray: {e}", exc_info=True)
                finally:
                    self.system_tray = None
            
            # Clean up history manager
            if hasattr(self, 'history_manager') and self.history_manager:
                try:
                    if hasattr(self.history_manager, 'cleanup'):
                        self.history_manager.cleanup()
                except Exception as e:
                    logging.error(f"Error cleaning up history manager: {e}", exc_info=True)
                finally:
                    self.history_manager = None
            
            # Process any pending events before quitting
            QApplication.processEvents()
            
            # Remove any remaining references
            if hasattr(self, 'app'):
                self.app.processEvents()
                self.app.quit()
            
            # Force garbage collection
            import gc
            gc.collect()
            
        except Exception as e:
            logging.critical(f"Critical error during application exit: {e}", exc_info=True)
        finally:
            # Ensure the application exits
            os._exit(0) if hasattr(os, '_exit') else os._exit(0)

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