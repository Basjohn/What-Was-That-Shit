import os
import datetime
import binascii
import logging
from pathlib import Path
from PIL import Image
import io
import hashlib

class HistoryManager:
    def __init__(self, base_path):
        self.base_path = Path(base_path)
        self._ensure_base_path()
    
    def _ensure_base_path(self):
        """Ensure the base history path exists"""
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True, exist_ok=True)
            logging.info(f"Created history directory: {self.base_path}")
    
    def _get_directory_path(self, file_type):
        """Get the directory path based on current date and file type"""
        now = datetime.datetime.now()
        year_dir = self.base_path / str(now.year)
        month_dir = year_dir / f"{now.month:02d}"
        type_dir = month_dir / file_type.lower().strip('.')
        
        # Ensure all directories exist
        for directory in [year_dir, month_dir, type_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        return type_dir
    
    def _generate_filename(self, image_data, file_type):
        """Generate a unique hexadecimal filename based on CRC and timestamp"""
        # Calculate CRC of image data
        crc = binascii.crc32(image_data) & 0xFFFFFFFF
        # Get timestamp for additional uniqueness
        timestamp = int(datetime.datetime.now().timestamp())
        # Combine and use part of it for the filename (4 hex digits)
        filename = f"{(crc ^ timestamp) & 0xFFFF:04X}"
        return f"{filename}.{file_type.lower().strip('.')}"
    
    def _get_image_crc(self, image_data):
        """Get a CRC hash of the image data for duplicate checking"""
        return binascii.crc32(image_data) & 0xFFFFFFFF
    
    def save_image(self, image, file_type='jpg'):
        """Save an image to the history directory structure
        
        Args:
            image: PIL.Image object
            file_type: File extension (jpg, png, etc.)
            
        Returns:
            str: Path to saved file or None if failed
        """
        if not image:
            logging.warning("Attempted to save None image to history")
            return None
        
        # Normalize file_type by removing any leading dots and converting to lowercase
        file_type = file_type.lower().strip('.')
        
        try:
            # Get directory path for this file type
            directory = self._get_directory_path(file_type)
            
            # For GIFs we need special handling to preserve animation
            if file_type == 'gif':
                logging.info("GIF detected in history, saving with animation preservation...")
                
                # Generate a unique filename based on timestamp
                timestamp = int(datetime.datetime.now().timestamp())
                filename = f"{timestamp:08X}.{file_type}"
                file_path = directory / filename
                
                # Handle potential filename conflicts
                counter = 0
                while file_path.exists():
                    counter += 1
                    alt_filename = f"{timestamp:08X}_{counter:02d}.{file_type}"
                    file_path = directory / alt_filename
                
                # If we have raw GIF data, use it directly (most reliable)
                if hasattr(image, '_raw_gif_data') and image._raw_gif_data:
                    logging.info("Using raw GIF data for history saving - best animation preservation")
                    try:
                        with open(file_path, 'wb') as f:
                            f.write(image._raw_gif_data)
                        logging.info(f"Saved animated GIF using raw data to: {file_path}")
                        return str(file_path)
                    except Exception as raw_err:
                        logging.error(f"Error saving GIF using raw data: {raw_err}")
                
                # If the image is marked as animated, try to save with animation
                if getattr(image, 'is_animated', False):
                    try:
                        logging.info("Saving GIF as animated (marked as animated)")
                        image.save(
                            file_path, 
                            format='GIF',
                            save_all=True, 
                            append_images=getattr(image, 'append_images', []),
                            duration=getattr(image, 'duration', 100),
                            loop=0,
                            optimize=False
                        )
                        logging.info(f"Saved animated GIF to history: {file_path}")
                        return str(file_path)
                    except Exception as anim_err:
                        logging.error(f"Error saving animated GIF: {anim_err}")
                
                # Fall back to standard save for GIFs
                try:
                    logging.info("Falling back to standard GIF save")
                    image.save(file_path, format='GIF')
                    logging.info(f"Saved GIF (not animated) to history: {file_path}")
                    return str(file_path)
                except Exception as std_err:
                    logging.error(f"Error with standard GIF save: {std_err}")
                    # Continue to general image saving as last resort
            
            # For non-GIF images or fallback for GIFs
            img_byte_arr = io.BytesIO()
            
            # Handle formats properly, normalizing JPG to JPEG for PIL
            save_format = 'JPEG' if file_type in ['jpg', 'jpeg'] else file_type.upper()
            image.save(img_byte_arr, format=save_format)
            img_data = img_byte_arr.getvalue()
            
            # Skip 0KB files
            if len(img_data) == 0:
                logging.warning("Skipping 0KB image save")
                return None
            
            # Generate filename based on content hash
            filename = self._generate_filename(img_data, file_type)
            file_path = directory / filename
            
            # Check for duplicate filename and handle it
            counter = 0
            while file_path.exists():
                # If file exists, check if it's the same content by CRC
                with open(file_path, 'rb') as existing_file:
                    existing_data = existing_file.read()
                    if self._get_image_crc(existing_data) == self._get_image_crc(img_data):
                        # Same image, no need to save again
                        logging.info(f"Image already exists in history: {file_path}")
                        return str(file_path)
                
                # Different content but same filename, create a new one
                counter += 1
                alt_filename = f"{filename.split('.')[0]}_{counter:02d}.{file_type}"
                file_path = directory / alt_filename
            
            # Save the image with proper format handling
            image.save(file_path, format=save_format)
            logging.info(f"Saved image to history: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logging.error(f"Failed to save image to history: {e}")
            return None
