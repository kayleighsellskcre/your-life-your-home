"""
Video Studio - FFmpeg-based video generation system
Generates luxury real estate marketing videos with branding
"""

import subprocess
import os
import json
import tempfile
from pathlib import Path
from typing import List, Dict, Optional
import base64

# Check if FFmpeg is available
try:
    subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, timeout=5)
    FFMPEG_AVAILABLE = True
except (FileNotFoundError, subprocess.SubprocessError, Exception):
    FFMPEG_AVAILABLE = False
    print("WARNING: FFmpeg not found. Video Studio will not be functional.")

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
                    
                    segments.append(segment_path)
                
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
                
                # Concatenate all segments
                all_segments = [intro_path] + segments + [outro_path]
                concat_list_path = temp_path / "concat_list.txt"
                with open(concat_list_path, 'w') as f:
                    for seg in all_segments:
                        f.write(f"file '{seg}'\n")
                
                # Final output path
                output_filename = f"video_{project_id}_{aspect_ratio.replace(':', 'x')}.mp4"
                output_path = self.output_dir / output_filename
                
                # Concatenate all segments
                concat_cmd = [
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_list_path),
                    '-c', 'copy',
                    str(output_path)
                ]
                
                subprocess.run(concat_cmd, check=True, capture_output=True)
                
                # Add music if provided
                if music_path and os.path.exists(music_path):
                    output_with_music = self.output_dir / f"video_{project_id}_{aspect_ratio.replace(':', 'x')}_music.mp4"
                    self._add_background_music(output_path, music_path, output_with_music)
                    output_path = output_with_music
                
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
        """Create video segment from image with Ken Burns effect"""
        
        # Ken Burns zoom effect
        zoom_factor = 1.1 if style == "luxury_cinematic" else 1.05
        
        cmd = [
            'ffmpeg',
            '-loop', '1',
            '-i', image_path,
            '-vf', f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},zoompan=z='min(zoom+0.0015,{zoom_factor})':d={int(duration*30)}:s={width}x{height},format=yuv420p",
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
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
        """Create intro card with text overlay"""
        
        # Create a dark gradient background
        bg_color = "#2c3e50" if style == "luxury_cinematic" else "#34495e"
        
        # Build filter complex for text overlay
        filter_parts = [
            f"color=c={bg_color}:s={width}x{height}:d={duration}[bg]"
        ]
        
        # Add logo if provided
        if logo_path and logo_path.exists():
            filter_parts.append(
                f"[bg][1:v]overlay=(W-w)/2:H/4[bg_logo]"
            )
            filter_base = "[bg_logo]"
        else:
            filter_base = "[bg]"
        
        # Add headline text
        headline_escaped = headline.replace("'", "\\'").replace(":", "\\:")
        address_escaped = address.replace("'", "\\'").replace(":", "\\:")
        
        filter_parts.append(
            f"{filter_base}drawtext=text='{headline_escaped}':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf:fontsize=80:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-40"
        )
        
        # Simplified command without logo for now
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f"color=c={bg_color}:s={width}x{height}:d={duration}",
            '-vf', f"drawtext=text='{headline_escaped}':fontsize=80:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
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
        """Create outro card with agent branding"""
        
        bg_color = "#2c3e50" if style == "luxury_cinematic" else "#34495e"
        
        agent_name_escaped = agent_name.replace("'", "\\'").replace(":", "\\:")
        agent_phone_escaped = agent_phone.replace("'", "\\'").replace(":", "\\:")
        
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f"color=c={bg_color}:s={width}x{height}:d={duration}",
            '-vf', f"drawtext=text='{agent_name_escaped}':fontsize=60:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-50,drawtext=text='{agent_phone_escaped}':fontsize=40:fontcolor=#c89666:x=(w-text_w)/2:y=(h-text_h)/2+50",
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
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

