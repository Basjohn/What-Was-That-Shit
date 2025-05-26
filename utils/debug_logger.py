import logging
import os
import sys
import traceback
from datetime import datetime

class DebugLogger:
    def __init__(self):
        self.logger = logging.getLogger('ImageDebug')
        self.logger.setLevel(logging.DEBUG)
        
        # Create debug log file
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f'image_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        
        self.logger.addHandler(handler)
    
    def log_image_info(self, image, stage):
        try:
            self.logger.debug(f"Stage: {stage}")
            self.logger.debug(f"Image type: {type(image)}")
            if hasattr(image, 'size'):
                self.logger.debug(f"Image size: {image.size}")
            if hasattr(image, 'mode'):
                self.logger.debug(f"Image mode: {image.mode}")
        except Exception as e:
            self.logger.error(f"Error logging image info: {str(e)}")
