# Quick OpenAI API Key Setup

## 🚀 Fast Setup (3 Steps)

### Step 1: Get Your API Key
1. Go to: https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy the key (starts with `sk-`)

### Step 2: Add to .env File
1. In your project folder, create/edit `.env` file
2. Add this line:
   ```
   OPENAI_API_KEY=sk-your-actual-key-here
   ```
3. Save the file

### Step 3: Install Libraries
Run in PowerShell:
```powershell
pip install openai python-dotenv
```

**Done!** Restart your Flask app and the AI refinement will work.

---

## 🎯 Or Use the Setup Script

Run this in PowerShell:
```powershell
.\setup_openai.ps1
```

It will guide you through entering your key securely.

---

## ✅ Test It

1. Go to a transaction → "Feature Spotlight Cards"
2. Add a feature with rough text
3. Click "✨ Refine" button
4. Watch it transform into elegant, professional text!

---

## 📋 For Railway (Production)

1. Go to Railway dashboard → Your project → Variables
2. Add: `OPENAI_API_KEY` = `sk-your-key-here`
3. Redeploy

---

## 💰 Cost

- Very affordable: ~$0.0015 per refinement
- 100 refinements = less than 2 cents!

---

## ❓ Troubleshooting

**Not working?**
- Check `.env` file exists and has the key
- Restart Flask app after adding key
- Check console for error messages
- Verify key starts with `sk-`

**Still using simple refinement?**
- That's okay! It still works, just without AI
- Check that `openai` library is installed: `pip install openai`

