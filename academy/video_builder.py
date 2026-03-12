# academy/video_builder.py

import subprocess
import os


def build_video_from_image(image_path: str, video_path: str, duration: int = 18):
    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", image_path,
        "-t", str(duration),
        "-vf", "scale=1080:1920,zoompan=z='min(zoom+0.0015,1.12)':d=24*18:s=1080x1920,format=yuv420p",
        "-r", "24",
        "-pix_fmt", "yuv420p",
        video_path,
    ]
    subprocess.run(cmd, check=True)
    return video_path


def merge_audio(video_path: str, audio_path: str, out_path: str):
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def cleanup_temp(paths):
    for p in paths:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
