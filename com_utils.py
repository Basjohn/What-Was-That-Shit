"""Utility functions for COM initialization and thread safety."""
import ctypes
import logging
import threading
from contextlib import contextmanager

try:
    import pythoncom
    import win32api
    import win32process
    import win32con
    import win32com.client
    import win32clipboard
    COM_SUPPORT = True
except ImportError:
    COM_SUPPORT = False

# Thread-local storage for COM initialization
_local = threading.local()

def is_main_thread():
    """Check if the current thread is the main thread."""
    return threading.current_thread() is threading.main_thread()

@contextmanager
def com_apartment_thread():
    """Context manager for COM apartment-threaded operations."""
    if not COM_SUPPORT:
        yield
        return
    
    # Initialize COM for this thread if not already done
    if not hasattr(_local, 'com_initialized'):
        try:
            pythoncom.CoInitialize()
            _local.com_initialized = True
            logging.debug("COM initialized for thread %s", threading.current_thread().name)
        except Exception as e:
            logging.error("Failed to initialize COM: %s", e)
            _local.com_initialized = False
    
    try:
        yield
    finally:
        # Don't uninitialize COM as it can cause issues with Qt's event loop
        pass

@contextmanager
def clipboard_access(max_retries=3, retry_delay=0.1):
    """Context manager for safe clipboard access with COM initialization.
    
    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    """
    if not COM_SUPPORT:
        logging.warning("COM support not available for clipboard access")
        yield
        return
    
    last_error = None
    for attempt in range(max_retries):
        try:
            with com_apartment_thread():
                try:
                    # Try to open clipboard with a small delay if not first attempt
                    if attempt > 0:
                        time.sleep(retry_delay)
                        
                    # Try to open clipboard
                    win32clipboard.OpenClipboard(0)  # Pass 0 to prevent other apps from modifying the clipboard
                    
                    try:
                        yield  # Execute the code within the with block
                        return  # Success, exit the retry loop
                        
                    finally:
                        # Always try to close the clipboard
                        try:
                            win32clipboard.CloseClipboard()
                        except Exception as close_error:
                            if attempt == max_retries - 1:  # Only log on final attempt
                                logging.warning("Error closing clipboard: %s", close_error)
                            
                except Exception as e:
                    last_error = e
                    # Log the error if this is the last attempt
                    if attempt == max_retries - 1:
                        logging.error("Clipboard access error (attempt %d/%d): %s", 
                                    attempt + 1, max_retries, e, exc_info=True)
                    # Try to close clipboard if it was opened but an error occurred
                    try:
                        win32clipboard.CloseClipboard()
                    except:
                        pass
                    
                    # If this was the last attempt, re-raise the exception
                    if attempt == max_retries - 1:
                        raise
                    
        except Exception as e:
            last_error = e
            if attempt == max_retries - 1:  # Last attempt
                logging.error("Error in clipboard access context (attempt %d/%d): %s", 
                            attempt + 1, max_retries, e, exc_info=True)
                raise RuntimeError(f"Failed to access clipboard after {max_retries} attempts") from last_error
    
    # This should never be reached due to the raise statements above
    raise RuntimeError("Unexpected error in clipboard access")
