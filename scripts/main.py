#!/usr/bin/env python3
"""
What's Up? - Autonomous Philosophical Media Engine
Main automation script for generating movie/series blog posts.

Features:
- Reads from IMDb CSV exports (movies.csv, series.csv)
- Fetches metadata and images from TMDB API
- Uses Gemini AI for philosophical content generation
- Falls back to Gemini web search if TMDB data unavailable
- Telegram/SMTP alerts for missing images
- WebP image optimization (<500KB)
- Pre-check system for next item's images
"""

import os
import sys
import json
import random
import time
import re
import shutil
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
from PIL import Image

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("⚠️  google-genai not installed. Content generation will be limited.")

# ==================== CONFIGURATION ====================

# API Keys (from environment variables)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SMTP_EMAIL = os.getenv('SMTP_EMAIL')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL')

# File Paths (relative to script location)
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
DATA_DIR = ROOT_DIR / 'data'
POSTS_DIR = ROOT_DIR / '_posts'
IMAGES_DIR = ROOT_DIR / 'assets' / 'img' / 'posts'

MOVIES_CSV = DATA_DIR / 'movies.csv'
SERIES_CSV = DATA_DIR / 'series.csv'
HISTORY_FILE = DATA_DIR / 'history.log'
METADATA_FILE = DATA_DIR / 'metadata_db.json'

# TMDB Configuration
TMDB_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/'

# Image Configuration
HERO_MAX_SIZE_KB = 500
HERO_TARGET_WIDTH = 1920
BODY_MAX_SIZE_KB = 300
BODY_TARGET_WIDTH = 1280

# ==================== VALIDATION ====================

def validate_environment():
    """Ensure all required environment variables are set."""
    required = ['GEMINI_API_KEY', 'TMDB_API_KEY']
    optional = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'SMTP_EMAIL', 'SMTP_PASSWORD']
    
    missing_required = [var for var in required if not os.getenv(var)]
    missing_optional = [var for var in optional if not os.getenv(var)]
    
    if missing_required:
        print(f"❌ Missing REQUIRED environment variables: {', '.join(missing_required)}")
        sys.exit(1)
    
    if missing_optional:
        print(f"⚠️  Missing optional variables (fallback features disabled): {', '.join(missing_optional)}")
    
    print("✅ Environment validated")
    return True


def validate_csv_files():
    """Check CSV files exist and are valid."""
    for csv_file in [MOVIES_CSV, SERIES_CSV]:
        if not csv_file.exists():
            print(f"❌ CSV file not found: {csv_file}")
            sys.exit(1)
        
        try:
            df = pd.read_csv(csv_file)
            required_cols = ['Const', 'Title', 'Year']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                print(f"❌ Missing columns in {csv_file.name}: {missing_cols}")
                sys.exit(1)
            
            print(f"✅ {csv_file.name}: {len(df)} items")
        except Exception as e:
            print(f"❌ Error reading {csv_file.name}: {e}")
            sys.exit(1)
    
    return True


# ==================== CSV & HISTORY MANAGEMENT ====================

def backup_csv_files():
    """Create backups of CSV files before processing."""
    for csv_file in [MOVIES_CSV, SERIES_CSV]:
        if csv_file.exists():
            backup = csv_file.with_suffix('.backup.csv')
            shutil.copy(csv_file, backup)
            print(f"📦 Backup created: {backup.name}")


def load_history():
    """Load processed IMDb IDs from history file."""
    if not HISTORY_FILE.exists():
        return set()
    
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        processed = set()
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                # Extract IMDb ID (first part before any whitespace or comment)
                imdb_id = line.split()[0] if line.split() else None
                if imdb_id and imdb_id.startswith('tt'):
                    processed.add(imdb_id)
        return processed


def save_to_history(imdb_id, title):
    """Add processed item to history."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        f.write(f"{imdb_id}  # {title} - {timestamp}\n")
    
    print(f"📝 Added to history: {imdb_id}")


def is_sunday_fifth_run():
    """
    Check if this is Sunday's 3rd run (the 5th post of the day).
    Sunday runs at 03:00, 09:00, and 14:00 UTC.
    The 14:00 UTC run is the 5th post (only 1 item instead of 2).
    """
    now = datetime.utcnow()
    is_sunday = now.weekday() == 6  # 0=Monday, 6=Sunday
    is_fifth_run_time = 13 <= now.hour <= 15  # 14:00 UTC window (with delay buffer)
    return is_sunday and is_fifth_run_time


def select_items():
    """
    Select items for this run.
    
    Normal runs: 1 movie + 1 series = 2 posts
    Sunday 5th run: Only 1 item (alternating movie/series weekly)
    """
    history = load_history()
    print(f"📊 Already processed: {len(history)} items")
    
    # Check if this is Sunday's 5th post (single item only)
    fifth_run = is_sunday_fifth_run()
    if fifth_run:
        print("🌟 SUNDAY SPECIAL: 5th post run (single item)")
    
    # Load CSVs
    movies_df = pd.read_csv(MOVIES_CSV)
    series_df = pd.read_csv(SERIES_CSV)
    
    # Filter out already processed items
    available_movies = movies_df[~movies_df['Const'].isin(history)]
    available_series = series_df[~series_df['Const'].isin(history)]
    
    movie = None
    series = None
    next_movie = None
    next_series = None
    
    # For Sunday's 5th run, only pick 1 item (alternate weekly)
    if fifth_run:
        week_number = datetime.utcnow().isocalendar()[1]
        pick_movie = (week_number % 2 == 0)  # Even weeks: movie, Odd weeks: series
        
        if pick_movie and not available_movies.empty:
            movie = available_movies.iloc[0].to_dict()
            if len(available_movies) > 1:
                next_movie = available_movies.iloc[1].to_dict()
            print(f"🎬 Sunday Special (Movie): {movie['Title']} ({movie['Year']})")
        elif not available_series.empty:
            series = available_series.iloc[0].to_dict()
            if len(available_series) > 1:
                next_series = available_series.iloc[1].to_dict()
            print(f"📺 Sunday Special (Series): {series['Title']} ({series['Year']})")
        elif not available_movies.empty:
            movie = available_movies.iloc[0].to_dict()
            if len(available_movies) > 1:
                next_movie = available_movies.iloc[1].to_dict()
            print(f"🎬 Sunday Special (Movie fallback): {movie['Title']} ({movie['Year']})")
    else:
        # Normal run: pick both movie and series
        if available_movies.empty:
            print("⚠️ No more movies to process!")
        else:
            movie = available_movies.iloc[0].to_dict()
            if len(available_movies) > 1:
                next_movie = available_movies.iloc[1].to_dict()
            print(f"🎬 Selected movie: {movie['Title']} ({movie['Year']})")
        
        if available_series.empty:
            print("⚠️ No more series to process!")
        else:
            series = available_series.iloc[0].to_dict()
            if len(available_series) > 1:
                next_series = available_series.iloc[1].to_dict()
            print(f"📺 Selected series: {series['Title']} ({series['Year']})")
    
    return movie, series, next_movie, next_series


# ==================== TMDB API ====================

def fetch_tmdb_data(imdb_id):
    """Fetch comprehensive data from TMDB using IMDb ID."""
    
    # Step 1: Find TMDB ID from IMDb ID
    find_url = f"{TMDB_BASE_URL}/find/{imdb_id}"
    params = {
        'api_key': TMDB_API_KEY,
        'external_source': 'imdb_id'
    }
    
    try:
        response = requests.get(find_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"❌ TMDB API error: {e}")
        return None, None
    
    # Determine media type
    tmdb_id = None
    media_type = None
    
    if data.get('movie_results'):
        tmdb_id = data['movie_results'][0]['id']
        media_type = 'movie'
    elif data.get('tv_results'):
        tmdb_id = data['tv_results'][0]['id']
        media_type = 'tv'
    else:
        print(f"⚠️ Could not find {imdb_id} on TMDB")
        return None, None
    
    # Step 2: Fetch full details with images, credits, and watch providers
    details_url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}"
    params = {
        'api_key': TMDB_API_KEY,
        'append_to_response': 'images,credits,watch/providers'
    }
    
    try:
        response = requests.get(details_url, params=params, timeout=30)
        response.raise_for_status()
        return response.json(), media_type
    except requests.RequestException as e:
        print(f"❌ TMDB details error: {e}")
        return None, None


def check_image_availability(imdb_id):
    """Check if TMDB has high-quality images for an item."""
    tmdb_data, _ = fetch_tmdb_data(imdb_id)
    
    if not tmdb_data:
        return False
    
    backdrops = tmdb_data.get('images', {}).get('backdrops', [])
    
    # Check for hero-quality image (width >= 1920)
    hero_quality = any(img.get('width', 0) >= 1920 for img in backdrops)
    
    return hero_quality


def get_streaming_providers(tmdb_data, country='US'):
    """Extract streaming providers from TMDB data."""
    providers = tmdb_data.get('watch/providers', {}).get('results', {})
    country_data = providers.get(country, {})
    
    flatrate = country_data.get('flatrate', [])
    
    if not flatrate:
        return None
    
    return [p['provider_name'] for p in flatrate[:5]]


# ==================== IMAGE PROCESSING ====================

def download_image(url, timeout=60):
    """Download image from URL and return bytes."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        print(f"❌ Image download error: {e}")
        return None


def process_and_save_image(image_data, output_path, max_size_kb=500, target_width=1920):
    """Convert to WebP, resize, and compress image."""
    
    try:
        img = Image.open(BytesIO(image_data))
    except Exception as e:
        print(f"❌ Cannot open image: {e}")
        return False
    
    # Convert to RGB (WebP doesn't support all modes)
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        if 'A' in img.mode:
            background.paste(img, mask=img.split()[-1])
        else:
            background.paste(img)
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Resize to target width while maintaining aspect ratio
    if img.width > target_width:
        ratio = target_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
    
    # Create output directory
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Compress iteratively to meet size requirement
    quality = 90
    while quality > 20:
        buffer = BytesIO()
        img.save(buffer, format='WEBP', quality=quality, method=6)
        size_kb = len(buffer.getvalue()) / 1024
        
        if size_kb <= max_size_kb:
            with open(output_path, 'wb') as f:
                f.write(buffer.getvalue())
            print(f"   ✓ Saved {output_path.name}: {size_kb:.1f}KB (quality: {quality})")
            return True
        
        quality -= 5
    
    # Last resort: reduce dimensions further
    img = img.resize((int(img.width * 0.75), int(img.height * 0.75)), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    img.save(buffer, format='WEBP', quality=70, method=6)
    
    with open(output_path, 'wb') as f:
        f.write(buffer.getvalue())
    
    size_kb = len(buffer.getvalue()) / 1024
    print(f"   ✓ Saved {output_path.name}: {size_kb:.1f}KB (resized)")
    return True


def download_and_process_images(tmdb_data, imdb_id):
    """Download hero image and optional body images."""
    
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    
    images = []
    backdrops = tmdb_data.get('images', {}).get('backdrops', [])
    
    if not backdrops:
        print(f"⚠️ No backdrop images found for {imdb_id}")
        return None
    
    # Sort by quality (vote_average * width)
    backdrops.sort(
        key=lambda x: x.get('vote_average', 0) * x.get('width', 0), 
        reverse=True
    )
    
    # Download hero image (best quality)
    hero = backdrops[0]
    hero_url = f"{TMDB_IMAGE_BASE}original{hero['file_path']}"
    
    print(f"📸 Downloading hero image...")
    hero_data = download_image(hero_url)
    
    if hero_data:
        hero_path = IMAGES_DIR / f"{imdb_id}_hero.webp"
        if process_and_save_image(hero_data, hero_path, HERO_MAX_SIZE_KB, HERO_TARGET_WIDTH):
            images.append(('hero', str(hero_path.relative_to(ROOT_DIR))))
    
    # Download up to 3 additional body images
    for i, backdrop in enumerate(backdrops[1:4], 1):
        img_url = f"{TMDB_IMAGE_BASE}w1280{backdrop['file_path']}"
        
        print(f"📸 Downloading body image {i}...")
        img_data = download_image(img_url, timeout=30)
        
        if img_data:
            img_path = IMAGES_DIR / f"{imdb_id}_{i}.webp"
            if process_and_save_image(img_data, img_path, BODY_MAX_SIZE_KB, BODY_TARGET_WIDTH):
                images.append((f'body_{i}', str(img_path.relative_to(ROOT_DIR))))
    
    return images if images else None


# ==================== TELEGRAM INTEGRATION ====================

def send_telegram_message(message):
    """Send a message via Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        print("📱 Telegram message sent")
        return True
    except requests.RequestException as e:
        print(f"❌ Telegram error: {e}")
        return False


def check_telegram_for_uploads(imdb_id):
    """Check Telegram for images with matching caption tokens."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {}
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    
    try:
        response = requests.get(url, timeout=30)
        updates = response.json().get('result', [])
    except requests.RequestException:
        return {}
    
    downloaded_images = {}
    message_ids_to_delete = []
    
    for update in updates:
        message = update.get('message', {})
        caption = message.get('caption', '')
        
        # Check if caption contains our token
        if f"_{imdb_id}" in caption:
            photos = message.get('photo', [])
            if photos:
                file_id = photos[-1]['file_id']  # Highest resolution
                
                # Get file path
                file_info_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
                file_info = requests.get(file_info_url, params={'file_id': file_id}).json()
                
                file_path = file_info.get('result', {}).get('file_path')
                if file_path:
                    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                    image_data = download_image(file_url)
                    
                    if image_data:
                        if caption.upper().startswith('HERO_'):
                            downloaded_images['hero'] = image_data
                        elif caption.upper().startswith('IMG1_'):
                            downloaded_images['img1'] = image_data
                        elif caption.upper().startswith('IMG2_'):
                            downloaded_images['img2'] = image_data
                        elif caption.upper().startswith('IMG3_'):
                            downloaded_images['img3'] = image_data
                        
                        message_ids_to_delete.append(message['message_id'])
    
    # Delete processed messages
    for msg_id in message_ids_to_delete:
        delete_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
        requests.get(delete_url, params={'chat_id': TELEGRAM_CHAT_ID, 'message_id': msg_id})
    
    if downloaded_images:
        print(f"📥 Downloaded {len(downloaded_images)} images from Telegram")
        print(f"🗑️ Deleted {len(message_ids_to_delete)} processed messages")
    
    return downloaded_images


def trigger_manual_fallback(imdb_id, title):
    """Send alerts for manual image upload."""
    
    # Telegram alert
    telegram_msg = f"""
🎬 *Manual Upload Required*

*Title:* {title}
*IMDb ID:* {imdb_id}

📸 *Upload Images with These Captions:*

1️⃣ `HERO_{imdb_id}` _(Landscape/Backdrop - REQUIRED)_
2️⃣ `IMG1_{imdb_id}` _(Optional)_
3️⃣ `IMG2_{imdb_id}` _(Optional)_
4️⃣ `IMG3_{imdb_id}` _(Optional)_

⏰ *Deadline:* Before next scheduled run (~6 hours)

_Reply with your photos. They will be processed automatically._
"""
    send_telegram_message(telegram_msg)
    
    # Email alert
    if SMTP_EMAIL and SMTP_PASSWORD and NOTIFICATION_EMAIL:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🎬 Action Required: Image Missing for {title}"
            msg['From'] = SMTP_EMAIL
            msg['To'] = NOTIFICATION_EMAIL
            
            html = f"""
            <html>
            <body>
                <h2>⚠️ Manual Image Upload Required</h2>
                <p><strong>Title:</strong> {title}</p>
                <p><strong>IMDb ID:</strong> {imdb_id}</p>
                <hr>
                <p>Please check your Telegram and upload the required images.</p>
                <p>Tokens to use as captions:</p>
                <ul>
                    <li><code>HERO_{imdb_id}</code> - Required landscape image</li>
                    <li><code>IMG1_{imdb_id}</code> - Optional</li>
                    <li><code>IMG2_{imdb_id}</code> - Optional</li>
                    <li><code>IMG3_{imdb_id}</code> - Optional</li>
                </ul>
            </body>
            </html>
            """
            msg.attach(MIMEText(html, 'html'))
            
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, NOTIFICATION_EMAIL, msg.as_string())
            
            print("✉️ Email alert sent")
        except Exception as e:
            print(f"⚠️ Email error: {e}")


# ==================== GEMINI CONTENT GENERATION ====================

def generate_blog_post(imdb_data, tmdb_data, media_type, has_images=True, image_count=4):
    """Generate philosophical blog post using Gemini AI."""
    
    if not GENAI_AVAILABLE or not GEMINI_API_KEY:
        print("❌ Gemini AI not available")
        return None
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Get streaming data
    streaming_providers = None
    if tmdb_data:
        streaming_providers = get_streaming_providers(tmdb_data)
    
    streaming_section = ""
    if streaming_providers:
        streaming_section = "\n".join([f"- {p}" for p in streaming_providers])
    
    # Get cast
    cast = []
    if tmdb_data:
        credits = tmdb_data.get('credits', {})
        cast = [c['name'] for c in credits.get('cast', [])[:5]]
    
    # Handle missing TMDB data with web search instruction
    plot = tmdb_data.get('overview', '') if tmdb_data else ''
    web_search_instruction = ""
    if not plot:
        web_search_instruction = """
        
        IMPORTANT: No plot information was found in our database.
        Please use your web search capabilities to:
        1. Research this movie/series thoroughly
        2. Find plot details, themes, and critical reception
        3. If web search fails, use your best knowledge to write about it
        """
    
    imdb_id = imdb_data['Const']
    title = imdb_data['Title']
    year = imdb_data.get('Year', 'Unknown')
    genres = imdb_data.get('Genres', 'Drama')
    directors = imdb_data.get('Directors', 'Unknown')
    rating = imdb_data.get('IMDb Rating', 'N/A')
    
    # Determine image paths
    hero_image = f"/assets/img/posts/{imdb_id}_hero.webp" if has_images else ""
    body_images = []
    if has_images and image_count > 1:
        for i in range(1, min(image_count, 4)):  # Max 3 body images
            body_images.append(f"/assets/img/posts/{imdb_id}_{i}.webp")
    
    # Build image instructions
    image_instructions = ""
    if body_images:
        image_instructions = f"""
IMPORTANT - EMBED THESE IMAGES in your content:
- Image 1: ![Scene from {title}]({body_images[0]}){{: .rounded-10 w-75 .shadow}}
{"- Image 2: ![Scene from " + title + "](" + body_images[1] + "){: .rounded-10 w-75 .shadow}" if len(body_images) > 1 else ""}
{"- Image 3: ![Scene from " + title + "](" + body_images[2] + "){: .rounded-10 w-75 .shadow}" if len(body_images) > 2 else ""}

Place these images strategically between sections to break up text and enhance visual appeal.
"""
    
    # Build prompt
    prompt = f"""
You are a renowned film philosopher and cultural critic writing for "What's Up?" - 
a sophisticated platform that explores the deeper meaning behind cinema.

Write a beautifully formatted philosophical blog post about:

TITLE: {title} ({year})
TYPE: {'Movie' if media_type == 'movie' else 'TV Series'}
GENRES: {genres}
DIRECTOR: {directors}
IMDB RATING: {rating}
CAST: {', '.join(cast) if cast else 'Not available'}

PLOT: {plot if plot else 'Not available - see instructions below'}
{web_search_instruction}

{image_instructions}

FORMATTING REQUIREMENTS (VERY IMPORTANT):
1. Write 800-1200 words of philosophical analysis
2. Use RICH MARKDOWN formatting:
   - Start with a powerful opening quote using > blockquote
   - Use ## Section Headers to organize content (3-4 sections)
   - Include > blockquotes for memorable quotes from the film or philosophers
   - Use **bold** for emphasis on key philosophical concepts
   - Use *italics* for film titles and foreign terms
   - Add horizontal rules --- between major sections
   - Embed the body images between sections (see image instructions above)
   
3. STRUCTURE your post like this:
   - Opening: A philosophical hook or profound quote (blockquote)
   - Section 1 (##): The core philosophical theme
   - [IMAGE 1 here if available]
   - Section 2 (##): Character study or ethical dilemmas  
   - [IMAGE 2 here if available]
   - Section 3 (##): Metaphysical/existential exploration
   - [IMAGE 3 here if available]
   - Closing: A thought-provoking conclusion or question
   
4. Explore existential, metaphysical, or ethical themes - go beyond plot summaries
5. Connect the work to broader human experiences and philosophical questions
6. Use elegant prose with occasional poetic flourishes
7. {"Include the streaming section at the end" if streaming_providers else "Do NOT include a streaming section"}
8. Assign exactly 3 mood tags from: [Cerebral, Melancholy, Hopeful, Intense, Nostalgic, 
   Existential, Romantic, Heroic, Dystopian, Surreal]

OUTPUT FORMAT (Jekyll Frontmatter + Markdown):

---
title: "Your Philosophical Title Here - Be Creative and Evocative"
date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S +0530')}
categories: [Philosophical, {genres.split(',')[0].strip() if genres else 'Drama'}]
tags: [mood1, mood2, mood3]
{"image:" if has_images else "# No image available"}
{f"  path: {hero_image}" if has_images else ""}
{f'  alt: "Evocative description of the scene"' if has_images else ""}
description: "Compelling meta description exploring the film's themes (150-160 chars)"
---

> "A profound opening quote that sets the philosophical tone" — Attribution
{{: .prompt-tip }}

[Opening paragraph with beautiful prose...]

## 🎭 First Section Title

[Content with **bold concepts** and *italicized terms*...]

{"![A compelling scene from " + title + "](" + body_images[0] + "){: .rounded-10 w-75 .shadow}" if body_images else ""}
_A caption describing the image's significance_

## 🧠 Second Section Title

[More philosophical exploration...]

{"![Another powerful moment](" + body_images[1] + "){: .rounded-10 w-75 .shadow}" if len(body_images) > 1 else ""}

## 🌌 Third Section Title  

[Deeper existential themes...]

{"![The visual metaphor](" + body_images[2] + "){: .rounded-10 w-75 .shadow}" if len(body_images) > 2 else ""}

---

> "A closing thought or question that lingers with the reader"

{"## 📺 Where to Watch" if streaming_providers else ""}
{streaming_section if streaming_section else ""}

---

*What's Up? explores the philosophical depths of cinema.* ✨
"""
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.85,
                max_output_tokens=4096,
            )
        )
        
        content = response.text.strip()
        
        # Clean up any markdown code blocks wrapping
        if content.startswith('```'):
            content = re.sub(r'^```(?:markdown|md)?\s*\n', '', content)
            content = re.sub(r'\n```\s*$', '', content)
        
        return content
        
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return None


# ==================== METADATA TRACKING ====================

def update_metadata(imdb_id, title, moods, url):
    """Update metadata database for weekly roundups."""
    
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing metadata
    if METADATA_FILE.exists():
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    else:
        metadata = {'posts': []}
    
    # Add new entry
    metadata['posts'].append({
        'imdb_id': imdb_id,
        'title': title,
        'moods': moods,
        'url': url,
        'date': datetime.now().isoformat()
    })
    
    # Keep only last 100 entries
    metadata['posts'] = metadata['posts'][-100:]
    
    # Save
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def extract_moods_from_content(content):
    """Extract mood tags from generated content."""
    # Look for tags line in frontmatter
    match = re.search(r'tags:\s*\[([^\]]+)\]', content)
    if match:
        tags = [t.strip().strip('"\'') for t in match.group(1).split(',')]
        return tags[:3]
    return ['Cerebral', 'Intense', 'Existential']  # Default


# ==================== MAIN PROCESSING ====================

def process_item(item_data, media_type_label):
    """Process a single movie or series."""
    
    imdb_id = item_data['Const']
    title = item_data['Title']
    
    print(f"\n{'='*60}")
    print(f"🎬 Processing {media_type_label}: {title} ({item_data.get('Year', 'N/A')})")
    print(f"   IMDb ID: {imdb_id}")
    print('='*60)
    
    # Step 1: Check Telegram for manual uploads first
    print("\n🔍 Checking Telegram for manual uploads...")
    telegram_images = check_telegram_for_uploads(imdb_id)
    
    images = None
    tmdb_data = None
    media_type = 'movie' if media_type_label == 'Movie' else 'tv'
    
    if telegram_images:
        # Process Telegram images
        print(f"✅ Found {len(telegram_images)} images from Telegram!")
        images = []
        
        for img_type, img_data in telegram_images.items():
            if img_type == 'hero':
                output_path = IMAGES_DIR / f"{imdb_id}_hero.webp"
                if process_and_save_image(img_data, output_path, HERO_MAX_SIZE_KB, HERO_TARGET_WIDTH):
                    images.append(('hero', str(output_path.relative_to(ROOT_DIR))))
            else:
                idx = img_type[-1]  # img1, img2, img3
                output_path = IMAGES_DIR / f"{imdb_id}_{idx}.webp"
                if process_and_save_image(img_data, output_path, BODY_MAX_SIZE_KB, BODY_TARGET_WIDTH):
                    images.append((img_type, str(output_path.relative_to(ROOT_DIR))))
    
    # Step 2: Fetch TMDB data
    print("\n📥 Fetching TMDB data...")
    tmdb_data, detected_type = fetch_tmdb_data(imdb_id)
    
    if detected_type:
        media_type = detected_type
    
    if tmdb_data:
        print(f"   ✓ Found: {tmdb_data.get('title', tmdb_data.get('name', 'Unknown'))}")
        print(f"   ✓ Overview: {len(tmdb_data.get('overview', ''))} chars")
        print(f"   ✓ Backdrops: {len(tmdb_data.get('images', {}).get('backdrops', []))} available")
    else:
        print("   ⚠️ No TMDB data found - will use Gemini web search")
    
    # Step 3: Download TMDB images if we don't have Telegram images
    if not images and tmdb_data:
        print("\n📸 Downloading TMDB images...")
        images = download_and_process_images(tmdb_data, imdb_id)
    
    has_images = bool(images)
    image_count = len(images) if images else 0
    
    if not has_images:
        print("\n⚠️ No images available - post will be created without hero image")
        # We continue anyway - Gemini can still write the post
    else:
        print(f"   ✓ {image_count} image(s) ready for embedding")
    
    # Step 4: Generate content with Gemini
    print("\n✍️ Generating philosophical content with Gemini...")
    content = generate_blog_post(item_data, tmdb_data, media_type, has_images, image_count)
    
    if not content:
        print("❌ Content generation failed!")
        return False
    
    print(f"   ✓ Generated {len(content)} characters")
    
    # Step 5: Save the post
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create filename-safe title
    clean_title = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:50]
    filename = f"{datetime.now().strftime('%Y-%m-%d')}-{clean_title}.md"
    filepath = POSTS_DIR / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ Post saved: {filepath.name}")
    
    # Step 6: Update history and metadata
    save_to_history(imdb_id, title)
    
    moods = extract_moods_from_content(content)
    post_url = f"/posts/{clean_title}/"
    update_metadata(imdb_id, title, moods, post_url)
    
    return True


def pre_check_next_items(next_movie, next_series):
    """Pre-check image availability for next scheduled items."""
    
    print("\n" + "="*60)
    print("🔮 PRE-CHECK: Verifying next items have images")
    print("="*60)
    
    items_to_alert = []
    
    if next_movie:
        print(f"\n🎬 Checking next movie: {next_movie['Title']}")
        if not check_image_availability(next_movie['Const']):
            print(f"   ⚠️ No high-quality images found!")
            items_to_alert.append(('Movie', next_movie))
        else:
            print(f"   ✓ Images available")
    
    if next_series:
        print(f"\n📺 Checking next series: {next_series['Title']}")
        if not check_image_availability(next_series['Const']):
            print(f"   ⚠️ No high-quality images found!")
            items_to_alert.append(('Series', next_series))
        else:
            print(f"   ✓ Images available")
    
    # Trigger alerts for items without images
    for media_type, item in items_to_alert:
        print(f"\n🚨 Triggering manual fallback for: {item['Title']}")
        trigger_manual_fallback(item['Const'], item['Title'])
    
    return len(items_to_alert) == 0  # Return True if all have images


# ==================== MAIN ENTRY POINT ====================

def main():
    """Main execution flow."""
    
    print("\n" + "="*60)
    print("🎬 What's Up? - Autonomous Philosophical Media Engine")
    print("="*60)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Validate environment
    print("\n📋 Validating environment...")
    validate_environment()
    validate_csv_files()
    
    # Backup CSV files
    print("\n📦 Creating CSV backups...")
    backup_csv_files()
    
    # Select items to process
    print("\n📋 Selecting items to process...")
    movie, series, next_movie, next_series = select_items()
    
    if not movie and not series:
        print("\n❌ No items available to process!")
        print("   Check that your CSV files have unprocessed entries.")
        return
    
    # Pre-check next items (Early Warning System)
    pre_check_next_items(next_movie, next_series)
    
    # Process current items
    success_count = 0
    
    if movie:
        if process_item(movie, 'Movie'):
            success_count += 1
    
    if series:
        if process_item(series, 'Series'):
            success_count += 1
    
    # Summary
    print("\n" + "="*60)
    print(f"✅ Automation complete!")
    print(f"   Processed: {success_count} item(s)")
    print(f"   Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)


if __name__ == "__main__":
    main()
