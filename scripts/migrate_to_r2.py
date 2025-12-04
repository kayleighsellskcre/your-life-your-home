"""
Migrate existing local files to Cloudflare R2
Run this after setting up R2 credentials in Railway
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_connection
from r2_storage import upload_local_file_to_r2, is_r2_enabled


def migrate_documents_to_r2():
    """Upload all local homeowner documents to R2"""
    
    if not is_r2_enabled():
        print("❌ R2 is not configured. Set environment variables first:")
        print("   - R2_ENDPOINT")
        print("   - R2_ACCESS_KEY_ID")
        print("   - R2_SECRET_ACCESS_KEY")
        print("   - R2_BUCKET")
        return
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all documents without R2 key
    cur.execute("""
        SELECT id, file_name 
        FROM homeowner_documents 
        WHERE r2_key IS NULL OR r2_key = ''
    """)
    docs = cur.fetchall()
    
    if not docs:
        print("✅ No documents need migration. All files are already in R2!")
        conn.close()
        return
    
    print(f"Found {len(docs)} documents to migrate...\n")
    
    # Path to local files
    base_dir = Path(__file__).parent.parent
    local_dir = base_dir / "static" / "uploads" / "homeowner_docs"
    
    success_count = 0
    error_count = 0
    
    for doc in docs:
        doc_id = doc["id"]
        filename = doc["file_name"]
        local_path = local_dir / filename
        
        if not local_path.exists():
            print(f"⚠️  File not found locally: {filename}")
            error_count += 1
            continue
        
        try:
            # Upload to R2
            print(f"Uploading: {filename}...", end=" ")
            result = upload_local_file_to_r2(str(local_path), folder="documents")
            
            # Update database with R2 info
            cur.execute("""
                UPDATE homeowner_documents 
                SET r2_key = ?, r2_url = ? 
                WHERE id = ?
            """, (result["key"], result["url"], doc_id))
            conn.commit()
            
            print(f"✅ → {result['key']}")
            success_count += 1
            
            # Optional: Delete local file after successful upload
            # Uncomment the next line to delete local files after migration
            # local_path.unlink()
            # print(f"   🗑️  Deleted local copy")
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            error_count += 1
    
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"✅ Migration complete!")
    print(f"   Successful: {success_count}")
    print(f"   Errors: {error_count}")
    print(f"{'='*60}")
    
    if success_count > 0:
        print("\n💡 Tip: Local files are still on disk.")
        print("   Once you verify R2 works, you can delete them to save space.")


if __name__ == "__main__":
    print("="*60)
    print("  Cloudflare R2 Migration Tool")
    print("  Your Life Your Home Platform")
    print("="*60)
    print()
    
    migrate_documents_to_r2()
