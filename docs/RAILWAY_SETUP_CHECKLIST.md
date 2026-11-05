# 🚀 Quick Setup: Add These to Railway NOW

## Your R2 Public URL:
```
https://pub-544fd02b06a54002a87f3e0fad80a4d6.r2.dev
```

---

## ✅ Add These 5 Variables to Railway

Go to: **Railway Dashboard → Your Project → Variables**

Click **"+ New Variable"** and add each one:

### 1. R2_ENDPOINT
```
https://<your-account-id>.r2.cloudflarestorage.com
```
👆 Replace `<your-account-id>` with your actual Cloudflare account ID  
(Found in R2 dashboard URL or bucket settings)

---

### 2. R2_ACCESS_KEY_ID
```
<paste-your-access-key-here>
```
👆 From Cloudflare R2 → API Tokens

---

### 3. R2_SECRET_ACCESS_KEY
```
<paste-your-secret-key-here>
```
👆 From Cloudflare R2 → API Tokens

---

### 4. R2_BUCKET
```
ylh-documents
```
👆 Or whatever you named your bucket

---

### 5. R2_PUBLIC_URL (Optional but Recommended)
```
https://pub-544fd02b06a54002a87f3e0fad80a4d6.r2.dev
```
✅ **This is YOUR URL - already configured!**

---

## 🎯 After Adding Variables:

1. **Railway auto-redeploys** (watch the logs)
2. **Upload a test document** on your site
3. **Check R2 dashboard** - file should appear!
4. **View the document** - it loads from R2!

---

## 🧪 Test Locally (Optional)

Want to test R2 before deploying? Set these in PowerShell:

```powershell
$env:R2_ENDPOINT="https://<your-account-id>.r2.cloudflarestorage.com"
$env:R2_ACCESS_KEY_ID="<your-access-key>"
$env:R2_SECRET_ACCESS_KEY="<your-secret-key>"
$env:R2_BUCKET="ylh-documents"
$env:R2_PUBLIC_URL="https://pub-544fd02b06a54002a87f3e0fad80a4d6.r2.dev"

flask run
```

Then upload a file - it'll go straight to R2!

---

## 🆘 Need Your Account ID?

### Method 1: Check R2 Dashboard URL
```
https://dash.cloudflare.com/<ACCOUNT-ID>/r2/overview
                              ^^^^^^^^^^
                              This is it!
```

### Method 2: Check Bucket Settings
1. Go to R2 Dashboard
2. Click your bucket
3. Look for "S3 API" section
4. Endpoint shows: `https://<ACCOUNT-ID>.r2.cloudflarestorage.com`

---

## ✅ Checklist

- [ ] Found R2_ENDPOINT (with account ID)
- [ ] Got R2_ACCESS_KEY_ID from API tokens
- [ ] Got R2_SECRET_ACCESS_KEY from API tokens
- [ ] Know bucket name (R2_BUCKET)
- [ ] Have public URL: `https://pub-544fd02b06a54002a87f3e0fad80a4d6.r2.dev`
- [ ] Added all 5 variables to Railway
- [ ] Railway redeployed
- [ ] Tested uploading a document
- [ ] Verified file appears in R2 dashboard

---

## 🎉 Once Complete:

Your platform will:
✅ Upload all documents to Cloudflare R2  
✅ Serve files from R2 CDN (faster!)  
✅ Save Railway disk space  
✅ Cost ~$0.50/month for 100GB  
✅ Scale to thousands of users  

You're minutes away from production-ready cloud storage! 🚀
