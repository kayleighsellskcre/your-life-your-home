"""
Background Removal Utility for Fixture Images

This script can be used to automatically remove backgrounds from fixture/furniture images.
It uses the rembg library which uses AI models for background removal.

Installation:
    pip install rembg pillow

Usage:
    python scripts/remove_background.py input_image.jpg output_image.png
"""

import sys
from pathlib import Path

try:
    from rembg import remove
    from PIL import Image
except ImportError:
    print("ERROR: Required libraries not installed.")
    print("Please install: pip install rembg pillow")
    sys.exit(1)


def remove_background(input_path: str, output_path: str) -> bool:
    """Remove background from an image file.
    
    Args:
        input_path: Path to input image
        output_path: Path to save output image (PNG with transparency)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        if not input_path.exists():
            print(f"Error: Input file not found: {input_path}")
            return False
        
        # Load image
        with Image.open(input_path) as img:
            # Remove background
            output = remove(img)
            
            # Save as PNG with transparency
            output.save(output_path, format='PNG')
            print(f"✓ Background removed successfully!")
            print(f"  Saved to: {output_path}")
            return True
            
    except Exception as e:
        print(f"Error removing background: {e}")
        return False


def main():
    if len(sys.argv) < 3:
        print("Usage: python remove_background.py <input_image> <output_image>")
        print("Example: python remove_background.py chair.jpg chair_nobg.png")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # Ensure output is PNG for transparency
    if not output_file.lower().endswith('.png'):
        output_file = output_file.rsplit('.', 1)[0] + '.png'
        print(f"Note: Output format changed to PNG for transparency: {output_file}")
    
    success = remove_background(input_file, output_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
