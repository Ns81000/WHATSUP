# IMDb Rating Feature - Setup Guide

## ✅ Feature Implemented

IMDb ratings are now automatically fetched and displayed on each blog post!

### What Was Added:

1. **Python Script (`scripts/main.py`)**
   - `fetch_omdb_rating()` function - fetches IMDb rating from OMDb API
   - Graceful failure handling - if rating unavailable, post still generates
   - Rating added to frontmatter during post generation

2. **Post Layout (`_layouts/post.html`)**
   - Inline rating badge displayed with post metadata
   - Only shows if rating is available (conditional rendering)

3. **Styling (`_sass/addon/commons/_imdb-rating.scss`)**
   - IMDb yellow gradient badge
   - Responsive design (mobile-friendly)
   - Dark mode support
   - Hover effects

---

## 🔧 Setup for GitHub Actions

### Step 1: Get OMDb API Key (FREE - 2 minutes)

1. Go to: https://www.omdbapi.com/apikey.aspx
2. Select: **FREE! (1,000 daily limit)**
3. Enter your email address
4. Check your email and click verification link
5. Copy your API key (looks like: `abc12345`)

### Step 2: Add Secret to GitHub Repository

1. Go to your repository: https://github.com/Ns81000/WHATSUP
2. Click: **Settings** (top right)
3. In left sidebar: **Secrets and variables** → **Actions**
4. Click: **New repository secret**
5. Add secret:
   - **Name:** `OMDB_API_KEY`
   - **Value:** `your_api_key_here` (paste from step 1)
6. Click: **Add secret**

### Step 3: Verify Environment Variable in Workflow

Your GitHub Actions workflow (`.github/workflows/daily_post.yml`) should already include environment variables. Verify this section exists:

```yaml
env:
  GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
  TMDB_API_KEY: ${{ secrets.TMDB_API_KEY }}
  OMDB_API_KEY: ${{ secrets.OMDB_API_KEY }}  # ← Should be here
  TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
  TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
  SMTP_EMAIL: ${{ secrets.SMTP_EMAIL }}
  SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
  NOTIFICATION_EMAIL: ${{ secrets.NOTIFICATION_EMAIL }}
```

If missing, add it manually to `.github/workflows/daily_post.yml`.

### Step 4: Push Changes to GitHub

```bash
cd c:\Users\Ns8pc\Music\WHATSUP-main
git add .
git commit -m "Add IMDb rating feature to blog posts"
git push origin main
```

### Step 5: Test

Next time GitHub Actions runs (scheduled time), new posts will automatically include IMDb ratings!

---

## 🧪 Local Testing (Optional)

### Test the Feature Locally:

1. **Set Environment Variable:**
   ```powershell
   $env:OMDB_API_KEY = "your_api_key_here"
   $env:GEMINI_API_KEY = "your_gemini_key"
   $env:TMDB_API_KEY = "your_tmdb_key"
   ```

2. **Run Script:**
   ```powershell
   cd c:\Users\Ns8pc\Music\WHATSUP-main
   python scripts/main.py
   ```

3. **Check Output:**
   - Console should show: `✓ IMDb Rating: 7.0/10 (91,234 votes)`
   - Generated post should have in frontmatter:
     ```yaml
     imdb_rating: 7.0
     imdb_votes: "91,234"
     ```

4. **View Post:**
   - Run Jekyll locally: `bundle exec jekyll serve`
   - Open: http://localhost:4000/WHATSUP
   - Check post metadata for yellow rating badge

---

## 📊 How It Works

### Generation Flow:

```
1. Select movie from CSV (IMDb ID: tt2934286)
2. Fetch TMDB data (metadata + images)
3. ✨ NEW: Fetch OMDb rating
   - API call: https://www.omdbapi.com/?i=tt2934286&apikey=YOUR_KEY
   - Response: {"imdbRating": "7.0", "imdbVotes": "91,234"}
   - If fails: Skip (post still generates)
4. Generate content with Gemini (unchanged)
5. ✨ NEW: Add rating to frontmatter
6. Save markdown file
```

### Post Frontmatter:

**Before (without rating):**
```yaml
---
title: "Post Title"
date: 2026-02-03
categories: [Philosophical, Action]
tags: [Cerebral, Intense]
description: "..."
---
```

**After (with rating):**
```yaml
---
title: "Post Title"
date: 2026-02-03
categories: [Philosophical, Action]
tags: [Cerebral, Intense]
imdb_rating: 7.0
imdb_votes: "91,234"
description: "..."
---
```

### Display:

Posts now show inline with metadata:
```
Posted on February 3, 2026 • ⭐ 7.0/10 (91,234 votes)
```

---

## 🛡️ Graceful Failure Handling

### If OMDb API is unavailable:
- ✅ Console shows: `⚠️ OMDb API error (skipping rating)`
- ✅ Post still generates normally
- ✅ No rating badge displayed (clean fallback)
- ✅ Gemini unaffected

### If OMDb API key not configured:
- ✅ Console shows: `⚠️ OMDb API key not configured (ratings disabled)`
- ✅ All posts generate without ratings
- ✅ Everything works as before

### If rating not available for a film:
- ✅ Console shows: `⚠️ No IMDb rating available`
- ✅ Post generates without rating
- ✅ No badge displayed

---

## 💰 API Usage & Limits

### OMDb Free Tier:
- **Daily Limit:** 1,000 requests
- **Your Usage:** ~5 requests/day (1 per post × 4-5 posts)
- **Monthly Usage:** ~150 requests/month
- **Quota Used:** 0.5% of daily limit 😎

### No Additional Costs:
- ✅ OMDb is 100% free for your use case
- ✅ No credit card required
- ✅ No upgrade needed

---

## 🎨 Customization Options

### Change Badge Color (in `_sass/addon/commons/_imdb-rating.scss`):

```scss
// Current: IMDb yellow
background: linear-gradient(135deg, #f5c518 0%, #e8b708 100%);

// Option 1: Blue gradient
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

// Option 2: Red gradient
background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);

// Option 3: Green gradient
background: linear-gradient(135deg, #56ab2f 0%, #a8e063 100%);
```

### Change Position:

**Current:** Inline with post date/metadata

**Alternative 1 - Below hero image:**
Edit `_layouts/post.html`, move badge code after image section.

**Alternative 2 - In sidebar:**
Create custom include file and add to sidebar layout.

---

## 🔍 Troubleshooting

### Problem: Ratings not showing

**Check:**
1. OMDb API key added to GitHub Secrets?
2. Secret name exactly: `OMDB_API_KEY` (case-sensitive)
3. Workflow file includes environment variable?
4. Check GitHub Actions logs for errors

### Problem: "API Error: 401"

**Solution:**
- API key is invalid or expired
- Get new key from https://www.omdbapi.com/apikey.aspx
- Update GitHub Secret

### Problem: "API Error: 429"

**Solution:**
- Daily limit exceeded (unlikely at 5 requests/day)
- Wait until next day (UTC midnight)

### Problem: Rating shows "N/A"

**Solution:**
- Film doesn't have IMDb rating yet (new releases)
- This is normal - badge won't display for these posts

---

## ✅ Verification Checklist

After setup, verify:

- [ ] OMDb API key obtained
- [ ] Secret added to GitHub: `OMDB_API_KEY`
- [ ] Environment variable in workflow file
- [ ] Code pushed to GitHub
- [ ] Wait for next scheduled run
- [ ] Check new posts for rating badge
- [ ] View GitHub Actions logs for success message

---

## 📞 Support

If you encounter issues:

1. Check GitHub Actions logs
2. Look for `⭐ Fetching IMDb rating...` in logs
3. Check for error messages
4. Verify API key is correct

---

## 🎉 Success!

Once configured, every new blog post will automatically include:
- ⭐ IMDb rating (e.g., 7.0/10)
- Vote count (e.g., 91,234 votes)
- Beautiful yellow badge inline with metadata
- Fully responsive design
- Dark mode support

**No manual work required!** 🚀
