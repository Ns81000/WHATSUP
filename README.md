<p align="center">
  <img src="https://img.shields.io/badge/🎬-What's%20Up%3F-ff6b6b?style=for-the-badge&labelColor=1a1a2e" alt="What's Up?"/>
</p>

<h1 align="center">🎬 What's Up?</h1>

<p align="center">
  <strong>Autonomous Philosophical Media Engine</strong><br>
  <em>AI-powered deep dives into the existential depths of cinema</em>
</p>

<p align="center">
  <a href="https://github.com/Ns81000/WHATSUP/actions/workflows/daily_post.yml">
    <img src="https://github.com/Ns81000/WHATSUP/actions/workflows/daily_post.yml/badge.svg" alt="Daily Posts"/>
  </a>
  <a href="https://github.com/Ns81000/WHATSUP/actions/workflows/pages-deploy.yml">
    <img src="https://github.com/Ns81000/WHATSUP/actions/workflows/pages-deploy.yml/badge.svg" alt="Deploy"/>
  </a>
  <a href="https://ns81000.github.io/WHATSUP">
    <img src="https://img.shields.io/badge/Live%20Site-GitHub%20Pages-blue?style=flat-square" alt="Live Site"/>
  </a>
  <img src="https://img.shields.io/badge/Posts%2FDay-4--5-green?style=flat-square" alt="Posts per day"/>
  <img src="https://img.shields.io/badge/Powered%20By-Gemini%20AI-4285F4?style=flat-square" alt="Gemini AI"/>
</p>

<p align="center">
  <a href="#-what-is-this">What is this?</a> •
  <a href="#-how-it-works">How it Works</a> •
  <a href="#-features">Features</a> •
  <a href="#-tech-stack">Tech Stack</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-configuration">Configuration</a>
</p>

---

## 🤔 What is This?

**What's Up?** is a **fully autonomous blog** that generates philosophical movie and TV series analyses using AI. Unlike typical movie review sites that focus on ratings and plot summaries, this platform explores:

- 🧠 **Existential themes** — What does this film say about the human condition?
- 🔮 **Metaphysical questions** — How does it challenge our perception of reality?
- 💭 **Philosophical frameworks** — What schools of thought does it embody?
- ❤️ **Emotional resonance** — Why does this story move us?

> *"We don't just watch films. We explore the questions they dare to ask."*

---

## ⚙️ How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           🕐 GITHUB ACTIONS                                 │
│                    Triggers automatically 2-3 times daily                   │
│                                                                             │
│     Mon-Sat: 08:30 AM + 05:30 PM IST (4 posts)                            │
│     Sunday:  08:30 AM + 02:30 PM + 07:30 PM IST (5 posts)                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           🐍 PYTHON AUTOMATION                              │
│                                                                             │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                │
│   │  📋 READ     │    │  🎬 FETCH    │    │  🖼️ PROCESS  │                │
│   │  CSV Lists   │───▶│  TMDB Data   │───▶│  Images      │                │
│   │  (IMDb IDs)  │    │  (metadata)  │    │  (WebP)      │                │
│   └──────────────┘    └──────────────┘    └──────────────┘                │
│                                                  │                          │
│                                                  ▼                          │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                │
│   │  📝 CREATE   │    │  🤖 GENERATE │    │  🧠 ANALYZE  │                │
│   │  Jekyll Post │◀───│  Content     │◀───│  with Gemini │                │
│   │  (.md file)  │    │  (markdown)  │    │  AI          │                │
│   └──────────────┘    └──────────────┘    └──────────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           🌐 GITHUB PAGES                                   │
│                                                                             │
│              Jekyll builds static HTML → Live website updated               │
│                    https://ns81000.github.io/WHATSUP                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Complete Flow

| Step | What Happens | Technology |
|------|--------------|------------|
| 1️⃣ | GitHub Actions triggers on schedule | Cron jobs (UTC) |
| 2️⃣ | Python script reads from IMDb CSV lists | Pandas |
| 3️⃣ | Fetches movie/series data from TMDB API | REST API |
| 4️⃣ | Downloads and optimizes images to WebP (<500KB) | Pillow |
| 5️⃣ | Gemini AI generates philosophical analysis | Google Gemini 2.5 Flash |
| 6️⃣ | Creates Jekyll markdown post with frontmatter | Python |
| 7️⃣ | Commits and pushes to repository | Git |
| 8️⃣ | Jekyll builds and deploys to GitHub Pages | GitHub Actions |

---

## ✨ Features

### 🤖 Fully Autonomous
Zero human intervention required. The system runs 24/7, generating fresh content every day.

### 📅 Smart Scheduling

| Day | Runs | Posts | Timing (IST) |
|-----|------|-------|--------------|
| Monday - Saturday | 2 | 4 posts | 08:30 AM, 05:30 PM |
| Sunday | 3 | 5 posts | 08:30 AM, 02:30 PM, 07:30 PM |

**Weekly output:** 29 posts (24 Mon-Sat + 5 Sunday)

### 🖼️ Intelligent Image Handling

```
TMDB API Available?
       │
       ├── YES → Download backdrop → Convert to WebP → Compress to <500KB
       │
       └── NO → Pre-check system alerts you 6 hours in advance
                      │
                      ├── Telegram Bot notification
                      └── Email notification (SMTP)
                              │
                              ▼
                      Upload manually → Next run processes it
```

### 🧠 AI-Powered Content

Each post includes:

| Section | Description |
|---------|-------------|
| **Opening Hook** | Philosophical quote or thought-provoking question |
| **Thematic Analysis** | Deep dive into existential/metaphysical themes |
| **Character Study** | Psychological examination of key characters |
| **Visual Storytelling** | Analysis of cinematography and symbolism |
| **The Question It Asks** | Core philosophical inquiry of the work |
| **Streaming Info** | Where to watch (via TMDB data) |

### 🏷️ Mood Categorization

Every post is tagged with a philosophical mood:

| Mood | Description | Example Films |
|------|-------------|---------------|
| 🧠 Cerebral | Intellectually challenging | Inception, Primer |
| 😢 Melancholy | Sad, wistful | Eternal Sunshine, Her |
| 🌅 Hopeful | Optimistic, uplifting | The Shawshank Redemption |
| ⚡ Intense | High tension, gripping | Whiplash, Uncut Gems |
| 🕰️ Nostalgic | Evokes longing | Cinema Paradiso |
| ❓ Existential | Questions existence | Blade Runner, 2001 |
| 💕 Romantic | Love-focused | Before Sunrise |
| 🦸 Heroic | Triumphant, inspiring | Rocky, Gladiator |
| 🌑 Dystopian | Dark future | The Matrix, Children of Men |
| 🌀 Surreal | Dreamlike, abstract | Mulholland Drive |

### 🔍 Pre-Check System

The system looks **ahead** at the next scheduled items:

```python
# Before processing current items, check if NEXT items have images
if not check_image_availability(next_movie):
    trigger_manual_fallback()  # Sends Telegram/Email alert
```

This gives you **6+ hours** to manually upload images before they're needed.

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | Jekyll + Chirpy Theme | Beautiful, responsive static site |
| **Hosting** | GitHub Pages | Free, fast, reliable hosting |
| **Automation** | GitHub Actions | Scheduled cron jobs |
| **Logic** | Python 3.11 | Core automation script |
| **AI** | Google Gemini 2.5 Flash | Content generation |
| **Media API** | TMDB API | Movie/series metadata & images |
| **Images** | Pillow + WebP | Image processing & optimization |
| **Data** | Pandas + CSV | IMDb list management |
| **Notifications** | Telegram Bot + SMTP | Manual fallback alerts |
| **Comments** | Giscus | GitHub-based discussions |
| **Search** | Pagefind | Static site search |

---

## 📁 Project Structure

```
WHATSUP/
│
├── 📂 .github/workflows/          # GitHub Actions
│   ├── daily_post.yml             # Main automation (4-5 posts/day)
│   └── pages-deploy.yml           # Jekyll build & deploy
│
├── 📂 _posts/                     # Generated blog posts (auto-populated)
│   ├── 2026-02-02-interstellar-beyond-the-stars.md
│   ├── 2026-02-02-breaking-bad-the-descent.md
│   └── ... (grows daily)
│
├── 📂 assets/
│   ├── 📂 img/
│   │   ├── 📂 posts/              # Post images (WebP, <500KB)
│   │   │   ├── tt0816692_hero.webp
│   │   │   └── ...
│   │   └── 📂 favicons/           # Site icons
│   └── 📂 css/                    # Stylesheets
│
├── 📂 data/                       # Automation data
│   ├── movies.csv                 # 572 movies (IMDb export)
│   ├── series.csv                 # 105 series (IMDb export)
│   ├── history.log                # Processed IMDb IDs
│   └── metadata_db.json           # Mood/theme tracking
│
├── 📂 scripts/                    # Python automation
│   ├── main.py                    # Master script (~900 lines)
│   └── requirements.txt           # Python dependencies
│
├── 📂 _tabs/                      # Navigation pages
│   ├── about.md                   # About page
│   ├── archives.md                # Post archives
│   ├── categories.md              # Category listing
│   └── tags.md                    # Tag listing
│
├── 📂 _data/                      # Jekyll data files
│   ├── authors.yml
│   ├── contact.yml
│   └── 📂 locales/                # Translations
│
├── 📂 _includes/                  # Jekyll partials
├── 📂 _layouts/                   # Page templates
├── 📂 _sass/                      # Stylesheets (SCSS)
│
├── _config.yml                    # Jekyll configuration
├── Gemfile                        # Ruby dependencies
├── index.html                     # Homepage
└── README.md                      # This file
```

---

## 🚀 Quick Start

### Prerequisites

- GitHub account
- API Keys:
  - [Google Gemini API](https://aistudio.google.com/) (free tier available)
  - [TMDB API](https://www.themoviedb.org/settings/api) (free)
- Optional:
  - Telegram Bot Token (for notifications)
  - Gmail App Password (for email alerts)

### Step 1: Fork or Clone

```bash
git clone https://github.com/Ns81000/WHATSUP.git
cd WHATSUP
```

### Step 2: Configure GitHub Secrets

Go to **Settings → Secrets and Variables → Actions → New repository secret**

| Secret | Required | How to Get |
|--------|----------|------------|
| `GEMINI_API_KEY` | ✅ Yes | [Google AI Studio](https://aistudio.google.com/) |
| `TMDB_API_KEY` | ✅ Yes | [TMDB Settings](https://www.themoviedb.org/settings/api) |
| `GH_PAT` | ✅ Yes | [GitHub Tokens](https://github.com/settings/tokens) (repo scope) |
| `TELEGRAM_BOT_TOKEN` | Optional | [@BotFather](https://t.me/botfather) |
| `TELEGRAM_CHAT_ID` | Optional | [@userinfobot](https://t.me/userinfobot) |
| `SMTP_EMAIL` | Optional | Your Gmail address |
| `SMTP_PASSWORD` | Optional | [Gmail App Password](https://myaccount.google.com/apppasswords) |
| `NOTIFICATION_EMAIL` | Optional | Where to receive alerts |

### Step 3: Add Your IMDb Lists

Export your IMDb watchlists as CSV and place in `data/`:

```
data/
├── movies.csv    # Your movie list
└── series.csv    # Your TV series list
```

**Required CSV columns:** `Const` (IMDb ID), `Title`, `Year`

### Step 4: Enable GitHub Pages

1. Go to **Settings → Pages**
2. Source: **GitHub Actions**
3. Save

### Step 5: Run Manually (Optional)

1. Go to **Actions → What's Up? Daily Post Automation**
2. Click **Run workflow**
3. Check **Skip random delay** for faster testing

---

## ⚙️ Configuration

### _config.yml (Key Settings)

```yaml
# Site Identity
title: "What's Up?"
tagline: Exploring the Philosophical Depths of Cinema
url: "https://ns81000.github.io"
baseurl: "/WHATSUP"

# Timezone
timezone: Asia/Kolkata

# Comments (Giscus)
comments:
  provider: giscus
  giscus:
    repo: Ns81000/WHATSUP
    repo_id: # Get from giscus.app
    category: Announcements
    category_id: # Get from giscus.app
```

### Schedule Customization

Edit `.github/workflows/daily_post.yml`:

```yaml
on:
  schedule:
    # Format: 'minute hour * * day-of-week'
    - cron: '0 3 * * *'   # Daily at 03:00 UTC (08:30 IST)
    - cron: '0 12 * * *'  # Daily at 12:00 UTC (05:30 IST)
    - cron: '0 9 * * 0'   # Sundays only at 09:00 UTC
    - cron: '0 14 * * 0'  # Sundays only at 14:00 UTC
```

---

## 📊 Data Sources

### Movies (572 titles)

The movie list includes carefully curated selections across:

| Category | Examples |
|----------|----------|
| 🎬 Auteur Cinema | Kubrick, Nolan, Tarantino, Villeneuve |
| 🦸 Superhero | MCU, DCEU, X-Men, Spider-Man |
| 🚀 Sci-Fi | Star Wars, Blade Runner, Dune |
| 🎭 Drama | Shawshank, Godfather, Schindler's List |
| 🇮🇳 Bollywood | Dangal, 3 Idiots, Lagaan |
| 🎨 Animation | Pixar, Ghibli, DreamWorks |
| 🌍 International | Parasite, Amélie, Pan's Labyrinth |

### TV Series (105 titles)

| Category | Examples |
|----------|----------|
| 📺 Prestige TV | Breaking Bad, The Wire, Mad Men |
| ⚔️ Fantasy | Game of Thrones, The Witcher |
| 🔬 Sci-Fi | Stranger Things, Black Mirror |
| 😂 Comedy | The Office, Brooklyn Nine-Nine |
| 🎭 Drama | Better Call Saul, Succession |
| 🦸 Superhero | The Boys, Daredevil |

---

## 🔧 Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| Workflow not running | Check if Actions are enabled in repo settings |
| No posts generated | Verify API keys are set correctly in Secrets |
| Images missing | TMDB may not have images; check Telegram for fallback |
| Build failing | Check Gemfile.lock and Ruby version compatibility |
| Posts not appearing | Wait for Jekyll build to complete (~2-3 mins) |

### Logs

Check workflow logs at **Actions → [Workflow Run] → generate-and-publish**

---

## 📄 License

This project uses the [MIT License](LICENSE).

The Jekyll theme [Chirpy](https://github.com/cotes2020/jekyll-theme-chirpy) is also MIT licensed.

---

## 🙏 Acknowledgments

| Resource | Purpose |
|----------|---------|
| [TMDB](https://www.themoviedb.org/) | Movie/series metadata and images |
| [Google Gemini](https://ai.google.dev/) | AI content generation |
| [Chirpy Theme](https://github.com/cotes2020/jekyll-theme-chirpy) | Beautiful Jekyll theme |
| [IMDb](https://www.imdb.com/) | Curated movie/series lists |
| [Giscus](https://giscus.app/) | GitHub-based comments |

---

<p align="center">
  <strong>What's Up?</strong> — <em>Exploring the philosophical depths of cinema</em> 🎬🧠
</p>

<p align="center">
  Made with ❤️ and 🤖
</p>
