# OpenAI API Key Setup Guide

## Step 1: Get Your OpenAI API Key

1. **Go to OpenAI's website**
   - Visit: https://platform.openai.com/
   - Sign up for an account or log in if you already have one

2. **Navigate to API Keys**
   - Click on your profile icon (top right)
   - Select "View API keys" or go directly to: https://platform.openai.com/api-keys

3. **Create a new API key**
   - Click "Create new secret key"
   - Give it a name (e.g., "Your Life Your Home - Feature Cards")
   - **IMPORTANT**: Copy the key immediately - you won't be able to see it again!
   - The key will look like: `sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

4. **Set up billing** (if needed)
   - Go to: https://platform.openai.com/account/billing
   - Add a payment method
   - Set up usage limits if desired
   - Note: GPT-3.5-turbo is very affordable (~$0.0015 per 1K tokens)

---

## Step 2: Set Up Locally (Development)

### Option A: Using PowerShell (Windows)

1. **Open PowerShell** in your project directory

2. **Set the environment variable** (temporary - for current session):
   ```powershell
   $env:OPENAI_API_KEY="sk-proj-your-actual-key-here"
   ```

3. **To make it permanent**, add it to your system:
   ```powershell
   [System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'sk-proj-your-actual-key-here', 'User')
   ```

4. **Restart your terminal** and verify:
   ```powershell
   echo $env:OPENAI_API_KEY
   ```

### Option B: Using .env file (Recommended)

1. **Create a `.env` file** in your project root (if it doesn't exist)

2. **Add your API key**:
   ```
   OPENAI_API_KEY=sk-proj-your-actual-key-here
   ```

3. **Make sure `.env` is in `.gitignore`** (it should already be there)

4. **Install python-dotenv** (if not already installed):
   ```powershell
   pip install python-dotenv
   ```

5. **Load it in your Flask app** - Add this near the top of `app.py`:
   ```python
   from dotenv import load_dotenv
   load_dotenv()  # This loads variables from .env file
   ```

---

## Step 3: Install OpenAI Library

```powershell
pip install openai
```

Or add to `requirements.txt`:
```
openai
```

---

## Step 4: Set Up on Railway (Production)

1. **Go to your Railway project**
   - Visit: https://railway.app/
   - Select your project

2. **Add Environment Variable**
   - Click on your service
   - Go to "Variables" tab
   - Click "New Variable"
   - Name: `OPENAI_API_KEY`
   - Value: `sk-proj-your-actual-key-here`
   - Click "Add"

3. **Redeploy** (Railway will automatically redeploy when you add variables)

---

## Step 5: Test It

1. **Start your Flask app**:
   ```powershell
   flask run
   ```

2. **Go to a transaction** → Click "Feature Spotlight Cards"

3. **Add a feature** with rough text, e.g.:
   - Title: "big pantry"
   - Room: "kitchen"
   - Description: "lots of storage space"

4. **Click "Refine"** button next to the title

5. **You should see** the text get refined to something like:
   - Title: "Spacious Pantry"
   - Description: "Ample storage space maximizes kitchen organization and keeps countertops clutter-free."

---

## Troubleshooting

### "OpenAI refinement failed"
- Check that `OPENAI_API_KEY` is set correctly
- Verify the key is valid at https://platform.openai.com/api-keys
- Check your OpenAI account has credits/billing set up
- Check the console/terminal for error messages

### "Module not found: openai"
- Run: `pip install openai`

### API Key not working
- Make sure there are no extra spaces or quotes around the key
- Verify the key starts with `sk-`
- Check your OpenAI account billing status

### Still using simple refinement
- The system falls back to simple text processing if OpenAI fails
- Check the console logs for error messages
- Verify the environment variable is loaded: `print(os.environ.get('OPENAI_API_KEY'))`

---

## Security Notes

⚠️ **NEVER commit your API key to git!**
- The `.env` file should be in `.gitignore` (already configured)
- Never share your API key publicly
- If you accidentally commit it, regenerate the key immediately

---

## Cost Estimate

- GPT-3.5-turbo: ~$0.0015 per 1K tokens
- Each refinement uses ~100-150 tokens
- **100 refinements ≈ $0.015** (less than 2 cents!)
- Very affordable for production use

---

## Next Steps

Once set up, the AI will automatically:
- Refine all features when generating PDFs
- Allow manual refinement via the "Refine" button
- Make your feature cards more professional and elegant

