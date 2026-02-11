#!/usr/bin/env python3
"""
What's Up? - Automated Backup System
Compresses critical data directories and emails the backup archive.

Backed-up directories:
  - _posts/          (blog post markdown files)
  - assets/img/posts (post images)
  - data/            (CSVs, metadata, history)
  - Original/        (original CSV backups)

Features:
  - High compression (gzip level 9)
  - Auto-splits archive if >24MB (Gmail 25MB limit safety margin)
  - Sends backup as email attachment via SMTP
  - Detailed summary in email body
  - Timestamped archive names
"""

import os
import sys
import tarfile
import smtplib
import math
from pathlib import Path
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent

SMTP_EMAIL = os.getenv('SMTP_EMAIL')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL')

BACKUP_DIRS = [
    '_posts',
    os.path.join('assets', 'img', 'posts'),
    'data',
    'Original',
]

MAX_ATTACHMENT_BYTES = 24 * 1024 * 1024  # 24MB safety margin for Gmail's 25MB limit
TEMP_DIR = ROOT_DIR / '.backup_temp'


def validate_env():
    missing = []
    if not SMTP_EMAIL:
        missing.append('SMTP_EMAIL')
    if not SMTP_PASSWORD:
        missing.append('SMTP_PASSWORD')
    if not NOTIFICATION_EMAIL:
        missing.append('NOTIFICATION_EMAIL')

    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    print("✅ Backup environment validated")


def collect_stats():
    stats = {}
    total_files = 0
    total_bytes = 0

    for rel_dir in BACKUP_DIRS:
        dir_path = ROOT_DIR / rel_dir
        if not dir_path.exists():
            stats[rel_dir] = {'files': 0, 'bytes': 0, 'status': 'MISSING'}
            print(f"   ⚠️  {rel_dir}/ — directory not found, skipping")
            continue

        dir_files = 0
        dir_bytes = 0

        for f in dir_path.rglob('*'):
            if f.is_file():
                dir_files += 1
                dir_bytes += f.stat().st_size

        stats[rel_dir] = {'files': dir_files, 'bytes': dir_bytes, 'status': 'OK'}
        total_files += dir_files
        total_bytes += dir_bytes
        print(f"   📂 {rel_dir}/  →  {dir_files} files, {format_size(dir_bytes)}")

    stats['_total'] = {'files': total_files, 'bytes': total_bytes}
    return stats


def format_size(num_bytes):
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.2f} MB"


def create_archive():
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    archive_name = f"whatsup_backup_{timestamp}.tar.gz"
    archive_path = TEMP_DIR / archive_name

    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n📦 Creating archive: {archive_name}")
    print("   Compression: gzip level 9 (maximum)")

    with tarfile.open(archive_path, 'w:gz', compresslevel=9) as tar:
        for rel_dir in BACKUP_DIRS:
            dir_path = ROOT_DIR / rel_dir
            if dir_path.exists():
                tar.add(str(dir_path), arcname=rel_dir)
                print(f"   ✓ Added {rel_dir}/")
            else:
                print(f"   ⚠️ Skipped {rel_dir}/ (not found)")

    archive_size = archive_path.stat().st_size
    print(f"\n   Archive size: {format_size(archive_size)}")

    return archive_path, archive_size


def split_archive(archive_path, chunk_size=MAX_ATTACHMENT_BYTES):
    archive_size = archive_path.stat().st_size
    num_chunks = math.ceil(archive_size / chunk_size)

    if num_chunks <= 1:
        return [archive_path]

    print(f"\n✂️  Archive exceeds {format_size(MAX_ATTACHMENT_BYTES)} — splitting into {num_chunks} parts")

    chunks = []
    with open(archive_path, 'rb') as f:
        for i in range(num_chunks):
            chunk_path = archive_path.with_suffix(f'.part{i + 1:02d}')
            data = f.read(chunk_size)
            with open(chunk_path, 'wb') as chunk_file:
                chunk_file.write(data)
            chunks.append(chunk_path)
            print(f"   ✓ Part {i + 1}/{num_chunks}: {format_size(len(data))}")

    return chunks


def build_email_body(stats, archive_size, num_parts):
    timestamp = datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')

    rows = ""
    for rel_dir in BACKUP_DIRS:
        s = stats.get(rel_dir, {})
        status_icon = "✅" if s.get('status') == 'OK' else "⚠️"
        rows += f"""
        <tr>
            <td style="padding:8px 12px; border-bottom:1px solid #eee;">{status_icon} {rel_dir}/</td>
            <td style="padding:8px 12px; border-bottom:1px solid #eee; text-align:right;">{s.get('files', 0)}</td>
            <td style="padding:8px 12px; border-bottom:1px solid #eee; text-align:right;">{format_size(s.get('bytes', 0))}</td>
        </tr>"""

    total = stats.get('_total', {})
    split_note = ""
    if num_parts > 1:
        split_note = f"""
        <div style="background:#fef3c7; padding:12px 16px; border-left:4px solid #f59e0b; margin:16px 0; border-radius:4px;">
            <strong>⚠️ Split Archive:</strong> The backup was split into <strong>{num_parts} parts</strong> due to email size limits.
            To restore, concatenate all parts in order:<br>
            <code style="background:#1f2937; color:#10b981; padding:2px 6px; border-radius:3px;">
            cat whatsup_backup_*.part* > whatsup_backup.tar.gz
            </code>
        </div>"""

    html = f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height:1.6; color:#333; max-width:600px; margin:0 auto;">
        <div style="background: linear-gradient(135deg, #6366f1, #8b5cf6); padding:24px 28px; border-radius:12px 12px 0 0;">
            <h2 style="color:#fff; margin:0;">💾 What's Up? Backup Complete</h2>
            <p style="color:#e0e7ff; margin:8px 0 0;">{timestamp}</p>
        </div>

        <div style="background:#fff; padding:20px 28px; border:1px solid #e5e7eb; border-top:none;">
            <h3 style="color:#4f46e5; margin-top:0;">📊 Backup Summary</h3>

            <table style="width:100%; border-collapse:collapse; font-size:14px;">
                <thead>
                    <tr style="background:#f8fafc;">
                        <th style="padding:8px 12px; text-align:left; border-bottom:2px solid #6366f1;">Directory</th>
                        <th style="padding:8px 12px; text-align:right; border-bottom:2px solid #6366f1;">Files</th>
                        <th style="padding:8px 12px; text-align:right; border-bottom:2px solid #6366f1;">Size</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                    <tr style="background:#f0fdf4; font-weight:bold;">
                        <td style="padding:8px 12px;">Total</td>
                        <td style="padding:8px 12px; text-align:right;">{total.get('files', 0)}</td>
                        <td style="padding:8px 12px; text-align:right;">{format_size(total.get('bytes', 0))}</td>
                    </tr>
                </tbody>
            </table>

            <div style="background:#f0f9ff; padding:12px 16px; border-left:4px solid #3b82f6; margin:16px 0; border-radius:4px;">
                <strong>📦 Archive:</strong> {format_size(archive_size)} (gzip level 9)
            </div>

            {split_note}

            <h3 style="color:#4f46e5;">🔄 Restore Instructions</h3>
            <ol style="font-size:14px;">
                <li>Download the attached <code>.tar.gz</code> file</li>
                <li>Extract: <code style="background:#1f2937; color:#10b981; padding:2px 6px; border-radius:3px;">tar -xzf whatsup_backup_*.tar.gz</code></li>
                <li>Copy extracted folders back into the project root</li>
            </ol>
        </div>

        <div style="background:#f8fafc; padding:16px 28px; border-radius:0 0 12px 12px; border:1px solid #e5e7eb; border-top:none;">
            <p style="color:#9ca3af; font-size:12px; margin:0;">
                🤖 Automated backup by What's Up? Blog Engine<br>
                Schedule: Every 3 days via GitHub Actions
            </p>
        </div>
    </body>
    </html>
    """
    return html


def send_backup_email(file_paths, stats, archive_size):
    num_parts = len(file_paths)

    for idx, file_path in enumerate(file_paths):
        part_label = f" (Part {idx + 1}/{num_parts})" if num_parts > 1 else ""

        msg = MIMEMultipart()
        msg['Subject'] = f"💾 What's Up? Backup — {datetime.now().strftime('%b %d, %Y')}{part_label}"
        msg['From'] = SMTP_EMAIL
        msg['To'] = NOTIFICATION_EMAIL

        if idx == 0:
            html_body = build_email_body(stats, archive_size, num_parts)
            msg.attach(MIMEText(html_body, 'html'))
        else:
            msg.attach(MIMEText(
                f"Part {idx + 1} of {num_parts} — concatenate all parts before extracting.",
                'plain'
            ))

        with open(file_path, 'rb') as f:
            attachment = MIMEBase('application', 'octet-stream')
            attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header(
                'Content-Disposition',
                f'attachment; filename="{file_path.name}"'
            )
            msg.attach(attachment)

        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(SMTP_EMAIL, SMTP_PASSWORD)
                server.sendmail(SMTP_EMAIL, NOTIFICATION_EMAIL, msg.as_string())

            file_size = file_path.stat().st_size
            print(f"   ✉️  Sent{part_label}: {file_path.name} ({format_size(file_size)})")
        except Exception as e:
            print(f"   ❌ Email error{part_label}: {e}")
            return False

    return True


def cleanup():
    if TEMP_DIR.exists():
        import shutil
        shutil.rmtree(TEMP_DIR)
        print("🧹 Temporary files cleaned up")


def main():
    print("=" * 60)
    print("💾 What's Up? — Automated Backup System")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    validate_env()

    print("\n📊 Scanning directories...")
    stats = collect_stats()

    total = stats.get('_total', {})
    if total.get('files', 0) == 0:
        print("\n⚠️  No files found to backup! Exiting.")
        sys.exit(0)

    archive_path, archive_size = create_archive()

    file_paths = split_archive(archive_path, MAX_ATTACHMENT_BYTES)

    print(f"\n📧 Sending backup via email...")
    print(f"   To: {NOTIFICATION_EMAIL}")
    print(f"   Parts: {len(file_paths)}")

    success = send_backup_email(file_paths, stats, archive_size)

    cleanup()

    if success:
        print("\n" + "=" * 60)
        print("✅ Backup complete and sent successfully!")
        print(f"   Total data: {format_size(total.get('bytes', 0))}")
        print(f"   Compressed: {format_size(archive_size)}")
        ratio = (1 - archive_size / max(total.get('bytes', 1), 1)) * 100
        print(f"   Compression ratio: {ratio:.1f}% smaller")
        print("=" * 60)
    else:
        print("\n❌ Backup failed — email delivery error")
        sys.exit(1)


if __name__ == '__main__':
    main()
