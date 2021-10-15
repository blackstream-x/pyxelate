# Pixelate videos

Call **pixelate_video.py** either from the command line or via
context menu from your file manager
(see [file manager integration](./file-manager-integration.md)).

The application guides you through several panels to specify the pixelation
of one or more (moving) objects in a video.
Clicking  anywhere with the secondary (usually right) mouse button
is a shortcut for clicking the `▷ Next` button.

1. _(tba: Cut video start: select the first frame -
   all frames before the selected one will be discarded.)_
2. _(tba: Cut video end: select the last frame -
   all frames after the selected one will be discarded.)_
3. Select pixelation start by selecting frame and area.
4. Select pixelation stop by selecting frame and area.
   _(tba: Normally, clicking the `▷ Next` button will take you to the following panel.
   This panel behaves differently: it is repeated until you click the `✓ Apply` button,
   allowing chained pixelations to break up non-linear movements of objects
   in the video indo smaller linear movement steps.)_
5. The pixelation is applied using linear movements of the pixelated area
   between the consecutive “stations” selected in the previous panels.
   You can review the whole clip flip book style, and you can save the video,
   and/or jump to the pixelation start selection panel (#3) for an additional pixelation.

Please note that video length is limited to 10000 frames, that is roughly
5′33″ for NTSC or 6′40″ for PAL videos.
You can extend this limit up to a theoretical value of 999999 frames
(9 hours and 15 minutes for NTSC or 11 hours and 6 minutes for PAL)
by changing the `MAX_NB_FRAMES` variable in the script,
if you have enough disk space and patience for editing that large videos.

_(to be continued)_
