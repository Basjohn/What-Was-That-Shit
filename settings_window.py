import logging
import os
import subprocess
import platform
from pathlib import Path
from PyQt5.QtCore import (
    Qt, QTimer, QSize, QPoint, QEvent, QPropertyAnimation, 
    QSequentialAnimationGroup, QAbstractAnimation, pyqtProperty as Property,
    QUrl
)
from PyQt5.QtGui import (
    QColor, QPalette, QDesktopServices, QPixmap, QPainter, QIcon
)
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, 
    QSlider, QComboBox, QPushButton, QGroupBox, QFormLayout,
    QFileDialog, QToolTip, QWidget, QSpacerItem, QSizePolicy,
    QFrame, QGraphicsOpacityEffect, QApplication, QMessageBox, QLineEdit, QSpinBox,
    QTextBrowser
)

class SettingsWindow(QDialog):
    def __init__(self, settings, overlay=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.overlay = overlay
        # Remove the default titlebar and context help button
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setResult(0)
        self.init_ui()
        self.load_settings()
        
        # For window dragging
        self.dragging = False
        self.drag_position = None
        
    def init_ui(self):
        """Initialize the UI components."""
        self.setMinimumSize(400, 450)
        
        # Set theme based on settings
        self.apply_theme(self.settings.get("theme", "dark"))
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        self.setLayout(main_layout)
        
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
    
    def create_custom_title_bar(self):
        """Create a custom title bar with close button."""
        title_bar = QFrame()
        title_bar.setMinimumHeight(60)  # Increased by 50%
        title_bar.setMaximumHeight(60)  # Increased by 50%
        title_bar.setObjectName("title_bar")  # Add ID for CSS styling
        
        # Use horizontal layout for the title bar
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(20, 0, 15, 0)  # Added more left padding
        title_layout.setSpacing(10)
        
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
                background-color: #2D2D30;
                color: #FFFFFF;
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
                background-color: #D2D2CF;
                color: #000000;
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
    
    def create_monitoring_section(self, parent_layout):
        """Create the monitoring settings section."""
        monitor_frame = QFrame()
        monitor_layout = QHBoxLayout(monitor_frame)
        
        # Settings on the left
        monitor_settings = QFrame()
        settings_layout = QVBoxLayout(monitor_settings)
        
        group_box = QGroupBox("Monitoring")
        # Remove the hardcoded color styling, will be handled by the theme
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # PrintScreen monitoring
        self.monitor_print_screen_checkbox = QCheckBox("Monitor Print Screen")
        layout.addWidget(self.monitor_print_screen_checkbox)
        
        # Ctrl+C monitoring
        self.monitor_ctrl_c_checkbox = QCheckBox("Monitor Ctrl+C")
        layout.addWidget(self.monitor_ctrl_c_checkbox)
        
        # Auto refresh
        self.auto_refresh_checkbox = QCheckBox("Auto-Refresh Overlay On Clipboard Change")
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
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Resize options
        layout.addWidget(QLabel("Resize Options:"))
        
        # Resize image to fit window
        self.resize_image_checkbox = QCheckBox("Resize Image To Fit Window")
        self.resize_image_checkbox.setChecked(self.settings.get("resize_image_to_fit", True))
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
        self.video_aware_capture_checkbox.setToolTip("Experimental, aka it won't work for shit yet.")
        # Connect the stateChanged signal to a handler that will also check the double shift checkbox
        self.video_aware_capture_checkbox.stateChanged.connect(self.on_video_aware_changed)
        layout.addWidget(self.video_aware_capture_checkbox)
        
        # Draw Capture Frame option
        self.draw_capture_frame_checkbox = QCheckBox("Draw Capture Frame")
        self.draw_capture_frame_checkbox.setChecked(self.settings.get("draw_capture_frame", False))
        self.draw_capture_frame_checkbox.setToolTip("When enabled, shows a blue outline around the area being captured with double shift for 0.3 seconds")
        layout.addWidget(self.draw_capture_frame_checkbox)
        
        # Double-shift capture size
        capture_size_layout = QHBoxLayout()
        
        # Add a "Double-shift capture size:" label
        capture_size_layout.addWidget(QLabel("Double-Shift Capture Size:"))
        
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
        opacity_layout.addWidget(self.opacity_slider)
        
        self.opacity_value_label = QLabel(f"{self.opacity_slider.value()}%")
        opacity_layout.addWidget(self.opacity_value_label)
        
        layout.addLayout(opacity_layout)
        
        group_box.setLayout(layout)
        parent_layout.addWidget(group_box)
        
    def create_theme_section(self, parent_layout):
        """Create the theme settings section."""
        group_box = QGroupBox("Theme")
        layout = QVBoxLayout()
        layout.setSpacing(10)
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
        layout = QVBoxLayout()
        layout.setSpacing(10)
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
    
    def update_history_size(self):
        """Update the history folder size label."""
        try:
            # Get the history folder path directly from the settings object
            history_folder = self.settings.history_folder
            logging.info(f"Checking history folder size: {history_folder}")
            
            if history_folder and os.path.exists(history_folder):
                size = self.get_folder_size(history_folder)
                self.history_folder_label.setText(f"{size}")
            else:
                logging.warning(f"History folder does not exist: {history_folder}")
                self.history_folder_label.setText("0.00 GB")
        except Exception as e:
            logging.error(f"Error updating history size: {e}")
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
            self.history_folder_label.setText("<b>YOU KNOW WHAT YOU DID</b>")
            QTimer.singleShot(2000, self.update_history_size)
    
    def open_history_folder(self):
        """Open the history folder in the file explorer."""
        try:
            # Access the history_folder directly from the settings object
            history_folder = self.settings.history_folder
            logging.info(f"Opening history folder: {history_folder}")
            
            if history_folder and os.path.exists(history_folder):
                # Use the appropriate command based on the operating system
                if platform.system() == "Windows":
                    os.startfile(history_folder)
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", history_folder])
                else:  # Linux or other Unix-like
                    subprocess.run(["xdg-open", history_folder])
            else:
                logging.error(f"History folder does not exist: {history_folder}")
        except Exception as e:
            logging.error(f"Error opening history folder: {e}")
    
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
            self.double_shift_capture_checkbox.setChecked(False)
        if hasattr(self, 'clickthrough_checkbox'):
            self.clickthrough_checkbox.setChecked(False)
        if hasattr(self, 'opacity_slider'):
            self.opacity_slider.setValue(77)
        self.theme_combo.setCurrentIndex(0)  # Dark
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
        try:
            # Save window position
            self.settings.set("settings_window_x", self.pos().x())
            self.settings.set("settings_window_y", self.pos().y())
            
            # Clean up any UI resources
            for child in self.findChildren(QWidget):
                try:
                    child.deleteLater()
                except:
                    pass
            
            # Clean up resources
            self.deleteLater()
            
            logging.info("Settings window resources cleaned up")
        except Exception as e:
            logging.error(f"Error cleaning up settings window: {e}")
        
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
        # Determine theme
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
    """A frameless, themed dialog showing information about the application."""
    
    def __init__(self, parent=None, dark_theme=True):
        super().__init__(parent, Qt.FramelessWindowHint)
        self.dark_theme = dark_theme
        self.setFixedSize(550, 400)  # Made wider and taller
        
        # Very simple styling approach - use stylesheet only with important to override any conflicts
        if dark_theme:
            self.setStyleSheet("""
                QDialog {
                    background-color: #252525 !important;
                    color: white !important;
                    border: 2px solid #444 !important;
                }
                QLabel {
                    color: white !important;
                }
                QPushButton {
                    background-color: #444 !important;
                    color: white !important;
                    border-radius: 5px !important;
                    border: 1px solid #555 !important;
                    padding: 5px !important;
                }
                QPushButton:hover {
                    background-color: #555 !important;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #F0F0F0 !important;
                    color: black !important;
                    border: 2px solid #CCC !important;
                }
                QLabel {
                    color: black !important;
                }
                QPushButton {
                    background-color: #DDD !important;
                    color: black !important;
                    border-radius: 5px !important;
                    border: 1px solid #BBB !important;
                    padding: 5px !important;
                }
                QPushButton:hover {
                    background-color: #CCC !important;
                }
            """)
        
        # Center on parent
        if parent:
            self.move(parent.x() + parent.width()//2 - self.width()//2,
                     parent.y() + parent.height()//2 - self.height()//2)
        
        # Create layout - back to using layouts instead of absolute positioning
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Add title
        title = QLabel("WWTS")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20pt; font-weight: bold;")
        layout.addWidget(title)
        
        # Add content text
        content = QLabel("Made for my own shitty memories, shared freely for yours.\nYou can always donate to my dumbass though or buy my shitty literature.")
        content.setAlignment(Qt.AlignCenter)
        content.setWordWrap(True)
        layout.addWidget(content)
        
        # Create buttons with layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(50)
        button_layout.addStretch(1)
        
        # PayPal button
        paypal_button = QPushButton("PayPal")
        paypal_button.setFixedSize(100, 40)
        paypal_button.setToolTip("Donate via PayPal")
        paypal_button.clicked.connect(lambda: self.open_url("https://www.paypal.com/donate/?business=UBZJY8KHKKLGC&no_recurring=0&item_name=Why+are+you+doing+this?+Are+you+drunk?+&currency_code=USD"))
        button_layout.addWidget(paypal_button)
        
        # Goodreads button
        goodreads_button = QPushButton("Goodreads")
        goodreads_button.setFixedSize(100, 40)
        goodreads_button.setToolTip("Check out our book on Goodreads")
        goodreads_button.clicked.connect(lambda: self.open_url("https://www.goodreads.com/book/show/25006763-usu"))
        button_layout.addWidget(goodreads_button)
        
        # Amazon button
        amazon_button = QPushButton("Amazon")
        amazon_button.setFixedSize(100, 40)
        amazon_button.setToolTip("Check out our book on Amazon")
        amazon_button.clicked.connect(lambda: self.open_url("https://www.amazon.com/Usu-Jayde-Ver-Elst-ebook/dp/B00V8A5K7Y"))
        button_layout.addWidget(amazon_button)
        
        # GitHub button
        github_button = QPushButton("GitHub")
        github_button.setFixedSize(100, 40)
        github_button.setToolTip("Visit Basjohn's GitHub page")
        github_button.clicked.connect(lambda: self.open_url("https://github.com/Basjohn"))
        button_layout.addWidget(github_button)
        
        button_layout.addStretch(1)
        layout.addLayout(button_layout)
        
        # Add spacer
        layout.addStretch(1)
        
        # Add OK button
        ok_button = QPushButton("OK")
        ok_button.setFixedWidth(100)
        ok_button.clicked.connect(self.accept)
        
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
