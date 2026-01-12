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
                
                # PROFESSIONAL TRANSITION VARIETY between segments
                all_segments = [intro_path] + segments + [outro_path]
                
                # Curated list of professional, elegant transitions
                professional_transitions = [
                    'fade',          # Classic fade
                    'fadeblack',     # Fade through black (cinematic)
                    'fadewhite',     # Fade through white (clean)
                    'wipeleft',      # Smooth wipe left
                    'wiperight',     # Smooth wipe right
                    'wipeup',        # Smooth wipe up
                    'wipedown',      # Smooth wipe down
                    'slideleft',     # Slide left
                    'slideright',    # Slide right
                    'slideup',       # Slide up
                    'slidedown',     # Slide down
                    'smoothleft',    # Smooth directional left
                    'smoothright',   # Smooth directional right
                    'smoothup',      # Smooth directional up
                    'smoothdown',    # Smooth directional down
                    'circleopen',    # Elegant circle reveal
                    'circleclose',   # Elegant circle close
                    'dissolve',      # Classic dissolve
                ]
                
                import random
                fade_duration = 0.6  # Slightly longer for smoothness
                
                # Create varied transitions using xfade filter
                xfade_chain = "[0:v]"
                for i in range(1, len(all_segments)):
                    # Pick a different transition for each segment
                    # Use fadeblack for intro/outro, varied for photos
                    if i == 1:  # Intro → First photo
                        transition = 'fadeblack'
                    elif i == len(all_segments) - 1:  # Last photo → Outro
                        transition = 'fadeblack'
                    else:  # Between photos - use variety
                        transition = random.choice(professional_transitions)
                    
                    if i == 1:
                        # First transition
                        xfade_chain = f"[0:v][1:v]xfade=transition={transition}:duration={fade_duration}:offset={3-fade_duration}[v1]"
                    elif i < len(all_segments) - 1:
                        # Middle transitions
                        prev_offset = 3 + (i-1) * duration_per_item - (i-1) * fade_duration
                        xfade_chain += f";[v{i-1}][{i}:v]xfade=transition={transition}:duration={fade_duration}:offset={prev_offset-fade_duration}[v{i}]"
                    else:
                        # Last transition
                        prev_offset = 3 + (i-1) * duration_per_item - (i-1) * fade_duration
                        xfade_chain += f";[v{i-1}][{i}:v]xfade=transition={transition}:duration={fade_duration}:offset={prev_offset-fade_duration}[outv]"
                
                # Final output path
                output_filename = f"video_{project_id}_{aspect_ratio.replace(':', 'x')}.mp4"
                output_path = self.output_dir / output_filename
                
                # Build FFmpeg command with smooth fades
                fade_cmd = ['ffmpeg']
                for seg in all_segments:
                    fade_cmd.extend(['-i', str(seg)])
                
                fade_cmd.extend([
                    '-filter_complex', xfade_chain,
                    '-map', '[outv]',
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-crf', '20',
                    '-pix_fmt', 'yuv420p',
                    '-y',
                    str(output_path)
                ])
                
                print(f"[VIDEO RENDERER] Creating video with smooth fade transitions...")
                result = subprocess.run(fade_cmd, check=True, capture_output=True, text=True)
                print(f"[VIDEO RENDERER] Transitions complete")
                
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
        """Create video segment with LUXURIOUS CINEMATIC EFFECTS"""
        
        # More dramatic zoom for luxury feel
        if style == "luxury_cinematic":
            zoom_factor = 1.25  # Increased from 1.2
        else:
            zoom_factor = 1.18  # Increased from 1.15
        
        # Smooth zoom expression
        zoom_expr = f"'min(zoom+0.0018,{zoom_factor})'"  # Slightly faster zoom
        
        # Varied panning for visual interest
        import random
        pan_direction = random.choice(['left', 'right', 'center', 'up', 'down'])
        
        if pan_direction == 'left':
            x_expr = "'iw/2-(iw/zoom/2)+(on*2)'"  # Increased from 1.5
            y_expr = "'ih/2-(ih/zoom/2)'"
        elif pan_direction == 'right':
            x_expr = "'iw/2-(iw/zoom/2)-(on*2)'"
            y_expr = "'ih/2-(ih/zoom/2)'"
        elif pan_direction == 'up':
            x_expr = "'iw/2-(iw/zoom/2)'"
            y_expr = "'ih/2-(ih/zoom/2)+(on*2)'"
        elif pan_direction == 'down':
            x_expr = "'iw/2-(iw/zoom/2)'"
            y_expr = "'ih/2-(ih/zoom/2)-(on*2)'"
        else:  # center
            x_expr = "'iw/2-(iw/zoom/2)'"
            y_expr = "'ih/2-(ih/zoom/2)'"
        
        # LUXURIOUS filter chain with enhanced colors
        filter_chain = [
            f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase",
            f"crop={width*2}:{height*2}",
            f"zoompan=z={zoom_expr}:x={x_expr}:y={y_expr}:d={int(duration*30)}:s={width}x{height}",
            # Enhanced luxury color grading - richer, more vibrant
            f"eq=contrast=1.18:brightness=0.04:saturation=1.25:gamma=1.1",  # Increased saturation & added gamma
            # Stronger sharpen for crystal clarity
            "unsharp=7:7:1.3:7:7:0.0",  # Increased from 5:5:1.0
            "format=yuv420p"
        ]
        
        cmd = [
            'ffmpeg',
            '-loop', '1',
            '-i', image_path,
            '-vf', ",".join(filter_chain),
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'medium',  # Changed from ultrafast for better quality
            '-crf', '18',  # Higher quality (lower CRF)
            '-y',
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
    
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
        """
        Create video segment with 3D-STYLE EFFECTS
        - Parallax depth effect (simulates 3D movement)
        - Perspective zoom (creates depth illusion)
        - Edge highlighting (architectural emphasis)
        - Room labels with fade-in animation
        - Professional architectural color grading
        """
        
        import random
        
        # 3D movement patterns for variety
        movement_patterns = [
            {
                'name': 'forward_zoom',
                'zoom': "min(zoom+0.002,1.3)",
                'x': "'iw/2-(iw/zoom/2)'",
                'y': "'ih/2-(ih/zoom/2)'"
            },
            {
                'name': 'dolly_left',
                'zoom': "1.15",
                'x': "'iw/2-(iw/zoom/2)+(on*2.5)'",
                'y': "'ih/2-(ih/zoom/2)-(on*0.8)'"
            },
            {
                'name': 'dolly_right',
                'zoom': "1.15",
                'x': "'iw/2-(iw/zoom/2)-(on*2.5)'",
                'y': "'ih/2-(ih/zoom/2)-(on*0.8)'"
            },
            {
                'name': 'crane_up',
                'zoom': "min(zoom+0.0012,1.2)",
                'x': "'iw/2-(iw/zoom/2)'",
                'y': "'ih/2-(ih/zoom/2)+(on*3)'"
            },
            {
                'name': 'crane_down',
                'zoom': "min(zoom+0.0012,1.2)",
                'x': "'iw/2-(iw/zoom/2)'",
                'y': "'ih/2-(ih/zoom/2)-(on*3)'"
            },
            {
                'name': 'orbit_left',
                'zoom': "1.18",
                'x': "'iw/2-(iw/zoom/2)+(on*2)'",
                'y': "'ih/2-(ih/zoom/2)+(sin(on*0.1)*50)'"
            },
            {
                'name': 'orbit_right',
                'zoom': "1.18",
                'x': "'iw/2-(iw/zoom/2)-(on*2)'",
                'y': "'ih/2-(ih/zoom/2)+(sin(on*0.1)*50)'"
            }
        ]
        
        # Pick a random 3D movement
        movement = random.choice(movement_patterns)
        
        # Build LUXURIOUS 3D-style filter chain
        filter_parts = [
            # Scale up for premium quality
            f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase",
            f"crop={width*2}:{height*2}",
            # Apply dramatic 3D camera movement
            f"zoompan=z={movement['zoom']}:x={movement['x']}:y={movement['y']}:d={int(duration*30)}:s={width}x{height}",
            # LUXURIOUS architectural color grading - rich, vibrant, premium
            "eq=contrast=1.20:brightness=0.05:saturation=1.20:gamma=1.08",  # Enhanced
            # Crystal-sharp clarity for 3D depth
            "unsharp=9:9:1.5:9:9:0.0",  # Much stronger sharpening
        ]
        
        # Add room label if provided
        if room_label:
            # Simple escape for FFmpeg drawtext - just escape the essential characters
            label_escaped = room_label.replace("\\", "\\\\").replace(":", "\\:").replace("'", "")
            
            # Calculate label position (top-left corner with fade-in)
            label_x = 60
            label_y = 80
            underline_width = 350  # Luxurious wider underline
            
            # Build drawtext with proper escaping
            drawtext_filter = (
                f"drawtext=text={label_escaped}:"
                f"fontsize=85:fontcolor=white@0.98:"  # Larger, brighter text
                f"x={label_x}:y={label_y}:"
                f"shadowcolor=black@0.9:shadowx=5:shadowy=5:"  # Stronger shadow
                f"font=Arial"  # Ensure consistent font
            )
            filter_parts.append(drawtext_filter)
            
            # Add luxurious gold underline accent
            drawbox_filter = (
                f"drawbox=x={label_x}:y={label_y + 95}:w={underline_width}:h=6:"
                f"color=#d4af37@0.95:t=fill"  # Bright gold color
            )
            filter_parts.append(drawbox_filter)
        
        # Combine all filters
        filter_chain = ",".join(filter_parts)
        
        cmd = [
            'ffmpeg',
            '-loop', '1',
            '-i', image_path,
            '-vf', filter_chain,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '17',  # PREMIUM quality for luxury 3D effect
            '-pix_fmt', 'yuv420p',
            '-y',
            str(output_path)
        ]
        
        print(f"[VIDEO RENDERER] Creating luxurious 3D segment with {movement['name']} movement...")
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
        """Create simple but elegant intro card"""
        
        # Different styles for different video types
        if style == "3d_property_tour":
            bg_color = "#0a0e27"  # Deep modern blue
        elif style == "luxury_cinematic":
            bg_color = "#1a1a2e"
        else:
            bg_color = "#2c3e50"
        
        # Simple escape - just remove problematic characters
        headline_escaped = headline.replace("\\", "\\\\").replace(":", "\\:").replace("'", "")
        address_escaped = address.replace("\\", "\\\\").replace(":", "\\:").replace("'", "")
        
        # Center positions (fixed values for 1080x1920 or 1920x1080)
        headline_y = height // 2 - 80
        underline_y = height // 2 - 15
        address_y = height // 2 + 60
        
        # LUXURIOUS intro with elegant styling
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f"color=c={bg_color}:s={width}x{height}:d={duration}",
            '-vf', (
                f"fade=t=in:st=0:d=1.0,"  # Slower, more elegant fade
                f"drawtext=text={headline_escaped}:fontsize=120:fontcolor=white@0.98:x=(w-text_w)/2:y={headline_y}:shadowcolor=black@0.9:shadowx=6:shadowy=6:font=Arial,"  # Bigger, brighter
                f"drawbox=x={width//2-350}:y={underline_y}:w=700:h=5:color=#d4af37@0.95:t=fill,"  # Gold underline
                f"drawtext=text={address_escaped}:fontsize=60:fontcolor=#d4af37@0.98:x=(w-text_w)/2:y={address_y}:shadowcolor=black@0.8:shadowx=4:shadowy=4:font=Arial"  # Gold address
            ),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '20',  # Higher quality
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
        """Create simple but elegant outro card"""
        
        bg_color = "#1a1a2e" if style == "luxury_cinematic" else "#1c1c28"
        
        # Simple escape - remove problematic characters
        agent_name_escaped = agent_name.replace("\\", "\\\\").replace(":", "\\:").replace("'", "")
        agent_phone_escaped = agent_phone.replace("\\", "\\\\").replace(":", "\\:").replace("'", "")
        
        # Center positions (fixed values)
        name_y = height // 2 - 100
        line1_y = height // 2 - 115
        phone_y = height // 2 - 10
        line2_y = height // 2 + 65
        cta_y = height // 2 + 120
        
        # LUXURIOUS outro with gold accents
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f"color=c={bg_color}:s={width}x{height}:d={duration}",
            '-vf', (
                f"fade=t=in:st=0:d=0.9,"  # Slower fade
                f"drawtext=text={agent_name_escaped}:fontsize=110:fontcolor=white@0.98:x=(w-text_w)/2:y={name_y}:shadowcolor=#d4af37@0.8:shadowx=4:shadowy=4:font=Arial,"  # Gold shadow
                f"drawbox=x={width//2-300}:y={line1_y}:w=600:h=4:color=#d4af37@0.95:t=fill,"  # Gold line
                f"drawtext=text={agent_phone_escaped}:fontsize=70:fontcolor=#d4af37@0.98:x=(w-text_w)/2:y={phone_y}:shadowcolor=white@0.5:shadowx=3:shadowy=3:font=Arial,"  # Bigger gold phone
                f"drawbox=x={width//2-300}:y={line2_y}:w=600:h=4:color=#d4af37@0.95:t=fill,"  # Gold line
                f"drawtext=text=CONTACT ME TODAY:fontsize=55:fontcolor=white@0.98:x=(w-text_w)/2:y={cta_y}:shadowcolor=black@0.9:shadowx=5:shadowy=5:font=Arial"  # Bigger CTA
            ),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '20',  # Higher quality
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

