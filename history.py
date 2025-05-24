import os
import datetime
import binascii
import logging
import random
import string
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
    
    def _get_directory_path(self, file_type, is_temporary=False):
        """Get the directory path based on current date and file type
        
        Args:
            file_type: File extension (jpg, png, etc.)
            is_temporary: If True, this is a temporary file
            
        Returns:
            Path: The directory path where the file should be saved
        """
        now = datetime.datetime.now()
        year_dir = self.base_path / str(now.year)
        month_dir = year_dir / f"{now.month:02d}"
        
        # Ensure year and month directories exist
        for directory in [year_dir, month_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        return month_dir  # We'll store all files directly in the month directory now
    
    def _generate_filename(self, file_type, is_temporary=False):
        """Generate a sequential filename in the format 0000.filetype
        
        Args:
            file_type: File extension (jpg, png, etc.)
            is_temporary: If True, add '_T' before the extension
            
        Returns:
            str: Generated filename in format 0000[.ext] or 0000_T[.ext]
        """
        # Get all files in the directory
        directory = self._get_directory_path(file_type, is_temporary)
        
        # Get all used counters
        used_counters = set()
        for file in directory.glob('*.*'):
            if file.is_file():
                try:
                    # Extract counter from filename (format: 0000[.ext] or 0000_T[.ext])
                    base = file.stem
                    if base.endswith('_T'):
                        base = base[:-2]  # Remove _T suffix if present
                    counter = int(base)  # The entire base is the counter
                    used_counters.add(counter)
                except (ValueError, IndexError):
                    continue
        
        # Find the first available counter starting from 0
        counter = 0
        while counter in used_counters:
            counter += 1
            
            # Safety check to prevent infinite loop in case of too many files
            if counter > 9999:  # 4-digit counter max
                raise RuntimeError("Maximum number of files (9999) reached in the directory")
        
        # Format the filename
        base_name = f"{counter:04d}"  # 4-digit counter
        if is_temporary:
            base_name += "_T"
            
        return f"{base_name}.{file_type.lower().strip('.')}"
    
    def _get_image_crc(self, image_data):
        """Get a CRC hash of the image data for duplicate checking"""
        return binascii.crc32(image_data) & 0xFFFFFFFF
    
    def save_image(self, image, file_type='jpg', is_temporary=False, app_instance=None):
        try:
            if not image:
                logging.error("Cannot save None image")
                return None

            logging.debug(f"Saving image - Type: {type(image)}, Format: {getattr(image, 'format', 'unknown')}")
            if hasattr(image, 'size'):
                logging.debug(f"Image size: {image.size}")
            if hasattr(image, 'mode'):
                logging.debug(f"Image mode: {image.mode}")

            # Validate image before saving
            if not self._validate_image(image):
                logging.error("Image validation failed")
                return None

            # Normalize file_type by removing any leading dots and converting to lowercase
            file_type = file_type.lower().strip('.')
            
            try:
                # Get directory path (now just year/month)
                directory = self._get_directory_path(file_type, is_temporary)
                
                # Generate the new sequential filename
                filename = self._generate_filename(file_type, is_temporary)
                file_path = directory / filename
                
                # Set the filename attribute on the image object
                image.filename = str(file_path)
                
                # For GIFs we need special handling to preserve animation
                if file_type == 'gif':
                    logging.info("GIF detected in history, saving with animation preservation...")
                    
                    # Check if image is animated
                    is_animated = getattr(image, 'is_animated', False)
                    if is_animated:
                        try:
                            # Get animation data
                            frames = []
                            durations = []
                            try:
                                for frame_num in range(image.n_frames):
                                    image.seek(frame_num)
                                    frames.append(image.copy())
                                    durations.append(image.info.get('duration', 100))
                            except (AttributeError, EOFError) as e:
                                logging.warning(f"Error extracting GIF frames: {e}")
                            
                            if frames:
                                frames[0].save(
                                    file_path,
                                    save_all=True,
                                    append_images=frames[1:],
                                    duration=durations,
                                    loop=0,
                                    format='GIF'
                                )
                                logging.info(f"Saved animated GIF with {len(frames)} frames")
                                return str(file_path)
                        except Exception as e:
                            logging.error(f"Failed to save animated GIF: {e}")
                    
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
                try:
                    # Handle formats properly, normalizing JPG to JPEG for PIL
                    save_format = 'JPEG' if file_type in ['jpg', 'jpeg'] else file_type.upper()
                    
                    # Skip 0KB files
                    if not hasattr(image, 'size') or image.size[0] == 0 or image.size[1] == 0:
                        logging.warning("Skipping 0-size image save")
                        return None
                    
                    # Save the image with proper format handling
                    image.save(file_path, format=save_format)
                    logging.info(f"Saved image to history: {file_path}")
                    
                    # If we have an app instance with a history_db, update it
                    if app_instance and hasattr(app_instance, 'history_db') and app_instance.history_db:
                        try:
                            # Add to history database
                            img_id = app_instance.history_db.add_image(
                                file_path=str(file_path),
                                is_temporary=is_temporary,
                                width=image.width,
                                height=image.height
                            )
                            if img_id:
                                app_instance.history_db.set_current_image(img_id)
                        except Exception as db_error:
                            logging.error(f"Error updating history database: {db_error}")
                    
                    return str(file_path)
                    
                except Exception as save_err:
                    logging.error(f"Error saving image: {save_err}")
                    return None
                
            except Exception as e:
                logging.error(f"Failed to save image to history: {e}", exc_info=True)
                return None

        except Exception as e:
            logging.error(f"History save error: {e}", exc_info=True)
            return None

    def _validate_image(self, image):
        """Validate image before saving."""
        try:
            if not hasattr(image, 'size'):
                logging.error("Image has no size attribute")
                return False
            if not image.size or image.size[0] <= 0 or image.size[1] <= 0:
                logging.error(f"Invalid image size: {image.size}")
                return False
            return True
        except Exception as e:
            logging.error(f"Image validation error: {e}")
            return False
