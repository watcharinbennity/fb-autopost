import subprocess


def build_video(image,video):

    cmd=[
    "ffmpeg",
    "-y",
    "-loop","1",
    "-i",image,
    "-t","20",
    "-vf","scale=1080:1920",
    "-pix_fmt","yuv420p",
    video
    ]

    subprocess.run(cmd,check=True)
