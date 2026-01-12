"""
Test if FFmpeg is installed and working
Run this to verify your video studio setup
"""
import subprocess
import sys

print("\n" + "="*60)
print("🎬 VIDEO STUDIO - SYSTEM CHECK")
print("="*60 + "\n")

# Test 1: FFmpeg
print("1️⃣ Testing FFmpeg installation...")
print("-" * 60)
try:
    result = subprocess.run(
        ['ffmpeg', '-version'], 
        capture_output=True, 
        text=True, 
        timeout=5
    )
    
    if result.returncode == 0:
        print("✅ FFmpeg is INSTALLED and working!")
        version_line = result.stdout.split('\n')[0]
        print(f"   Version: {version_line}")
        ffmpeg_ok = True
    else:
        print("❌ FFmpeg found but returned an error")
        print(f"   Error: {result.stderr}")
        ffmpeg_ok = False
except FileNotFoundError:
    print("❌ FFmpeg is NOT installed")
    print("   Please install FFmpeg to create videos")
    print("   See: INSTALL_FFMPEG_WINDOWS.md")
    ffmpeg_ok = False
except subprocess.TimeoutExpired:
    print("⚠️  FFmpeg check timed out")
    ffmpeg_ok = False
except Exception as e:
    print(f"❌ Error checking FFmpeg: {e}")
    ffmpeg_ok = False

print()

# Test 2: Pillow (PIL)
print("2️⃣ Testing Pillow (image processing)...")
print("-" * 60)
try:
    from PIL import Image
    import PIL
    print(f"✅ Pillow is INSTALLED!")
    print(f"   Version: {PIL.__version__}")
    pillow_ok = True
except ImportError:
    print("❌ Pillow is NOT installed")
    print("   Run: pip install Pillow")
    pillow_ok = False

print()

# Test 3: Check directories
print("3️⃣ Checking required directories...")
print("-" * 60)
import os
from pathlib import Path

dirs_to_check = [
    "uploads/video_media",
    "generated_videos"
]

dirs_ok = True
for dir_path in dirs_to_check:
    path = Path(dir_path)
    if path.exists():
        print(f"✅ {dir_path}/ exists")
    else:
        print(f"⚠️  {dir_path}/ does NOT exist (will be created automatically)")
        try:
            path.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ Created {dir_path}/")
        except Exception as e:
            print(f"   ❌ Could not create: {e}")
            dirs_ok = False

print()

# Final Summary
print("="*60)
print("📊 SUMMARY")
print("="*60)

if ffmpeg_ok and pillow_ok and dirs_ok:
    print("✅ ALL CHECKS PASSED!")
    print("🎉 Your Video Studio is ready to create videos!")
    print("\nNext steps:")
    print("1. Start your app: python app.py")
    print("2. Go to: http://localhost:5000/agent/video-studio")
    print("3. Create your first video!")
else:
    print("❌ SOME CHECKS FAILED")
    print("\nWhat needs fixing:")
    if not ffmpeg_ok:
        print("  • Install FFmpeg (see INSTALL_FFMPEG_WINDOWS.md)")
    if not pillow_ok:
        print("  • Install Pillow: pip install Pillow")
    if not dirs_ok:
        print("  • Fix directory permissions")

print("="*60 + "\n")
