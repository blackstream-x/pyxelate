# Pixelate videos

Call **pixelate_video.py** either from the command line or via
context menu from your file manager
(see [file manager integration](./file-manager-integration.md)).

The GUI guides you through several panels to specify the pixelation of the video:
1. Select the start frame
2. Select the start area
3. Select the end frame
4. Select the end area
5. The pixelation is applied from the start area in the start frame to the end area in the end frame.
   You can review the whole clip filp book style, and you can save the video,
   and/or start at 1 again for an additional pixelation.

Please note that video length is limited to 10000 frames, that is roughly
5′33″ for NTSC or 6′40″ for PAL videos.
You can extend this limit up to a theoretical value of 999999 frames
(9 hours and 15 minutes for NTSC or 11 hours and 6 minutes for PAL)
by changing the `MAX_NB_FRAMES` variable in the script,
if you have enough disk space and patience for editing that large videos.

_(to be continued)_
