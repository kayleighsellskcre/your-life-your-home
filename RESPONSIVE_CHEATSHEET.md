# 📱 Responsive Design Cheat Sheet
## Quick Reference for Developers

---

## 🎯 The 5 Golden Rules

1. **Use Full-Width Buttons on Mobile** (`.btn` class auto-handles this)
2. **Min 52px Touch Targets** (All components follow this)
3. **16px Font for Form Inputs** (Prevents iOS zoom)
4. **Never Create Horizontal Scroll** (Use `.container` classes)
5. **Test Mobile First** (Design mobile, enhance desktop)

---

## 📐 Breakpoints (Quick Ref)

```
320px+    Extra small phones
480px+    Small phones
768px+    Tablets & up (mobile breakpoint)
900px+    Tablets landscape
1200px+   Desktop
1920px+   4K displays
```

**Mobile Portrait:** `@media (max-width: 768px)`
**Landscape:** `@media (max-height: 500px) and (orientation: landscape)`

---

## 🎨 Essential Classes

### Layout
```html
<div class="container">           <!-- Max-width container -->
<div class="dashboard-container"> <!-- Dashboard layout -->
<div class="section">             <!-- Vertical padding -->
```

### Buttons
```html
<button class="btn btn-primary">Primary</button>
<button class="btn btn-secondary">Secondary</button>
<button class="btn btn-outline">Outline</button>
<button class="btn btn-premium">Premium</button>
```

### Cards
```html
<div class="card">Card</div>
<div class="card-premium">Premium Card</div>
<div class="card-hero">Hero Card</div>
```

### Grids
```html
<div class="dashboard-grid">   <!-- Auto-responsive -->
<div class="stats-grid">       <!-- Stats layout -->
<div class="board-grid">       <!-- Board/gallery -->
```

### Forms
```html
<div class="form-group">
  <label class="form-label">Label</label>
  <input type="text" class="form-control">
</div>
```

### Alerts
```html
<div class="alert alert-success">Success!</div>
<div class="alert alert-error">Error!</div>
<div class="alert alert-info">Info</div>
```

### Mobile Components
```html
<div class="mobile-tabs">                <!-- Scrollable tabs -->
<div class="swipeable-container">        <!-- Swipe cards -->
<div class="bottom-nav">                 <!-- Bottom nav -->
<button class="fab">+</button>           <!-- Action button -->
```

---

## 🎭 Responsive Utilities

### Visibility
```css
.hide-mobile     /* Hide on mobile */
.show-mobile     /* Show only mobile */
.hide-desktop    /* Hide on desktop */
.show-desktop    /* Show only desktop */
.desktop-only    /* Desktop only */
.mobile-only     /* Mobile only */
```

### Spacing (Mobile)
```css
.p-mobile-0      /* padding: 0 */
.p-mobile-1      /* padding: 1rem */
.p-mobile-2      /* padding: 1.5rem */

.m-mobile-0      /* margin: 0 */
.m-mobile-1      /* margin: 1rem */
.mt-mobile-1     /* margin-top: 1rem */
.mb-mobile-1     /* margin-bottom: 1rem */
```

### Width
```css
.w-mobile-100    /* width: 100% */
.w-mobile-auto   /* width: auto */
```

### Text Align
```css
.text-center-mobile  /* Center on mobile */
.text-left-mobile    /* Left on mobile */
```

---

## 🎨 Colors (CSS Variables)

```css
var(--olive-green)      /* #6B6A45 Primary */
var(--taupe-beige)      /* #C8B497 Secondary */
var(--warm-cream)       /* #F6F2E8 Background */
var(--light-cream)      /* #EFE9DC Alt bg */
var(--charcoal-brown)   /* #3A352C Text */
var(--white)            /* #FFFFFF White */
```

---

## 📝 Typography Scale

### Mobile (max-width: 768px)
```
h1: 2rem (32px)
h2: 1.5rem (24px)
h3: 1.25rem (20px)
p:  1rem (16px)
```

### Desktop (769px+)
```
h1: 3.5rem (56px)
h2: 2.8rem (44.8px)
h3: 2rem (32px)
p:  1rem (16px)
```

### 4K (1920px+)
```
h1: 4rem (64px)
h2: 3.2rem (51.2px)
h3: 2.4rem (38.4px)
p:  1.125rem (18px)
```

---

## 📋 Common Patterns

### Full Page Layout
```html
<div class="dashboard-container">
  <h1>Page Title</h1>
  <div class="dashboard-grid">
    <div class="card">Card 1</div>
    <div class="card">Card 2</div>
  </div>
</div>
```

### Form
```html
<form>
  <div class="form-group">
    <label class="form-label">Name</label>
    <input type="text" class="form-control">
  </div>
  <button type="submit" class="btn btn-primary">Submit</button>
</form>
```

### Modal
```html
<div class="modal-overlay" id="modal" style="display:none;">
  <div class="modal">
    <div class="modal-header">
      <h2 class="modal-title">Title</h2>
    </div>
    <div class="modal-body">Content</div>
    <div class="modal-footer">
      <button class="btn btn-primary">OK</button>
    </div>
  </div>
</div>
```

### Stats Display
```html
<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-label">Label</div>
    <div class="stat-value">$485K</div>
    <div class="stat-change">+5.2%</div>
  </div>
</div>
```

### Alert
```html
<div class="alert alert-success">
  ✓ Success message
</div>
```

---

## ✅ Mobile Testing Checklist

Quick checks before deploying:

- [ ] **No horizontal scroll** (resize browser to 375px)
- [ ] **Buttons are tappable** (52px+ height)
- [ ] **Forms don't zoom** (16px font on inputs)
- [ ] **Cards stack** (single column on mobile)
- [ ] **Nav works** (mobile navigation accessible)
- [ ] **Images fit** (no overflow)
- [ ] **Text readable** (not too small)
- [ ] **Landscape works** (test sideways)

---

## 🚫 Common Mistakes

### ❌ DON'T DO THIS:
```html
<!-- Fixed widths -->
<div style="width: 800px;">

<!-- Tiny buttons -->
<button style="padding: 5px;">

<!-- Small fonts on inputs -->
<input style="font-size: 14px;">

<!-- Inline layout styles -->
<div style="display: flex; width: 1000px;">
```

### ✅ DO THIS INSTEAD:
```html
<!-- Responsive container -->
<div class="container">

<!-- Proper button -->
<button class="btn btn-primary">

<!-- Proper input -->
<input type="text" class="form-control">

<!-- Responsive grid -->
<div class="dashboard-grid">
```

---

## 🔧 Quick Fixes

### Horizontal scroll?
```css
overflow-x: hidden;
max-width: 100%;
```

### Text too small?
```css
@media (max-width: 768px) {
  font-size: 1rem;
}
```

### Button too small?
```html
<button class="btn btn-primary">
<!-- Auto 52px height -->
```

### Layout breaks?
```html
<div class="dashboard-grid">
<!-- Auto-stacks on mobile -->
```

---

## 🎓 Resources

- **Full Guide:** `RESPONSIVE_DESIGN_GUIDE.md`
- **Quick Start:** `MOBILE_QUICKSTART.md`
- **Live Demo:** `responsive_showcase.html`
- **This Cheat Sheet:** `RESPONSIVE_CHEATSHEET.md`

---

## 📱 Device Sizes to Test

```
iPhone SE:       375 x 667
iPhone 13:       390 x 844
iPhone Pro Max:  428 x 926
iPad:            768 x 1024
iPad Pro:       1024 x 1366
Laptop:         1280 x 720
Desktop:        1920 x 1080
4K:             3840 x 2160
```

---

## 💡 Pro Tips

1. **Start Mobile:** Design for 375px first
2. **Use DevTools:** F12 → Device Toolbar (Ctrl+Shift+M)
3. **Test Real Devices:** Emulator ≠ real device
4. **Use Classes:** Don't write custom CSS
5. **Check Hover:** Mobile has no hover
6. **Keyboard Nav:** Tab through everything
7. **Print Test:** Try printing pages

---

## 📏 Spacing Scale

```
--spacing-xs: 0.5rem    (8px)
--spacing-sm: 1rem      (16px)
--spacing-md: 2rem      (32px)
--spacing-lg: 4rem      (64px)
--spacing-xl: 6rem      (96px)
```

---

## 🎯 Touch Target Sizes

```
Minimum (WCAG AA):  48px x 48px
Recommended (AAA):  52px x 52px
Our Standard:       52px+ height
```

All `.btn` buttons automatically meet this standard.

---

## 📞 Quick Debug

### Chrome DevTools
```
1. Press F12
2. Click "Toggle Device Toolbar"
3. Select device or enter custom size
4. Test!
```

### Screen Size Detection (JS)
```javascript
console.log(window.innerWidth);
// 375 = iPhone SE
// 768 = iPad
// 1920 = Desktop
```

---

## 🎨 Style Override (If Needed)

```css
/* Mobile specific */
@media (max-width: 768px) {
  .my-element {
    font-size: 1rem;
    padding: 1rem;
  }
}

/* Desktop specific */
@media (min-width: 769px) {
  .my-element {
    font-size: 1.5rem;
    padding: 2rem;
  }
}
```

---

## ✨ Final Reminders

1. **Mobile-First** - Always
2. **Use Classes** - Don't reinvent
3. **Test Early** - Catch issues fast
4. **Real Devices** - Test on actual phones
5. **Accessibility** - Keyboard & screen readers
6. **Performance** - Keep it fast
7. **Consistency** - Use design system

---

**🎨 Your Life • Your Home** - Beautiful on every screen!

---

## 🖨️ Print This!

This cheat sheet is designed to be printed and kept at your desk for quick reference while developing.

**Print Settings:**
- Paper: Letter/A4
- Orientation: Portrait
- Color: Optional (works in B&W)
- Margins: Normal

---

*Last Updated: December 2024*
*Version: 2.0*

