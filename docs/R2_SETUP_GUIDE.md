# Cloudflare R2 Setup Guide

## ✅ What's Been Implemented

Your platform now supports Cloudflare R2 cloud storage for all documents and files!

### Files Created/Modified:
1. **`r2_storage.py`** - Helper functions for R2 operations
2. **`database.py`** - Added `r2_key` and `r2_url` columns
3. **`app.py`** - Updated upload/download routes to use R2
4. **`requirements.txt`** - Already includes `boto3`

---

## 🚀 How to Enable R2 on Railway

### Step 1: Get Your Cloudflare R2 Credentials

1. Log into Cloudflare Dashboard
2. Go to **R2** section
3. Create a bucket (e.g., `ylh-documents`)
4. Click **"Manage R2 API Tokens"**
5. Create a new API token with:
   - Permission: **Read & Write**
   - Apply to: **Specific bucket** (select your bucket)
6. Save these values:
   - Access Key ID
   - Secret Access Key
   - Bucket name
   - Account ID (from R2 dashboard URL)

### Step 2: Set Environment Variables in Railway

Go to your Railway project → Variables → Add these:

```
R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<your-access-key>
R2_SECRET_ACCESS_KEY=<your-secret-key>
R2_BUCKET=ylh-documents
```

**Optional (for public access):**
```
R2_PUBLIC_URL=https://pub-544fd02b06a54002a87f3e0fad80a4d6.r2.dev
```

To get public URL:
- In R2 dashboard, click your bucket
- Go to Settings → Public Access
- Click "Allow Access"
- Copy the R2.dev URL

### Step 3: Deploy to Railway

Railway will automatically:
1. Install `boto3` from requirements.txt
2. Load your R2 environment variables
3. Start uploading files to R2!

---

## 🏠 How It Works Locally (Development)

### Without R2 Variables:
- Files save to local disk (`static/uploads/homeowner_docs/`)
- Everything works normally for development

### With R2 Variables Set:
```powershell
$env:R2_ENDPOINT="https://..."
$env:R2_ACCESS_KEY_ID="..."
$env:R2_SECRET_ACCESS_KEY="..."
$env:R2_BUCKET="ylh-documents"
flask run
```

- Files upload to R2 automatically
- Test the full cloud storage flow locally

---

## 📁 What Gets Stored in R2

### Current Implementation:
- ✅ Homeowner documents (PDFs, files uploaded via "Upload Documents")

### Future (Easy to Add):
- Design board images
- Timeline photos
- Profile pictures
- Property images

All follow the same pattern - just call `upload_file_to_r2()` in any route!

---

## 🔄 Migration: Moving Existing Local Files to R2

If you already have files in `static/uploads/`, run this script to migrate them:

```python
# scripts/migrate_to_r2.py
import sys
sys.path.insert(0, '..')

from pathlib import Path
from database import get_connection
from r2_storage import upload_local_file_to_r2

def migrate_documents():
    """Upload all local documents to R2 and update database"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all documents without r2_key
    cur.execute("SELECT id, file_name FROM homeowner_documents WHERE r2_key IS NULL")
    docs = cur.fetchall()
    
    local_dir = Path("../static/uploads/homeowner_docs")
    
    for doc in docs:
        doc_id = doc["id"]
        filename = doc["file_name"]
        local_path = local_dir / filename
        
        if not local_path.exists():
            print(f"❌ File not found: {filename}")
            continue
        
        try:
            # Upload to R2
            result = upload_local_file_to_r2(local_path, folder="documents")
            
            # Update database
            cur.execute(
                "UPDATE homeowner_documents SET r2_key = ?, r2_url = ? WHERE id = ?",
                (result["key"], result["url"], doc_id)
            )
            conn.commit()
            
            print(f"✅ Migrated: {filename} → {result['key']}")
            
            # Optional: delete local file after successful upload
            # local_path.unlink()
            
        except Exception as e:
            print(f"❌ Failed {filename}: {e}")
    
    conn.close()
    print("\n✅ Migration complete!")

if __name__ == "__main__":
    migrate_documents()
```

Run it:
```bash
cd scripts
python migrate_to_r2.py
```

---

## 💰 Cost Estimate

### Cloudflare R2 Pricing:
- Storage: **$0.015/GB/month**
- Downloads: **$0** (FREE!)
- Uploads: **$0** (FREE!)

### Example Costs:
```
100 users × 50MB each = 5GB
Cost: $0.08/month 🎉

1000 users × 50MB each = 50GB
Cost: $0.75/month 🎉

10,000 users × 50MB each = 500GB
Cost: $7.50/month 🎉
```

Compare to AWS S3:
- Storage: $0.023/GB (~50% more expensive)
- Downloads: $0.09/GB (**R2 is FREE!**)

**R2 will save you hundreds of dollars as you scale!**

---

## ✅ Testing Checklist

### Local Testing (Without R2):
- [x] Upload a PDF → Saves to local disk
- [x] View document → Serves from local disk
- [x] Everything works as before

### Railway Testing (With R2):
1. Set R2 environment variables
2. Deploy to Railway
3. Upload a test PDF
4. Check Cloudflare R2 dashboard - file should appear!
5. Click "View" - file should load from R2
6. Delete document - file should be removed from R2

---

## 🆘 Troubleshooting

### "Module 'boto3' not found"
- Run: `pip install boto3`
- Or: `pip install -r requirements.txt`

### "R2 storage is not configured"
- Check environment variables are set
- Verify exact variable names (case-sensitive)
- Restart Flask after setting variables

### Files still saving locally on Railway
- Double-check Railway environment variables
- View logs: `railway logs`
- Look for R2 errors in output

### "Access Denied" error
- Verify R2 API token has Read & Write permissions
- Check bucket name matches exactly
- Confirm Account ID in endpoint URL is correct

---

## 🎯 Next Steps

You're all set! Here's what happens now:

1. **Local Development**: Files save to disk (easy testing)
2. **Railway Production**: Files go to R2 automatically
3. **Future Migrations**: Easy switch to Supabase (files stay in R2)
4. **Scaling**: Add more file types (images, videos) same way

Your platform now has **enterprise-grade file storage** for pennies! 🚀
