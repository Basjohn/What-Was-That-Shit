import sqlite3
import os
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any, Union

class HistoryDB:
    def __init__(self, db_path: str = 'wwts_history.db'):
        """Initialize the history database.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with proper settings and retry logic.
        
        Returns:
            sqlite3.Connection: A database connection
            
        Raises:
            sqlite3.Error: If all retry attempts fail
        """
        max_retries = 3
        retry_delay = 0.1  # 100ms initial delay
        
        for attempt in range(max_retries):
            conn = None
            try:
                conn = sqlite3.connect(
                    self.db_path,
                    timeout=5.0,  # Reduced timeout from 10s to 5s
                    isolation_level='IMMEDIATE',  # Better for concurrent access
                    check_same_thread=False  # Allow connection from different threads
                )
                conn.row_factory = sqlite3.Row  # Enable column access by name
                
                # Set pragmas for better concurrency
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')  # Better performance than FULL
                conn.execute('PRAGMA busy_timeout=5000')  # 5 second busy timeout
                conn.execute('PRAGMA cache_size=-2000')  # 2MB cache
                
                return conn
                
            except sqlite3.OperationalError as e:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
                        
                if 'database is locked' in str(e) and attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    continue
                    
                logging.error(f"Database connection error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:  # Only raise on last attempt
                    logging.error("All retry attempts failed")
                raise
                
            except Exception as e:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
                logging.error(f"Unexpected database error: {e}")
                raise
    
    def _init_db(self):
        """Initialize the database with required tables."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Create images table
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_temporary BOOLEAN DEFAULT 0,
                    width INTEGER,
                    height INTEGER
                )
                ''')
                
                # Create navigation_order table to track the order of images
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS navigation_order (
                    image_id INTEGER PRIMARY KEY,
                    prev_id INTEGER,
                    next_id INTEGER,
                    FOREIGN KEY (image_id) REFERENCES images (id),
                    FOREIGN KEY (prev_id) REFERENCES images (id),
                    FOREIGN KEY (next_id) REFERENCES images (id)
                )
                ''')
                
                # Create current_position table to track the last viewed image
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS current_position (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    image_id INTEGER,
                    FOREIGN KEY (image_id) REFERENCES images (id)
                )
                ''')
                
                # Insert initial row for current_position if it doesn't exist
                cursor.execute('''
                INSERT OR IGNORE INTO current_position (id, image_id) VALUES (1, NULL)
                ''')
                
                conn.commit()
                
        except sqlite3.Error as e:
            logging.error(f"Error initializing database: {e}")
            raise
    
    def add_image(self, file_path: str, is_temporary: bool = False, width: int = None, height: int = None) -> Optional[int]:
        """Add a new image to the database.
        
        Args:
            file_path: Path to the image file
            is_temporary: Whether this is a temporary image
            width: Image width in pixels
            height: Image height in pixels
            
        Returns:
            int: The ID of the inserted image, or None if failed
        """
        try:
            if not file_path:
                logging.error("Cannot add image: file_path is None or empty")
                return None

            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Add debug logging
                logging.debug(f"Adding image to history DB: {file_path}")
                
                # Check if image already exists
                cursor.execute('SELECT id FROM images WHERE file_path = ?', (file_path,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing record
                    cursor.execute('''
                    UPDATE images 
                    SET timestamp = CURRENT_TIMESTAMP, 
                        is_temporary = ?,
                        width = ?,
                        height = ?
                    WHERE id = ?
                    ''', (is_temporary, width, height, existing['id']))
                    return existing['id']
                
                # Insert new image
                cursor.execute('''
                INSERT INTO images (file_path, is_temporary, width, height)
                VALUES (?, ?, ?, ?)
                ''', (file_path, is_temporary, width, height))
                
                image_id = cursor.lastrowid
                
                # Update navigation order
                self._update_navigation_order(conn, image_id)
                
                # Update current position if not set
                cursor.execute('SELECT image_id FROM current_position WHERE id = 1')
                if cursor.fetchone()['image_id'] is None:
                    self.set_current_image(image_id)
                
                conn.commit()
                return image_id
                
        except sqlite3.Error as e:
            logging.error(f"Error adding image to database: {e}")
            return None
    
    def _update_navigation_order(self, conn, new_image_id: int):
        """Update the navigation order to include the new image.
        
        Args:
            conn: Database connection
            new_image_id: ID of the new image
        """
        cursor = conn.cursor()
        
        # Get the current last image
        cursor.execute('''
        SELECT id FROM images 
        WHERE id != ? 
        ORDER BY timestamp DESC 
        LIMIT 1
        ''', (new_image_id,))
        
        last_image = cursor.fetchone()
        
        if last_image:
            # Update the previous last image to point to the new one
            cursor.execute('''
            INSERT OR REPLACE INTO navigation_order (image_id, prev_id, next_id)
            VALUES (?, 
                   (SELECT prev_id FROM navigation_order WHERE image_id = ?),
                   ?)
            ''', (last_image['id'], last_image['id'], new_image_id))
            
            # Insert the new image with proper navigation
            cursor.execute('''
            INSERT OR REPLACE INTO navigation_order (image_id, prev_id, next_id)
            VALUES (?, ?, NULL)
            ''', (new_image_id, last_image['id']))
        else:
            # This is the first image
            cursor.execute('''
            INSERT OR REPLACE INTO navigation_order (image_id, prev_id, next_id)
            VALUES (?, NULL, NULL)
            ''', (new_image_id,))
    
    def set_current_image(self, image_id: int) -> bool:
        """Set the current image position.
        
        Args:
            image_id: ID of the image to set as current
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                UPDATE current_position 
                SET image_id = ? 
                WHERE id = 1
                ''', (image_id,))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"Error setting current image: {e}")
            return False
    
    def get_current_image(self) -> Optional[dict]:
        """Get the current image.
        
        Returns:
            Optional[dict]: Current image data or None if not found
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT i.* FROM images i
                JOIN current_position cp ON i.id = cp.image_id
                WHERE cp.id = 1
                ''')
                return dict(cursor.fetchone()) if cursor.fetchone() else None
        except (sqlite3.Error, TypeError):
            return None
    
    def get_adjacent_image(self, current_id: int, direction: str = 'next') -> Optional[dict]:
        """Get the next or previous image in the navigation order.
        
        Args:
            current_id: Current image ID
            direction: 'next' or 'prev'
            
        Returns:
            Optional[dict]: Adjacent image data or None if not found
        """
        if direction not in ('next', 'prev'):
            raise ValueError("Direction must be 'next' or 'prev'")
            
        field = 'next_id' if direction == 'next' else 'prev_id'
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # First try to get from navigation order
                cursor.execute(f'''
                SELECT i.* FROM images i
                JOIN navigation_order no ON i.id = no.{field}
                WHERE no.image_id = ?
                ''', (current_id,))
                
                result = cursor.fetchone()
                if result:
                    return dict(result)
                
                # If not found in navigation order, fall back to timestamp order
                cursor.execute('''
                SELECT * FROM images 
                WHERE id != ? 
                ORDER BY timestamp DESC 
                LIMIT 1
                ''', (current_id,))
                
                result = cursor.fetchone()
                return dict(result) if result else None
                
        except sqlite3.Error as e:
            logging.error(f"Error getting {direction} image: {e}")
            return None
    
    def get_all_images(self) -> List[dict]:
        """Get all images in the database.
        
        Returns:
            List[dict]: List of all images with their data
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM images ORDER BY timestamp DESC')
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logging.error(f"Error getting all images: {e}")
            return []
    
    def cleanup_missing_files(self) -> int:
        """Remove database entries for files that no longer exist.
        
        Returns:
            int: Number of entries removed
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Get all file paths
                cursor.execute('SELECT id, file_path FROM images')
                to_remove = []
                
                for row in cursor.fetchall():
                    if not os.path.exists(row['file_path']):
                        to_remove.append(row['id'])
                
                # Remove entries
                removed = 0
                for img_id in to_remove:
                    try:
                        cursor.execute('DELETE FROM navigation_order WHERE image_id = ?', (img_id,))
                        cursor.execute('DELETE FROM images WHERE id = ?', (img_id,))
                        removed += 1
                    except sqlite3.Error as e:
                        logging.error(f"Error removing image ID {img_id}: {e}")
                
                # Update current position if it points to a removed image
                if to_remove:
                    cursor.execute('''
                    UPDATE current_position 
                    SET image_id = (SELECT id FROM images ORDER BY timestamp DESC LIMIT 1)
                    WHERE id = 1 AND image_id IS NULL
                    ''')
                
                conn.commit()
                return removed
                
        except sqlite3.Error as e:
            logging.error(f"Error cleaning up missing files: {e}")
            return 0
