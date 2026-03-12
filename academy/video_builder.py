import subprocess


def image_to_video(image,output):

    cmd=[
    "ffmpeg",
    "-y",
    "-loop","1",
    "-i",image,
    "-t","20",
    "-vf","scale=1080:1920",
    "-pix_fmt","yuv420p",
    output
    ]

    subprocess.run(cmd,check=True)
