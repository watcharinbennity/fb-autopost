import subprocess

def merge(video,audio,out):

    cmd=[
    "ffmpeg",
    "-y",
    "-i",video,
    "-i",audio,
    "-shortest",
    "-c:v","copy",
    "-c:a","aac",
    out
    ]

    subprocess.run(cmd)
