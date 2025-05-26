import os
import logging
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication, QStyle
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QObject

class SystemTrayManager(QObject):
    """Manages the system tray icon and menu."""
    
    # Signals
    settings_requested = pyqtSignal()
    history_requested = pyqtSignal()
    overlay_focus_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    
    def __init__(self, icon_path):
        super().__init__()
        self.icon_path = icon_path
        self.tray_icon = None
        self.init_tray()
    
    def init_tray(self):
        """Initialize the system tray icon and menu."""
        # Check if system tray is available
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logging.warning("System tray is not available on this system")
            return
            
        logging.info("Initializing system tray...")
        
        try:
            # Create tray icon with parent
            self.tray_icon = QSystemTrayIcon()
            
            # Set icon
            if self.icon_path and os.path.exists(self.icon_path):
                try:
                    # Convert path to absolute and normalize
                    icon_path = os.path.abspath(self.icon_path)
                    logging.info(f"Attempting to load icon from: {icon_path}")
                    
                    # Create QIcon with explicit file path
                    icon = QIcon(icon_path)
                    if icon.isNull():
                        raise Exception("Failed to create QIcon from file")
                        
                    self.tray_icon.setIcon(icon)
                    logging.info(f"Successfully loaded tray icon from {icon_path}")
                except Exception as e:
                    logging.error(f"Failed to load tray icon: {e}", exc_info=True)
                    # Fallback to default icon
                    self.tray_icon.setIcon(QApplication.style().standardIcon(QStyle.SP_ComputerIcon))
            else:
                logging.warning(f"Icon file not found: {self.icon_path}")
                # Use a default system icon
                self.tray_icon.setIcon(QApplication.style().standardIcon(QStyle.SP_ComputerIcon))
        except Exception as e:
            logging.error(f"Failed to initialize system tray: {e}", exc_info=True)
            return
        
        # Create and set up the menu
        self._create_menu()
        
        # Show the tray icon
        try:
            if not self.tray_icon.isVisible():
                self.tray_icon.show()
                logging.info("System tray icon shown successfully")
                # Force a repaint of the system tray area
                QApplication.processEvents()
            else:
                logging.info("System tray icon was already visible")
        except Exception as e:
            logging.error(f"Failed to show system tray icon: {e}", exc_info=True)
        
        # Double check if the icon is visible
        if hasattr(self, 'tray_icon') and self.tray_icon:
            logging.info(f"System tray icon is visible: {self.tray_icon.isVisible()}")
            logging.info(f"System tray icon is system tray available: {QSystemTrayIcon.isSystemTrayAvailable()}")
        
        logging.info("System tray icon initialization complete")
        
    def _create_menu(self):
        """Create the system tray menu."""
        if not hasattr(self, 'tray_icon') or not self.tray_icon:
            return
            
        # Create the menu
        self.tray_menu = QMenu()
        
        # Settings action
        settings_action = QAction("Settings", self.tray_icon)
        settings_action.triggered.connect(self.settings_requested.emit)
        self.tray_menu.addAction(settings_action)
        
        # History action
        history_action = QAction("History", self.tray_icon)
        history_action.triggered.connect(self.history_requested.emit)
        self.tray_menu.addAction(history_action)
        
        # Focus overlay action
        overlay_action = QAction("Focus Overlay", self.tray_icon)
        overlay_action.triggered.connect(self.overlay_focus_requested.emit)
        self.tray_menu.addAction(overlay_action)
        
        # Separator
        self.tray_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("Exit", self.tray_icon)
        exit_action.triggered.connect(self.exit_requested.emit)
        self.tray_menu.addAction(exit_action)
        
        # Set the context menu
        self.tray_icon.setContextMenu(self.tray_menu)
        
        # Connect activated signal (left-click)
        self.tray_icon.activated.connect(self.tray_icon_activated)
    
    def tray_icon_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.Trigger:  # Left click
            self.settings_requested.emit()
    
    def show_message(self, title, message, icon=QSystemTrayIcon.Information):
        """Show a notification message from the tray icon."""
        if self.tray_icon and self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage(title, message, icon, 3000)  # 3000ms = 3s
    
    def update_icon(self, icon_path=None):
        """Update the tray icon."""
        if icon_path:
            self.icon_path = icon_path
        
        if os.path.exists(self.icon_path):
            icon = QIcon(self.icon_path)
            self.tray_icon.setIcon(icon)
    
    def cleanup(self):
        """Clean up resources before exiting."""
        if self.tray_icon:
            self.tray_icon.hide()
            
            # Explicitly delete the tray icon to ensure resources are freed
            self.tray_icon.deleteLater()
            self.tray_icon = None
            
            # Process pending events to ensure deletion completes
            QApplication.processEvents()
