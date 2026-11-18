"""Video processing, validation, compression, and storage service for Kimbela VPS.

Handles server-side duration verification, chunked streaming to disk,
automated FFmpeg compression with sensible web defaults (H.264/AAC in MP4),
pure-Python ISO BMFF container fallback, unpredictable filename generation,
and atomic placement in the VPS uploads directory.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import struct
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta
from typing import Any, BinaryIO, Dict, Optional, Tuple

from flask import current_app

logger = logging.getLogger(__name__)

# Upload limits and expiration defaults
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_VIDEO_DURATION_SECONDS = 120.0  # 2 minutes maximum
CHUNK_SIZE = 1024 * 1024  # 1 MB stream chunk
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
ALLOWED_MIME_PREFIXES = ("video/",)
VIDEO_EXPIRED_SENTINEL = "expired"
DEFAULT_EXPIRATION_DAYS = 10


class VideoError(Exception):
    """Base exception for video validation and processing errors."""

    def __init__(self, code: str, user_message: str):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


class VideoValidationError(VideoError):
    """Client-facing validation failure (duration, size, headers, MIME)."""
    pass


class VideoProcessingError(VideoError):
    """Server-side compression or transcode failure."""
    pass


def get_video_upload_dirs() -> Tuple[str, str]:
    """Return (video_dir, tmp_dir) within the configured upload directory."""
    try:
        base_upload = current_app.config.get("UPLOAD_FOLDER")
    except Exception:
        base_upload = None

    if not base_upload:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        base_upload = os.path.join(base_dir, "uploads")

    video_dir = os.path.join(base_upload, "video")
    tmp_dir = os.path.join(video_dir, "tmp")
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)
    return video_dir, tmp_dir


def is_video_upload(media_file) -> bool:
    """Determine whether an uploaded file object represents a video."""
    if not media_file:
        return False
    filename = (getattr(media_file, "filename", "") or "").lower()
    content_type = (getattr(media_file, "content_type", "") or "").lower()

    if any(filename.endswith(ext) for ext in ALLOWED_VIDEO_EXTENSIONS):
        return True
    if any(content_type.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        return True
    return False


def _stream_to_temp_file(media_file, tmp_dir: str) -> Tuple[str, int]:
    """Stream incoming media file chunk-by-chunk to disk to protect RAM."""
    fd, temp_path = tempfile.mkstemp(prefix="upload_", suffix=".tmp", dir=tmp_dir)
    total_bytes = 0

    try:
        with os.fdopen(fd, "wb") as dest:
            stream = getattr(media_file, "stream", None)
            if stream is not None and hasattr(stream, "read"):
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > MAX_VIDEO_SIZE:
                        raise VideoValidationError(
                            "file_too_large",
                            "Video file too large! Maximum size is 100MB.",
                        )
                    dest.write(chunk)
            elif hasattr(media_file, "read"):
                while True:
                    chunk = media_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > MAX_VIDEO_SIZE:
                        raise VideoValidationError(
                            "file_too_large",
                            "Video file too large! Maximum size is 100MB.",
                        )
                    dest.write(chunk)
            else:
                raise VideoValidationError(
                    "unreadable_media",
                    "Uploaded file stream is invalid.",
                )
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise

    if total_bytes == 0:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise VideoValidationError("empty_file", "The uploaded video file is empty.")

    return temp_path, total_bytes


def _validate_magic_bytes(filepath: str, extension: str) -> None:
    """Validate container magic bytes to prevent renamed or malicious files."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(64)
    except OSError as exc:
        raise VideoValidationError("unreadable_file", "Cannot read uploaded media.") from exc

    if len(header) < 12:
        raise VideoValidationError("invalid_video_header", "The uploaded file is not a valid video.")

    ext = extension.lower()
    if ext in (".mp4", ".mov", ".m4v"):
        # ISO Base Media File Format: [4 bytes length][ftyp]
        box_type = header[4:8]
        if box_type != b"ftyp":
            raise VideoValidationError(
                "invalid_video_header",
                "The uploaded file is not a valid MP4 or MOV video.",
            )
    elif ext == ".webm":
        # EBML header: 0x1A 0x45 0xDF 0xA3
        if not header.startswith(b"\x1a\x45\xdf\xa3"):
            raise VideoValidationError(
                "invalid_video_header",
                "The uploaded file is not a valid WebM video.",
            )
    else:
        # Generic check
        if header[4:8] != b"ftyp" and not header.startswith(b"\x1a\x45\xdf\xa3"):
            raise VideoValidationError(
                "invalid_video_header",
                "The uploaded file is not a valid video.",
            )


def parse_iso_bmff_duration(stream: BinaryIO) -> Optional[float]:
    """Parse video duration from ISO BMFF (MP4/MOV) container atoms in pure Python."""
    stream.seek(0, 2)
    total_size = stream.tell()
    stream.seek(0)

    header = stream.read(8)
    if len(header) < 8:
        return None
    _, box_type = struct.unpack(">I4s", header)
    if box_type != b"ftyp":
        return None

    def scan_boxes(start: int, end: int) -> Optional[float]:
        pos = start
        while pos < end:
            stream.seek(pos)
            data = stream.read(8)
            if len(data) < 8:
                break
            box_len, b_type = struct.unpack(">I4s", data)
            if box_len == 1:
                ext_data = stream.read(8)
                if len(ext_data) < 8:
                    break
                box_len = struct.unpack(">Q", ext_data)[0]
                header_len = 16
            else:
                header_len = 8

            if box_len == 0:
                box_len = end - pos
            if box_len < header_len:
                break

            if b_type == b"moov":
                result = scan_boxes(pos + header_len, pos + box_len)
                if result is not None:
                    return result
            elif b_type == b"mvhd":
                mvhd_data = stream.read(min(box_len - header_len, 32))
                if len(mvhd_data) >= 20:
                    version = mvhd_data[0]
                    if version == 0:
                        timescale, duration = struct.unpack(">II", mvhd_data[12:20])
                    elif version == 1 and len(mvhd_data) >= 28:
                        timescale, duration = struct.unpack(">IQ", mvhd_data[20:32])
                    else:
                        return None
                    if timescale > 0:
                        return float(duration) / float(timescale)
            pos += box_len
        return None

    return scan_boxes(0, total_size)


def parse_webm_duration(stream: BinaryIO) -> Optional[float]:
    """Parse video duration from WebM EBML info elements in pure Python."""
    stream.seek(0, 2)
    total_size = stream.tell()
    stream.seek(0)

    header = stream.read(4)
    if header != b"\x1a\x45\xdf\xa3":
        return None

    data = stream.read(min(total_size, 65536))
    dur_idx = data.find(b"\x44\x89")
    if dur_idx != -1 and dur_idx + 6 <= len(data):
        size_byte = data[dur_idx + 2]
        size = size_byte & 0x7F
        dur_bytes = data[dur_idx + 3 : dur_idx + 3 + size]
        if size == 4:
            val = struct.unpack(">f", dur_bytes)[0]
            return float(val) / 1000.0 if val > 1000.0 else float(val)
        elif size == 8:
            val = struct.unpack(">d", dur_bytes)[0]
            return float(val) / 1000.0 if val > 1000.0 else float(val)
    return None


def is_faststart_mp4(filepath: str) -> bool:
    """Return True if moov atom precedes mdat atom (faststart web streaming)."""
    try:
        with open(filepath, "rb") as f:
            f.seek(0, 2)
            total = f.tell()
            f.seek(0)
            pos = 0
            moov_pos = None
            mdat_pos = None

            while pos < total:
                f.seek(pos)
                data = f.read(8)
                if len(data) < 8:
                    break
                box_len, b_type = struct.unpack(">I4s", data)
                if box_len == 1:
                    ext = f.read(8)
                    if len(ext) < 8:
                        break
                    box_len = struct.unpack(">Q", ext)[0]
                if box_len == 0:
                    box_len = total - pos

                if b_type == b"moov" and moov_pos is None:
                    moov_pos = pos
                elif b_type == b"mdat" and mdat_pos is None:
                    mdat_pos = pos

                if moov_pos is not None and mdat_pos is not None:
                    break
                pos += box_len

            if moov_pos is not None and mdat_pos is not None:
                return moov_pos < mdat_pos
            return False
    except Exception:
        return False


def _probe_with_ffprobe(filepath: str) -> Optional[Dict]:
    """Execute ffprobe JSON probe to extract streams, duration, and codecs."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None

    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration,format_name,size,bit_rate:stream=index,codec_name,codec_type,width,height",
        "-of",
        "json",
        filepath,
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode != 0:
            return None
        data = json.loads(res.stdout)
        format_info = data.get("format", {})
        streams = data.get("streams", [])

        duration = None
        if "duration" in format_info:
            try:
                duration = float(format_info["duration"])
            except (ValueError, TypeError):
                pass

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            return None

        if duration is None and video_stream and "duration" in video_stream:
            try:
                duration = float(video_stream["duration"])
            except (ValueError, TypeError):
                pass

        bit_rate = None
        if format_info.get("bit_rate"):
            try:
                bit_rate = int(format_info["bit_rate"])
            except (ValueError, TypeError):
                pass

        return {
            "duration": duration,
            "format_name": format_info.get("format_name", ""),
            "video_codec": (video_stream.get("codec_name") or "").lower(),
            "audio_codec": (audio_stream.get("codec_name") or "").lower() if audio_stream else None,
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "bit_rate": bit_rate,
        }
    except Exception:
        return None


def probe_video_metadata(filepath: str, extension: str) -> Dict:
    """Extract metadata and duration using ffprobe if available or native parsers."""
    probed = _probe_with_ffprobe(filepath)
    if probed is not None and probed.get("duration") is not None:
        return probed

    duration = None
    ext = extension.lower()
    try:
        with open(filepath, "rb") as f:
            if ext in (".mp4", ".mov", ".m4v"):
                duration = parse_iso_bmff_duration(f)
            elif ext == ".webm":
                duration = parse_webm_duration(f)
    except Exception as exc:
        raise VideoValidationError(
            "unreadable_duration",
            "Unable to determine video duration. The file may be corrupted.",
        ) from exc

    if duration is None:
        raise VideoValidationError(
            "unreadable_duration",
            "Unable to determine video duration. The file may be corrupted.",
        )

    return {
        "duration": duration,
        "format_name": ext.lstrip("."),
        "video_codec": None,
        "audio_codec": None,
        "width": None,
        "height": None,
        "bit_rate": None,
    }


def _compress_or_optimize(
    input_path: str,
    output_path: str,
    metadata: Dict,
    extension: str,
) -> None:
    """Compress video using sensible web defaults (H.264+AAC in MP4, max 1080p, CRF 23)."""
    ffmpeg_bin = shutil.which("ffmpeg")

    if not ffmpeg_bin:
        # Fallback when FFmpeg is not installed on host
        ext = extension.lower()
        if ext in (".mp4", ".mov", ".m4v"):
            shutil.copy2(input_path, output_path)
            logger.warning("FFmpeg not installed; stored validated MP4 without re-encoding: %s", output_path)
            return
        raise VideoProcessingError(
            "ffmpeg_not_available",
            "Video processing binary is not available on the server.",
        )

    format_name = metadata.get("format_name", "").lower()
    video_codec = metadata.get("video_codec")
    audio_codec = metadata.get("audio_codec")
    width = metadata.get("width") or 0
    height = metadata.get("height") or 0

    is_mp4 = "mp4" in format_name
    is_h264 = video_codec in ("h264", "avc1")
    is_aac = audio_codec in ("aac", None)
    is_standard_res = width > 0 and height > 0 and width <= 1920 and height <= 1080
    has_faststart = is_faststart_mp4(input_path) if is_mp4 else False

    # 1. Safe Optimization: If already H.264 + AAC + <=1080p + faststart, copy directly.
    if is_mp4 and is_h264 and is_aac and is_standard_res and has_faststart:
        shutil.copy2(input_path, output_path)
        logger.info("Video is already optimized and faststart; skipped re-encode.")
        return

    # 2. Fast remux: If already H.264 + AAC + <=1080p, only move moov atom to front.
    if is_mp4 and is_h264 and is_aac and is_standard_res and not has_faststart:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            input_path,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            output_path,
        ]
    else:
        # 3. Transcode with sensible settings:
        # - capped at 1080p (scale='min(1080,iw)':-2)
        # - libx264, preset fast, crf 23 (visually near-lossless)
        # - aac 128k
        # - +faststart (enables streaming playback before full download)
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            input_path,
            "-vf",
            "scale='min(1080,iw)':-2",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            output_path,
        ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            logger.error("FFmpeg compression failed: %s", res.stderr)
            raise VideoProcessingError(
                "compression_failed",
                "Video compression failed. Please ensure the video is not corrupted.",
            )
    except subprocess.TimeoutExpired as exc:
        raise VideoProcessingError(
            "compression_timeout",
            "Video processing timed out. Please try a shorter or smaller video.",
        ) from exc


def process_and_store_feed_video(media_file) -> str:
    """Validate, compress, and store one feed video upload directly on the VPS.

    Returns the relative web path (e.g. '/uploads/video/<uuid>.mp4').
    """
    if not media_file:
        raise VideoValidationError("missing_file", "No video file provided.")

    filename = getattr(media_file, "filename", "") or ""
    content_type = (getattr(media_file, "content_type", "") or "").lower()

    if not filename or "." not in filename:
        raise VideoValidationError("invalid_filename", "Video filename is missing or invalid.")

    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise VideoValidationError(
            "unsupported_format",
            "Unsupported video format. Allowed formats: MP4, MOV, WebM.",
        )

    if content_type and not content_type.startswith(ALLOWED_MIME_PREFIXES) and content_type != "application/octet-stream":
        raise VideoValidationError(
            "invalid_mime_type",
            "Invalid MIME type for video upload.",
        )

    video_dir, tmp_dir = get_video_upload_dirs()
    temp_upload_path = None
    staged_output_path = None

    try:
        # 1. Stream chunk-by-chunk to disk to protect server RAM
        temp_upload_path, file_size = _stream_to_temp_file(media_file, tmp_dir)

        # 2. Validate magic bytes
        _validate_magic_bytes(temp_upload_path, extension)

        # 3. Probe duration and stream properties
        metadata = probe_video_metadata(temp_upload_path, extension)
        duration = metadata.get("duration")

        if duration is None or duration <= 0:
            raise VideoValidationError(
                "invalid_duration",
                "Video duration is invalid or unreadable.",
            )

        if duration > MAX_VIDEO_DURATION_SECONDS:
            raise VideoValidationError(
                "duration_exceeded",
                "Videos cannot exceed 2 minutes (120 seconds).",
            )

        # 4. Generate unpredictable UUID filename and staging destination
        secure_filename = f"{uuid.uuid4().hex}.mp4"
        staged_output_path = os.path.join(tmp_dir, f"staged_{secure_filename}")
        final_destination_path = os.path.join(video_dir, secure_filename)

        # 5. Compress or optimize video
        _compress_or_optimize(temp_upload_path, staged_output_path, metadata, extension)

        # 6. Atomically move processed file into destination
        os.replace(staged_output_path, final_destination_path)
        logger.info(
            "Video processed and stored successfully: %s (duration=%.2fs, size=%d bytes)",
            secure_filename,
            duration,
            os.path.getsize(final_destination_path),
        )

        return f"/uploads/video/{secure_filename}"

    finally:
        # 7. Safe temporary file cleanup: partially uploaded or failed files are removed
        for cleanup_path in (temp_upload_path, staged_output_path):
            if cleanup_path and os.path.exists(cleanup_path):
                try:
                    os.remove(cleanup_path)
                except OSError:
                    pass


def delete_stored_video_file(video_url: str) -> bool:
    """Safely unlink a local video file from disk, preventing path traversal."""
    if not video_url or not isinstance(video_url, str):
        return False

    prefix = "/uploads/video/"
    if not video_url.startswith(prefix):
        return False

    filename = video_url[len(prefix):].strip()
    # Strip any directory components to strictly prevent path traversal
    filename = os.path.basename(filename)
    if not filename:
        return False

    video_dir, _ = get_video_upload_dirs()
    target_path = os.path.join(video_dir, filename)

    if os.path.isfile(target_path):
        try:
            os.remove(target_path)
            logger.info("Deleted local video file: %s", filename)
            return True
        except OSError as exc:
            logger.error("Failed to delete local video file %s: %s", target_path, exc)
            return False

    return False


def cleanup_expired_videos(
    cutoff_delta: timedelta = timedelta(days=DEFAULT_EXPIRATION_DAYS),
    now: Optional[datetime] = None,
    batch_size: int = 100,
    cleanup_orphaned_tmp: bool = True,
) -> Dict[str, Any]:
    """Identify and delete physical video files older than cutoff_delta (default 10 days).

    - Identifies posts with active VPS video paths whose upload timestamp is >= cutoff_delta.
    - Safely unlinks the video file and any derivative files from VPS storage.
    - Updates post.video to VIDEO_EXPIRED_SENTINEL ("expired").
    - Preserves the original post, its text content, comments, likes, and reactions.
    - Idempotent and resilient to missing files, filesystem permission errors, and DB rollbacks.
    - Logs all successful deletions and failures.

    Returns a summary dict with statistics.
    """
    from extensions import db
    from models import Post
    from time_utils import utcnow

    effective_now = now or utcnow()
    cutoff_time = effective_now - cutoff_delta

    video_dir, tmp_dir = get_video_upload_dirs()

    # Query posts with local videos uploaded at or before cutoff_time
    candidates = (
        Post.query.filter(
            Post.video.like("/uploads/video/%"),
            Post.created_at <= cutoff_time,
        )
        .order_by(Post.created_at.asc())
        .limit(batch_size)
        .all()
    )

    stats = {
        "checked": len(candidates),
        "expired": 0,
        "failed": 0,
        "missing_files_handled": 0,
        "cutoff_used": cutoff_time.isoformat(),
    }

    for post in candidates:
        video_url = post.video
        post_id = post.id

        if not video_url or not video_url.startswith("/uploads/video/"):
            continue

        raw_name = video_url.split("?")[0].replace("/uploads/video/", "").strip()
        filename = os.path.basename(raw_name)

        # Path traversal guard
        if not filename or filename != raw_name or "/" in filename or "\\" in filename:
            logger.error(
                "Suspicious video filename detected on post %d: %r; skipping deletion",
                post_id,
                video_url,
            )
            stats["failed"] += 1
            continue

        target_path = os.path.join(video_dir, filename)
        # Verify target is strictly within video_dir
        if not os.path.abspath(target_path).startswith(os.path.abspath(video_dir)):
            logger.error(
                "Path traversal detected on post %d: %r; skipping deletion",
                post_id,
                target_path,
            )
            stats["failed"] += 1
            continue

        # 1. Unlink physical video file if present on disk
        try:
            if os.path.isfile(target_path):
                os.remove(target_path)
                logger.info(
                    "Unlinked expired video file for post %d: %s",
                    post_id,
                    filename,
                )
            else:
                stats["missing_files_handled"] += 1
                logger.info(
                    "Physical video file was already absent for post %d (%s); marking expired",
                    post_id,
                    filename,
                )

            # 2. Unlink any potential derivative files or staging files
            base_name, _ = os.path.splitext(filename)
            for deriv_ext in (".jpg", ".jpeg", ".png", ".webp"):
                deriv_path = os.path.join(video_dir, f"{base_name}{deriv_ext}")
                if os.path.isfile(deriv_path):
                    try:
                        os.remove(deriv_path)
                    except OSError:
                        pass
                thumb_path = os.path.join(video_dir, f"{base_name}_thumb{deriv_ext}")
                if os.path.isfile(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except OSError:
                        pass

            staged_path = os.path.join(tmp_dir, f"staged_{filename}")
            if os.path.isfile(staged_path):
                try:
                    os.remove(staged_path)
                except OSError:
                    pass

        except OSError as exc:
            # Filesystem permission error or I/O failure
            logger.error(
                "Filesystem failure deleting video for post %d (%s): %s",
                post_id,
                target_path,
                exc,
            )
            stats["failed"] += 1
            # Do NOT update database; leave video path intact so cleanup can be retried
            continue

        # 3. Update database record to mark video expired while preserving the post
        try:
            post.video = VIDEO_EXPIRED_SENTINEL
            db.session.commit()
            stats["expired"] += 1
            logger.info("Successfully marked video expired for post %d", post_id)
        except Exception as exc:
            db.session.rollback()
            logger.error(
                "Database error updating post %d to expired state: %s",
                post_id,
                exc,
            )
            stats["failed"] += 1

    # 4. Cleanup of orphaned temporary files older than 24h
    if cleanup_orphaned_tmp and os.path.isdir(tmp_dir):
        tmp_cutoff = (effective_now - timedelta(hours=24)).timestamp()
        try:
            for entry in os.listdir(tmp_dir):
                entry_path = os.path.join(tmp_dir, entry)
                if os.path.isfile(entry_path):
                    try:
                        if os.path.getmtime(entry_path) < tmp_cutoff:
                            os.remove(entry_path)
                            logger.info("Cleaned up orphaned temp file: %s", entry)
                    except OSError:
                        pass
        except OSError as exc:
            logger.warning("Could not scan tmp directory for cleanup: %s", exc)

    return stats
