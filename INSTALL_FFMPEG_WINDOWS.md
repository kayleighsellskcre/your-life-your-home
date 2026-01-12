# 🎬 Install FFmpeg on Windows - Quick Guide

## ✅ **Good News: Pillow is installed!**
## ❌ **Problem: FFmpeg is NOT installed (that's why videos fail)**

---

## 🚀 **OPTION 1: Install FFmpeg via Chocolatey (EASIEST)**

### **Step 1: Install Chocolatey (if you don't have it)**
Open PowerShell as Administrator and run:
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

### **Step 2: Install FFmpeg**
```powershell
choco install ffmpeg -y
```

### **Step 3: Verify Installation**
Close and reopen PowerShell, then run:
```powershell
ffmpeg -version
```

If you see version info, you're good! ✅

---

## 🚀 **OPTION 2: Install FFmpeg Manually (IF CHOCOLATEY DOESN'T WORK)**

### **Step 1: Download FFmpeg**
1. Go to: https://www.gyan.dev/ffmpeg/builds/
2. Click **"ffmpeg-release-essentials.zip"**
3. Download the zip file (~70MB)

### **Step 2: Extract FFmpeg**
1. Extract the zip file to: `C:\ffmpeg`
2. You should have: `C:\ffmpeg\bin\ffmpeg.exe`

### **Step 3: Add FFmpeg to PATH**

**Method A: Using PowerShell (Quick)**
Open PowerShell as Administrator and run:
```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\ffmpeg\bin", "Machine")
```

**Method B: Using GUI**
1. Open Start Menu
2. Search for "Environment Variables"
3. Click "Edit the system environment variables"
4. Click "Environment Variables" button
5. Under "System variables", find "Path"
6. Click "Edit"
7. Click "New"
8. Add: `C:\ffmpeg\bin`
9. Click OK on all windows
10. **RESTART your terminal/PowerShell**

### **Step 4: Verify Installation**
Open a NEW PowerShell window and run:
```powershell
ffmpeg -version
```

You should see:
```
ffmpeg version 6.x.x
...
```

---

## 🚀 **OPTION 3: Install FFmpeg via Scoop (ALTERNATIVE)**

### **Step 1: Install Scoop**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
```

### **Step 2: Install FFmpeg**
```powershell
scoop install ffmpeg
```

### **Step 3: Verify**
```powershell
ffmpeg -version
```

---

## ✅ **After FFmpeg is Installed:**

### **Test Your Video Studio:**

1. **Restart your Flask app:**
   ```powershell
   # Stop your current app (Ctrl+C)
   python app.py
   ```

2. **Go to Video Studio:**
   - Navigate to: http://localhost:5000/agent/video-studio

3. **Try Creating a Video:**
   - Click "3D Property Tour" (if you have premium enabled)
   - Or click any other video type
   - Upload 3-5 photos
   - Fill in details
   - Click "Create Video"

4. **Wait 1-2 minutes for rendering**

5. **Success!** 🎉 Your video should now render successfully!

---

## 🐛 **Troubleshooting:**

### **"'ffmpeg' is not recognized"**
- Make sure you restarted PowerShell/Terminal after installing
- Verify PATH is set correctly: `echo $env:Path` (should include ffmpeg)
- Try logging out and back in to Windows

### **"Access Denied" when installing**
- Run PowerShell as Administrator
- Right-click PowerShell → "Run as Administrator"

### **"FFmpeg installed but videos still fail"**
- Check Railway logs if deployed
- Verify uploaded images are valid (JPG/PNG)
- Try with smaller images (< 5MB each)
- Check console for specific error messages

### **"Permission denied" errors**
- Make sure `uploads/` folder exists and is writable
- Make sure `generated_videos/` folder exists
- Check folder permissions

---

## 📱 **For Railway Deployment:**

FFmpeg is already configured in your `nixpacks.toml` file:
```toml
[phases.setup]
aptPkgs = ['ffmpeg']
```

This means FFmpeg will automatically install when you deploy to Railway! ✅

---

## 🎬 **Quick Verification Script:**

Create a test file `test_ffmpeg.py`:
```python
import subprocess
import sys

print("Testing FFmpeg installation...")
print("-" * 50)

try:
    result = subprocess.run(
        ['ffmpeg', '-version'], 
        capture_output=True, 
        text=True, 
        timeout=5
    )
    
    if result.returncode == 0:
        print("✅ FFmpeg is installed and working!")
        print("\nVersion info:")
        print(result.stdout.split('\n')[0])
    else:
        print("❌ FFmpeg found but returned an error")
        print(result.stderr)
except FileNotFoundError:
    print("❌ FFmpeg is NOT installed")
    print("Please install FFmpeg using one of the methods above")
except Exception as e:
    print(f"❌ Error checking FFmpeg: {e}")

print("-" * 50)
```

Run it:
```powershell
python test_ffmpeg.py
```

---

## 🎯 **Quick Install Command (Chocolatey):**

**Just copy and paste this into PowerShell as Administrator:**
```powershell
# Install Chocolatey if needed
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
}

# Install FFmpeg
choco install ffmpeg -y

# Verify
ffmpeg -version
```

---

## 💡 **Why You Need FFmpeg:**

FFmpeg is the industry-standard video processing tool that:
- ✅ Converts images to video segments
- ✅ Applies Ken Burns effects (zoom/pan)
- ✅ Adds 3D camera movements
- ✅ Creates intro/outro cards
- ✅ Merges video segments
- ✅ Adds transitions and effects
- ✅ Exports final MP4 videos

Without FFmpeg, **no videos can be created**. It's essential!

---

## 🎉 **After Installation:**

Once FFmpeg is installed, you'll be able to:
- ✅ Create regular listing videos
- ✅ Create 3D Property Tour videos
- ✅ Use all video styles (Luxury, Modern, Architectural)
- ✅ Add room labels and effects
- ✅ Export professional videos in any format

---

## 📞 **Still Having Issues?**

1. **Check if FFmpeg is in PATH:**
   ```powershell
   where.exe ffmpeg
   ```
   Should return: `C:\ffmpeg\bin\ffmpeg.exe` or similar

2. **Test FFmpeg directly:**
   ```powershell
   ffmpeg -version
   ```

3. **Check Python can find it:**
   ```python
   import subprocess
   subprocess.run(['ffmpeg', '-version'])
   ```

4. **Restart everything:**
   - Close all terminals
   - Close VS Code/IDE
   - Restart Flask app
   - Try again

---

## 🚀 **Recommended Installation Order:**

1. ✅ Install FFmpeg (Option 1 or 2 above)
2. ✅ Restart terminal
3. ✅ Verify installation: `ffmpeg -version`
4. ✅ Restart Flask app: `python app.py`
5. ✅ Go to Admin → Enable Premium
6. ✅ Go to Video Studio
7. ✅ Create your first video!
8. ✅ Watch it render successfully! 🎬

---

**Once FFmpeg is installed, your Video Studio will work perfectly!** ✨
