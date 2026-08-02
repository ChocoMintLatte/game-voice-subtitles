import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QIcon

def main():
    app = QApplication(sys.argv)
    
    png_path = r"C:\Users\USER\.gemini\antigravity\brain\5617a79e-b0ea-478a-b6fe-a495c0b54f50\app_icon_1783250749757.png"
    ico_path = r"C:\Users\USER\.gemini\antigravity\scratch\game-voice-subtitles\app_icon.ico"
    
    pixmap = QPixmap(png_path)
    if pixmap.isNull():
        print("Error: Failed to load PNG.")
        sys.exit(1)
        
    pixmap.save(r"C:\Users\USER\.gemini\antigravity\scratch\game-voice-subtitles\app_icon.png", "PNG")
    
    try:
        success = pixmap.save(ico_path, "ICO")
        if success:
            print("Successfully converted to ICO using PyQt6.")
            sys.exit(0)
    except Exception as e:
        print(f"PyQt6 ICO save failed: {e}")
        
    # Try using PIL if installed or try installing it
    try:
        from PIL import Image
        img = Image.open(png_path)
        img.save(ico_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print("Successfully converted to ICO using Pillow.")
        sys.exit(0)
    except Exception as e2:
        print(f"Pillow conversion failed: {e2}")
        sys.exit(1)

if __name__ == '__main__':
    main()
