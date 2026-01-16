"""
Video Studio - FFmpeg-based video generation system
Generates luxury real estate marketing videos with branding
"""

import os
import json
import tempfile
from pathlib import Path
from typing import List, Dict, Optional
import base64

# Import subprocess with fallback
try:
    import subprocess
    SUBPROCESS_AVAILABLE = True
except ImportError:
    SUBPROCESS_AVAILABLE = False
    print("CRITICAL: subprocess module not available. Video Studio disabled.")

# Check if FFmpeg is available
FFMPEG_AVAILABLE = False
if SUBPROCESS_AVAILABLE:
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'], 
            capture_output=True, 
            timeout=3,
            text=True,
            check=False  # Don't raise on non-zero exit
        )
        FFMPEG_AVAILABLE = result.returncode == 0
        if not FFMPEG_AVAILABLE:
            print("WARNING: FFmpeg returned non-zero exit code. Video Studio will not be functional.")
    except FileNotFoundError:
        FFMPEG_AVAILABLE = False
        print("WARNING: FFmpeg not found in PATH. Video Studio will not be functional.")
    except subprocess.TimeoutExpired:
        FFMPEG_AVAILABLE = False
        print("WARNING: FFmpeg check timed out. Video Studio will not be functional.")
    except Exception as e:
        FFMPEG_AVAILABLE = False
        print(f"WARNING: FFmpeg check failed: {e}. Video Studio will not be functional.")

# Only import PIL if we need it
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: Pillow not found. Image processing may be limited.")


class VideoRenderer:
    """
    Handles video rendering using FFmpeg
    Creates luxury real estate marketing videos
    """
    
    def __init__(self, output_dir: str = "generated_videos"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    def create_listing_video(
        self,
        project_id: int,
        media_files: List[str],  # List of image/video paths
        style: str = "luxury_cinematic",
        aspect_ratio: str = "9:16",  # 9:16, 16:9, 1:1
        duration: int = 30,  # seconds
        headline: str = "Just Listed",
        property_address: str = "",
        agent_name: str = "",
        agent_phone: str = "",
        agent_logo: Optional[str] = None,  # base64 or path
        agent_photo: Optional[str] = None,  # base64 or path
        music_path: Optional[str] = None,
        include_captions: bool = True,
        video_type: str = "listing",  # listing, 3d-tour
        room_labels: Optional[List[str]] = None,  # For 3D tours
    ) -> Dict:
        """
        Generate a luxury real estate video
        
        Returns:
            {
                "success": True/False,
                "output_path": "path/to/video.mp4",
                "error": "error message if failed"
            }
        """
        
        # Check if FFmpeg is available
        if not SUBPROCESS_AVAILABLE:
            return {
                "success": False,
                "error": "subprocess module not available. Cannot render videos."
            }
            
        if not FFMPEG_AVAILABLE:
            return {
                "success": False,
                "error": "FFmpeg is not installed. Please install FFmpeg or wait for Railway deployment to complete."
            }
        
        try:
            # Calculate dimensions based on aspect ratio
            dimensions = self._get_dimensions(aspect_ratio)
            width, height = dimensions
            
            # Calculate duration per media item
            duration_per_item = duration / len(media_files)
            
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Save logos/photos if they're base64
                logo_path = self._save_base64_image(agent_logo, temp_path / "logo.png") if agent_logo else None
                photo_path = self._save_base64_image(agent_photo, temp_path / "photo.png") if agent_photo else None
                
                # Generate video segments
                segments = []
                for idx, media_file in enumerate(media_files):
                    segment_path = temp_path / f"segment_{idx}.mp4"
                    
                    print(f"[VIDEO RENDERER] Processing media {idx+1}/{len(media_files)}: {media_file}")
                    
                    # Get room label if provided
                    room_label = room_labels[idx] if room_labels and idx < len(room_labels) else None
                    
                    if self._is_image(media_file):
                        # Create video from image with appropriate effect
                        if video_type == "3d-tour":
                            # Use 3D-style effects for property tours
                            self._create_3d_image_segment(
                                media_file,
                                segment_path,
                                duration_per_item,
                                width,
                                height,
                                style,
                                room_label
                            )
                        else:
                            # Use Ken Burns effect for regular listings
                            self._create_image_segment(
                                media_file,
                                segment_path,
                                duration_per_item,
                                width,
                                height,
                                style
                            )
                    else:
                        # Process video segment
                        self._process_video_segment(
                            media_file,
                            segment_path,
                            duration_per_item,
                            width,
                            height
                        )
                    
                    if segment_path.exists():
                        print(f"[VIDEO RENDERER] ✓ Segment {idx} created: {segment_path.stat().st_size} bytes")
                        segments.append(segment_path)
                    else:
                        print(f"[VIDEO RENDERER] ✗ Segment {idx} NOT created!")
                        raise Exception(f"Failed to create segment {idx} from {media_file}")
                
                # Create intro card
                intro_path = temp_path / "intro.mp4"
                self._create_intro_card(
                    intro_path,
                    headline,
                    property_address,
                    logo_path,
                    width,
                    height,
                    style,
                    duration=3
                )
                
                # Create outro card
                outro_path = temp_path / "outro.mp4"
                self._create_outro_card(
                    outro_path,
                    agent_name,
                    agent_phone,
                    logo_path,
                    photo_path,
                    width,
                    height,
                    style,
                    duration=3
                )
                
                # ROBUST CONCATENATION - Works with ANY number of photos!
                all_segments = [intro_path] + segments + [outro_path]
                
                print(f"[VIDEO RENDERER] Combining {len(all_segments)} segments into final video...")
                
                # Create concat file for FFmpeg (MUCH more reliable than complex filter chains!)
                concat_file = temp_path / "concat_list.txt"
                with open(concat_file, 'w') as f:
                    for seg in all_segments:
                        # Write each segment path (use forward slashes for Windows compatibility)
                        seg_path = str(seg).replace('\\', '/')
                        f.write(f"file '{seg_path}'\n")
                
                # Final output path
                output_filename = f"video_{project_id}_{aspect_ratio.replace(':', 'x')}.mp4"
                output_path = self.output_dir / output_filename
                
                # Build LUXURY FFmpeg concat command (fast combine, already rendered segments!)
                concat_cmd = [
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_file),
                    '-c', 'copy',  # COPY - don't re-encode! Just combine!
                    '-y',
                    str(output_path)
                ]
                
                print(f"[VIDEO RENDERER] Rendering final video with {len(all_segments)} segments...")
                result = subprocess.run(concat_cmd, check=True, capture_output=True, text=True)
                print(f"[VIDEO RENDERER] ✓ Final video created successfully!")
                
                # Add music if provided
                if music_path and os.path.exists(music_path):
                    output_with_music = self.output_dir / f"video_{project_id}_{aspect_ratio.replace(':', 'x')}_music.mp4"
                    self._add_background_music(output_path, music_path, output_with_music)
                    output_path = output_with_music
                
                # Verify the file was actually created
                if not output_path.exists():
                    raise Exception(f"Video file was not created at {output_path}")
                
                print(f"[VIDEO RENDERER] Successfully created video at {output_path}")
                print(f"[VIDEO RENDERER] File size: {output_path.stat().st_size} bytes")
                
                return {
                    "success": True,
                    "output_path": str(output_path),
                    "filename": output_filename
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_dimensions(self, aspect_ratio: str) -> tuple:
        """Get video dimensions for aspect ratio"""
        ratios = {
            "9:16": (1080, 1920),  # Reels/TikTok
            "16:9": (1920, 1080),  # YouTube
            "1:1": (1080, 1080)    # Square
        }
        return ratios.get(aspect_ratio, (1080, 1920))
    
    def _is_image(self, file_path: str) -> bool:
        """Check if file is an image"""
        extensions = ['.jpg', '.jpeg', '.png', '.heic', '.webp']
        return any(file_path.lower().endswith(ext) for ext in extensions)
    
    def _save_base64_image(self, base64_data: str, output_path: Path) -> Optional[Path]:
        """Save base64 image to file"""
        if not PIL_AVAILABLE:
            print("WARNING: PIL not available, cannot save base64 image")
            return None
            
        try:
            from PIL import Image
            import io
            
            if base64_data.startswith('data:image'):
                # Extract base64 data
                base64_data = base64_data.split(',')[1]
            
            image_data = base64.b64decode(base64_data)
            img = Image.open(io.BytesIO(image_data))
            img.save(output_path)
            return output_path
        except Exception as e:
            print(f"Error saving base64 image: {e}")
            return None
    
    def _create_image_segment(
        self,
        image_path: str,
        output_path: Path,
        duration: float,
        width: int,
        height: int,
        style: str
    ):
        """Create LUXURY video segment with MAXIMUM effects - Pre-rendered!"""
        
        import random
        
        # ULTRA-SIMPLE movements - guaranteed to work on Windows!
        movements = [
            f"z=zoom+0.001:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)",  # Zoom in (standard)
            f"z=1.12:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)",  # Static zoom centered
            f"z=1.1:x=x+2:y=ih/2-(ih/zoom/2)",  # Pan right
            f"z=1.08:x=iw/2-(iw/zoom/2):y=y+1",  # Pan down
        ]
        movement = random.choice(movements)
        
        # Build ULTRA-LUXURY filter chain - Magazine-quality presentation
        filters = [
            # 1. SCALE TO FIT ENTIRE PHOTO (no cropping!) with black letterbox
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
            # 2. CINEMATIC MOVEMENT (Ken Burns effect)
            f"zoompan={movement}:d={int(duration*30)}:s={width}x{height}:fps=30",
            # 3. HIGH-END COLOR GRADING (luxury magazine look)
            "eq=contrast=1.25:brightness=0.06:saturation=1.28:gamma=1.05",
            # 4. CRYSTAL-SHARP CLARITY (premium definition)
            "unsharp=9:9:2.0:9:9:0.2",
            # 5. DRAMATIC VIGNETTE (cinematic depth)
            "vignette=angle=PI/3.5:mode=forward",
            # 6. SILKY-SMOOTH CROSSFADE TRANSITIONS (1.5 second luxury fade)
            f"fade=t=in:st=0:d=1.5,fade=t=out:st={duration-1.5}:d=1.5"
        ]
        
        cmd = [
            'ffmpeg',
            '-loop', '1',
            '-i', image_path,
            '-vf', ','.join(filters),
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'medium',  # Balanced quality/speed
            '-crf', '18',  # High quality (excellent balance)
            '-pix_fmt', 'yuv420p',
            '-y',
            str(output_path)
        ]
        
        print(f"[VIDEO RENDERER] Creating LUXURY segment with cinematic effects...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: {result.stderr}")
            raise Exception(f"Segment creation failed: {result.stderr}")
        print(f"[VIDEO RENDERER] ✓ LUXURY segment created!")
    
    def _create_3d_image_segment(
        self,
        image_path: str,
        output_path: Path,
        duration: float,
        width: int,
        height: int,
        style: str,
        room_label: Optional[str] = None
    ):
        """Create PREMIUM 3D segment with MAXIMUM architectural effects!"""
        
        import random
        
        # Choose random 3D effect (using DIFFERENT filters for variety!)
        effect_type = random.choice(['perspective', 'tilt', 'zoom'])
        
        # Build ULTRA-3D filter chain - SHOW COMPLETE PHOTO with elegant transitions
        filters = [
            # SCALE TO FIT ENTIRE PHOTO (no cropping!) with black letterbox
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        ]
        
        # Add 3D movement effect
        if effect_type == 'perspective':
            # PERSPECTIVE TRANSFORM - Creates actual 3D depth!
            # Subtle perspective that simulates forward movement
            filters.append(f"perspective=x0=0:y0={int(height*0.05)}:x1={width}:y1={int(height*0.05)}:x2=0:y2={height}:x3={width}:y3={height}:sense=source")
        elif effect_type == 'tilt':
            # SUBTLE ROTATION - Creates 3D tilt effect
            filters.append("rotate=angle=-0.5*PI/180:fillcolor=black")
        
        # ZOOMPAN with simple working expression
        movement = f"z=zoom+0.002:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)"
        filters.append(f"zoompan={movement}:d={int(duration*30)}:s={width}x{height}:fps=30")
        
        # ULTRA-LUXURY 3D DEPTH EFFECTS
        filters.extend([
            # DRAMATIC ARCHITECTURAL COLOR GRADING (high-end magazine look)
            "eq=contrast=1.28:brightness=0.07:saturation=1.32:gamma=1.08",
            # RAZOR-SHARP CLARITY (maximum 3D definition)
            "unsharp=11:11:2.5:11:11:0.3",
            # CINEMATIC VIGNETTE (creates dramatic depth focus)
            "vignette=angle=PI/3:mode=forward",
            # PREMIUM CROSSFADE TRANSITIONS (1.8 second buttery-smooth fade)
            f"fade=t=in:st=0:d=1.8,fade=t=out:st={duration-1.8}:d=1.8"
        ])
        
        # Add room label if provided
        if room_label:
            # Clean label text - remove ALL special characters
            label_clean = room_label.replace("'", "").replace(":", "").replace('"', '').replace("\\", "").replace(",", "")[:30]
            # ULTRA-LUXURY ROOM LABEL with premium styling
            label_filter = f"drawtext=text='{label_clean}':fontsize=95:fontcolor=white@0.99:x=(w-text_w)/2:y=110:shadowcolor=#d4af37@0.95:shadowx=8:shadowy=8:box=1:boxcolor=black@0.7:boxborderw=20"
            filters.append(label_filter)
        
        cmd = [
            'ffmpeg',
            '-loop', '1',
            '-i', image_path,
            '-vf', ','.join(filters),
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'medium',  # Balanced quality/speed
            '-crf', '17',  # High quality (excellent)
            '-pix_fmt', 'yuv420p',
            '-y',
            str(output_path)
        ]
        
        print(f"[VIDEO RENDERER] Creating ULTRA-LUXURY 3D segment{' with room label' if room_label else ''}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: {result.stderr}")
            raise Exception(f"3D segment failed: {result.stderr}")
        print(f"[VIDEO RENDERER] ✓ ULTRA-LUXURY 3D segment created!")
    
    def _process_video_segment(
        self,
        video_path: str,
        output_path: Path,
        duration: float,
        width: int,
        height: int
    ):
        """Process video segment - resize and trim"""
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vf', f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-y',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
    
    def _create_intro_card(
        self,
        output_path: Path,
        headline: str,
        address: str,
        logo_path: Optional[Path],
        width: int,
        height: int,
        style: str,
        duration: float = 3
    ):
        """Create STUNNING intro card with luxury branding"""
        
        # Luxury backgrounds
        if style == "3d_property_tour":
            bg_color = "#0a0e27"
        elif style == "luxury_cinematic":
            bg_color = "#1a1a2e"
        else:
            bg_color = "#2c3e50"
        
        # Clean text for FFmpeg - remove ALL special characters
        headline_clean = headline.replace("'", "").replace('"', '').replace(":", " ").replace("\\", "").replace(",", "")[:50]
        address_clean = address.replace("'", "").replace('"', '').replace(":", " ").replace("\\", "").replace(",", " ")[:60]
        
        # Calculate positions for center alignment
        headline_y = int(height / 2 - 120)
        line_y = int(height / 2 - 20)
        address_y = int(height / 2 + 60)
        
        # Build ULTRA-LUXURY text overlay filter
        text_filters = [
            # Elegant fade in background
            f"fade=t=in:st=0:d=1.2",
            # HEADLINE - Large, bold, premium white with dramatic shadow
            f"drawtext=text='{headline_clean}':fontsize=130:fontcolor=white@0.99:x=(w-text_w)/2:y={headline_y}:shadowcolor=black@0.95:shadowx=7:shadowy=7",
            # PREMIUM GOLDEN ACCENT LINE (thicker, brighter)
            f"drawbox=x=(w-450)/2:y={line_y}:w=450:h=8:color=#d4af37@0.98:t=fill",
            # ADDRESS - Elegant golden text with glow effect
            f"drawtext=text='{address_clean}':fontsize=75:fontcolor=#d4af37@0.99:x=(w-text_w)/2:y={address_y}:shadowcolor=black@0.85:shadowx=4:shadowy=4"
        ]
        
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f"color=c={bg_color}:s={width}x{height}:d={duration}",
            '-vf', ','.join(text_filters),
            '-c:v', 'libx264',
            '-preset', 'fast',  # Fast for text cards
            '-crf', '20',
            '-pix_fmt', 'yuv420p',
            '-y',
            str(output_path)
        ]
        
        print(f"[VIDEO RENDERER] Creating ULTRA-LUXURY intro card...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: {result.stderr}")
            raise Exception(f"Intro card failed: {result.stderr}")
        print(f"[VIDEO RENDERER] ✓ ULTRA-LUXURY intro created!")
    
    def _create_outro_card(
        self,
        output_path: Path,
        agent_name: str,
        agent_phone: str,
        logo_path: Optional[Path],
        photo_path: Optional[Path],
        width: int,
        height: int,
        style: str,
        duration: float = 3
    ):
        """Create STUNNING outro card with agent branding"""
        
        bg_color = "#1a1a2e" if style == "luxury_cinematic" else "#1c1c28"
        
        # Clean text - remove ALL special characters
        name_clean = agent_name.replace("'", "").replace('"', '').replace(":", " ").replace("\\", "").replace(",", "")[:40]
        phone_clean = agent_phone.replace("'", "").replace('"', '').replace(":", " ").replace("\\", "").replace(",", "")[:20]
        
        # Calculate positions
        name_y = int(height / 2 - 140)
        line_y = int(height / 2 - 30)
        phone_y = int(height / 2 + 40)
        cta_y = int(height / 2 + 140)
        
        # Build ULTRA-LUXURY outro filter
        text_filters = [
            # Elegant fade in
            f"fade=t=in:st=0:d=1.2",
            # AGENT NAME - Bold premium white with golden glow
            f"drawtext=text='{name_clean}':fontsize=120:fontcolor=white@0.99:x=(w-text_w)/2:y={name_y}:shadowcolor=#d4af37@0.9:shadowx=6:shadowy=6",
            # PREMIUM GOLDEN ACCENT LINE (thicker)
            f"drawbox=x=(w-550)/2:y={line_y}:w=550:h=8:color=#d4af37@0.98:t=fill",
            # PHONE - Prominent golden text with glow
            f"drawtext=text='{phone_clean}':fontsize=85:fontcolor=#d4af37@0.99:x=(w-text_w)/2:y={phone_y}:shadowcolor=black@0.9:shadowx=5:shadowy=5",
            # CALL TO ACTION - Elegant white with emphasis
            f"drawtext=text='Contact Me Today':fontsize=70:fontcolor=white@0.95:x=(w-text_w)/2:y={cta_y}:shadowcolor=black@0.85:shadowx=4:shadowy=4"
        ]
        
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f"color=c={bg_color}:s={width}x{height}:d={duration}",
            '-vf', ','.join(text_filters),
            '-c:v', 'libx264',
            '-preset', 'fast',  # Fast for text cards
            '-crf', '20',
            '-pix_fmt', 'yuv420p',
            '-y',
            str(output_path)
        ]
        
        print(f"[VIDEO RENDERER] Creating ULTRA-LUXURY outro card...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: {result.stderr}")
            raise Exception(f"Outro card failed: {result.stderr}")
        print(f"[VIDEO RENDERER] ✓ ULTRA-LUXURY outro created!")
    
    def _add_background_music(
        self,
        video_path: Path,
        music_path: str,
        output_path: Path
    ):
        """Add background music to video"""
        
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-i', music_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            '-y',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)


# Export
__all__ = ['VideoRenderer']

