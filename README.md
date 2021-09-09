# pyxelate

GUI scripts to partially pixelate images or short video clips

## Requirements

- Python 3 (<https://www.python.org/>)
- Pillow (<https://pypi.org/project/Pillow/>)
- FFmpeg (<http://ffmpeg.org/>) for editing videos

## Usage

The easiest way to use the scripts in this module is to set up
[file manager integration](docs/file-manager-integration.md) and
start the pixelation GUI from your file manager’s context menu.

Alternatively, you can start the <autoselect.py> script with
the image or video file to pixelate as a command line parameter:

`autoselect.py example.jpg`

This will start <pixelate_image.py> for image files
or __pixelate\_video.py (tba)__ for video files.

See [pixelating images](docs/pixelating-images.md)
and [pixelating videos](docs/pixelating-videos.md)
for detailed descriptions.

## Bugs / Feature requests

Feel free to open an issue [here](https://github.com/blackstream-x/pyxelate/issues).
