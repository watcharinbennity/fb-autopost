import subprocess

def animate(image,video):

    cmd=[

    "ffmpeg",
    "-y",
    "-loop","1",
    "-i",image,
    "-t","15",
    "-vf","scale=1080:1920,zoompan=z='min(zoom+0.003,1.18)':d=360:s=1080x1920",
    "-r","24",
    video

    ]

    subprocess.run(cmd)
