# 🚀 Quick Start: 3D Property Tours

## Get Started in 3 Minutes!

### **Step 1: Upgrade Your Account to Premium** (30 seconds)

Run this command:
```bash
python scripts/upgrade_to_premium.py
```

Or manually in your database:
```sql
UPDATE users SET subscription_tier = 'premium' WHERE email = 'your-email@example.com';
```

---

### **Step 2: Visit Video Studio** (10 seconds)

Navigate to:
```
http://localhost:5000/agent/video-studio
```

Or on production:
```
https://itsyourlifeyourhome.com/agent/video-studio
```

---

### **Step 3: Create Your First 3D Tour** (2 minutes)

#### **Step 3.1: Select 3D Property Tour**
- Click on the **"3D Property Tour"** card (purple with ✨ PREMIUM badge)
- Click **"Next"**

#### **Step 3.2: Choose Format**
- **Aspect Ratio:** Select "9:16" for Instagram Reels/TikTok
- **Duration:** Select "30 sec"
- Click **"Next"**

#### **Step 3.3: Upload Photos**
- Drag & drop 3-5 property photos
- Or click to browse
- Wait for uploads to complete
- Click **"Next"**

#### **Step 3.4: Select Style**
- Choose one of the 3D styles:
  - **Architectural 3D** (recommended for first try)
  - Modern 3D
  - Luxury 3D
- Click **"Next"**

#### **Step 3.5: Add Details & Room Labels**
- **Headline:** "Virtual Property Tour"
- **Address:** "123 Main Street"
- **Room Labels:** Add one per line:
  ```
  Living Room
  Gourmet Kitchen
  Master Bedroom
  Luxury Bathroom
  Outdoor Space
  ```
- Click **"Create Video"**

---

### **Step 4: Wait for Rendering** (1-2 minutes)

The system will:
1. Create intro card with 3D background
2. Apply 3D camera movements to each photo
3. Add room labels with fade-in animations
4. Apply professional color grading
5. Add outro card with your contact info
6. Combine everything into one seamless video

---

### **Step 5: Download & Share!** (30 seconds)

- Video will open automatically when complete
- Click **"📥 Download Video"**
- Share on Instagram Reels, TikTok, or YouTube!

---

## 🎥 **Example Result:**

Your video will have:
- ✅ Smooth 3D camera movements (dolly, crane, orbit)
- ✅ Professional room labels fading in
- ✅ Crisp architectural color grading
- ✅ Elegant transitions between rooms
- ✅ Branded intro & outro cards

---

## 💡 **Pro Tips:**

### **Best Photos to Use:**
1. **Front Exterior** - Wide angle, good lighting
2. **Living Room** - Show the space, not too cluttered
3. **Kitchen** - Clean counters, good angle
4. **Master Bedroom** - Made bed, natural light
5. **Bathroom** - Clean, bright, show features
6. **Outdoor Space** - Patio, yard, or view

### **Room Label Tips:**
- Keep labels short (1-3 words)
- Use descriptive adjectives: "Gourmet Kitchen", "Spa Bathroom"
- Match label order to photo order
- Capitalize first letters: "Master Suite", not "master suite"

### **Style Selection:**
- **Architectural 3D:** Best for modern homes, clean lines
- **Modern 3D:** Best for contemporary spaces, minimalist
- **Luxury 3D:** Best for high-end properties, dramatic

---

## 🐛 **Troubleshooting:**

### **"Video Studio is temporarily unavailable"**
- **Cause:** FFmpeg not installed yet
- **Fix:** Wait 5-10 minutes for Railway deployment to complete
- **Check:** Visit `/health/ffmpeg` to see status

### **"3D Property Tours are a Premium feature"**
- **Cause:** Your account is not upgraded
- **Fix:** Run `python scripts/upgrade_to_premium.py`
- **Or:** Manually update database (see Step 1)

### **"Please upload at least one photo"**
- **Cause:** No photos selected
- **Fix:** Make sure files are uploaded before clicking Next
- **Tip:** Wait for upload progress bars to complete

### **Video rendering failed**
- **Cause:** Various (file format, size, FFmpeg error)
- **Fix:** Try different photos (JPG format recommended)
- **Fix:** Reduce number of photos (3-5 is optimal)
- **Check:** Railway logs for specific error

### **Room labels don't match photos**
- **Cause:** Label order doesn't match photo order
- **Fix:** Rearrange labels or re-upload photos in correct order
- **Tip:** First label = first photo, second label = second photo, etc.

---

## 📱 **Sharing Your Video:**

### **Instagram Reels:**
1. Use 9:16 format
2. Download video
3. Open Instagram → Create Reel
4. Upload video
5. Add caption with property details
6. Post!

### **TikTok:**
1. Use 9:16 format
2. Download video
3. Open TikTok → Create
4. Upload video
5. Add hashtags: #realestate #propertytour #luxuryhomes
6. Post!

### **YouTube:**
1. Use 16:9 format
2. Download video
3. Open YouTube Studio
4. Create → Upload video
5. Add title, description, tags
6. Publish!

### **Facebook:**
1. Any format works (16:9 recommended)
2. Download video
3. Create post
4. Upload video
5. Add property details in caption
6. Post!

---

## 🎯 **Next Steps:**

1. ✅ Create your first 3D tour video
2. ✅ Share on social media
3. ✅ Monitor engagement (likes, views, shares)
4. ✅ Create more videos for other properties
5. ✅ Start offering to agents/lenders as premium feature
6. ✅ Set up subscription pricing ($29/month recommended)
7. ✅ Market the feature to your users!

---

## 💰 **Monetization:**

### **For Your Business:**
- Offer Premium subscriptions: $29-49/month
- Include unlimited 3D tours
- Agents will pay for this (saves them $200-500 per video)
- Average agent creates 2-5 videos per month
- 10 premium users = $290-490/month recurring revenue

### **Marketing Message:**
```
"Create professional 3D property tours in minutes.

What normally costs $200-500 per video from a 3D artist...
Now unlimited for just $29/month.

✨ Immersive camera movements
✨ Professional room labels
✨ Ready for Reels, TikTok, YouTube

Upgrade to Premium Today →"
```

---

## 📞 **Need Help?**

Read the full documentation: `3D_PROPERTY_TOUR_FEATURE.md`

---

**You're all set! Go create something amazing! 🎬✨**
