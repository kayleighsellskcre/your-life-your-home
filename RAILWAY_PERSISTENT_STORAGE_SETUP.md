# 🚨 CRITICAL: Railway Persistent Storage Setup

## THE PROBLEM
Your photos/logos are being deleted on every redeploy because Railway's filesystem is **EPHEMERAL** (temporary). Every time Railway redeploys your app, it creates a BRAND NEW container with a FRESH filesystem - your database file (`ylh.db`) is **DELETED**!

## THE SOLUTION
Add a **Persistent Volume** to Railway so your database survives redeploys.

---

## STEP-BY-STEP FIX (5 minutes):

### 1. Go to Your Railway Project Dashboard
   - https://railway.app/
   - Click on your "Your Life Your Home" project

### 2. Add a Volume
   - Click on your service/app
   - Go to the **"Settings"** tab
   - Scroll down to **"Volumes"**
   - Click **"+ Add Volume"**

### 3. Configure the Volume
   - **Name:** `ylh-data`
   - **Mount Path:** `/app/data`
   - Click **"Add"**

### 4. Add Environment Variable
   - Still in **"Settings"** tab
   - Scroll to **"Variables"** section
   - Click **"+ New Variable"**
   - **Name:** `RAILWAY_VOLUME_MOUNT_PATH`
   - **Value:** `/app/data`
   - Click **"Add"**

### 5. Redeploy
   - Railway will automatically redeploy
   - Your database will now be saved in `/app/data/ylh.db`
   - **This location persists across redeploys!** ✅

---

## VERIFY IT'S WORKING

After the redeploy, check your Railway logs. You should see:

```
[DATABASE] Using Railway persistent volume: /app/data/ylh.db
```

Instead of:

```
[DATABASE] WARNING: Railway detected but no persistent volume configured!
[DATABASE] Database will be wiped on redeploy.
```

---

## AFTER SETUP

1. **Upload your photo and logo again** (one last time!)
2. **They will now persist forever** - even through redeploys! 🎉

---

## ALTERNATIVE: Upgrade to PostgreSQL (Recommended for Production)

For even better performance and scalability, you should eventually migrate to PostgreSQL:

1. Add PostgreSQL database in Railway
2. Railway will provide a `DATABASE_URL` variable
3. I can update the code to use Postgres instead of SQLite

This is the industry standard for production web apps, but the volume solution above will work perfectly for now!

---

**Do this NOW and your photos/logos will NEVER disappear again!** 🔒

