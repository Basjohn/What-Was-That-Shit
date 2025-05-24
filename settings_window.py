import logging
import os
import subprocess
import platform
import time
import sqlite3
from pathlib import Path
from PyQt5.QtCore import (
    Qt, QTimer, QSize, QPoint, QEvent, QPropertyAnimation, 
    QSequentialAnimationGroup, QAbstractAnimation, pyqtProperty as Property,
    QUrl
)
from PyQt5.QtGui import (
    QColor, QPalette, QDesktopServices, QPixmap, QPainter, QIcon, QFont
)
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QCheckBox, 
    QSlider, QComboBox, QPushButton, QGroupBox, QFormLayout,
    QFileDialog, QToolTip, QWidget, QSpacerItem, QSizePolicy,
    QFrame, QGraphicsOpacityEffect, QApplication, QMessageBox, QLineEdit, QSpinBox,
    QTextBrowser, QStyle, QStyleOption, QMainWindow
)

class BorderedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Create a central widget to hold the content
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("central_widget")
        
        # Main layout for the central widget
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(2, 2, 2, 2)  # Make room for the border
        
        # Set the central widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.central_widget)
        
        # For window dragging
        self.dragging = False
        self.drag_position = None
    
    def paintEvent(self, event):
        """Handle custom painting."""
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, painter, self)
        super().paintEvent(event)


class SettingsWindow(BorderedDialog):
    def __init__(self, settings, overlay=None, parent=None):
        # Initialize the parent class with the parent parameter
        super().__init__(parent)
        self.settings = settings
        self.overlay = overlay
        
        # Set the settings window reference in the overlay
        if self.overlay:
            self.overlay.settings_window = self
            
        # Remove the default titlebar and context help button
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setResult(0)
        
        # Tooltip delay is controlled by the system, we'll keep the default
        # Set initial window style with border and semi-transparent background
        self.setStyleSheet("""
            QDialog {
                background-color: rgba(45, 45, 48, 0.8);
                border: 2px solid white;
                border-radius: 5px;
            }
        """)
        
        self.init_ui()
        self.load_settings()
        
        # For window dragging
        self.dragging = False
        self.drag_position = None
    
    # Paint event is now handled by BorderedDialog
        
    def init_ui(self):
        """Initialize the UI components."""
        self.setMinimumSize(400, 450)
        
        # Set theme based on settings
        self.apply_theme(self.settings.get("theme", "dark"))
        
        # Main layout is already set up in BorderedDialog
        main_layout = self.main_layout
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Create custom title bar with close button
        title_bar = self.create_custom_title_bar()
        main_layout.addWidget(title_bar)
        
        # Create sections
        self.create_monitoring_section(main_layout)
        self.create_overlay_section(main_layout)
        self.create_theme_section(main_layout)
        self.create_history_section(main_layout)
        
        # Add button section at the bottom
        self.create_button_section(main_layout)
        
        # Set up connections
        self.setup_connections()
        
        # Set dialog to non-modal
        self.setModal(False)
        
        # Restore window position from settings
        try:
            x = self.settings.get("settings_window_x", None)
            y = self.settings.get("settings_window_y", None)
            
            if x is not None and y is not None:
                # Ensure the window is visible on screen
                desktop = QApplication.desktop()
                screen_rect = desktop.availableGeometry(desktop.primaryScreen())
                
                # Make sure the position is within screen bounds
                if x >= 0 and x < screen_rect.width() - 100 and y >= 0 and y < screen_rect.height() - 100:
                    self.move(x, y)
                    logging.info(f"Restored settings window position: {x}, {y}")
                else:
                    logging.warning(f"Saved position ({x}, {y}) is outside screen bounds, using default position")
        except Exception as e:
            logging.error(f"Error restoring settings window position: {e}")
    
    def create_custom_title_bar(self):
        """Create a custom title bar with close button."""
        title_bar = QFrame()
        title_bar.setMinimumHeight(60)  # Increased by 50%
        title_bar.setMaximumHeight(60)  # Increased by 50%
        title_bar.setObjectName("title_bar")  # Add ID for CSS styling
        
        # Use horizontal layout for the title bar
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(20, 0, 15, 0)  # Added more left padding
        title_layout.setSpacing(1)  # Reduced from 10 to 1 for tighter grouping
        
        # Title text - left aligned with moderate padding
        title_text = QLabel("What Was That Shit?!")
        title_text.setObjectName("title_text")  # Add ID for CSS styling
        title_layout.addWidget(title_text)
        
        # Add stretching space to push the close button to the right
        title_layout.addStretch(1)
        
        # Close button - changed to match minimize button color
        close_button = QPushButton("✕")
        close_button.setFixedSize(QSize(36, 36))
        close_button.setObjectName("close_button")  # Add ID for CSS styling
        close_button.clicked.connect(self.close_application)
        close_button.setCursor(Qt.PointingHandCursor)
        title_layout.addWidget(close_button)
        
        return title_bar
    
    def close_application(self):
        """Exit the application completely."""
        QApplication.quit()
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging the window."""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging the window."""
        if event.buttons() & Qt.LeftButton and self.dragging:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release after dragging."""
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()
        
    def apply_dark_theme(self):
        """Apply a dark theme to the entire UI."""
        self.setStyleSheet("""
            QDialog {
                background-color: rgba(45, 45, 48, 0.9);
                border: 2px solid white;
                border-radius: 5px;
                color: #FFFFFF;
            }
            
            QToolTip {
                background-color: #2D2D30;
                color: #FFFFFF;
                border: 1px solid #3F3F46;
                padding: 5px;
                border-radius: 3px;
            }
            QGroupBox {
                background-color: #333337;
                border-radius: 8px;
                font-weight: bold;
                margin-top: 15px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 5px 10px;
                background-color: #333337;
                border-radius: 5px;
                color: #FFFFFF;
            }
            QLabel {
                color: #FFFFFF;
            }
            QLabel#history_folder_label {
                color: #FFFFFF;
                background-color: #444444;
                border-radius: 4px;
                padding: 4px;
            }
            QFrame#title_bar {
                background-color: #1e1e21;
                border-radius: 4px;
                border-bottom: 3px solid #444444;
            }
            QLabel#title_text {
                font-size: 22px;
                font-weight: bold;
                color: #FFFFFF;
            }
            QPushButton#close_button {
                background-color: #555555;
                color: white;
                border-radius: 18px;
                font-weight: bold;
                font-size: 18px;
                border: none;
            }
            QPushButton#close_button:hover {
                background-color: #666666;
            }
            QPushButton#close_button:pressed {
                background-color: #444444;
            }
            QPushButton {
                background-color: #444444;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
            QPushButton:pressed {
                background-color: #333333;
            }
            QPushButton#save_button {
                background-color: #444444;
            }
            QPushButton#save_button:hover {
                background-color: #555555;
            }
            QPushButton#save_button:pressed {
                background-color: #333333;
            }
            QCheckBox {
                color: #FFFFFF;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #444444;
                border: 1px solid #777777;
            }
            QCheckBox::indicator:checked {
                background-color: #1A1A1A;
                border: 1px solid #555555;
            }
            QComboBox {
                background-color: #444444;
                border: none;
                border-radius: 4px;
                padding: 5px;
                color: #FFFFFF;
                min-height: 30px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                background-color: #444444;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox QAbstractItemView {
                background-color: #444444;
                color: #FFFFFF;
                selection-background-color: #1A1A1A;
            }
            QSlider::groove:horizontal {
                border: 1px solid #444444;
                height: 8px;
                background: #444444;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #1A1A1A;
                border: none;
                width: 22px;
                height: 22px;
                margin: -7px 0;
                border-radius: 11px;
            }
            QSlider::add-page:horizontal {
                background: #444444;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #555555;
                border-radius: 4px;
            }
        """)
    
    def apply_light_theme(self):
        """Apply a light theme to the entire UI (inverted dark theme)."""
        self.setStyleSheet("""
            QDialog {
                background-color: rgba(210, 210, 207, 0.9);
                border: 2px solid #333333;
                border-radius: 5px;
                color: #000000;
            }
            
            QToolTip {
                background-color: #F0F0F0;
                color: #000000;
                border: 1px solid #A0A0A0;
                padding: 5px;
                border-radius: 3px;
            }
            QGroupBox {
                background-color: #CCCCC8;
                border-radius: 8px;
                font-weight: bold;
                margin-top: 15px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 5px 10px;
                background-color: #CCCCC8;
                border-radius: 5px;
                color: #000000;
            }
            QLabel {
                color: #000000;
            }
            QLabel#history_folder_label {
                color: #000000;
                background-color: #BBBBBB;
                border-radius: 4px;
                padding: 4px;
            }
            QFrame#title_bar {
                background-color: #333337;
                border-radius: 4px;
                border-bottom: 3px solid #444444;
            }
            QLabel#title_text {
                font-size: 22px;
                font-weight: bold;
                color: #FFFFFF;
            }
            QPushButton#close_button {
                background-color: #555555;
                color: white;
                border-radius: 18px;
                font-weight: bold;
                font-size: 18px;
                border: none;
            }
            QPushButton#close_button:hover {
                background-color: #666666;
            }
            QPushButton#close_button:pressed {
                background-color: #444444;
            }
            QPushButton {
                background-color: #BBBBBB;
                color: #000000;
                border: none;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #AAAAAA;
            }
            QPushButton:pressed {
                background-color: #CCCCCC;
            }
            QPushButton#save_button {
                background-color: #BBBBBB;
            }
            QPushButton#save_button:hover {
                background-color: #AAAAAA;
            }
            QPushButton#save_button:pressed {
                background-color: #CCCCCC;
            }
            QCheckBox {
                color: #000000;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #BBBBBB;
                border: 1px solid #888888;
            }
            QCheckBox::indicator:checked {
                background-color: #FF8400;
                border: 1px solid #FF8400;
            }
            QComboBox {
                background-color: #BBBBBB;
                border: none;
                border-radius: 4px;
                padding: 5px;
                color: #000000;
                min-height: 30px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                background-color: #BBBBBB;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox QAbstractItemView {
                background-color: #BBBBBB;
                color: #000000;
                selection-background-color: #FF8400;
            }
            QSlider::groove:horizontal {
                border: 1px solid #BBBBBB;
                height: 8px;
                background: white;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #FF8400;
                border: none;
                width: 22px;
                height: 22px;
                margin: -7px 0;
                border-radius: 11px;
            }
            QSlider::add-page:horizontal {
                background: #BBBBBB;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: white;
                border-radius: 4px;
            }
        """)
    
    def apply_theme(self, theme_name):
        """Apply the selected theme."""
        logging.info(f"Applying theme: {theme_name}")
        if theme_name == "light":
            self.apply_light_theme()
        else:
            # Default to dark theme
            self.apply_dark_theme()
        
        # Apply tooltip styles that work with the current theme
        tooltip_style = """
            QToolTip {
                padding: 5px;
                border-radius: 3px;
                opacity: 230;
        """
        
        if theme_name == "light":
            tooltip_style += """
                background-color: #F0F0F0;
                color: #000000;
                border: 1px solid #A0A0A0;
            """
        else:
            tooltip_style += """
                background-color: #2D2D30;
                color: #FFFFFF;
                border: 1px solid #3F3F46;
            """
        
        tooltip_style += "}"
        self.setStyleSheet(self.styleSheet() + tooltip_style)
            
        # Update any theme-specific elements that aren't handled by stylesheets
        self.update_theme_specific_elements(theme_name)
    
    def update_theme_specific_elements(self, theme_name):
        """Update UI elements that need special handling for different themes."""
        # If we have an icon path stored and the icon label exists
        if hasattr(self, 'icon_path') and self.icon_path and hasattr(self, 'icon_label'):
            # No need to invert the icon, just load it normally regardless of theme
            icon_pixmap = QPixmap(self.icon_path)
            icon_height = 150
            aspect_ratio = icon_pixmap.width() / icon_pixmap.height()
            icon_width = int(icon_height * aspect_ratio)
            
            # Scale with high quality
            self.icon_label.setPixmap(icon_pixmap.scaled(
                icon_width, icon_height, 
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        
        # Update overlay background color if overlay exists
        if hasattr(self, 'overlay') and self.overlay:
            if theme_name == "light":
                # Light grey background for light theme with black border
                self.overlay.setStyleSheet("background-color: #E0E0E0; border: 3px solid #000000;")
            else:
                # Dark grey background for dark theme with black border
                self.overlay.setStyleSheet("background-color: #252525; border: 3px solid #000000;")
    
    def _get_section_style(self):
        """Return the stylesheet for section group boxes."""
        return """
            QGroupBox {
                border: 1.5px solid #666666;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 20px;
                padding-bottom: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 2px 10px;
                background-color: #3a3a3a;
                border: 1.5px solid #666666;
                border-radius: 8px;
                color: #ffffff;
            }
        """

    def create_monitoring_section(self, parent_layout):
        """Create the monitoring settings section."""
        monitor_frame = QFrame()
        monitor_layout = QHBoxLayout(monitor_frame)
        
        # Settings on the left
        monitor_settings = QFrame()
        settings_layout = QVBoxLayout(monitor_settings)
        settings_layout.setContentsMargins(0, 0, 0, 0)  # Remove any default margins
        
        group_box = QGroupBox("Monitoring")
        group_box.setStyleSheet(self._get_section_style())
        layout = QVBoxLayout()
        layout.setSpacing(1)  # Reduced from 10 to 1 for tighter grouping
        layout.setContentsMargins(15, 15, 15, 15)
        
        # PrintScreen monitoring
        self.monitor_print_screen_checkbox = QCheckBox("Monitor Print Screen")
        self.monitor_print_screen_checkbox.setToolTip("Does nothing because it all enters the clipboard anyway")
        layout.addWidget(self.monitor_print_screen_checkbox)
        
        # Ctrl+C monitoring
        self.monitor_ctrl_c_checkbox = QCheckBox("Monitor Ctrl+C")
        self.monitor_ctrl_c_checkbox.setToolTip("Why did I even make this optional?")
        layout.addWidget(self.monitor_ctrl_c_checkbox)
        
        # Auto refresh
        self.auto_refresh_checkbox = QCheckBox("Auto-Refresh Overlay On Clipboard Change")
        self.auto_refresh_checkbox.setObjectName("autoRefreshCheckbox")  # Add object name for reference
        self.auto_refresh_checkbox.setToolTip("Core feature that changes overlay images for you")
        layout.addWidget(self.auto_refresh_checkbox)
        
        # Minimize on startup
        self.minimize_on_startup_checkbox = QCheckBox("Minimize On Startup")
        layout.addWidget(self.minimize_on_startup_checkbox)
        
        group_box.setLayout(layout)
        settings_layout.addWidget(group_box)
        monitor_layout.addWidget(monitor_settings)
        
        # Icon on the right side - as large as the monitoring panel
        icon_frame = QFrame()
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setAlignment(Qt.AlignCenter)
        
        # First try to use the specified icon path
        icon_path = "D:\\Artwork\\ICONS\\GoldenTransparency.png"
        
        # Fallback to the default icon if the specified one doesn't exist
        if not os.path.exists(icon_path):
            icon_path = str(Path(os.path.dirname(os.path.abspath(__file__))) / "resources" / "icons" / "WWTS.ico")
        
        self.icon_label = QLabel()
        
        if os.path.exists(icon_path):
            # Store the path for later use when theme changes
            self.icon_path = icon_path
            # Calculate size based on the monitoring panel
            icon_pixmap = QPixmap(icon_path)
            # Make icon almost as tall as the monitor section, preserving aspect ratio
            icon_height = 150  # Approximate height to match monitoring panel
            aspect_ratio = icon_pixmap.width() / icon_pixmap.height()
            icon_width = int(icon_height * aspect_ratio)
            
            # Scale with high quality
            self.icon_label.setPixmap(icon_pixmap.scaled(
                icon_width, icon_height, 
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        else:
            # Fallback if no icon is found
            self.icon_label.setText("Icon not found")
            self.icon_path = None
        
        icon_layout.addWidget(self.icon_label)
        monitor_layout.addWidget(icon_frame)
        
        parent_layout.addWidget(monitor_frame)
        
    def create_overlay_section(self, parent_layout):
        """Create the overlay settings section."""
        group_box = QGroupBox("Overlay")
        group_box.setStyleSheet(self._get_section_style())
        layout = QVBoxLayout()
        layout.setSpacing(1)  # Reduced from 10 to 1 for tighter grouping
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Resize options
        layout.addWidget(QLabel("Resize Options:"))
        
        # Resize image to fit window
        self.resize_image_checkbox = QCheckBox("Resize Image To Fit Window")
        self.resize_image_checkbox.setChecked(self.settings.get("resize_image_to_fit", True))
        self.resize_image_checkbox.setToolTip("You don't wanna change this, you really don't.")
        layout.addWidget(self.resize_image_checkbox)
        
        # Scroll Wheel Resize option
        self.scroll_wheel_resize_checkbox = QCheckBox("Enable Scroll Wheel Resizing")
        self.scroll_wheel_resize_checkbox.setChecked(self.settings.get("scroll_wheel_resize", True))
        layout.addWidget(self.scroll_wheel_resize_checkbox)
        
        # Double Shift Capture option
        self.double_shift_capture_checkbox = QCheckBox("Enable Double Shift Image Capture")
        self.double_shift_capture_checkbox.setChecked(self.settings.get("double_shift_capture", False))
        layout.addWidget(self.double_shift_capture_checkbox)
        
        # Video Aware Capture option
        self.video_aware_capture_checkbox = QCheckBox("Save Entire Video Frames With Double Shift")
        self.video_aware_capture_checkbox.setChecked(self.settings.get("video_aware_capture", False))
        self.video_aware_capture_checkbox.setToolTip("When enabled, automatically detects video players and captures the entire video frame")
        # Connect the stateChanged signal to a handler that will also check the double shift checkbox
        self.video_aware_capture_checkbox.stateChanged.connect(self.on_video_aware_changed)
        layout.addWidget(self.video_aware_capture_checkbox)
        
        # Draw Capture Frame option
        self.draw_capture_frame_checkbox = QCheckBox("Draw Capture Frame")
        self.draw_capture_frame_checkbox.setChecked(self.settings.get("draw_capture_frame", False))
        self.draw_capture_frame_checkbox.setToolTip("Requires restart!\n\nWhen enabled, shows a blue outline around the area being captured with double shift for 0.3 seconds")
        layout.addWidget(self.draw_capture_frame_checkbox)
        
        # Double-shift capture size
        capture_size_layout = QHBoxLayout()
        
        # Add a "Double-shift capture size:" label with tooltip
        capture_size_label = QLabel("Double-Shift Capture Size:")
        capture_size_label.setToolTip("Set this especially large if you want to focus on video frames.")
        capture_size_layout.addWidget(capture_size_label)
        
        # Height input
        self.capture_height_input = QSpinBox()
        self.capture_height_input.setMinimum(50)
        self.capture_height_input.setMaximum(2000)
        self.capture_height_input.setValue(self.settings.get("capture_height", 400))
        capture_size_layout.addWidget(QLabel("Height:"))
        capture_size_layout.addWidget(self.capture_height_input)
        
        # Width input
        self.capture_width_input = QSpinBox()
        self.capture_width_input.setMinimum(50)
        self.capture_width_input.setMaximum(2000)
        self.capture_width_input.setValue(self.settings.get("capture_width", 500))
        capture_size_layout.addWidget(QLabel("Width:"))
        capture_size_layout.addWidget(self.capture_width_input)
        
        # Add stretch to push elements to the left
        capture_size_layout.addStretch(1)
        
        layout.addLayout(capture_size_layout)
        
        # Clickthrough option
        self.clickthrough_checkbox = QCheckBox("Allow Clicks To Pass Through Overlay")
        self.clickthrough_checkbox.setChecked(self.settings.get("clickthrough", False))
        self.clickthrough_checkbox.setToolTip("Requires Restart And Produces Naught But Sadness")
        layout.addWidget(self.clickthrough_checkbox)
        
        # Opacity
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:"))
        
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(self.settings.get("opacity", 77))
        self.opacity_slider.setTickPosition(QSlider.TicksBelow)
        self.opacity_slider.setTickInterval(10)
        self.opacity_slider.valueChanged.connect(self.update_opacity_label)
        self.opacity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #666666;
                height: 5px;
                background: #444444;
                margin: 0px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #666666;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #f0f0f0;
            }
        """)
        opacity_layout.addWidget(self.opacity_slider)
        
        self.opacity_value_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_value_label.setMinimumWidth(40)  # Ensure consistent width for the percentage
        opacity_layout.addWidget(self.opacity_value_label)
        
        layout.addLayout(opacity_layout)
        
        group_box.setLayout(layout)
        parent_layout.addWidget(group_box)
        
    def create_theme_section(self, parent_layout):
        """Create the theme settings section."""
        group_box = QGroupBox("Theme")
        group_box.setStyleSheet(self._get_section_style())
        layout = QVBoxLayout()
        layout.setSpacing(1)  # Reduced from 10 to 1 for tighter grouping
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Theme Selection
        theme_label = QLabel("Select theme:")
        layout.addWidget(theme_label)
        
        # Theme combobox
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark") 
        self.theme_combo.addItem("Auto (system)", "auto")
        
        # Set current theme
        current_theme = self.settings.get("theme", "dark")
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == current_theme:
                self.theme_combo.setCurrentIndex(i)
                break
                
        # Connect theme change signal
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        
        layout.addWidget(self.theme_combo)
        
        group_box.setLayout(layout)
        parent_layout.addWidget(group_box)
        
    def create_history_section(self, parent_layout):
        """Create the history settings section."""
        group_box = QGroupBox("History")
        group_box.setStyleSheet(self._get_section_style())
        layout = QVBoxLayout()
        layout.setSpacing(1)  # Reduced from 10 to 1 for tighter grouping
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Save to history checkbox
        self.save_history_checkbox = QCheckBox("Save Images To History")
        self.save_history_checkbox.setChecked(self.settings.get("save_history", False))
        self.save_history_checkbox.stateChanged.connect(self.save_history_changed)
        layout.addWidget(self.save_history_checkbox)
        
        # History folder path with size display and open button
        folder_layout = QHBoxLayout()
        
        # Add a "History Footprint:" label
        folder_layout.addWidget(QLabel("History Footprint:"))
        
        # History folder size label (now with reduced width)
        self.history_folder_label = QLabel("0.00 GB")
        self.history_folder_label.setObjectName("history_folder_label")  # Add ID for CSS styling
        self.history_folder_label.setFixedWidth(300)  # Wide enough for "YOU KNOW WHAT YOU DID"
        self.history_folder_label.setCursor(Qt.PointingHandCursor)
        self.history_folder_label.mousePressEvent = self.on_history_label_click
        folder_layout.addWidget(self.history_folder_label)
        
        # Add "Open" button
        self.open_history_button = QPushButton("Open")
        self.open_history_button.setCursor(Qt.PointingHandCursor)
        self.open_history_button.clicked.connect(self.open_history_folder)
        folder_layout.addWidget(self.open_history_button)
        
        # Add "Sort" button
        self.sort_history_button = QPushButton("Sort")
        self.sort_history_button.setCursor(Qt.PointingHandCursor)
        self.sort_history_button.clicked.connect(self.sort_history_files)
        folder_layout.addWidget(self.sort_history_button)
        
        # Add a stretch to push everything to the left
        folder_layout.addStretch(1)
        
        layout.addLayout(folder_layout)
        
        group_box.setLayout(layout)
        parent_layout.addWidget(group_box)
        
        # Update folder size initially
        self.update_history_size()
    
    def get_folder_size(self, folder_path):
        """Calculate the total size of a folder in GB."""
        total_size = 0
        try:
            if os.path.exists(folder_path):
                for dirpath, dirnames, filenames in os.walk(folder_path):
                    for filename in filenames:
                        try:
                            file_path = os.path.join(dirpath, filename)
                            if os.path.exists(file_path):  # Ensure file still exists
                                total_size += os.path.getsize(file_path)
                        except Exception as e:
                            # Skip problematic files but log the error
                            logging.warning(f"Error getting size for file {filename}: {e}")
                            continue
            
            # Convert to GB with 2 decimal places
            size_gb = total_size / (1024 * 1024 * 1024)
            return f"{size_gb:.2f} GB"
        except Exception as e:
            logging.error(f"Error calculating folder size: {e}")
            return "0.00 GB"
    
    def _create_styled_message_box(self, title, message, icon=QMessageBox.Information):
        """Create a styled message box with no title bar and thin white border."""
        msg = QMessageBox()
        msg.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2d2d2d;
                border: 1px solid white;
                color: white;
            }
            QLabel {
                color: white;
                padding: 10px;
            }
            QPushButton {
                background-color: #3e3e3e;
                color: white;
                border: 1px solid #555;
                padding: 5px 15px;
                min-width: 80px;
            }
            QPushButton:hover {
            }
        """)
        msg.setIcon(icon)
        msg.setText(message)
        msg.setWindowTitle(title)
        return msg

    def _unload_current_image(self):
        """
        Completely unload the current image from the overlay, ensuring all resources are released.
        This is important before performing file operations on the image files.
        """
        if not hasattr(self, 'overlay'):
            return
            
        try:
            # Clear any animation timers first
            if hasattr(self.overlay, 'animation_timer') and self.overlay.animation_timer.isActive():
                self.overlay.animation_timer.stop()
            
            # Clear GIF frames if they exist
            if hasattr(self.overlay, 'gif_frames'):
                self.overlay.gif_frames = []
                
            # Clear the current image and pixmap
            if hasattr(self.overlay, 'original_image'):
                self.overlay.original_image = None
                
            if hasattr(self.overlay, 'pixmap'):
                self.overlay.pixmap = None
                
            # Clear the image label safely
            if hasattr(self.overlay, 'image_label') and self.overlay.image_label:
                try:
                    self.overlay.image_label.clear()
                    # Create an empty QPixmap instead of passing None
                    from PyQt5.QtGui import QPixmap
                    empty_pixmap = QPixmap()
                    self.overlay.image_label.setPixmap(empty_pixmap)
                except Exception as e:
                    logging.debug(f"Error clearing image label: {e}")
            
            # Clear the current file path
            if hasattr(self.overlay, 'current_file_path'):
                self.overlay.current_file_path = None
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Force update the display multiple times to ensure all events are processed
            for _ in range(3):
                QApplication.processEvents()
                time.sleep(0.1)
                
        except Exception as e:
            logging.error(f"Error in _unload_current_image: {e}")
            # Don't re-raise the exception to prevent crashes during sorting
            pass
    
    def _get_sorted_files(self, history_folder):
        """Get all files in the history folder sorted by their numerical prefix.
        
        Returns:
            List of tuples: (dir_path, counter, _, extension, is_temporary, full_path)
            Note: The third element is kept for backward compatibility but will be None
        """
        import re
        
        files = []
        total_files = 0
        matched_files = 0
        
        logging.info(f"Scanning for files in: {history_folder}")
        
        for root, _, filenames in os.walk(history_folder):
            # Skip temporary sort directories
            if 'wwts_sort_' in root:
                continue
                
            for filename in filenames:
                total_files += 1
                base_name, ext = os.path.splitext(filename)
                ext = ext.lower().lstrip('.')
                
                # Skip non-image files
                if ext not in ('png', 'jpg', 'jpeg', 'gif', 'bmp'):
                    continue
                
                # Check if it's a temporary file
                is_temporary = base_name.endswith('_T')
                if is_temporary:
                    base_name = base_name[:-2]  # Remove _T suffix
                
                # Extract counter (should be the entire base_name if it's a number)
                counter = 0
                try:
                    counter = int(base_name)
                except ValueError:
                    # If not a number, assign a high number to put it at the end
                    counter = 9999 + total_files
                
                full_path = os.path.join(root, filename)
                files.append((root, counter, None, ext, is_temporary, full_path))
                matched_files += 1
        
        logging.info(f"Found {matched_files} matching files out of {total_files} total files")
        
        # Sort by counter to maintain original order
        files.sort(key=lambda x: x[1])
        return files
    
    def _safe_rename(self, src, dst, max_attempts=3, delay=0.5):
        """Safely rename a file with retries and error handling."""
        import shutil
        import time
        
        attempts = 0
        last_error = None
        
        while attempts < max_attempts:
            try:
                # Try to rename the file
                if os.path.exists(dst):
                    # If destination exists, remove it first
                    if os.path.isfile(dst):
                        os.unlink(dst)
                    else:
                        shutil.rmtree(dst)
                
                # Perform the rename
                os.rename(src, dst)
                return True
                
            except (OSError, PermissionError, IOError) as e:
                last_error = e
                attempts += 1
                if attempts < max_attempts:
                    time.sleep(delay)
                    # Force garbage collection and process events between attempts
                    import gc
                    gc.collect()
                    QApplication.processEvents()
        
        logging.error(f"Failed to rename {src} to {dst} after {max_attempts} attempts: {last_error}")
        return False

    def _rename_files_with_sequential_numbers(self, files):
        """Rename files with sequential numbers in the format 0000.filetype
        
        Args:
            files: List of tuples containing (dir_path, counter, random_suffix, ext, is_temporary, old_path)
            
        Returns:
            List of tuples (old_path, new_path) for all renamed files
        """
        import shutil
        
        renamed_files = []
        seen_paths = set()
        
        # First pass: Generate all target paths and check for conflicts
        path_mapping = {}
        
        for idx, (dir_path, _, _, ext, is_temporary, old_path) in enumerate(files):
            # Skip temporary files that should be deleted
            if is_temporary:
                continue
                
            # Generate new filename with sequential number (0000.filetype format)
            new_filename = f"{idx:04d}.{ext}"
            new_path = os.path.join(dir_path, new_filename)
            
            # If the file is already in the right place, skip it
            if os.path.normpath(old_path) == os.path.normpath(new_path):
                seen_paths.add(new_path.lower())
                continue
                
            # Make sure we don't have duplicate target paths
            if new_path.lower() in seen_paths:
                # If we hit a duplicate, find the next available number
                counter = idx + 1
                while True:
                    new_filename = f"{counter:04d}.{ext}"
                    new_path = os.path.join(dir_path, new_filename)
                    if not os.path.exists(new_path) and new_path.lower() not in seen_paths:
                        break
                    counter += 1
                    if counter > 9999:
                        raise RuntimeError("Maximum number of files (9999) reached in the directory")
            
            seen_paths.add(new_path.lower())
            path_mapping[old_path] = new_path
        
        # Second pass: Perform the renames in a safe way
        for old_path, new_path in path_mapping.items():
            try:
                # If target exists and is different from source, handle it
                if os.path.exists(new_path) and os.path.normpath(old_path) != os.path.normpath(new_path):
                    # If it's the same file (case-insensitive), skip it
                    if old_path.lower() == new_path.lower():
                        continue
                        
                    # Otherwise, generate a temporary name in the same directory
                    temp_path = f"{new_path}.tmp"
                    counter = 1
                    while os.path.exists(temp_path):
                        temp_path = f"{new_path}.{counter}.tmp"
                        counter += 1
                    
                    # Move the existing file out of the way
                    shutil.move(new_path, temp_path)
                    
                    try:
                        # Now move the new file into place
                        shutil.move(old_path, new_path)
                        renamed_files.append((old_path, new_path))
                        
                        # If we successfully moved the new file, remove the old one
                        try:
                            os.remove(temp_path)
                        except OSError as e:
                            logging.warning(f"Could not remove temporary file {temp_path}: {e}")
                            
                    except Exception as e:
                        # If moving the new file failed, restore the old one
                        logging.error(f"Error moving {old_path} to {new_path}: {e}")
                        if os.path.exists(temp_path):
                            shutil.move(temp_path, new_path)
                        continue
                else:
                    # No conflict, just rename the file
                    try:
                        shutil.move(old_path, new_path)
                        renamed_files.append((old_path, new_path))
                    except Exception as e:
                        logging.error(f"Error moving {old_path} to {new_path}: {e}")
                        continue
                        
            except Exception as e:
                logging.error(f"Error processing {old_path}: {e}")
                continue
                
        return renamed_files
    def sort_history_files(self):
        """Sort and rename history files to ensure sequential numbering."""
        import tempfile
        import shutil
        import time
        
        # Track the current image path before sorting to reload it after
        current_image_path = None
        if hasattr(self, 'overlay') and hasattr(self.overlay, 'current_file_path') and self.overlay.current_file_path:
            current_image_path = self.overlay.current_file_path
            logging.info(f"Tracking current image for reload: {current_image_path}")
        
        # Check if history folder exists
        if not os.path.exists(self.settings.history_folder):
            msg = self._create_styled_message_box("Error", "History folder does not exist.")
            msg.exec_()
            return
            
        # Check if we have access to overlay and history_db
        if not hasattr(self, 'overlay') or not hasattr(self.overlay, 'history_db') or not self.overlay.history_db:
            msg = self._create_styled_message_box(
                "Error", 
                "Could not access history database.\nPlease ensure history is enabled in settings.",
                QMessageBox.Warning
            )
            msg.exec_()
            return
        
        # Close any existing database connection
        if hasattr(self.overlay.history_db, '_connection') and self.overlay.history_db._connection:
            try:
                self.overlay.history_db._connection.close()
            except Exception as e:
                logging.error(f"Error closing existing connection: {e}")
            self.overlay.history_db._connection = None
            
        # Get database connection for the operation
        conn = None
        cursor = None
        renamed_files = []
        
        try:
            conn = self.overlay.history_db._get_connection()
            cursor = conn.cursor()
            cursor.execute('BEGIN TRANSACTION')

            # Get all files, ordered by timestamp
            cursor.execute('''
                SELECT id, file_path, is_temporary 
                FROM images 
                WHERE is_temporary = 0 OR ? = 1
                ORDER BY timestamp
            ''', (int(self.save_history_checkbox.isChecked()),))

            db_files = cursor.fetchall()

            if not db_files:
                conn.rollback()
                msg = self._create_styled_message_box("Sort Complete", "No files to sort in the database.")
                msg.exec_()
                return

            # Get all files from the filesystem
            sorted_files = self._get_sorted_files(self.settings.history_folder)

            if not sorted_files:
                conn.rollback()
                msg = self._create_styled_message_box("Sort Complete", "No files found to sort.")
                msg.exec_()
                return

            # Rename files with sequential numbers
            renamed_files = self._rename_files_with_sequential_numbers(sorted_files)

            if not renamed_files:
                conn.rollback()
                msg = self._create_styled_message_box("Sort Complete", "No files needed to be renamed.")
                msg.exec_()
                return

            # Update the database with new file paths
            for old_path, new_path in renamed_files:
                try:
                    cursor.execute('''
                        UPDATE images 
                        SET file_path = ? 
                        WHERE file_path = ?
                    ''', (new_path, old_path))
                except sqlite3.Error as e:
                    logging.error(f"Error updating database for {old_path}: {e}")

            # Commit all changes
            conn.commit()

            # Reload the current image if there was one
            if current_image_path:
                # Find the new path for the current image
                for old_path, new_path in renamed_files:
                    if old_path == current_image_path:
                        current_image_path = new_path
                        break

                # Try to reload the image
                if hasattr(self.overlay, 'load_image'):
                    try:
                        self.overlay.load_image(current_image_path)
                    except Exception as e:
                        logging.error(f"Error reloading image: {e}")

            # Show success message
            msg = self._create_styled_message_box(
                "Sort Complete", 
                f"Successfully renamed {len(renamed_files)} files."
            )
            msg.exec_()

        except Exception as e:
            if conn:
                conn.rollback()
            logging.error(f"Error during sort operation: {e}")
            msg = self._create_styled_message_box(
                "Sort Error", 
                f"An error occurred during sorting: {str(e)}",
                QMessageBox.Critical
            )
            msg.exec_()

        finally:
            # Ensure connection is closed
            if 'conn' in locals() and conn:
                try:
                    conn.close()
                except Exception as e:
                    logging.warning(f"Error closing connection: {e}")
            
            # Ensure temp directory is cleaned up
            if 'temp_dir' in locals() and temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as cleanup_error:
                    logging.warning(f"Failed to clean up temporary directory on error: {cleanup_error}")
            
            # Clean up any remaining temporary files
            if 'path_mapping' in locals() and 'temp_dir' in locals():
                self._cleanup_temp_files(path_mapping, temp_dir)

    def _cleanup_temp_files(self, path_mapping, temp_dir):
        """Clean up temporary files and directories after an error."""
        try:
            # Remove all files in the temp directory
            for file_id, (temp_path, new_path, _) in path_mapping.items():
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception as e:
                        logging.error(f"Error removing temp file {temp_path}: {e}")
            
            # Remove the temp directory if empty
            try:
                os.rmdir(temp_dir)
            except:
                pass
        except Exception as e:
            logging.error(f"Error during temp file cleanup: {e}")

    def _restore_files(self, path_mapping, updated_paths, temp_dir):
        """Attempt to restore files to their original locations after a failed sort operation."""
        try:
            # First, move any updated files back to their temp locations
            for file_id, new_path in updated_paths.items():
                if file_id in path_mapping:
                    temp_path = path_mapping[file_id][0]
                    if os.path.exists(new_path) and not os.path.exists(temp_path):
                        if not self._copy_file(new_path, temp_path):
                            logging.error(f"Failed to restore {new_path} to {temp_path}")
            
            # Then move all files back to their original locations
            for file_id, (temp_path, new_path, _) in path_mapping.items():
                if os.path.exists(temp_path):
                    old_path = path_mapping[file_id][1] if file_id in path_mapping else None
                    if old_path and not os.path.exists(old_path):
                        if not self._copy_file(temp_path, old_path):
                            logging.error(f"Failed to restore {temp_path} to {old_path}")
            
            # Clean up temp directory if empty
            self._cleanup_temp_files(path_mapping, temp_dir)
                
        except Exception as e:
            logging.error(f"Error during file restoration: {e}")
            self._cleanup_temp_files(path_mapping, temp_dir)
    
    def update_history_size(self):
        """Update the history folder size label."""
        try:
            # Get the history folder path using the property
            history_folder = self.settings.history_folder
            logging.info(f"Checking history folder size: {history_folder}")
            
            if os.path.exists(history_folder):
                size = self.get_folder_size(history_folder)
                self.history_folder_label.setText(f"{size}")
            else:
                logging.warning(f"History folder does not exist: {history_folder}")
                self.history_folder_label.setText("0.00 GB")
        except Exception as e:
            logging.error(f"Error checking history folder size: {e}")
            self.history_folder_label.setText("0.00 GB")
    
    def on_history_label_click(self, event):
        """Handle click on history folder label."""
        try:
            # Make the text bold and all caps
            self.history_folder_label.setText("<b>YOU KNOW WHAT YOU DID</b>")
            
            # Simply reset after 2 seconds
            QTimer.singleShot(2000, self.update_history_size)
        except Exception as e:
            logging.error(f"Error in history label click: {e}")
            # Fallback to simple text update
            self.history_folder_label.setText("Error")
            QTimer.singleShot(2000, self.update_history_size)
    
    def open_history_folder(self):
        """Open the history folder in the file explorer."""
        try:
            # Get the history folder path using the property
            history_folder = self.settings.history_folder
            logging.info(f"Opening history folder: {history_folder}")
            
            if os.path.exists(history_folder):
                if platform.system() == "Windows":
                    os.startfile(history_folder)
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", history_folder])
                else:  # Linux and other Unix-like
                    subprocess.run(["xdg-open", history_folder])
            else:
                logging.error(f"History folder does not exist: {history_folder}")
                QMessageBox.warning(self, "Folder Not Found", 
                                  "The history folder could not be found. It may have been moved or deleted.")
        except Exception as e:
            logging.error(f"Error opening history folder: {e}")
            QMessageBox.critical(self, "Error", f"Could not open history folder: {e}")
    
    def update_opacity_label(self, value):
        """Update the opacity label and apply to overlay immediately."""
        self.opacity_value_label.setText(f"{value}%")
        
        # Update overlay opacity in real-time if overlay exists
        if self.overlay:
            self.overlay.update_opacity(value)
    
    def load_settings(self):
        """Load current settings into UI elements."""
        try:
            # Monitoring
            self.monitor_print_screen_checkbox.setChecked(self.settings.get("monitor_print_screen", True))
            self.monitor_ctrl_c_checkbox.setChecked(self.settings.get("monitor_ctrl_c", True))
            self.auto_refresh_checkbox.setChecked(self.settings.get("auto_refresh", True))
            self.minimize_on_startup_checkbox.setChecked(self.settings.get("minimize_on_startup", False))
            
            # Overlay
            self.resize_image_checkbox.setChecked(self.settings.get("resize_image_to_fit", True))
            self.scroll_wheel_resize_checkbox.setChecked(self.settings.get("scroll_wheel_resize", True))
            self.double_shift_capture_checkbox.setChecked(self.settings.get("double_shift_capture", True))
            self.video_aware_capture_checkbox.setChecked(self.settings.get("video_aware_capture", False))
            self.draw_capture_frame_checkbox.setChecked(self.settings.get("draw_capture_frame", False))
            self.clickthrough_checkbox.setChecked(self.settings.get("clickthrough", False))
            self.opacity_slider.setValue(self.settings.get("opacity", 77))
            self.update_opacity_label(self.opacity_slider.value())
            
            # Theme
            theme_value = self.settings.get("theme", "dark")
            # Find the index for the theme value
            for i in range(self.theme_combo.count()):
                if self.theme_combo.itemData(i) == theme_value:
                    self.theme_combo.setCurrentIndex(i)
                    break
            
            # History
            self.save_history_checkbox.setChecked(self.settings.get("save_history", False))
            
            # We don't display the actual history folder path anymore
            # Just ensure it's set correctly in the settings
            history_folder = self.settings.get("history_folder", "")
            if not history_folder:
                # Set default history folder
                history_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'history')
                self.settings.set("history_folder", history_folder)
        
        except Exception as e:
            logging.error(f"Error loading settings: {e}")
    
    def save_settings(self):
        """Save settings from UI elements."""
        try:
            # Monitoring
            self.settings.set("monitor_print_screen", self.monitor_print_screen_checkbox.isChecked())
            self.settings.set("monitor_ctrl_c", self.monitor_ctrl_c_checkbox.isChecked())
            self.settings.set("auto_refresh", self.auto_refresh_checkbox.isChecked())
            self.settings.set("minimize_on_startup", self.minimize_on_startup_checkbox.isChecked())
            
            # Overlay
            self.settings.set("resize_image_to_fit", self.resize_image_checkbox.isChecked())
            self.settings.set("scroll_wheel_resize", self.scroll_wheel_resize_checkbox.isChecked())
            self.settings.set("double_shift_capture", self.double_shift_capture_checkbox.isChecked())
            self.settings.set("video_aware_capture", self.video_aware_capture_checkbox.isChecked())
            self.settings.set("draw_capture_frame", self.draw_capture_frame_checkbox.isChecked())
            self.settings.set("clickthrough", self.clickthrough_checkbox.isChecked())
            self.settings.set("opacity", self.opacity_slider.value())
            
            # Theme
            theme_index = self.theme_combo.currentIndex()
            theme_value = self.theme_combo.itemData(theme_index)
            self.settings.set("theme", theme_value)
            
            # History
            self.settings.set("save_history", self.save_history_checkbox.isChecked())
            
            # Save capture size settings
            self.settings.set("capture_height", self.capture_height_input.value())
            self.settings.set("capture_width", self.capture_width_input.value())
            
            # Save settings to file
            self.settings.save_settings()
            
            # Apply settings to overlay
            if self.overlay:
                self.apply_settings_to_overlay()
            
            # Show feedback (optional)
            self.save_button.setText("Saved!")
            QTimer.singleShot(1000, lambda: self.save_button.setText("Save"))
            
        except Exception as e:
            logging.error(f"Error saving settings: {e}")
    
    def reset_to_defaults(self):
        """Reset all settings to default values."""
        # Set default values
        self.monitor_print_screen_checkbox.setChecked(True)
        self.monitor_ctrl_c_checkbox.setChecked(True)
        self.auto_refresh_checkbox.setChecked(True)
        self.minimize_on_startup_checkbox.setChecked(False)
        if hasattr(self, 'resize_image_checkbox'):
            self.resize_image_checkbox.setChecked(True)
        if hasattr(self, 'scroll_wheel_resize_checkbox'):
            self.scroll_wheel_resize_checkbox.setChecked(True)
        if hasattr(self, 'double_shift_capture_checkbox'):
            self.double_shift_capture_checkbox.setChecked(True)  # Enable double-shift capture
        if hasattr(self, 'video_aware_capture_checkbox'):
            self.video_aware_capture_checkbox.setChecked(True)  # Enable video aware capture
        if hasattr(self, 'draw_capture_frame_checkbox'):
            self.draw_capture_frame_checkbox.setChecked(True)  # Enable draw capture frame
        if hasattr(self, 'clickthrough_checkbox'):
            self.clickthrough_checkbox.setChecked(False)
        if hasattr(self, 'opacity_slider'):
            self.opacity_slider.setValue(77)
        # Set theme to Dark (index 0 is Dark, 1 is Light, 2 is Auto)
        self.theme_combo.setCurrentIndex(0)
        self.apply_theme("dark")  # Ensure dark theme is applied immediately
        self.save_history_checkbox.setChecked(False)
        
    def minimize_to_tray(self):
        """Hide the settings window."""
        self.hide()
        
    def showEvent(self, event):
        """Handle window show event."""
        super().showEvent(event)
        self.setup_connections()
        
        # Update the history size when window is shown
        try:
            self.update_history_size()
        except Exception as e:
            logging.error(f"Error updating history size in showEvent: {e}")
        
    def closeEvent(self, event):
        """Handle window close event."""
        # Save window position
        self.settings.set("settings_window_x", self.pos().x())
        self.settings.set("settings_window_y", self.pos().y())
        
        # Clean up resources
        self.deleteLater()
        
        # Accept the event
        event.accept()
    
    def apply_settings_to_overlay(self):
        """Apply current settings to the overlay."""
        if not self.overlay:
            return
            
        # Apply clickthrough
        if self.settings.get("clickthrough", False):
            self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        else:
            self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            
        # Apply opacity
        opacity = self.settings.get("opacity", 77)
        self.overlay.update_opacity(opacity)

    def toggle_overlay(self):
        """Toggle the overlay visibility and update button text."""
        if not self.overlay:
            return
            
        if self.overlay.isVisible():
            # Hide the overlay
            self.overlay.hide()
            self.toggle_overlay_button.setText("Open Overlay")
        else:
            # Show the overlay
            self.overlay.show()
            self.toggle_overlay_button.setText("Hide Overlay")
            
    def setup_connections(self):
        """Set up signal/slot connections for UI elements."""
        # Update toggle button text based on overlay visibility when the settings window is shown
        if self.overlay:
            button_text = "Hide Overlay" if self.overlay.isVisible() else "Open Overlay"
            self.toggle_overlay_button.setText(button_text)
            
        # Connect theme combo box to theme change
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        
        # Connect video aware capture checkbox to on_video_aware_changed
        if hasattr(self, 'video_aware_capture_checkbox'):
            self.video_aware_capture_checkbox.stateChanged.connect(self.on_video_aware_changed)
            
        # Connect auto-refresh checkbox to update the overlay's context menu
        if hasattr(self, 'auto_refresh_checkbox'):
            self.auto_refresh_checkbox.stateChanged.connect(self._on_auto_refresh_changed)
    
    def _on_auto_refresh_changed(self, state):
        """Handle auto-refresh checkbox state change and update the overlay's context menu."""
        if hasattr(self, 'overlay') and self.overlay:
            # Get the current state from the checkbox
            new_value = (state == Qt.Checked)
            # Update the settings
            self.settings.set("auto_refresh", new_value)
            # Ensure the overlay's context menu is updated
            if hasattr(self.overlay, '_update_context_menu'):
                self.overlay._update_context_menu()
    
    def on_video_aware_changed(self, state):
        """Handle Video Aware Capture checkbox state change."""
        # If Video Aware Capture is checked, ensure Double Shift Capture is also checked
        if state == Qt.Checked and hasattr(self, 'double_shift_capture_checkbox'):
            self.double_shift_capture_checkbox.setChecked(True)
    
    def on_theme_changed(self, index):
        """Handle theme selection change."""
        theme_value = self.theme_combo.itemData(index)
        
        # Apply the theme
        self.apply_theme(theme_value)
        
        # Store the theme setting
        self.settings.set("theme", theme_value)
        
        # Apply theme to overlay if it exists
        if self.overlay:
            if theme_value == "dark":
                self.overlay.setStyleSheet("background-color: #252525; border: 4px solid #000000 !important;")
            elif theme_value == "light":
                self.overlay.setStyleSheet("background-color: #f0f0f0; border: 4px solid #cccccc !important;")
            else:  # Auto
                # Determine system theme and apply appropriate style
                palette = QApplication.palette()
                if palette.color(QPalette.Window).lightness() < 128:  # Dark theme
                    self.overlay.setStyleSheet("background-color: #252525; border: 4px solid #000000 !important;")
                else:  # Light theme
                    self.overlay.setStyleSheet("background-color: #f0f0f0; border: 4px solid #cccccc !important;")
    
    def save_history_changed(self, state):
        """Handle save history checkbox state change."""
        is_checked = state == Qt.Checked
        self.settings.set("save_history", is_checked)
        
        # Update UI elements based on the setting
        if hasattr(self, 'history_path_field'):
            self.history_path_field.setEnabled(is_checked)
            
        # Update history size display
        self.update_history_size()
    
    def show_about_dialog(self):
        """Show the about dialog."""
        theme = self.settings.get("theme", "Dark")
        dark_theme = (theme == "Dark")
        dialog = AboutDialog(self, dark_theme)
        dialog.exec_()
    
    def create_button_section(self, parent_layout):
        """Create the button section at the bottom of the settings."""
        buttons_layout = QHBoxLayout()
        
        # About button (round with question mark)
        self.about_button = RoundButton("?")
        self.about_button.setToolTip("About WWTS")
        self.about_button.clicked.connect(self.show_about_dialog)
        buttons_layout.addWidget(self.about_button)
        
        # Default button (round with D)
        self.default_button = RoundButton("D")
        self.default_button.setToolTip("Reset to default settings")
        self.default_button.clicked.connect(self.reset_to_defaults)
        buttons_layout.addWidget(self.default_button)
        
        # Add spacer to push save/cancel to right
        buttons_layout.addStretch(1)
        
        # Save Button (with darker grey)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("save_button")  # Set ID for stylesheet
        self.save_button.clicked.connect(self.save_settings)
        self.save_button.setCursor(Qt.PointingHandCursor)
        buttons_layout.addWidget(self.save_button)
        
        # Toggle Overlay Button
        self.toggle_overlay_button = QPushButton("Hide Overlay")
        self.toggle_overlay_button.clicked.connect(self.toggle_overlay)
        self.toggle_overlay_button.setCursor(Qt.PointingHandCursor)
        buttons_layout.addWidget(self.toggle_overlay_button)
        
        # Minimize Button - hides settings window to system tray
        self.minimize_button = QPushButton("Minimize")
        self.minimize_button.clicked.connect(self.minimize_to_tray)
        self.minimize_button.setCursor(Qt.PointingHandCursor)
        buttons_layout.addWidget(self.minimize_button)
        
        parent_layout.addLayout(buttons_layout)

class AboutDialog(QDialog):
    """A themed dialog showing information about the application."""
    
    def __init__(self, parent=None, dark_theme=True):
        super().__init__(parent, Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.dark_theme = dark_theme
        self.setFixedSize(450, 400)
        
        # Set window title
        self.setWindowTitle("About WWTS")
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Apply theme
        self.apply_theme()
        
        # Initialize UI
        self.init_ui()
        
        # Center on parent
        if parent:
            self.move(parent.x() + parent.width()//2 - self.width()//2,
                     parent.y() + parent.height()//2 - self.height()//2)
    
    def apply_theme(self):
        """Apply the current theme to the dialog."""
        if self.dark_theme:
            # Set dark theme with explicit colors
            style = """
                QDialog {
                    background-color: #2d2d2d;
                    color: white;

                }
                QLabel {
                    color: white;
                }
                QPushButton {
                    background-color: #3e3e3e;
                    color: white;
                    border: 1px solid #555555;
                    padding: 5px 10px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
                QPushButton:pressed {
                    background-color: #333333;
                }
            """
            self.setStyleSheet(style)
            
            # Set palette for better color consistency
            palette = self.palette()
            palette.setColor(palette.Window, QColor(45, 45, 45))
            palette.setColor(palette.WindowText, Qt.white)
            palette.setColor(palette.Button, QColor(62, 62, 62))
            palette.setColor(palette.ButtonText, Qt.white)
            palette.setColor(palette.Text, Qt.white)
            self.setPalette(palette)

        
    def init_ui(self):
        """Initialize the user interface."""
        layout = self.layout()
        
        # Add title with version
        title = QLabel("WWTS")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Add version info
        version = QLabel("Version 1.0.0")
        version.setAlignment(Qt.AlignCenter)
        version_font = QFont()
        version_font.setItalic(True)
        version.setFont(version_font)
        layout.addWidget(version)
        
        # Add vertical spacer
        layout.addItem(QSpacerItem(20, 15, QSizePolicy.Minimum, QSizePolicy.Fixed))
        
        # Add content text
        content = QLabel(
            "Made for my own shitty memories, shared freely for yours.\n"
            "You can always donate to my dumbass though or buy my shitty literature."
        )
        content.setAlignment(Qt.AlignCenter)
        content.setWordWrap(True)
        content.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(content)
        
        # Add vertical spacer
        layout.addItem(QSpacerItem(20, 15, QSizePolicy.Minimum, QSizePolicy.Fixed))
        
        # Create buttons grid
        buttons_grid = QGridLayout()
        buttons_grid.setSpacing(10)
        buttons_grid.setColumnStretch(0, 1)
        buttons_grid.setColumnStretch(1, 1)
        
        # PayPal button
        paypal_button = QPushButton("PayPal")
        paypal_button.setToolTip("Donate via PayPal")
        paypal_button.clicked.connect(lambda: self.open_url(
            "https://www.paypal.com/donate/?business=UBZJY8KHKKLGC&no_recurring=0&item_name=Why+are+you+doing+this?+Are+you+drunk?+&currency_code=USD"
        ))
        buttons_grid.addWidget(paypal_button, 0, 0)
        
        # Goodreads button
        goodreads_button = QPushButton("Goodreads")
        goodreads_button.setToolTip("Check out our book on Goodreads")
        goodreads_button.clicked.connect(lambda: self.open_url(
            "https://www.goodreads.com/book/show/25006763-usu"
        ))
        buttons_grid.addWidget(goodreads_button, 0, 1)
        
        # Amazon button
        amazon_button = QPushButton("Amazon")
        amazon_button.setToolTip("Check out our book on Amazon")
        amazon_button.clicked.connect(lambda: self.open_url(
            "https://www.amazon.com/Usu-Jayde-Ver-Elst-ebook/dp/B00V8A5K7Y"
        ))
        buttons_grid.addWidget(amazon_button, 1, 0)
        
        # GitHub button
        github_button = QPushButton("GitHub")
        github_button.setToolTip("Visit Basjohn's GitHub page")
        github_button.clicked.connect(lambda: self.open_url(
            "https://github.com/Basjohn"
        ))
        buttons_grid.addWidget(github_button, 1, 1)
        
        layout.addLayout(buttons_grid)
        
        # Add OK button at the bottom
        ok_button = QPushButton("OK")
        ok_button.setFixedWidth(120)
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
    def mousePressEvent(self, event):
        """Allow dragging the dialog."""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Move the dialog when dragged."""
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
            
    def open_url(self, url):
        """Open a URL in the default browser."""
        QDesktopServices.openUrl(QUrl(url))

class RoundButton(QPushButton):
    """A custom button that is guaranteed to be circular."""
    
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(30, 30)
        self.setStyleSheet("""
            background-color: #555555;
            color: white;
            font-weight: bold;
            font-size: 14px;
            border: none;
        """)
        self.setCursor(Qt.PointingHandCursor)
    
    def paintEvent(self, event):
        """Override paint event to draw a circular button."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw the circular background
        painter.setBrush(QColor(self.palette().color(QPalette.Button)))
        painter.setPen(Qt.NoPen)
        
        # Adjust color for hover/pressed states
        if self.underMouse():
            painter.setBrush(QColor("#666666"))
            if self.isDown():
                painter.setBrush(QColor("#444444"))
        else:
            painter.setBrush(QColor("#555555"))
            
        painter.drawEllipse(0, 0, self.width(), self.height())
        
        # Draw text
        painter.setPen(QColor("white"))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())
