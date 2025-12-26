"""
Database functions for Video Studio
"""

import json
from database import get_connection
from typing import Optional, List, Dict

def create_video_project(
    user_id: int,
    video_type: str,
    aspect_ratio: str,
    duration: int,
    style_preset: str,
    headline: str = "",
    property_address: str = "",
    highlights: str = "",
    media_files: List[str] = None,
    transaction_id: Optional[int] = None,
    include_lender: bool = False,
    include_captions: bool = True
) -> int:
    """Create a new video project"""
    conn = get_connection()
    cur = conn.cursor()
    
    media_json = json.dumps(media_files or [])
    
    cur.execute("""
        INSERT INTO video_projects (
            user_id, transaction_id, video_type, aspect_ratio, duration,
            style_preset, headline, property_address, highlights, media_files,
            include_lender, include_captions, render_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
    """, (
        user_id, transaction_id, video_type, aspect_ratio, duration,
        style_preset, headline, property_address, highlights, media_json,
        1 if include_lender else 0, 1 if include_captions else 0
    ))
    
    project_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    return project_id

def get_video_project(project_id: int):
    """Get video project by ID"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM video_projects WHERE id = ?", (project_id,))
    project = cur.fetchone()
    conn.close()
    
    if project:
        project_dict = dict(project)
        # Parse JSON fields
        if project_dict.get('media_files'):
            project_dict['media_files'] = json.loads(project_dict['media_files'])
        return project_dict
    return None

def get_user_video_projects(user_id: int) -> List[Dict]:
    """Get all video projects for a user"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT * FROM video_projects 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    """, (user_id,))
    
    projects = cur.fetchall()
    conn.close()
    
    result = []
    for project in projects:
        project_dict = dict(project)
        if project_dict.get('media_files'):
            project_dict['media_files'] = json.loads(project_dict['media_files'])
        result.append(project_dict)
    
    return result

def update_video_render_status(
    project_id: int,
    status: str,
    output_path: Optional[str] = None,
    thumbnail_path: Optional[str] = None
):
    """Update video project render status"""
    conn = get_connection()
    cur = conn.cursor()
    
    if output_path:
        cur.execute("""
            UPDATE video_projects 
            SET render_status = ?, output_path = ?, thumbnail_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, output_path, thumbnail_path, project_id))
    else:
        cur.execute("""
            UPDATE video_projects 
            SET render_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, project_id))
    
    conn.commit()
    conn.close()

def delete_video_project(project_id: int, user_id: int) -> bool:
    """Delete a video project"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        DELETE FROM video_projects 
        WHERE id = ? AND user_id = ?
    """, (project_id, user_id))
    
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    
    return deleted

