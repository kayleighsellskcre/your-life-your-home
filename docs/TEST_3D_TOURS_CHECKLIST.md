# ✅ 3D Property Tours - Testing Checklist

## Before You Start
- [ ] Read `QUICK_START_3D_TOURS.md`
- [ ] Read `3D_TOURS_COMPLETE_SUMMARY.md`
- [ ] Have 3-5 test photos ready (property photos or any images)

---

## Setup & Configuration

### Database Setup
- [ ] Run `python scripts/upgrade_to_premium.py`
- [ ] Verify your subscription tier is 'premium' or 'pro'
- [ ] Confirm user record updated successfully

### Server Status
- [ ] Start the Flask app: `python app.py`
- [ ] Server running on http://localhost:5000
- [ ] No errors in console
- [ ] FFmpeg is installed (check `/health/ffmpeg`)

---

## UI Testing - Video Studio Page

### Access
- [ ] Navigate to `/agent/video-studio`
- [ ] Page loads without errors
- [ ] Video Studio interface displays
- [ ] Can see existing video types

### 3D Property Tour Card
- [ ] See "3D Property Tour" card
- [ ] See "✨ PREMIUM" badge on card
- [ ] Card has purple gradient styling
- [ ] Card description: "Immersive walkthrough experience"

### Premium Access (With Premium Tier)
- [ ] Click on "3D Property Tour" card
- [ ] No upgrade prompt appears
- [ ] Card becomes selected (highlighted)
- [ ] Next button text updates
- [ ] Can proceed to next step

### Free User Test (Optional)
- [ ] Set subscription_tier to 'free' in database
- [ ] Refresh page
- [ ] Click on "3D Property Tour" card
- [ ] Upgrade prompt appears
- [ ] Prompt explains premium features
- [ ] Cannot proceed without premium

---

## Create 3D Tour - Full Workflow

### Step 1: Video Type
- [ ] "3D Property Tour" card is selected
- [ ] Card shows purple highlight
- [ ] Other cards are not selected
- [ ] Next button is enabled
- [ ] Click "Next"

### Step 2: Format & Duration
- [ ] See 3 aspect ratio options (9:16, 16:9, 1:1)
- [ ] Select "9:16" (Reels/TikTok)
- [ ] Card highlights when selected
- [ ] See 3 duration options (15s, 30s, 60s)
- [ ] Select "30 sec"
- [ ] Duration highlights when selected
- [ ] Next button is enabled
- [ ] Click "Next"

### Step 3: Upload Media
- [ ] See upload zone with drag & drop area
- [ ] Click upload zone
- [ ] File picker opens
- [ ] Select 3-5 test photos
- [ ] Photos upload successfully
- [ ] See preview thumbnails in grid
- [ ] Thumbnails show uploaded images
- [ ] Can remove photos (X button)
- [ ] Next button is enabled
- [ ] Click "Next"

### Step 4: Choose Style
- [ ] See "3D Styles" section (not regular styles)
- [ ] Regular styles are hidden
- [ ] See 3 3D style options:
  - [ ] Architectural 3D (purple icon)
  - [ ] Modern 3D (blue icon)
  - [ ] Luxury 3D (pink icon)
- [ ] Click "Architectural 3D"
- [ ] Card highlights when selected
- [ ] Style description is visible
- [ ] Next button is enabled
- [ ] Click "Next"

### Step 5: Video Details
- [ ] See "Headline" input field
- [ ] Enter: "Virtual Property Tour"
- [ ] See "Property Address" input field
- [ ] Enter: "123 Main Street"
- [ ] See "Key Highlights" textarea
- [ ] Enter highlights (optional)
- [ ] See "Room Labels" section (NEW!)
- [ ] Room Labels field is visible
- [ ] See helpful tip about labels
- [ ] Enter room labels (one per line):
  ```
  Living Room
  Gourmet Kitchen
  Master Bedroom
  Spa Bathroom
  Outdoor Space
  ```
- [ ] Labels match number of photos uploaded
- [ ] See "Include Auto Captions" checkbox
- [ ] Checkbox is checked by default
- [ ] "Create Video" button is visible
- [ ] Click "Create Video"

### Video Rendering
- [ ] Form submits successfully
- [ ] Redirects to video view page
- [ ] See "Rendering..." status badge
- [ ] See project details displayed
- [ ] See "Refresh" instruction
- [ ] Wait 1-2 minutes
- [ ] Refresh page
- [ ] Status changes to "Complete"
- [ ] Video player appears
- [ ] Video file path is shown

### Video Playback
- [ ] Video player loads
- [ ] Click play button
- [ ] Video plays smoothly
- [ ] See intro card (0-3 seconds)
  - [ ] Dark blue background
  - [ ] "Virtual Property Tour" text
  - [ ] "123 Main Street" text
- [ ] See first photo with 3D movement
  - [ ] "Living Room" label visible
  - [ ] Label has golden underline
  - [ ] Camera movement is smooth
  - [ ] Label fades in after 0.3s
- [ ] See second photo with different movement
  - [ ] "Gourmet Kitchen" label visible
  - [ ] Different camera movement than first
- [ ] See third photo
  - [ ] "Master Bedroom" label visible
- [ ] See fourth photo
  - [ ] "Spa Bathroom" label visible
- [ ] See fifth photo (if uploaded)
  - [ ] "Outdoor Space" label visible
- [ ] See outro card (last 3 seconds)
  - [ ] Your name displayed
  - [ ] Your contact info displayed
  - [ ] "CONTACT ME TODAY" text
- [ ] Transitions between clips are smooth
- [ ] No black frames or glitches
- [ ] Video ends properly

### Download & Share
- [ ] See "Download Video" button
- [ ] Click download button
- [ ] Video file downloads (.mp4)
- [ ] File size is reasonable (5-20 MB)
- [ ] Open downloaded video
- [ ] Video plays in local player
- [ ] Quality is good (clear, not pixelated)
- [ ] Share link is visible (optional test)

---

## Visual Quality Checks

### Camera Movements
- [ ] Movements are smooth (not jerky)
- [ ] Different movements on different photos
- [ ] Movements add professional feel
- [ ] No distortion or warping

### Room Labels
- [ ] Labels are readable
- [ ] Font size is appropriate
- [ ] White text with shadow
- [ ] Golden underline is visible
- [ ] Labels don't cover important parts of image
- [ ] Fade-in animation is smooth
- [ ] Labels stay visible throughout clip

### Color Grading
- [ ] Colors are crisp and clear
- [ ] Not too dark or too bright
- [ ] Architectural feel (clean, modern)
- [ ] Consistent across all clips

### Overall Quality
- [ ] Video is sharp (not blurry)
- [ ] No compression artifacts
- [ ] Smooth 30fps playback
- [ ] Professional appearance

---

## Error Handling Tests

### Missing Information
- [ ] Try creating without selecting video type
  - [ ] Shows error message
- [ ] Try creating without format/duration
  - [ ] Shows error message
- [ ] Try creating without uploading photos
  - [ ] Shows error message
- [ ] Try creating without style selection
  - [ ] Shows error message

### Invalid Input
- [ ] Try uploading non-image files
  - [ ] Rejects or handles gracefully
- [ ] Try uploading very large files (>10MB)
  - [ ] Handles or shows warning
- [ ] Try creating with 1 photo only
  - [ ] Works or shows minimum requirement

### Room Labels Mismatch
- [ ] Upload 5 photos, add 3 labels
  - [ ] First 3 photos have labels
  - [ ] Last 2 photos have no labels (works fine)
- [ ] Upload 3 photos, add 5 labels
  - [ ] First 3 labels used
  - [ ] Extra 2 labels ignored

---

## Different Configurations Testing

### Test with Different Aspect Ratios
- [ ] Create video with 9:16 (vertical)
  - [ ] Video is vertical format
  - [ ] Plays correctly on phone
- [ ] Create video with 16:9 (horizontal)
  - [ ] Video is horizontal format
  - [ ] Good for YouTube
- [ ] Create video with 1:1 (square)
  - [ ] Video is square format
  - [ ] Good for Instagram feed

### Test with Different Durations
- [ ] Create 15-second video
  - [ ] Video is ~18 seconds (with intro/outro)
  - [ ] Clips are shorter
- [ ] Create 30-second video
  - [ ] Video is ~36 seconds
  - [ ] Good clip length
- [ ] Create 60-second video
  - [ ] Video is ~66 seconds
  - [ ] Longer, more detailed

### Test with Different 3D Styles
- [ ] Create with "Architectural 3D"
  - [ ] Deep blue intro card
  - [ ] Professional feel
- [ ] Create with "Modern 3D"
  - [ ] Different color treatment
- [ ] Create with "Luxury 3D"
  - [ ] Premium aesthetic

### Test with Different Number of Photos
- [ ] Create with 3 photos
  - [ ] Works correctly
  - [ ] Longer clips per photo
- [ ] Create with 5 photos
  - [ ] Works correctly
  - [ ] Balanced timing
- [ ] Create with 7 photos
  - [ ] Works correctly
  - [ ] Shorter clips per photo
- [ ] Create with 10 photos
  - [ ] Works correctly
  - [ ] Quick transitions

---

## Subscription Testing

### As Premium User
- [ ] Can see 3D Property Tour option
- [ ] Can click without restrictions
- [ ] Can create unlimited 3D tours
- [ ] No upgrade prompts

### As Free User
- [ ] Can see 3D Property Tour card
- [ ] See "PREMIUM" badge
- [ ] Click shows upgrade prompt
- [ ] Cannot create 3D tours
- [ ] Regular videos still work

### Upgrade Flow
- [ ] Free user clicks 3D card
- [ ] Sees clear upgrade message
- [ ] Message explains benefits
- [ ] Message says how to upgrade
- [ ] After upgrading, can use feature

---

## Browser Compatibility

### Desktop Browsers
- [ ] Chrome (latest)
  - [ ] UI displays correctly
  - [ ] Video creation works
  - [ ] Video plays correctly
- [ ] Firefox (latest)
  - [ ] UI displays correctly
  - [ ] Video creation works
  - [ ] Video plays correctly
- [ ] Safari (latest)
  - [ ] UI displays correctly
  - [ ] Video creation works
  - [ ] Video plays correctly
- [ ] Edge (latest)
  - [ ] UI displays correctly
  - [ ] Video creation works
  - [ ] Video plays correctly

### Mobile Browsers
- [ ] Mobile Chrome
  - [ ] Touch controls work
  - [ ] Video plays
- [ ] Mobile Safari
  - [ ] Touch controls work
  - [ ] Video plays
- [ ] Responsive design works
  - [ ] Cards stack properly
  - [ ] Buttons are tappable
  - [ ] No horizontal scrolling

---

## Performance Testing

### Rendering Speed
- [ ] 3 photos, 30 seconds: ~60-90 seconds
- [ ] 5 photos, 30 seconds: ~90-120 seconds
- [ ] 7 photos, 30 seconds: ~120-150 seconds
- [ ] Times are acceptable

### File Sizes
- [ ] 30-second video: 5-15 MB
- [ ] 60-second video: 10-25 MB
- [ ] Sizes are reasonable for sharing

### Server Resources
- [ ] CPU usage is acceptable during render
- [ ] Memory usage is stable
- [ ] No server crashes
- [ ] Multiple users can render simultaneously

---

## Edge Cases

### Special Characters in Labels
- [ ] Room labels with apostrophes: "Master's Suite"
- [ ] Room labels with colons: "Living Room: Main"
- [ ] Room labels with quotes: "The "Great" Room"
- [ ] All handle gracefully

### Long Room Labels
- [ ] Very long label: "The Absolutely Stunning Master Bedroom Suite"
  - [ ] Truncates or wraps appropriately
  - [ ] Doesn't break layout

### No Room Labels
- [ ] Create 3D tour without any room labels
  - [ ] Works correctly
  - [ ] Videos have movement but no labels

### Unusual Photos
- [ ] Portrait orientation photos
  - [ ] Handles correctly
- [ ] Very wide photos
  - [ ] Crops/scales appropriately
- [ ] Very tall photos
  - [ ] Crops/scales appropriately

---

## Documentation Review

### Files Created
- [ ] `3D_PROPERTY_TOUR_FEATURE.md` exists and is complete
- [ ] `QUICK_START_3D_TOURS.md` exists and is helpful
- [ ] `ROOM_LABELS_EXAMPLES.md` exists with examples
- [ ] `3D_TOURS_COMPLETE_SUMMARY.md` exists
- [ ] `3D_TOURS_UI_PREVIEW.md` exists
- [ ] `scripts/upgrade_to_premium.py` exists and works

### Documentation Quality
- [ ] Instructions are clear
- [ ] Examples are helpful
- [ ] Screenshots/diagrams are accurate
- [ ] Contact info is correct

---

## Final Checks

### User Experience
- [ ] Feature is easy to discover
- [ ] Wizard is intuitive
- [ ] Labels are self-explanatory
- [ ] Results are impressive
- [ ] Would users pay for this? YES!

### Business Value
- [ ] Clear premium/free distinction
- [ ] Upgrade prompts are effective
- [ ] Value proposition is clear
- [ ] Pricing strategy makes sense
- [ ] ROI is positive

### Production Ready
- [ ] No console errors
- [ ] No broken links
- [ ] No placeholder text
- [ ] No test data visible
- [ ] Error messages are helpful
- [ ] Success messages are clear

---

## 🎉 ALL TESTS PASSING?

### If YES:
✅ **Feature is ready to launch!**
- [ ] Deploy to production
- [ ] Announce to users
- [ ] Start accepting subscriptions
- [ ] Monitor usage and feedback
- [ ] Count your money! 💰

### If NO:
❌ **Fix issues found:**
1. Note which tests failed
2. Check error messages in logs
3. Review documentation for solutions
4. Fix issues one by one
5. Re-run failed tests
6. Repeat until all passing

---

## 📊 Success Metrics to Track

After launching, track:
- [ ] Number of 3D tours created
- [ ] Conversion rate (free → premium)
- [ ] User engagement with 3D videos
- [ ] Social media shares of 3D tours
- [ ] Monthly recurring revenue from feature
- [ ] User feedback and testimonials

---

## 🚀 Launch Checklist

Ready to launch?
- [ ] All tests passing
- [ ] Documentation complete
- [ ] Upgrade script tested
- [ ] Pricing decided
- [ ] Marketing materials ready
- [ ] Support plan in place
- [ ] Monitoring set up
- [ ] Backup plan ready

**GO TIME! 🎬✨**

---

## 📞 Need Help?

If something doesn't work:
1. Check the error message
2. Review the documentation
3. Check Railway logs
4. Verify FFmpeg is installed
5. Test with simpler inputs
6. Check database subscription tier

Most common issues:
- FFmpeg not installed → Wait for deployment
- Not premium → Run upgrade script
- Bad photo format → Use JPG files
- Too many photos → Start with 3-5

---

**Happy Testing! 🧪**

**Make it work. Make it beautiful. Make it profitable! 💰**
