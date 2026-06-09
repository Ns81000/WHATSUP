#!/usr/bin/env python3
"""
Verify image health status after running the fixer
"""

import os
from pathlib import Path

# File Paths
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
IMAGES_DIR = ROOT_DIR / 'assets' / 'img' / 'posts'
POSTS_DIR = ROOT_DIR / '_posts'

# Unhealthy blogs list
UNHEALTHY_BLOGS = {
    'tt154333956', 'tt936222', 'tt12465618', 'tt0407251', 'tt2635622',
    'tt0255111', 'tt10062614', 'tt2978626', 'tt8590992', 'tt35064818',
    'tt2112124', 'tt2824852', 'tt4683366', 'tt8504014', 'tt4856322',
    'tt2461132', 'tt5325684', 'tt3142232', 'tt11816092', 'tt6264938',
    'tt0254481', 'tt1029231', 'tt10350922', 'tt14044212', 'tt10230426',
    'tt1562871', 'tt11854694', 'tt13899566', 'tt16350094', 'tt28489281',
    'tt0082934', 'tt7280786', 'tt8289480', 'tt6735754'
}

def verify_health():
    """Check if all previously unhealthy blogs are now healthy"""
    print("=" * 70)
    print("✅ IMAGE HEALTH VERIFICATION")
    print("=" * 70)
    
    now_healthy = 0
    still_unhealthy = 0
    unhealthy_details = []
    
    for imdb_id in sorted(UNHEALTHY_BLOGS):
        hero = IMAGES_DIR / f"{imdb_id}_hero.webp"
        img1 = IMAGES_DIR / f"{imdb_id}_1.webp"
        img2 = IMAGES_DIR / f"{imdb_id}_2.webp"
        img3 = IMAGES_DIR / f"{imdb_id}_3.webp"
        
        has_hero = hero.exists()
        has_1 = img1.exists()
        has_2 = img2.exists()
        has_3 = img3.exists()
        
        image_count = sum([has_hero, has_1, has_2, has_3])
        
        if has_hero and has_1 and has_2 and has_3:
            now_healthy += 1
            print(f"✅ {imdb_id} - 4/4 images")
        else:
            still_unhealthy += 1
            status = f"[Hero: {'✓' if has_hero else '✗'} | 1: {'✓' if has_1 else '✗'} | 2: {'✓' if has_2 else '✗'} | 3: {'✓' if has_3 else '✗'}]"
            print(f"❌ {imdb_id} - {image_count}/4 images {status}")
            unhealthy_details.append((imdb_id, image_count))
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✅ Now Healthy: {now_healthy}/34")
    print(f"❌ Still Unhealthy: {still_unhealthy}/34")
    
    if still_unhealthy > 0:
        print("\nStill unhealthy blogs (sorted by image count):")
        for imdb_id, count in sorted(unhealthy_details, key=lambda x: x[1]):
            print(f"   • {imdb_id} ({count}/4 images)")
    else:
        print("\n🎉 ALL BLOGS ARE NOW HEALTHY! 🎉")
    
    print("=" * 70)

if __name__ == '__main__':
    verify_health()
