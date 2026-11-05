# Railway Database Persistence Setup Guide

## 🚨 CRITICAL: Your Database is Being Wiped on Every Deploy!

Railway's filesystem is **ephemeral** - any files written to disk are **lost on every redeploy**. This is why your database and settings keep disappearing.

## ✅ Solution: Set Up a Persistent Volume

### Step 1: Create a Persistent Volume in Railway

1. Go to your Railway project dashboard
2. Click on your service
3. Go to the **"Volumes"** tab
4. Click **"New Volume"**
5. Name it: `database-storage`
6. Set mount path: `/data` (or any path you prefer)
7. Click **"Add Volume"**

### Step 2: Set Environment Variable

In Railway → Your Service → Variables, add:

```
RAILWAY_VOLUME_MOUNT_PATH=/data
```

### Step 3: Redeploy

After adding the volume and environment variable, Railway will automatically redeploy. Your database will now persist in the `/data` directory.

## 📁 File Uploads (Photos/Logos)

Your photos and logos are already being saved to **Cloudflare R2** (cloud storage), which persists across deploys. The database just stores the URLs to these files.

**Make sure R2 is configured:**
- Set these environment variables in Railway:
  - `R2_ENDPOINT`
  - `R2_ACCESS_KEY_ID`
  - `R2_SECRET_ACCESS_KEY`
  - `R2_BUCKET`
  - `R2_PUBLIC_URL` (optional)

## 🔍 Verify It's Working

After setup, check Railway logs for:
```
[DATABASE] Using Railway persistent volume: /data/ylh.db
```

If you see:
```
[DATABASE] WARNING: Railway detected but no persistent volume configured!
```
Then the volume isn't set up correctly.

## 🆘 Alternative: Use Railway PostgreSQL

If persistent volumes don't work, consider migrating to Railway's PostgreSQL service (free tier available). This would require code changes but provides better persistence guarantees.

