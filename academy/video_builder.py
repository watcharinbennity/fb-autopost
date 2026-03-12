import subprocess

def build_video(image, out):
    cmd = [
        "ffmpeg",
        "-y",
        "-loop","1",
        "-i",image,
        "-t","18",
        "-vf","scale=1080:1920,zoompan=z='min(zoom+0.0015,1.15)':d=432:s=1080x1920",
        "-r","24",
        out
    ]
    subprocess.run(cmd,check=True)

def add_audio(video,audio,out):

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

    subprocess.run(cmd,check=True)
