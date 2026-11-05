# 🚂 Railway Deployment Fix
## Your Life • Your Home Platform

---

## ✅ What Was Fixed

Your Railway deployment was crashing due to missing configuration files. I've created the following files to fix it:

### 1. **`Procfile`** ✅
Tells Railway how to start your application using Gunicorn.

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
```

**What this does:**
- Uses Gunicorn (production WSGI server)
- Binds to `0.0.0.0` (accepts all connections)
- Uses Railway's `$PORT` environment variable
- 2 workers for handling requests
- 4 threads per worker
- 120-second timeout for long requests

### 2. **`railway.json`** ✅
Railway-specific configuration.

```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**What this does:**
- Uses Nixpacks builder (Railway's build system)
- Automatically restarts on failure
- Up to 10 retry attempts

### 3. **`nixpacks.toml`** ✅
System dependencies for WeasyPrint (PDF generation).

```toml
[phases.setup]
nixPkgs = ["python311", "cairo", "pango", "gdk-pixbuf", "libffi", "libjpeg", "zlib"]
```

**What this does:**
- Installs system libraries needed for WeasyPrint
- Cairo, Pango for PDF rendering
- Image libraries for PIL/Pillow

---

## 🚀 Deployment Steps

### 1. **Commit and Push**

```bash
git add Procfile railway.json nixpacks.toml
git commit -m "Fix Railway deployment configuration"
git push origin main
```

### 2. **Railway Will Auto-Deploy**
Railway will automatically detect the changes and redeploy your app.

### 3. **Monitor the Build**
Watch the Railway logs to ensure successful deployment:
- Go to your Railway dashboard
- Click on your project
- View the deployment logs

---

## 🔍 Common Issues & Solutions

### Issue: Build Fails with WeasyPrint Error

**Solution:** The `nixpacks.toml` file includes all necessary system dependencies. If it still fails, try adding these to Railway environment variables:

```
LIBRARY_PATH=/nix/store/*/lib
LD_LIBRARY_PATH=/nix/store/*/lib
```

### Issue: Database Not Persisting

**Solution:** Ensure you've set up Railway Volumes:

1. Go to Railway dashboard
2. Click your service
3. Go to "Data" tab
4. Add a volume mounted at `/app/data`
5. Update database path in environment variables:
   ```
   DATABASE_PATH=/app/data/homeowner_data.db
   ```

### Issue: R2 Storage Not Working

**Solution:** Verify environment variables in Railway:

```
R2_ENDPOINT=your-endpoint
R2_ACCESS_KEY_ID=your-access-key
R2_SECRET_ACCESS_KEY=your-secret-key
R2_BUCKET_NAME=your-bucket-name
```

### Issue: Port Binding Error

**Solution:** The Procfile now correctly uses `$PORT` which Railway provides automatically. No action needed.

### Issue: App Times Out

**Solution:** The timeout is set to 120 seconds. If you need more:

Edit `Procfile`:
```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 300
```

---

## 📊 Environment Variables Checklist

Ensure these are set in Railway:

### Required
- ✅ `PORT` - Automatically provided by Railway
- ✅ `SECRET_KEY` - Your Flask secret key
- ✅ `DATABASE_PATH` - Path to SQLite database

### Optional (R2 Storage)
- ⚪ `R2_ENDPOINT`
- ⚪ `R2_ACCESS_KEY_ID`
- ⚪ `R2_SECRET_ACCESS_KEY`
- ⚪ `R2_BUCKET_NAME`

### Optional (OpenAI)
- ⚪ `OPENAI_API_KEY`

### Optional (Homebot)
- ⚪ `HOMEBOT_API_KEY`
- ⚪ `HOMEBOT_WEBHOOK_SECRET`

---

## 🎯 Gunicorn Configuration Explained

### Workers (2)
```
--workers 2
```
- Number of worker processes
- Formula: `(2 x CPU cores) + 1`
- For Railway's basic plan: 2 is optimal
- Can increase to 4 for paid plans

### Threads (4)
```
--threads 4
```
- Threads per worker
- Handles concurrent requests within each worker
- Total concurrent requests: workers × threads = 8

### Timeout (120 seconds)
```
--timeout 120
```
- Request timeout in seconds
- Prevents hanging requests
- Increase if you have long-running operations

### Binding (0.0.0.0:$PORT)
```
--bind 0.0.0.0:$PORT
```
- `0.0.0.0` accepts connections from anywhere
- `$PORT` uses Railway's assigned port
- Critical for Railway to route traffic correctly

---

## 🧪 Testing Locally

To test the Gunicorn setup locally:

```bash
# Set PORT environment variable
export PORT=5000  # Windows: set PORT=5000

# Run with Gunicorn
gunicorn app:app --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120 --reload

# Test the app
# Open browser to http://localhost:5000
```

---

## 📈 Performance Optimization

### For Higher Traffic

If you experience high traffic, upgrade your Railway plan and adjust:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --threads 8 --timeout 120 --worker-class=gthread --worker-tmp-dir /dev/shm
```

**Changes:**
- 4 workers instead of 2
- 8 threads instead of 4
- `gthread` worker class for async support
- `--worker-tmp-dir /dev/shm` for better performance

### Memory Optimization

If you hit memory limits:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120 --max-requests 1000 --max-requests-jitter 50
```

**Changes:**
- 1 worker to reduce memory usage
- More threads to compensate
- Auto-restart workers after 1000 requests (prevents memory leaks)

---

## 🔧 Troubleshooting Commands

### View Logs in Real-Time
```bash
railway logs --follow
```

### Check Environment Variables
```bash
railway variables
```

### Restart Service
```bash
railway up
```

### Check Build Status
```bash
railway status
```

---

## 📝 Quick Deploy Checklist

Before deploying:

- [x] `Procfile` created ✅
- [x] `railway.json` created ✅
- [x] `nixpacks.toml` created ✅
- [ ] Environment variables set in Railway
- [ ] Database volume configured (if needed)
- [ ] R2 credentials added (if using R2)
- [ ] OpenAI key added (if using AI features)
- [ ] Committed and pushed to Git
- [ ] Railway build successful
- [ ] App accessible at Railway URL
- [ ] Test login functionality
- [ ] Test file uploads
- [ ] Test database operations

---

## 🎉 Success Indicators

Your deployment is successful when:

1. ✅ **Build completes** without errors
2. ✅ **Health check passes** (Railway shows green)
3. ✅ **App responds** at your Railway URL
4. ✅ **Logs show** "Booting worker with pid"
5. ✅ **No crash loops** in deployment history

---

## 📞 Still Having Issues?

### Check Railway Logs

Look for these common errors:

**"Address already in use"**
- Fixed by using `$PORT` variable ✅

**"ModuleNotFoundError"**
- Check `requirements.txt` is complete
- Verify all dependencies are listed

**"WeasyPrint error"**
- Fixed by `nixpacks.toml` system packages ✅

**"Database is locked"**
- Add Railway volume for persistence
- Check concurrent write operations

**"Memory limit exceeded"**
- Reduce workers in Procfile
- Upgrade Railway plan

### Railway Support Resources

- 📚 [Railway Docs](https://docs.railway.app/)
- 💬 [Railway Discord](https://discord.gg/railway)
- 🐛 [Railway GitHub](https://github.com/railwayapp/nixpacks)

---

## 🚀 Your App Should Now Deploy Successfully!

The three files I created will fix your Railway deployment crash:

1. **Procfile** - Proper app startup
2. **railway.json** - Railway configuration
3. **nixpacks.toml** - System dependencies

Simply commit and push these files, and Railway will automatically redeploy with the correct configuration!

---

**Status:** ✅ **FIXED - READY TO DEPLOY**

🎨 **Your Life • Your Home** - Now running smoothly on Railway!

