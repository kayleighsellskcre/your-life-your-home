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
                    
                    if self._is_image(media_file):
                        # Create video from image with Ken Burns effect
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
                
                # SIMPLE CONCATENATION - No fancy transitions for now
                all_segments = [intro_path] + segments + [outro_path]
                concat_list_path = temp_path / "concat_list.txt"
                with open(concat_list_path, 'w') as f:
                    for seg in all_segments:
                        f.write(f"file '{seg}'\n")
                
                # Final output path
                output_filename = f"video_{project_id}_{aspect_ratio.replace(':', 'x')}.mp4"
                output_path = self.output_dir / output_filename
                
                # Simple concatenate - NO xfade
                concat_cmd = [
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_list_path),
                    '-c', 'copy',
                    '-y',
                    str(output_path)
                ]
                
                print(f"[VIDEO RENDERER] Running simple concat...")
                result = subprocess.run(concat_cmd, check=True, capture_output=True, text=True)
                print(f"[VIDEO RENDERER] Concat complete")
                
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
        """Create video segment with CINEMATIC EFFECTS - Ken Burns + particles + lens flares"""
        
        # More dramatic zoom for luxury feel - SIMPLIFIED
        if style == "luxury_cinematic":
            zoom_factor = 1.2
        else:
            zoom_factor = 1.15
        
        # Simple zoom expression
        zoom_expr = f"'min(zoom+0.002,{zoom_factor})'"
        
        # Simplified panning - just left or right
        import random
        pan_direction = random.choice(['left', 'right', 'center'])
        
        if pan_direction == 'left':
            x_expr = "'iw/2-(iw/zoom/2)+(on*2)'"  # Pan left gradually
            y_expr = "'ih/2-(ih/zoom/2)'"
        elif pan_direction == 'right':
            x_expr = "'iw/2-(iw/zoom/2)-(on*2)'"  # Pan right gradually
            y_expr = "'ih/2-(ih/zoom/2)'"
        else:  # center
            x_expr = "'iw/2-(iw/zoom/2)'"
            y_expr = "'ih/2-(ih/zoom/2)'"
        
        # NO speed effects - keep it simple and stable
        
        # Build the SIMPLE filter chain
        filter_chain = [
            f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase",
            f"crop={width*2}:{height*2}",
            f"zoompan=z={zoom_expr}:x={x_expr}:y={y_expr}:d={int(duration*30)}:s={width}x{height}",
            f"eq=contrast=1.1:brightness=0.02:saturation=1.15",
            "unsharp=5:5:1.0:5:5:0.0",
            "format=yuv420p"
        ]
        
        cmd = [
            'ffmpeg',
            '-loop', '1',
            '-i', image_path,
            '-vf', ",".join(filter_chain),
            '-t', str(duration),  # Use original duration for output
            '-c:v', 'libx264',
            '-preset', 'slow',
            '-crf', '17',  # Even higher quality
            '-y',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
    
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
        """Create CINEMATIC intro card with particles, light rays, and animated text"""
        
        # Luxury gradient backgrounds
        if style == "luxury_cinematic":
            bg_color1 = "#0a0a0f"
            bg_color2 = "#1a1a2e"
        else:
            bg_color1 = "#1c1c28"
            bg_color2 = "#2c3e50"
        
        # Escape text for FFmpeg
        headline_escaped = headline.replace("'", "\\'").replace(":", "\\:")
        address_escaped = address.replace("'", "\\'").replace(":", "\\:")
        
        # Create DRAMATIC animated intro - SIMPLIFIED for compatibility
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f"color=c={bg_color1}:s={width}x{height}:d={duration}",
            '-vf', (
                # Subtle gradient (compatible)
                f"lutyuv=u=128:v=128+20*sin(2*PI*T/{duration}),"
                # Fade in dramatically
                f"fade=t=in:st=0:d=1.0,"
                # Vignette for focus
                "vignette=angle=PI/4:mode=forward,"
                # ANIMATED TEXT - Headline with scale + glow effect
                f"drawtext=text='{headline_escaped}':fontsize=110:fontcolor=white:x=(w-text_w)/2:y=h/2-100+(100*(1-min(1,t/1.2))):alpha='min(1,t/0.8)':shadowcolor=black@0.8:shadowx=4:shadowy=4,"
                # Luxury underline that grows
                f"drawbox=x=(w-600)/2:y=h/2-20:w=600*min(t/1.5,1):h=3:color=#c89666@0.8:t=fill,"
                # Address with fade + slide from bottom  
                f"drawtext=text='{address_escaped}':fontsize=55:fontcolor=#c89666:x=(w-text_w)/2:y=h/2+60+(50*(1-min(1,(t-0.8)/0.8))):alpha='if(lt(t,0.8),0,min(1,(t-0.8)*2))':shadowcolor=black@0.6:shadowx=3:shadowy=3"
            ),
            '-c:v', 'libx264',
            '-preset', 'slow',
            '-crf', '17',
            '-pix_fmt', 'yuv420p',
            '-y',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
    
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
        """Create SHOWSTOPPING outro card with particles, light beams, and CTA"""
        
        # Luxury gradient
        if style == "luxury_cinematic":
            bg_color1 = "#0a0a0f"
        else:
            bg_color1 = "#1c1c28"
        
        agent_name_escaped = agent_name.replace("'", "\\'").replace(":", "\\:")
        agent_phone_escaped = agent_phone.replace("'", "\\'").replace(":", "\\:")
        
        # Create SHOWSTOPPING outro - SIMPLIFIED for compatibility
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f"color=c={bg_color1}:s={width}x{height}:d={duration}",
            '-vf', (
                # Subtle animated gradient (compatible)
                f"lutyuv=u=128:v=128+25*sin(2*PI*T/{duration}),"
                # Fade in
                f"fade=t=in:st=0:d=0.7,"
                # Vignette
                "vignette=angle=PI/4,"
                # Name - scale up from center with glow
                f"drawtext=text='{agent_name_escaped}':fontsize=90:fontcolor=white:x=(w-text_w)/2:y=h/2-100:alpha='if(lt(t,0.3),0,min(1,(t-0.3)*3))':shadowcolor=#c89666@0.8:shadowx=0:shadowy=0,"
                # Decorative line above name
                f"drawbox=x=(w-500)/2:y=h/2-130:w=500*min(t/0.8,1):h=2:color=#c89666@0.9:t=fill,"
                # Contact with pulse effect
                f"drawtext=text='{agent_phone_escaped}':fontsize=65:fontcolor=#c89666:x=(w-text_w)/2:y=h/2-20:alpha='if(lt(t,0.8),0,min(1,(t-0.8)*2.5))':shadowcolor=white@0.4:shadowx=0:shadowy=0,"
                # Decorative line below contact
                f"drawbox=x=(w-500)/2:y=h/2+50:w=500*min((t-0.5)/0.8,1):h=2:color=#c89666@0.9:t=fill,"
                # CTA with animated entrance
                f"drawtext=text='CONTACT ME TODAY':fontsize=50:fontcolor=white@0.9:x=(w-text_w)/2:y=h/2+100+(30*(1-min(1,(t-1.2)/0.6))):alpha='if(lt(t,1.2),0,min(1,(t-1.2)*3))':shadowcolor=black@0.7:shadowx=3:shadowy=3,"
                # Secondary CTA
                f"drawtext=text='Let\\'s Make Your Dream Home a Reality':fontsize=38:fontcolor=white@0.7:x=(w-text_w)/2:y=h/2+170:alpha='if(lt(t,1.8),0,min(0.8,(t-1.8)*2))'"
            ),
            '-c:v', 'libx264',
            '-preset', 'slow',
            '-crf', '17',
            '-pix_fmt', 'yuv420p',
            '-y',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
    
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

