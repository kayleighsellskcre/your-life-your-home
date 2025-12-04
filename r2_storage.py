"""
Cloudflare R2 Storage Helper
Handles file uploads/downloads to R2 (S3-compatible storage)
"""
import os
import mimetypes
from pathlib import Path
from uuid import uuid4


def get_r2_client():
    """Get the R2 client from app.py (avoid circular import)"""
    from app import R2_CLIENT
    return R2_CLIENT


def is_r2_enabled():
    """Check if R2 is configured"""
    return all(key in os.environ for key in ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"])


def upload_file_to_r2(file_obj, original_filename, folder="documents"):
    """
    Upload a file to Cloudflare R2
    
    Args:
        file_obj: Flask file object (from request.files)
        original_filename: Original name of the file
        folder: Folder in R2 bucket (e.g., "documents", "images", "timeline")
    
    Returns:
        dict with 'key' (R2 path) and 'url' (public URL if available)
    """
    if not is_r2_enabled():
        raise Exception("R2 storage is not configured. Set environment variables.")
    
    client = get_r2_client()
    bucket = os.environ["R2_BUCKET"]
    
    # Generate unique filename to avoid collisions
    file_ext = Path(original_filename).suffix
    unique_name = f"{uuid4()}{file_ext}"
    file_key = f"{folder}/{unique_name}"
    
    # Detect content type
    content_type, _ = mimetypes.guess_type(original_filename)
    if not content_type:
        content_type = "application/octet-stream"
    
    # Upload to R2
    client.upload_fileobj(
        file_obj,
        bucket,
        file_key,
        ExtraArgs={"ContentType": content_type}
    )
    
    # Generate public URL if R2_PUBLIC_URL is set
    public_url = None
    if "R2_PUBLIC_URL" in os.environ:
        public_url = f"{os.environ['R2_PUBLIC_URL']}/{file_key}"
    
    return {
        "key": file_key,
        "url": public_url,
        "original_filename": original_filename
    }


def upload_local_file_to_r2(local_path, folder="documents"):
    """
    Upload an existing local file to R2
    
    Args:
        local_path: Path to local file (string or Path object)
        folder: Folder in R2 bucket
    
    Returns:
        dict with 'key' and 'url'
    """
    if not is_r2_enabled():
        raise Exception("R2 storage is not configured.")
    
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(f"File not found: {local_path}")
    
    client = get_r2_client()
    bucket = os.environ["R2_BUCKET"]
    
    # Generate unique filename
    file_ext = local_path.suffix
    unique_name = f"{uuid4()}{file_ext}"
    file_key = f"{folder}/{unique_name}"
    
    # Detect content type
    content_type, _ = mimetypes.guess_type(str(local_path))
    if not content_type:
        content_type = "application/octet-stream"
    
    # Upload to R2
    client.upload_file(
        str(local_path),
        bucket,
        file_key,
        ExtraArgs={"ContentType": content_type}
    )
    
    # Generate public URL
    public_url = None
    if "R2_PUBLIC_URL" in os.environ:
        public_url = f"{os.environ['R2_PUBLIC_URL']}/{file_key}"
    
    return {
        "key": file_key,
        "url": public_url,
        "original_filename": local_path.name
    }


def download_file_from_r2(file_key, destination_path):
    """
    Download a file from R2 to local disk
    
    Args:
        file_key: R2 object key (e.g., "documents/abc123.pdf")
        destination_path: Where to save the file locally
    
    Returns:
        Path to downloaded file
    """
    if not is_r2_enabled():
        raise Exception("R2 storage is not configured.")
    
    client = get_r2_client()
    bucket = os.environ["R2_BUCKET"]
    
    destination_path = Path(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    
    client.download_file(bucket, file_key, str(destination_path))
    
    return destination_path


def get_file_url_from_r2(file_key):
    """
    Get a presigned URL for a file (for private access)
    
    Args:
        file_key: R2 object key
    
    Returns:
        Presigned URL (valid for 1 hour)
    """
    if not is_r2_enabled():
        raise Exception("R2 storage is not configured.")
    
    # If public URL is configured, use that
    if "R2_PUBLIC_URL" in os.environ:
        return f"{os.environ['R2_PUBLIC_URL']}/{file_key}"
    
    # Otherwise generate presigned URL
    client = get_r2_client()
    bucket = os.environ["R2_BUCKET"]
    
    url = client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': file_key},
        ExpiresIn=3600  # 1 hour
    )
    
    return url


def delete_file_from_r2(file_key):
    """
    Delete a file from R2
    
    Args:
        file_key: R2 object key to delete
    
    Returns:
        True if successful
    """
    if not is_r2_enabled():
        raise Exception("R2 storage is not configured.")
    
    client = get_r2_client()
    bucket = os.environ["R2_BUCKET"]
    
    client.delete_object(Bucket=bucket, Key=file_key)
    
    return True


def file_exists_in_r2(file_key):
    """
    Check if a file exists in R2
    
    Args:
        file_key: R2 object key
    
    Returns:
        True if file exists, False otherwise
    """
    if not is_r2_enabled():
        return False
    
    try:
        client = get_r2_client()
        bucket = os.environ["R2_BUCKET"]
        client.head_object(Bucket=bucket, Key=file_key)
        return True
    except:
        return False
