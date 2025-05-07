"""DXWIN implementation from original WWTS"""
import ctypes
import time

def create(x, y, width, height, color, thickness, duration):
    """Draw rectangle overlay using Windows API"""
    try:
        # Get device context
        user32 = ctypes.windll.user32
        hdc = user32.GetDC(0)
        
        # Create pen
        gdi32 = ctypes.windll.gdi32
        pen = gdi32.CreatePen(0, thickness, (color[0] << 16) | (color[1] << 8) | color[2])
        old_pen = gdi32.SelectObject(hdc, pen)
        
        # Draw rectangle
        gdi32.Rectangle(hdc, x, y, x + width, y + height)
        
        # Clean up
        gdi32.SelectObject(hdc, old_pen)
        gdi32.DeleteObject(pen)
        user32.ReleaseDC(0, hdc)
        
        # Keep window alive for duration
        time.sleep(duration)
        return True
    except Exception as e:
        print(f"DXWIN Error: {e}")
        return False
