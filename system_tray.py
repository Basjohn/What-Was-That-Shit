import os
import logging
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication
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
        # Create tray icon
        self.tray_icon = QSystemTrayIcon()
        
        # Set icon
        if os.path.exists(self.icon_path):
            icon = QIcon(self.icon_path)
            self.tray_icon.setIcon(icon)
        else:
            logging.warning(f"Icon file not found: {self.icon_path}")
            # Use a default icon from Qt
            self.tray_icon.setIcon(QIcon.fromTheme("dialog-information"))
        
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
        
        # Set context menu for tray icon
        self.tray_icon.setContextMenu(self.tray_menu)
        
        # Connect activated signal (left-click)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        # Show the tray icon
        self.tray_icon.show()
        
        logging.info("System tray icon initialized")
    
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
        try:
            if hasattr(self, 'tray_menu') and self.tray_menu:
                # First detach the menu from the tray icon
                if hasattr(self, 'tray_icon') and self.tray_icon:
                    self.tray_icon.setContextMenu(None)
                    
                # Clear and delete all actions from the menu
                self.tray_menu.clear()
                self.tray_menu.deleteLater()
                self.tray_menu = None
            
            # Now handle the tray icon
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.hide()
                
                # Explicitly delete the tray icon to ensure resources are freed
                self.tray_icon.deleteLater()
                self.tray_icon = None
                
                # Process pending events to ensure deletion completes
                QApplication.processEvents()
                
            logging.info("System tray resources cleaned up")
        except Exception as e:
            logging.error(f"Error during system tray cleanup: {e}")
