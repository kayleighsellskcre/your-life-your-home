# 🎬 Video Studio Implementation Plan

## ✅ COMPLETED (Step 1 of 3)

### 1. Core Infrastructure
- ✅ **video_studio.py** - FFmpeg-based video renderer
  - Creates luxury real estate videos
  - Ken Burns effect on photos
  - Intro/outro cards with branding
  - Background music support
  - Multiple aspect ratios (9:16, 16:9, 1:1)

- ✅ **video_database.py** - Database functions
  - Create/read/update/delete video projects
  - Track render status
  - Store media files as JSON

- ✅ **database.py** - Added `video_projects` table
  - Stores all video project data
  - Links to users and transactions

- ✅ **templates/agent/video_studio.html** - Beautiful UI
  - 5-step wizard interface
  - Drag & drop file upload
  - Style presets selection
  - Luxury design matching platform

---

## 🚧 TODO (Step 2 of 3) - Flask Routes & Integration

### Need to Add to `app.py`:

```python
# Video Studio Routes
@app.route("/agent/video-studio")
def agent_video_studio():
    """Video Studio home - show existing projects"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    from video_database import get_user_video_projects
    projects = get_user_video_projects(user["id"])
    
    return render_template(
        "agent/video_studio.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        projects=projects
    )

@app.route("/agent/video-studio/create", methods=["POST"])
def agent_video_studio_create():
    """Create a new video project"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    try:
        # Get form data
        video_type = request.form.get('video_type')
        aspect_ratio = request.form.get('aspect_ratio')
        duration = int(request.form.get('duration'))
        style_preset = request.form.get('style_preset')
        headline = request.form.get('headline')
        property_address = request.form.get('property_address')
        highlights = request.form.get('highlights', '')
        include_captions = request.form.get('include_captions') == 'on'
        
        # Handle file uploads
        media_files = []
        if 'media_files' in request.files:
            files = request.files.getlist('media_files')
            upload_dir = Path("uploads/video_media")
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            for file in files:
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = upload_dir / f"{user['id']}_{int(time.time())}_{filename}"
                    file.save(filepath)
                    media_files.append(str(filepath))
        
        # Create project in database
        from video_database import create_video_project
        project_id = create_video_project(
            user_id=user["id"],
            video_type=video_type,
            aspect_ratio=aspect_ratio,
            duration=duration,
            style_preset=style_preset,
            headline=headline,
            property_address=property_address,
            highlights=highlights,
            media_files=media_files,
            include_captions=include_captions
        )
        
        # Start async rendering (use background job queue)
        from video_studio import VideoRenderer
        from video_database import update_video_render_status, get_user_profile
        
        # Get agent branding
        agent_profile = get_user_profile(user["id"])
        
        # Update status to rendering
        update_video_render_status(project_id, 'rendering')
        
        # Render video (this should be async in production)
        renderer = VideoRenderer()
        result = renderer.create_listing_video(
            project_id=project_id,
            media_files=media_files,
            style=style_preset,
            aspect_ratio=aspect_ratio,
            duration=duration,
            headline=headline,
            property_address=property_address,
            agent_name=user["name"],
            agent_phone=user.get("phone", user.get("email")),
            agent_logo=agent_profile.get("brokerage_logo") if agent_profile else None,
            agent_photo=agent_profile.get("professional_photo") if agent_profile else None,
            include_captions=include_captions
        )
        
        if result["success"]:
            # Update status to complete
            update_video_render_status(
                project_id,
                'complete',
                result["output_path"]
            )
            flash("Video created successfully!", "success")
        else:
            update_video_render_status(project_id, 'failed')
            flash(f"Video creation failed: {result.get('error')}", "error")
        
        return redirect(url_for("agent_video_studio_view", project_id=project_id))
        
    except Exception as e:
        flash(f"Error creating video: {str(e)}", "error")
        return redirect(url_for("agent_video_studio"))

@app.route("/agent/video-studio/<int:project_id>")
def agent_video_studio_view(project_id):
    """View a completed video project"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    from video_database import get_video_project
    project = get_video_project(project_id)
    
    if not project or project["user_id"] != user["id"]:
        flash("Video project not found", "error")
        return redirect(url_for("agent_video_studio"))
    
    return render_template(
        "agent/video_studio_view.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        project=project
    )
```

---

## 🚧 TODO (Step 3 of 3) - Production Enhancements

### 1. **Add to Navigation Menu**
Update `templates/agent/layout.html`:
```html
<a href="{{ url_for('agent_video_studio') }}" class="ylh-nav-button">
    🎬 Video Studio
</a>
```

### 2. **Add FFmpeg to Railway**
Create `railway.toml`:
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "gunicorn app:app"

[[deploy.environmentVariables]]
name = "NIXPACKS_APT_PKGS"
value = "ffmpeg"
```

### 3. **Background Job Queue (Production)**
For production, video rendering should be async:
- Use **Celery** + **Redis** for job queue
- Or use **Railway's built-in background workers**
- Show progress bar to user
- Send email when video is ready

### 4. **Storage**
- Store videos in **Railway Volume** or **S3/R2**
- Generate thumbnails for preview
- Allow download in multiple formats

### 5. **Music Library**
Add royalty-free music tracks:
```python
MUSIC_LIBRARY = {
    "luxury_cinematic": "music/luxury_piano.mp3",
    "modern_minimal": "music/ambient_minimal.mp3",
    "warm_inviting": "music/acoustic_warm.mp3"
}
```

### 6. **Captions**
Use **Whisper AI** or **AssemblyAI** for auto-captions:
```python
def generate_captions(video_path):
    # Use Whisper to transcribe
    # Burn captions into video with FFmpeg
    pass
```

---

## 📋 Current Status

**PHASE 1 COMPLETE** ✅
- Core video renderer built
- Database schema ready
- Beautiful UI created
- Ready for Flask integration

**NEXT STEP:** Add Flask routes to `app.py` (see code above)

**ESTIMATED TIME TO LAUNCH:** 2-3 hours

---

## 🎯 Features Delivered

✅ **5-Step Wizard UI**
✅ **Drag & Drop Upload**
✅ **Multiple Aspect Ratios** (9:16, 16:9, 1:1)
✅ **Duration Options** (15s, 30s, 60s)
✅ **3 Style Presets**
✅ **Ken Burns Effect** on photos
✅ **Intro/Outro Cards** with branding
✅ **Background Music** support
✅ **Agent Branding** (logo, photo, contact)
✅ **Database Tracking**

---

## 💰 Cost Estimate

**Option A (Self-Hosted FFmpeg):**
- Compute: ~$0.05 per video render
- Storage: ~$0.02 per GB/month
- **Total:** ~$10-20/month for 100 videos

**Option B (API Service like Shotstack):**
- ~$0.50-1.00 per video
- **Total:** ~$50-100/month for 100 videos

**Recommendation:** Start with Option A (self-hosted), it's what we built!

---

**Ready to integrate! Just add the Flask routes and deploy!** 🚀

