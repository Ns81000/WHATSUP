#!/usr/bin/env python3
"""
Add missing 3rd images to blog posts
"""

from pathlib import Path

posts_dir = Path(r'C:\Users\Ns8pc\Music\WHATSUP\_posts')

# Mapping: post file -> IMDb ID
posts_to_update = {
    '2026-04-09-guilty-2020.md': 'tt10062614',
    '2026-02-28-special-ops.md': 'tt11854694',
    '2026-03-20-special-ops-1-5-the-himmat-story-2021.md': 'tt13899566',
    '2026-03-18-mr-mrs-smith-2024.md': 'tt14044212',
    '2026-03-21-the-boys-presents-diabolical-2022.md': 'tt16350094',
    '2026-02-25-the-freelancer.md': 'tt28489281',
    '2026-04-29-it-s-entertainment-2014.md': 'tt2978626',
    '2026-03-17-black-warrant-2025.md': 'tt35064818',
    '2026-02-09-halo-the-fall-of-reach.md': 'tt4856322',
    '2026-03-06-treadstone.md': 'tt8289480',
    '2026-04-09-paper-boy-2018.md': 'tt8590992',
}

for filename, imdb_id in posts_to_update.items():
    file_path = posts_dir / filename
    
    if not file_path.exists():
        print(f"✗ File not found: {filename}")
        continue
    
    # Read file
    content = file_path.read_text(encoding='utf-8')
    
    # Create image reference
    image_ref = f'\n![Scene from film](/assets/img/posts/{imdb_id}_3.webp){{{{ .rounded-10 w-75 .shadow }}}}\n_The depth of human experience captured in a single frame._\n'
    
    # Find the separator and closing line
    closing = '\n---\n\n*What\'s Up? explores the philosophical depths of cinema.*'
    
    if closing in content:
        # Insert image before closing
        new_content = content.replace(
            closing,
            image_ref + closing
        )
        
        # Write back
        file_path.write_text(new_content, encoding='utf-8')
        print(f"✓ Added image to: {filename}")
    else:
        print(f"⚠️ Could not find closing marker in: {filename}")

print("\n✅ Images added to all blog posts!")
