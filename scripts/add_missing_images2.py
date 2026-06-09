#!/usr/bin/env python3
"""
Add missing 3rd images to blog posts - flexible version
"""

from pathlib import Path

posts_dir = Path(r'C:\Users\Ns8pc\Music\WHATSUP\_posts')

# Mapping: post file -> IMDb ID
posts_to_update = {
    '2026-02-28-special-ops.md': 'tt11854694',
    '2026-02-25-the-freelancer.md': 'tt28489281',
    '2026-04-29-it-s-entertainment-2014.md': 'tt2978626',
    '2026-03-06-treadstone.md': 'tt8289480',
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
    
    # Try different closing formats
    closings = [
        '---\n*What\'s Up? explores the philosophical depths of cinema.*',
        '---\n\n*What\'s Up? explores the philosophical depths of cinema.*',
    ]
    
    updated = False
    for closing in closings:
        if closing in content:
            new_content = content.replace(
                closing,
                f'---{image_ref}*What\'s Up? explores the philosophical depths of cinema.*'
            )
            file_path.write_text(new_content, encoding='utf-8')
            print(f"✓ Added image to: {filename}")
            updated = True
            break
    
    if not updated:
        print(f"⚠️ Could not find closing marker in: {filename}")

print("\n✅ Remaining images added!")
