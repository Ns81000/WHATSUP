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
- Sunday morning notification-only mode
"""

import os
import sys
import json
import random
import time
import argparse
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
IMAGE_USAGE_FILE = DATA_DIR / 'used_images.json'

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


def remove_from_csv(imdb_id, media_type):
    """Remove processed item from CSV file to prevent re-selection."""
    csv_file = MOVIES_CSV if media_type == 'movie' else SERIES_CSV
    
    try:
        df = pd.read_csv(csv_file)
        initial_count = len(df)
        df = df[df['Const'] != imdb_id]
        df.to_csv(csv_file, index=False)
        
        if len(df) < initial_count:
            print(f"📝 Removed {imdb_id} from {csv_file.name}")
        return True
    except Exception as e:
        print(f"⚠️ Failed to remove from CSV: {e}")
        return False


# ==================== HISTORY & WEEKLY RECAP ====================

def get_week_posts_from_history():
    """Extract all posts from the current week from history.log."""
    if not HISTORY_FILE.exists():
        return []
    
    # Get current week's date range (Monday to Sunday)
    # If it's Sunday, use current week. If past Sunday, use LAST week.
    today = datetime.now()
    
    # If today is Monday-Saturday, get THIS week's Monday
    # If today is Sunday, get THIS week's Monday (current week being completed)
    # This ensures we always capture Mon-Sun of the week being recapped
    if today.weekday() == 6:  # Sunday
        # Use THIS week's Monday (the week we're completing)
        monday = today - timedelta(days=6)
    else:
        # For any other day, calculate the most recent Monday
        monday = today - timedelta(days=today.weekday())
    
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Also calculate Sunday (end of the recap week)
    sunday = monday + timedelta(days=6)
    sunday = sunday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    week_posts = []
    
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Parse: tt1234567  # Title - 2026-02-02 09:20
            parts = line.split('#', 1)
            if len(parts) < 2:
                continue
            
            imdb_id = parts[0].strip()
            rest = parts[1].strip()
            
            # Extract title and date
            if ' - ' in rest:
                title_part, date_part = rest.rsplit(' - ', 1)
                title = title_part.strip()
                
                try:
                    # Parse date: 2026-02-02 09:20
                    post_date = datetime.strptime(date_part.strip(), '%Y-%m-%d %H:%M')
                    
                    # Check if this post is from the week being recapped (Mon-Sun inclusive)
                    if monday <= post_date <= sunday:
                        week_posts.append({
                            'imdb_id': imdb_id,
                            'title': title,
                            'date': post_date
                        })
                except:
                    continue
    
    return week_posts


def send_weekly_email_summary(week_posts):
    """Send email with this week's posts summary."""
    if not SMTP_EMAIL or not SMTP_PASSWORD or not NOTIFICATION_EMAIL:
        print("⚠️ Email not configured")
        return False
    
    if not week_posts:
        print("⚠️ No posts this week to summarize")
        return False
    
    week_num = datetime.now().isocalendar()[1]
    year = datetime.now().year
    recap_token = f"RECAP_W{week_num}_{year}"
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🌟 What's Up? Weekly Summary - {len(week_posts)} Posts"
        msg['From'] = SMTP_EMAIL
        msg['To'] = NOTIFICATION_EMAIL
        
        # Build post list
        posts_html = ""
        for idx, post in enumerate(week_posts, 1):
            date_str = post['date'].strftime('%A, %b %d at %I:%M %p')
            posts_html += f"""
            <li>
                <strong>{post['title']}</strong><br>
                <small>{date_str} • IMDb: {post['imdb_id']}</small>
            </li>
            """
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                h2 {{ color: #6366f1; }}
                ul {{ list-style-type: none; padding: 0; }}
                li {{ margin: 15px 0; padding: 10px; background: #f5f5f5; border-left: 3px solid #6366f1; }}
                .highlight {{ background: #fef3c7; padding: 15px; border-left: 4px solid #f59e0b; margin: 20px 0; }}
                .code {{ background: #1f2937; color: #10b981; padding: 3px 8px; border-radius: 4px; font-family: monospace; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; }}
            </style>
        </head>
        <body>
            <h2>🎬 What's Up? Weekly Summary</h2>
            <p>This week, we published <strong>{len(week_posts)} philosophical analyses</strong>:</p>
            <ul>
                {posts_html}
            </ul>
            
            <div class="highlight">
                <h3>🌟 Sunday Special - Weekly Recap Publishing Now</h3>
                <p><strong>Optional:</strong> Upload a custom hero image for this week's recap!</p>
                <p>If you'd like to add a beautiful hero image:</p>
                <ol>
                    <li>Upload an image to Telegram</li>
                    <li>Use this caption: <span class="code">{recap_token}</span></li>
                    <li>Requirements: Landscape image (1920px+ wide) representing the week's philosophical journey</li>
                </ol>
                <p><small>If no image is uploaded, the recap will publish without a custom hero image (perfectly fine!)</small></p>
            </div>
            
            <div class="footer">
                <p>The weekly journey post will weave together all {len(week_posts)} films into one philosophical narrative.</p>
                <p><em>This is an automated notification from What's Up? blog automation system.</em></p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html'))
        
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, NOTIFICATION_EMAIL, msg.as_string())
        
        print(f"✉️ Weekly summary email sent ({len(week_posts)} posts)")
        return True
    
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False


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
    Check if this is Sunday evening recap run.
    Sunday runs at 03:00 (notification only) and 14:00 UTC (recap generation).
    The 14:00 UTC run generates the weekly recap post.
    """
    now = datetime.utcnow()
    is_sunday = now.weekday() == 6  # 0=Monday, 6=Sunday
    is_recap_run_time = 13 <= now.hour <= 15  # 14:00 UTC window (with delay buffer)
    return is_sunday and is_recap_run_time


def select_items():
    """
    Select items for this run.
    
    Strategy:
    - First checks if items are queued from previous run
    - If queued: Use those (already image-validated)
    - If not: Randomly select 2 movies + 2 series, process 2, queue 2
    
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
    
    # Try to load queued items from previous run
    print("\n🔄 Checking for queued items from previous run...")
    queued_movie, queued_series = load_queued_items()
    
    if queued_movie and queued_series:
        print("   ✓ Found queued items (already image-validated)")
        movie = queued_movie
        series = queued_series
        print(f"   🎬 Movie: {movie['Title']} ({movie['Year']})")
        print(f"   📺 Series: {series['Title']} ({series['Year']})")
        # Select fresh next items for queue
        if not available_movies.empty:
            available_movies = available_movies[available_movies['Const'] != movie['Const']]
            if not available_movies.empty:
                next_movie = available_movies.iloc[random.randint(0, len(available_movies) - 1)].to_dict()
        if not available_series.empty:
            available_series = available_series[available_series['Const'] != series['Const']]
            if not available_series.empty:
                next_series = available_series.iloc[random.randint(0, len(available_series) - 1)].to_dict()
        return movie, series, next_movie, next_series
    else:
        print("   ℹ️ No queue found - selecting 4 new items (2 now, 2 next)")
    
    # For Sunday's 5th run, only pick 1 item (alternate weekly) - RANDOMLY
    if fifth_run:
        week_number = datetime.utcnow().isocalendar()[1]
        pick_movie = (week_number % 2 == 0)  # Even weeks: movie, Odd weeks: series
        
        if pick_movie and not available_movies.empty:
            random_idx = random.randint(0, len(available_movies) - 1)
            movie = available_movies.iloc[random_idx].to_dict()
            remaining = available_movies.drop(available_movies.index[random_idx])
            if not remaining.empty:
                next_movie = remaining.iloc[random.randint(0, len(remaining) - 1)].to_dict()
            print(f"🎬 Sunday Special (Movie - Random): {movie['Title']} ({movie['Year']})")
        elif not available_series.empty:
            random_idx = random.randint(0, len(available_series) - 1)
            series = available_series.iloc[random_idx].to_dict()
            remaining = available_series.drop(available_series.index[random_idx])
            if not remaining.empty:
                next_series = remaining.iloc[random.randint(0, len(remaining) - 1)].to_dict()
            print(f"📺 Sunday Special (Series - Random): {series['Title']} ({series['Year']})")
        elif not available_movies.empty:
            random_idx = random.randint(0, len(available_movies) - 1)
            movie = available_movies.iloc[random_idx].to_dict()
            remaining = available_movies.drop(available_movies.index[random_idx])
            if not remaining.empty:
                next_movie = remaining.iloc[random.randint(0, len(remaining) - 1)].to_dict()
            print(f"🎬 Sunday Special (Movie fallback - Random): {movie['Title']} ({movie['Year']})")
    else:
        # Normal run: pick both movie and series RANDOMLY
        if available_movies.empty:
            print("⚠️ No more movies to process!")
        else:
            # Random selection instead of sequential
            random_idx = random.randint(0, len(available_movies) - 1)
            movie = available_movies.iloc[random_idx].to_dict()
            # Get next movie (different from selected one)
            remaining_movies = available_movies.drop(available_movies.index[random_idx])
            if not remaining_movies.empty:
                next_movie = remaining_movies.iloc[random.randint(0, len(remaining_movies) - 1)].to_dict()
            print(f"🎬 Selected movie (random): {movie['Title']} ({movie['Year']})")
        
        if available_series.empty:
            print("⚠️ No more series to process!")
        else:
            # Random selection instead of sequential
            random_idx = random.randint(0, len(available_series) - 1)
            series = available_series.iloc[random_idx].to_dict()
            # Get next series (different from selected one)
            remaining_series = available_series.drop(available_series.index[random_idx])
            if not remaining_series.empty:
                next_series = remaining_series.iloc[random.randint(0, len(remaining_series) - 1)].to_dict()
            print(f"📺 Selected series (random): {series['Title']} ({series['Year']})")
    
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


def load_queued_items():
    """Load items queued from previous run."""
    queue_file = DATA_DIR / 'processing_queue.json'
    if not queue_file.exists():
        return None, None
    
    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
        return queue.get('movie'), queue.get('series')
    except Exception as e:
        print(f"   ⚠️ Error loading queue: {e}")
        return None, None


def save_queued_items(movie, series):
    """Save items for next run's processing."""
    queue_file = DATA_DIR / 'processing_queue.json'
    queue = {'movie': movie, 'series': series}
    
    with open(queue_file, 'w', encoding='utf-8') as f:
        json.dump(queue, f, indent=2)
    
    print(f"\n💾 Queued for next run:")
    if movie:
        print(f"   🎬 Movie: {movie['Title']} ({movie['Year']})")
    if series:
        print(f"   📺 Series: {series['Title']} ({series['Year']})")


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


def load_used_images():
    """Load the list of already used TMDB image file paths."""
    if not IMAGE_USAGE_FILE.exists():
        return set()
    
    try:
        with open(IMAGE_USAGE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(data.get('used_paths', []))
    except Exception as e:
        print(f"⚠️ Error loading image usage file: {e}")
        return set()


def save_used_image(file_path):
    """Mark a TMDB image file path as used."""
    IMAGE_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    used_images = load_used_images()
    used_images.add(file_path)
    
    try:
        with open(IMAGE_USAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'used_paths': list(used_images)}, f, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving image usage: {e}")


def download_and_process_images(tmdb_data, imdb_id):
    """Download hero image and optional body images, avoiding duplicates."""
    
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    
    images = []
    backdrops = tmdb_data.get('images', {}).get('backdrops', [])
    
    if not backdrops:
        print(f"⚠️ No backdrop images found for {imdb_id}")
        return None
    
    # Load previously used images to avoid duplicates
    used_images = load_used_images()
    print(f"   ℹ️ {len(used_images)} images already used in previous posts")
    
    # Filter out already used images
    available_backdrops = [b for b in backdrops if b['file_path'] not in used_images]
    
    if not available_backdrops:
        print(f"⚠️ All images for {imdb_id} have been used before! Using original list.")
        available_backdrops = backdrops
    else:
        print(f"   ✓ {len(available_backdrops)} unused images available")
    
    # SMART FILTERING: Prefer landscape scenes over posters
    # Filter by aspect ratio > 1.5 (widescreen scenes, not portrait posters)
    landscape_images = [b for b in available_backdrops if b.get('aspect_ratio', 0) > 1.5]
    
    # If we have landscape images, prefer those; otherwise use all available
    if landscape_images:
        available_backdrops = landscape_images
        print(f"   ✓ Filtered to {len(landscape_images)} landscape/widescreen images (no posters)")
    else:
        print(f"   ⚠️ No landscape images found, using all {len(available_backdrops)} images")
    
    # Further prefer images without text overlays (language-neutral)
    text_free_images = [b for b in available_backdrops if b.get('iso_639_1') is None]
    
    if text_free_images and len(text_free_images) >= 4:
        available_backdrops = text_free_images
        print(f"   ✓ Found {len(text_free_images)} text-free images (no language overlays)")
    
    # Sort by quality (vote_average * width)
    available_backdrops.sort(
        key=lambda x: x.get('vote_average', 0) * x.get('width', 0), 
        reverse=True
    )
    
    # Download hero image (best quality)
    hero = available_backdrops[0]
    hero_url = f"{TMDB_IMAGE_BASE}original{hero['file_path']}"
    
    print(f"📸 Downloading hero image (landscape scene, aspect: {hero.get('aspect_ratio', 'N/A'):.2f})...")
    hero_data = download_image(hero_url)
    
    if hero_data:
        hero_path = IMAGES_DIR / f"{imdb_id}_hero.webp"
        if process_and_save_image(hero_data, hero_path, HERO_MAX_SIZE_KB, HERO_TARGET_WIDTH):
            images.append(('hero', str(hero_path.relative_to(ROOT_DIR))))
            # Mark this image as used
            save_used_image(hero['file_path'])
            print(f"   ✓ Marked hero image as used: {hero['file_path']}")
    
    # Download up to 3 additional body images with SCATTERED selection for diversity
    # CRITICAL: Never reuse the hero image (index 0) in body images
    # Instead of [1,2,3], use scattered indices like [2, 6, 11] for more variety
    body_indices = []
    if len(available_backdrops) > 12:
        # If we have many images, pick widely scattered ones (skip hero at index 0)
        body_indices = [2, 6, 11]
    elif len(available_backdrops) > 6:
        # Medium amount, use moderate spacing
        body_indices = [2, 4, 6]
    else:
        # Few images, sequential but SKIP index 0 (hero)
        body_indices = [1, 2, 3]
    
    # Ensure indices are within bounds and NEVER include 0 (hero image)
    body_indices = [idx for idx in body_indices if idx < len(available_backdrops) and idx != 0]
    
    for i, idx in enumerate(body_indices, 1):
        backdrop = available_backdrops[idx]
        img_url = f"{TMDB_IMAGE_BASE}w1280{backdrop['file_path']}"
        
        print(f"📸 Downloading body image {i} (NEW, not used before)...")
        img_data = download_image(img_url, timeout=30)
        
        if img_data:
            img_path = IMAGES_DIR / f"{imdb_id}_{i}.webp"
            if process_and_save_image(img_data, img_path, BODY_MAX_SIZE_KB, BODY_TARGET_WIDTH):
                images.append((f'body_{i}', str(img_path.relative_to(ROOT_DIR))))
                # Mark this image as used
                save_used_image(backdrop['file_path'])
                print(f"   ✓ Marked body image {i} as used: {backdrop['file_path']}")
    
    return images if images else None


# ==================== TELEGRAM INTEGRATION ====================

def send_telegram_photo_request(message):
    """Send a Telegram message requesting photo upload and wait for response."""
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
        print("📱 Telegram photo request sent")
        return True
    except requests.RequestException as e:
        print(f"❌ Telegram error: {e}")
        return False


def wait_for_telegram_photo(timeout_minutes=30):
    """Wait for user to upload a photo via Telegram. Poll for updates."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured")
        return None, None
    
    print(f"⏳ Waiting up to {timeout_minutes} minutes for photo upload...")
    
    # Get current update ID to only check new messages
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        response = requests.get(url, timeout=10)
        updates = response.json().get('result', [])
        offset = updates[-1]['update_id'] + 1 if updates else 0
    except:
        offset = 0
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    while (time.time() - start_time) < timeout_seconds:
        try:
            # Poll for new updates
            response = requests.get(url, params={'offset': offset, 'timeout': 30}, timeout=35)
            data = response.json()
            
            if not data.get('ok'):
                continue
            
            updates = data.get('result', [])
            
            for update in updates:
                offset = update['update_id'] + 1
                message = update.get('message', {})
                photos = message.get('photo', [])
                
                if photos:
                    # Found a photo!
                    file_id = photos[-1]['file_id']  # Highest resolution
                    message_id = message['message_id']
                    
                    print(f"✅ Photo received! Downloading...")
                    
                    # Get file path
                    file_info_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
                    file_info = requests.get(file_info_url, params={'file_id': file_id}, timeout=10).json()
                    
                    file_path = file_info.get('result', {}).get('file_path')
                    if file_path:
                        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                        image_data = download_image(file_url)
                        
                        if image_data:
                            return image_data, message_id
            
            time.sleep(2)  # Poll every 2 seconds
        
        except Exception as e:
            print(f"⚠️ Polling error: {e}")
            time.sleep(5)
    
    print(f"⏱️ Timeout reached after {timeout_minutes} minutes")
    return None, None


def delete_telegram_message(message_id):
    """Delete a message from Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    delete_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
    try:
        response = requests.post(delete_url, json={
            'chat_id': TELEGRAM_CHAT_ID,
            'message_id': message_id
        }, timeout=10)
        response.raise_for_status()
        print("🗑️ Telegram message deleted")
        return True
    except Exception as e:
        print(f"⚠️ Failed to delete message: {e}")
        return False


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
        try:
            requests.post(delete_url, json={'chat_id': TELEGRAM_CHAT_ID, 'message_id': msg_id}, timeout=10)
        except Exception as e:
            print(f"⚠️ Failed to delete message {msg_id}: {e}")
    
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

def generate_weekly_recap_post(week_posts, hero_image_path):
    """Generate a beautiful weekly journey recap post with Gemini AI."""
    
    if not GENAI_AVAILABLE or not GEMINI_API_KEY:
        print("❌ Gemini AI not available")
        return None
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Build posts summary for prompt
    posts_summary = ""
    for idx, post in enumerate(week_posts, 1):
        date_str = post['date'].strftime('%A, %B %d')
        posts_summary += f"{idx}. **{post['title']}** ({date_str})\n"
    
    # Handle case where no hero image is provided
    image_section = ""
    hero_frontmatter = ""
    
    if hero_image_path:
        image_section = f"""
![This week's cinematic journey](/{hero_image_path}){{{{: .rounded-10 w-100 .shadow}}}}
_A visual reflection of the week's philosophical explorations_
"""
        hero_frontmatter = f"""image:
  path: /{hero_image_path}
  alt: "A cinematic representation of this week's philosophical journey"
"""
    else:
        hero_frontmatter = "# No hero image available"
    
    prompt = f"""
You are a masterful film philosopher crafting the ultimate weekly synthesis for "What's Up?" - 
a sophisticated platform exploring cinema's deeper meanings.

This week, we published {len(week_posts)} philosophical analyses:

{posts_summary}

Your task: Create a **STUNNING, BEAUTIFULLY FORMATTED weekly journey post** that weaves these films/series into ONE cohesive philosophical narrative.

CRITICAL REQUIREMENTS:

1. **Title**: Create a poetic, evocative title that captures the week's theme
   Example: "Echoes of Eternity: A Week Through Time, Memory, and Becoming"

2. **Find the Thread**: Identify the common philosophical themes across all {len(week_posts)} works
   - What existential questions connect them?
   - What human truths do they all explore?
   - How do they dialogue with each other?

3. **Structure** (1500-2000 words):
   
   **Opening** (3-4 paragraphs):
   - Start with a POWERFUL opening quote from a famous philosopher (Nietzsche, Camus, Sartre, Plato, etc.) with {{{{: .prompt-tip }}}}
   - Second paragraph: Introduce the week's thematic journey with ***magnificent prose***
   - Third paragraph: Establish the philosophical context
   - Fourth paragraph: Preview how the films connect
   
   **Section 1: The Philosophical Thread** (##) (4-5 paragraphs):
   - Reveal the connecting theme with rich, evocative language
   - Use a quote from a philosopher or film theorist (with {{{{: .prompt-info }}}})
   - Reference 3-4 films to establish the pattern
   - Use **bold** for key philosophical concepts
   - Use *italics* for all film titles
   
   {image_section if hero_image_path else ""}
   
   **Section 2: The Journey Through Cinema** (##) (Comprehensive):
   - Create a beautiful narrative weaving through ALL {len(week_posts)} works
   - For each film/series:
     - **Bold title** followed by 2-3 sentences of philosophical insight
     - Connect each work to the overarching theme
     - Use *film titles in italics* when mentioning them
   - Group related films into sub-themes if natural patterns emerge
   - Include a profound quote (with {{{{: .prompt-info }}}}) in the middle of this section
   
   **Section 3: Deeper Waters - The Human Condition** (##) (5-6 paragraphs):
   - Profound philosophical analysis
   - Connect themes to universal human experiences
   - Use a powerful quote from an existentialist philosopher ({{{{: .prompt-warning }}}})
   - Explore paradoxes, contradictions, and tensions
   - Reference specific films as illustrations
   
   **Section 4: The Synthesis** (##) (3-4 paragraphs):
   - Bring all threads together
   - What ultimate truth emerged from this week's journey?
   - Use a final profound quote ({{{{: .prompt-danger }}}} or {{{{: .prompt-tip }}}})
   
   **Closing** (2 paragraphs):
   - Synthesize the week's wisdom
   - End with thought-provoking questions that invite reader reflection
   - Final blockquote with poetic reflection

4. **ABUNDANT QUOTES** - Include at LEAST 6-8 blockquotes throughout:
   - Philosophers: Nietzsche, Camus, Sartre, Kierkegaard, Heidegger, etc.
   - Film theorists: Bazin, Tarkovsky, Bergman, etc.
   - Literary figures: Kafka, Dostoevsky, Borges, etc.
   - Use these prompt styles for variety:
     * {{{{: .prompt-tip }}}} - for wisdom, insight, enlightenment
     * {{{{: .prompt-info }}}} - for key observations, patterns
     * {{{{: .prompt-warning }}}} - for darker themes, tensions
     * {{{{: .prompt-danger }}}} - for profound existential truths

5. **Visual Structure**:
   - Use **bold** generously for key philosophical concepts
   - Use ***bold italics*** for POWERFUL, striking statements
   - Use *italics* for ALL film titles without exception
   - Use bullet lists with - only when listing multiple related items
   - Use --- horizontal rules between major sections (at least 3-4 total)
   - Embed blockquotes liberally throughout

6. **Mood Tags**: Select 3 from [Cerebral, Melancholy, Hopeful, Intense, Nostalgic, 
   Existential, Romantic, Heroic, Dystopian, Surreal, Profound, Transcendent]

7. **Description**: Compelling meta description (150-160 chars) about the week's philosophical journey

OUTPUT FORMAT:

---
title: "Your Poetic Weekly Title Here - Make it BEAUTIFUL"
date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S +0530')}
categories: [Weekly Recap, Philosophical]
tags: [mood1, mood2, mood3]
{hero_frontmatter}
description: "Compelling meta description capturing the week's essence"
---

> "A profound, carefully selected quote from a famous philosopher that perfectly captures this week's journey" — Philosopher Name
{{{{: .prompt-tip }}}}

[Opening paragraph with ***magnificent, poetic prose*** that immediately draws the reader in...]

[Second paragraph establishing philosophical context...]

[Third paragraph previewing the journey ahead...]

This week, we embarked on a cinematic odyssey through **{len(week_posts)} remarkable works**, each offering a unique lens through which to view [the connecting theme]. From *[first film]* to *[last film]*, a pattern emerged—a **philosophical tapestry** woven with threads of [theme], [theme], and ultimately, [ultimate theme].

## The Philosophical Thread

[Rich, evocative exploration of the common theme. Use sophisticated language, philosophical terminology...]

> "Another carefully chosen quote that deepens our understanding of the theme" — Philosopher
{{{{: .prompt-info }}}}

[Continue exploring with detailed film examples. Be specific, be profound...]

{image_section if hero_image_path else ""}

## The Journey Through Cinema

[Beautiful narrative introduction to the week's journey...]

**[Film 1 Title]**: [2-3 sentences of philosophical insight connecting to the theme. Use rich language...]

**[Film 2 Title]**: [How this work deepens or challenges the established theme...]

**[Film 3 Title]**: [Its unique perspective on the central question...]

[Continue for ALL {len(week_posts)} works with equal attention and depth...]

> "A mid-section quote that ties these works together" — Film Theorist or Philosopher
{{{{: .prompt-info }}}}

Each work added its voice to a growing chorus, building toward a profound realization about **[the ultimate theme]**.

---

## Deeper Waters: The Human Condition

[Deep, sophisticated philosophical analysis. Connect to real human experiences with nuance...]

[Explore paradoxes, tensions, contradictions that emerged from the week's viewing...]

> "A darker, more challenging quote about the human condition" — Existentialist Philosopher
{{{{: .prompt-warning }}}}

[Continue with rich, layered analysis referencing specific films...]

---

## The Synthesis

[Bring all threads together. What ultimate truth emerged? Be profound, be specific...]

> "A final, powerful quote that captures the synthesis" — Philosopher
{{{{: .prompt-danger }}}}

[Conclude the synthesis with elegant prose...]

---

What patterns do you notice emerging in your own life's narrative? How do these {len(week_posts)} stories mirror your journey through **[theme]** and **[theme]**? Which film resonated most deeply with your current existential state?

> "A poetic, reflective closing thought that lingers" — Philosopher or Poet
{{{{: .prompt-tip }}}}

"""
    
    print(f"🤖 Generating weekly recap with Gemini (retry with backoff)...")
    
    # Retry logic for API errors
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8,
                    top_p=0.95,
                    max_output_tokens=8192,
                )
            )
            
            content = response.text
            print(f"✅ Weekly recap content generated ({len(content)} chars)")
            return content
            
        except Exception as e:
            print(f"❌ Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"❌ All retries exhausted for weekly recap generation")
                return None


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
    
    # ALWAYS encourage web search for reviews and balanced perspective
    web_search_instruction = f"""

🌐 **CRITICAL: WEB SEARCH REQUIRED FOR AUTHENTIC REVIEWS**

Before writing, you MUST search the web for:
1. **Real critic reviews** from Rotten Tomatoes, Metacritic, IMDb user reviews
2. **Audience reactions** - both positive AND negative feedback
3. **Common criticisms** - what did people dislike or find problematic?
4. **Controversial aspects** - pacing issues, plot holes, performances, etc.

{'5. Plot details and themes (no plot data in database)' if not plot else ''}

⚠️ **BALANCE IS MANDATORY**:
- If critics panned it (low scores), your analysis MUST reflect that
- Include specific criticisms you find (e.g., "Critics noted the uneven pacing...")
- Don't be overly positive for poorly-received content
- Be honest about flaws while still finding philosophical value
- Write like a real human critic who has mixed feelings, not a PR piece

💡 **Examples of balanced writing**:
- "While the series stumbled with its CGI and uneven tone, it raises interesting questions about..."
- "Despite a convoluted plot that left many viewers confused, the film's exploration of... remains compelling"
- "Critics were divided—some found it groundbreaking, others called it pretentious—but undeniably it forces us to confront..."

Remember: Even flawed art can provoke philosophical reflection. Be honest about weaknesses while exploring deeper meanings.
    """
    
    imdb_id = imdb_data['Const']
    title = imdb_data['Title']
    year = imdb_data.get('Year', 'Unknown')
    genres = imdb_data.get('Genres', 'Drama')
    directors = imdb_data.get('Directors', 'Unknown')
    
    # Additional CSV data for richer context
    runtime = imdb_data.get('Runtime (mins)', 'N/A')
    release_date = imdb_data.get('Release Date', 'N/A')
    original_title = imdb_data.get('Original Title', title)
    imdb_url = imdb_data.get('URL', f'https://www.imdb.com/title/{imdb_id}/')
    
    # Determine image paths
    hero_image = f"/assets/img/posts/{imdb_id}_hero.webp" if has_images else ""
    body_images = []
    if has_images and image_count > 1:
        for i in range(1, min(image_count, 4)):  # Max 3 body images
            body_images.append(f"/assets/img/posts/{imdb_id}_{i}.webp")
    
    # Build image instructions - use PLACEHOLDERS that we'll replace with code
    image_instructions = ""
    if body_images:
        image_instructions = f"""
IMPORTANT - EMBED IMAGE PLACEHOLDERS in your content:
- Use [IMAGE_1] for the first body image (place between sections)
{"- Use [IMAGE_2] for the second body image" if len(body_images) > 1 else ""}
{"- Use [IMAGE_3] for the third body image" if len(body_images) > 2 else ""}

Place these placeholders strategically between sections to break up text.
DO NOT write the actual markdown syntax - just use the placeholder tags like [IMAGE_1].
We will automatically convert them to properly formatted images after generation.
"""
    
    # Build prompt with enriched CSV data
    prompt = f"""
You are a thoughtful film philosopher and cultural critic writing for "What's Up?" - 
a sophisticated platform that explores deeper meaning behind cinema.

🎭 **YOUR VOICE**: Write like a REAL HUMAN CRITIC with nuanced opinions, not a marketing bot.
- Have mixed feelings when appropriate
- Acknowledge flaws and criticism from real reviews
- Be honest but still find philosophical depth
- Sound natural and conversational, not overly formal
- Use contractions, varied sentence length, personal observations

Write a beautifully formatted philosophical blog post about:

=== CORE METADATA (FROM IMDb CSV EXPORT) ===
TITLE: {title} ({year})
ORIGINAL TITLE: {original_title}
TYPE: {'Movie' if media_type == 'movie' else 'TV Series'}
GENRES: {genres}
DIRECTOR: {directors}
RUNTIME: {runtime} minutes
RELEASE DATE: {release_date}
IMDB URL: {imdb_url}

=== TMDB DATA (IF AVAILABLE) ===
CAST: {', '.join(cast) if cast else 'Not available'}
PLOT OVERVIEW: {plot if plot else 'Not available - see web search instructions below'}
{web_search_instruction}

NOTE: You have rich metadata above. Use the IMDb URL, title, year, and other details to perform 
accurate web searches. Check Rotten Tomatoes, Metacritic, IMDb reviews, and critical reception.

🖼️ **IMAGE UNIQUENESS GUARANTEE**: 
The images provided for this post are UNIQUE and have NEVER been used in any previous post.
Our system tracks all used images across the entire blog to ensure each post has fresh, never-before-seen visuals.
This maintains visual diversity and prevents reader fatigue from seeing the same imagery repeatedly.

{image_instructions}

FORMATTING REQUIREMENTS (VERY IMPORTANT):
1. Write 800-1200 words of philosophical analysis
2. Use RICH MARKDOWN formatting throughout - make it visually stunning:

   TEXT FORMATTING:
   - **bold** for key philosophical concepts
   - *italics* for film titles, foreign terms, and emphasis
   - ***bold italics*** for powerful statements
   
   BLOCKQUOTES (use these prompt styles for variety):
   - Opening quote: > "Quote" followed by newline and {{: .prompt-tip }}
   - Key insight: > Important insight... followed by newline and {{: .prompt-info }}
   - Warning/dark theme: > Dark observation... followed by newline and {{: .prompt-warning }}
   - Profound realization: > Existential truth... followed by newline and {{: .prompt-danger }}
   
   STRUCTURE ELEMENTS:
   - ## Section Headers (use 3-4 compelling section titles)
   - --- horizontal rules between major sections
   - Bullet lists with - for listing themes or concepts
   - Numbered lists with 1. 2. 3. for sequences or steps
   
   IMAGES (embed between sections):
   - Use: ![Description](path){{: .rounded-10 w-75 .shadow}}
   - Add _italic caption below image_
   
3. STRUCTURE your post like this:
   - Opening: A philosophical quote with {{: .prompt-tip }}
   - First paragraph: Hook with honest assessment + elegant prose (mention reception if relevant)
   - Section 1 (##): The core philosophical theme (acknowledge any flaws/criticism first, then explore depth)
   {"- [IMAGE 1 with caption]" if body_images else ""}
   - Section 2 (##): What works vs. what doesn't - balanced analysis with specific examples from reviews
   - Use a {{: .prompt-info }} blockquote for a key insight
   {"- [IMAGE 2 with caption]" if len(body_images) > 1 else ""}
   - Section 3 (##): Despite flaws, the deeper questions it raises (metaphysical/existential exploration)
   {"- [IMAGE 3 with caption]" if len(body_images) > 2 else ""}
   - Closing section with {{: .prompt-warning }} - acknowledge mixed legacy but philosophical value
   - Final thought-provoking question or statement
   {"" if body_images else "- NOTE: No body images available. Do NOT include any image markdown."}  
   
   **CRITICAL**: Reference actual critical reception. If reviews were poor, SAY SO explicitly.
   Examples: "Despite its 32% Rotten Tomatoes score...", "Critics lambasted the pacing, and rightfully so...",
   "While audiences were divided...", "The film's weaknesses are undeniable, particularly..."

4. Explore existential, metaphysical, or ethical themes - go beyond plot summaries
5. Connect the work to broader human experiences and philosophical questions  
6. Use elegant but NATURAL prose - avoid over-the-top flowery language that sounds fake
   - Mix short punchy sentences with longer reflective ones
   - Use contractions naturally ("it's", "doesn't", "won't")
   - Sound like a smart friend analyzing a film, not a stuffy academic
   
🎯 **ORIGINALITY MANDATE - ZERO REPETITION**:
   - ❌ NEVER use these overused phrases:
     * "This is where we discover the true weight of choice — not in the outcome, but in the becoming"
     * "The hero's journey isn't just about what they achieve, but..."
     * "This isn't just a film; it's..."
     * "What does it mean to be..."
   - ✅ Create FRESH, ORIGINAL observations for each post
   - ✅ Vary your sentence structures and philosophical angles
   - ✅ Make each post feel unique and spontaneous, not templated
   - ✅ Use different philosophical frameworks (existentialism, stoicism, nihilism, etc.)
7. {"Include the streaming section at the end" if streaming_providers else "Do NOT include a streaming section"}
8. Assign exactly 3 mood tags from: [Cerebral, Melancholy, Hopeful, Intense, Nostalgic, 
   Existential, Romantic, Heroic, Dystopian, Surreal, Flawed, Divisive, Controversial]

🚨 CRITICAL FRONTMATTER FORMATTING RULES 🚨
The 'title' and 'description' fields in frontmatter MUST be plain text only - NO markdown formatting allowed!
- ❌ NEVER use *italics*, **bold**, or ***bold italics*** in title or description fields
- ❌ NO asterisks (*), underscores (_), or backticks (`) in title or description
- ✅ Use plain text only, with proper punctuation and capitalization
- ✅ Reference film titles without any markdown formatting in these fields
- ✅ Example: "Exploring Inception's dream logic" NOT "Exploring *Inception's* dream logic"

OUTPUT FORMAT (Jekyll Frontmatter + Markdown):

---
title: "Your Philosophical Title Here - Be Creative and Evocative (Plain Text Only)"
date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S +0530')}
categories: [Philosophical, {genres.split(',')[0].strip() if genres else 'Drama'}]
tags: [mood1, mood2, mood3]
{"image:" if has_images else "# No image available"}
{f"  path: {hero_image}" if has_images else ""}
{f'  alt: "Evocative description of the scene"' if has_images else ""}
description: "Compelling meta description with NO asterisks or markdown - plain text only (150-160 chars)"
---

> "A profound opening quote that captures the essence of the work" — Philosopher or Character
{{: .prompt-tip }}

[Opening paragraph with ***powerful prose*** that hooks the reader into the philosophical journey...]

## The Philosophical Core

[Rich content exploring the **central theme** with depth and nuance. Use *film title* in italics. Connect to broader philosophical ideas...]

Key themes to explore:
- **Theme one** — its significance
- **Theme two** — its implications  
- **Theme three** — its resonance

{"![A compelling scene from " + title + "](" + body_images[0] + "){: .rounded-10 w-75 .shadow}" if body_images else ""}
{"_A thoughtful caption describing the scene's deeper meaning_" if body_images else ""}

## The Human Condition

[Explore character psychology, moral dilemmas, and ethical questions...]

> This is where we discover the true weight of choice — not in the outcome, but in the *becoming*.
{{: .prompt-info }}

[Continue with analysis of how characters embody philosophical concepts...]

{"![Another powerful moment](" + body_images[1] + "){: .rounded-10 w-75 .shadow}" if len(body_images) > 1 else ""}
{"_Visual poetry captured in a single frame_" if len(body_images) > 1 else ""}

## Beyond the Surface

[Deeper existential, metaphysical themes. What questions does this work dare to ask?]

{"![The visual metaphor](" + body_images[2] + "){: .rounded-10 w-75 .shadow}" if len(body_images) > 2 else ""}
{"_The imagery speaks what words cannot express_" if len(body_images) > 2 else ""}

---

> "A haunting closing thought that lingers with the reader long after..." — Source
{{: .prompt-warning }}

[Final reflection — what does this work ultimately ask of us? What mirror does it hold up to our existence?]

{"## Where to Watch" if streaming_providers else ""}
{streaming_section if streaming_section else ""}

---

*What's Up? explores the philosophical depths of cinema.*
"""
    
    max_retries = 3
    retry_delay = 10  # seconds
    
    for attempt in range(max_retries):
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
            error_msg = str(e)
            print(f"⚠️ Gemini API error (attempt {attempt + 1}/{max_retries}): {error_msg}")
            
            # Check if it's a retryable error (503, 429, overloaded)
            if any(code in error_msg for code in ['503', '429', 'overloaded', 'UNAVAILABLE', 'quota']):
                if attempt < max_retries - 1:
                    print(f"   ⏳ Waiting {retry_delay}s before retry...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
            
            print(f"❌ Gemini API error: {e}")
            return None
    
    print(f"❌ All {max_retries} attempts failed")
    return None


# ==================== METADATA TRACKING ====================

def insert_images_into_content(content, imdb_id, body_images, title):
    """Replace image placeholders with actual markdown image syntax.
    
    Replaces [IMAGE_1], [IMAGE_2], [IMAGE_3] with properly formatted markdown.
    This ensures exact paths are used, not AI-generated paths that could be wrong.
    """
    if not body_images:
        return content
    
    # Replace each placeholder with actual markdown
    for i, img_path in enumerate(body_images, 1):
        placeholder = f"[IMAGE_{i}]"
        # Create proper markdown with exact path
        markdown = f"![Scene from {title}]({img_path}){{{{: .rounded-10 w-75 .shadow}}}}"
        content = content.replace(placeholder, markdown)
        print(f"   ✓ Replaced {placeholder} with {img_path}")
    
    return content


def sanitize_title_in_content(content):
    """Remove markdown formatting from the title field in frontmatter.
    
    Strips *, **, ***, _, __, ___, ` from the title line to ensure
    clean rendering in HTML <title> tags, social media, and navigation.
    """
    # Match the title line in YAML frontmatter
    title_pattern = r'(title:\s*["\']?)([^"\'\n]+)(["\']?)'
    
    def clean_title(match):
        prefix = match.group(1)  # 'title: "' or 'title: '
        title_text = match.group(2)  # The actual title
        suffix = match.group(3)  # '"' or ''
        
        # Remove markdown formatting characters
        # Remove ***text*** (bold+italic)
        cleaned = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', title_text)
        # Remove **text** (bold)
        cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
        # Remove *text* (italic)
        cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
        # Remove ___text___ (bold+italic underscore)
        cleaned = re.sub(r'___([^_]+)___', r'\1', cleaned)
        # Remove __text__ (bold underscore)
        cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)
        # Remove _text_ (italic underscore)
        cleaned = re.sub(r'_([^_]+)_', r'\1', cleaned)
        # Remove `code` backticks
        cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
        
        return f"{prefix}{cleaned}{suffix}"
    
    # Apply the cleaning function
    sanitized = re.sub(title_pattern, clean_title, content)
    
    return sanitized


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

def process_sunday_special():
    """Process the Sunday special weekly recap post."""
    
    print(f"\n{'='*60}")
    print(f"🌟 PROCESSING SUNDAY SPECIAL - WEEKLY RECAP")
    print(f"{'='*60}")
    
    # Step 1: Get this week's posts from history
    week_posts = get_week_posts_from_history()
    
    if not week_posts:
        print("⚠️ No posts found for this week. Cannot create recap.")
        return False
    
    if len(week_posts) < 3:
        print(f"⚠️ Only {len(week_posts)} posts this week (need 3+ for meaningful recap)")
        print("   Skipping recap generation this week.")
        return False
    
    print(f"📊 Found {len(week_posts)} posts from this week")
    for post in week_posts:
        print(f"   - {post['title']}")
    
    # Step 2: Send email summary to user
    print("\n📧 Sending weekly summary email...")
    send_weekly_email_summary(week_posts)
    
    # Step 3: Check Telegram for manually uploaded hero image
    week_num = datetime.now().isocalendar()[1]
    year = datetime.now().year
    recap_token = f"RECAP_W{week_num}_{year}"
    
    print(f"\n🔍 Checking Telegram for manual hero image upload (token: {recap_token})...")
    
    # Check if user already uploaded an image with the recap token
    telegram_images = {}
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        try:
            response = requests.get(url, timeout=30)
            updates = response.json().get('result', [])
            
            for update in updates:
                message = update.get('message', {})
                caption = message.get('caption', '')
                
                if recap_token in caption.upper():
                    photos = message.get('photo', [])
                    if photos:
                        file_id = photos[-1]['file_id']
                        
                        # Get file and download
                        file_info_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
                        file_info = requests.get(file_info_url, params={'file_id': file_id}, timeout=10).json()
                        file_path = file_info.get('result', {}).get('file_path')
                        
                        if file_path:
                            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                            image_data = download_image(file_url)
                            if image_data:
                                telegram_images['hero'] = image_data
                                print(f"✅ Found manually uploaded hero image!")
                                
                                # Delete the message
                                delete_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
                                requests.post(delete_url, json={
                                    'chat_id': TELEGRAM_CHAT_ID,
                                    'message_id': message['message_id']
                                }, timeout=10)
                                break
        except Exception as e:
            print(f"⚠️ Telegram check error: {e}")
    
    # Step 4: If no manual upload, send notification for next time
    if not telegram_images:
        print("⚠️ No hero image found via Telegram")
        print("   Sending notification for future Sunday specials...")
        
        telegram_msg = f"""
🌟 **SUNDAY SPECIAL - Image Notification**

This week's recap ({len(week_posts)} posts) was published without a custom hero image.

📸 **For next week's recap**, upload a hero image with this caption:
`{recap_token}`

Requirements:
- Landscape/widescreen image (1920px+ wide)
- Should represent the week's philosophical journey
- Upload anytime before next Sunday

_The system will auto-detect and use it for the recap post._
"""
        send_telegram_message(telegram_msg)
    
    # Step 5: Process hero image if available
    hero_image_relative = None
    
    if telegram_images and 'hero' in telegram_images:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        
        hero_filename = f"week{week_num}_{year}_recap_hero.webp"
        hero_path = IMAGES_DIR / hero_filename
        
        print(f"📸 Processing hero image...")
        if process_and_save_image(telegram_images['hero'], hero_path, HERO_MAX_SIZE_KB, HERO_TARGET_WIDTH):
            hero_image_relative = str(hero_path.relative_to(ROOT_DIR))
            print(f"✅ Hero image saved: {hero_filename}")
        else:
            print("⚠️ Failed to process hero image - continuing without it")
    
    # Step 6: Generate the weekly recap content with Gemini
    print("\n🤖 Generating weekly recap content with Gemini AI...")
    
    content = generate_weekly_recap_post(week_posts, hero_image_relative)
    
    if not content:
        print("❌ Failed to generate weekly recap content")
        return False
    
    # Step 7: Save the blog post
    print("\n💾 Saving weekly recap post...")
    
    # Generate filename
    week_start = datetime.now() - timedelta(days=datetime.now().weekday())
    date_str = week_start.strftime('%Y-%m-%d')
    clean_title = re.sub(r'[^\w\s-]', '', f"weekly-recap-week-{week_num}")
    clean_title = re.sub(r'[-\s]+', '-', clean_title).lower()
    
    post_filename = f"{date_str}-{clean_title}.md"
    post_path = POSTS_DIR / post_filename
    
    with open(post_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Weekly recap post saved: {post_filename}")
    
    # Step 8: Add to history
    recap_title = f"Weekly Recap - Week {week_num}"
    save_to_history(f"recap_w{week_num}_{year}", recap_title)
    
    print("\n" + "="*60)
    print(f"🎉 Sunday special completed successfully!")
    print(f"   Post: {post_filename}")
    if hero_image_relative:
        print(f"   Image: {hero_filename}")
    else:
        print(f"   Image: None (notification sent for next week)")
    print("="*60)
    
    return True


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
    
    # Step 4.5: Insert actual image paths (replace placeholders)
    if has_images and image_count > 1:
        print("   ✓ Inserting images with correct paths...")
        # Extract body image paths from images list
        body_image_paths = []
        for img_type, img_path in images:
            if img_type.startswith('body_'):
                body_image_paths.append(f"/{img_path}")
        if body_image_paths:
            content = insert_images_into_content(content, imdb_id, body_image_paths, title)
    
    # Step 4.6: Sanitize title to remove any markdown formatting
    print("   ✓ Sanitizing title field...")
    content = sanitize_title_in_content(content)
    
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
    
    # Step 7: Remove from CSV to prevent re-selection
    remove_from_csv(imdb_id, media_type)
    
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


# ==================== SUNDAY NOTIFICATION ====================

def send_sunday_morning_notification():
    """Send Sunday morning notification for weekly recap - notification only, no post generation."""
    
    print(f"\n{'='*60}")
    print(f"🌅 SUNDAY MORNING - WEEKLY RECAP NOTIFICATION")
    print(f"{'='*60}")
    
    # Get this week's posts from history
    week_posts = get_week_posts_from_history()
    
    if not week_posts:
        print("⚠️ No posts found for this week. Skipping notification.")
        return False
    
    if len(week_posts) < 3:
        print(f"⚠️ Only {len(week_posts)} posts this week - notification skipped")
        return False
    
    print(f"📊 Found {len(week_posts)} posts from this week")
    
    week_num = datetime.now().isocalendar()[1]
    year = datetime.now().year
    recap_token = f"RECAP_W{week_num}_{year}"
    
    # Send email summary
    print("\n📧 Sending weekly summary email...")
    if SMTP_EMAIL and SMTP_PASSWORD and NOTIFICATION_EMAIL:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🌟 What's Up? Weekly Recap - Upload Image for Tonight!"
            msg['From'] = SMTP_EMAIL
            msg['To'] = NOTIFICATION_EMAIL
            
            posts_html = ""
            for idx, post in enumerate(week_posts, 1):
                date_str = post['date'].strftime('%A, %b %d at %I:%M %p')
                posts_html += f"""
                <li>
                    <strong>{post['title']}</strong><br>
                    <small>{date_str} • IMDb: {post['imdb_id']}</small>
                </li>
                """
            
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    h2 {{ color: #6366f1; }}
                    ul {{ list-style-type: none; padding: 0; }}
                    li {{ margin: 15px 0; padding: 10px; background: #f5f5f5; border-left: 3px solid #6366f1; }}
                    .highlight {{ background: #fef3c7; padding: 20px; border-left: 4px solid #f59e0b; margin: 20px 0; }}
                    .code {{ background: #1f2937; color: #10b981; padding: 5px 10px; border-radius: 4px; font-family: monospace; font-size: 16px; }}
                    .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; }}
                    .deadline {{ color: #dc2626; font-weight: bold; font-size: 18px; }}
                </style>
            </head>
            <body>
                <h2>🌟 Sunday Special - Weekly Recap Coming Tonight!</h2>
                <p>Good morning! Here's what we published this week:</p>
                <ul>
                    {posts_html}
                </ul>
                
                <div class="highlight">
                    <h3>📸 Upload Hero Image for Tonight's Recap!</h3>
                    <p><strong>Deadline:</strong> <span class="deadline">Before 7:30 PM IST today</span></p>
                    <p><strong>What to do:</strong></p>
                    <ol>
                        <li>Find a beautiful philosophical/cinematic image</li>
                        <li>Upload to Telegram bot</li>
                        <li>Caption: <span class="code">{recap_token}</span></li>
                        <li>Requirements: Landscape (1920px+ wide)</li>
                    </ol>
                    <p><strong>Tonight at 7:30 PM IST:</strong></p>
                    <ul>
                        <li>✅ Script will check Telegram for your image</li>
                        <li>✅ Generate beautiful weekly recap (synthesizing all {len(week_posts)} posts)</li>
                        <li>✅ Publish with your hero image</li>
                    </ul>
                    <p><small>💡 If you don't upload, recap will publish text-only (still beautiful!)</small></p>
                </div>
                
                <div class="footer">
                    <p>This week's recap will weave together all {len(week_posts)} analyses into one philosophical narrative.</p>
                    <p><em>Automation will resume at 7:30 PM IST for recap generation.</em></p>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html, 'html'))
            
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, NOTIFICATION_EMAIL, msg.as_string())
            
            print(f"✅ Email sent successfully")
        except Exception as e:
            print(f"❌ Email error: {e}")
    
    # Send Telegram notification
    print("\n📱 Sending Telegram notification...")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        telegram_msg = f"""
🌅 **GOOD MORNING! Sunday Special Today**

This week, we published **{len(week_posts)} philosophical analyses**.

🌟 **Tonight's Weekly Recap**
At 7:30 PM IST, the automation will:
✅ Check Telegram for your image
✅ Generate beautiful weekly synthesis  
✅ Publish the recap post

📸 **Want to add a hero image?**

Upload to Telegram **before 7:30 PM IST** with caption:
`{recap_token}`

Requirements:
• Landscape/widescreen (1920px+ wide)
• Represents the week's philosophical journey

⏰ **Deadline: 7:30 PM IST today**

_Skip it? No problem! Recap will publish text-only._
"""
        send_telegram_message(telegram_msg)
    
    print("\n" + "="*60)
    print(f"✅ Sunday morning notification sent!")
    print(f"   Recap will be generated tonight at 7:30 PM IST")
    print(f"   Token: {recap_token}")
    print("="*60)
    
    return True


# ==================== MAIN ENTRY POINT ====================

def main():
    """Main execution flow."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='What\'s Up? Blog Automation')
    parser.add_argument('--sunday-notification', action='store_true',
                       help='Send Sunday morning notification only (no post generation)')
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("🎬 What's Up? - Autonomous Philosophical Media Engine")
    print("="*60)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check if this is Sunday morning notification-only mode
    if args.sunday_notification:
        send_sunday_morning_notification()
        return
    
    # Validate environment
    print("\n📋 Validating environment...")
    validate_environment()
    validate_csv_files()
    
    # Backup CSV files
    print("\n📦 Creating CSV backups...")
    backup_csv_files()
    
    # Check if this is Sunday special run
    fifth_run = is_sunday_fifth_run()
    
    if fifth_run:
        # Process Sunday special weekly recap
        print("\n🌟 This is the Sunday Special run - creating weekly recap!")
        if process_sunday_special():
            print("\n✅ Sunday special completed successfully!")
        else:
            print("\n⚠️ Sunday special failed or timed out")
        return
    
    # Normal processing for regular runs
    # Select items to process
    print("\n📋 Selecting items to process...")
    
    try:
        movie, series, next_movie, next_series = select_items()
    except Exception as e:
        print(f"\n❌ Error selecting items: {e}")
        print("   Check your CSV files for corruption or formatting issues.")
        return
    
    if not movie and not series:
        print("\n❌ No items available to process!")
        print("   Check that your CSV files have unprocessed entries.")
        return
    
    # Pre-check next items (Early Warning System)
    all_have_images = pre_check_next_items(next_movie, next_series)
    
    # Save next items to queue if they passed image check
    if all_have_images and (next_movie or next_series):
        save_queued_items(next_movie, next_series)
    elif not all_have_images:
        print("   ⚠️ Next items failed image check - NOT queued")
    
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
