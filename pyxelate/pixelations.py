# -*- coding: utf-8 -*-

"""

pixelations.py

Module for pixelating parts of images

Copyright (C) 2021 Rainer Schwarzbach

This file is part of pyxelate.

pyxelate is free software: you can redistribute it and/or modify
it under the terms of the MIT License.

pyxelate is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the LICENSE file for more details.

"""


import io
import logging
import math
import re
import time

from fractions import Fraction

from PIL import Image
from PIL import ImageDraw
from PIL import ImageTk
from PIL import features


#
# Constants
#


DEFAULT_TILESIZE = 25
DEFAULT_CANVAS_SIZE = (720, 405)

ELLIPSE = 'ellipse'
RECTANGLE = 'rectangle'

FRAME_PATTERN = 'frame%04d.jpg'


#
# Helper functions
#


def get_supported_extensions():
    """Get file name extensions supported by PIL"""
    prx_separator_line = re.compile('^-+$', re.M)
    prx_comma_blank = re.compile(r',\s+')
    prx_extensions = re.compile(r'^Extensions:\s+')
    prx_capabilities = re.compile(r'^Features:\s+')
    open_support = set()
    save_support = set()
    pil_info = io.StringIO()
    try:
        features.pilinfo(supported_formats=True, out=pil_info)
    except AttributeError:
        # ignore nonexisting function features.pilinfo
        # in very old PIL(LOW) versions
        pass
    #
    pil_info.seek(0)
    for block in prx_separator_line.split(pil_info.read()):
        if 'Extensions:' in block and 'Features:' in block:
            extensions = []
            capabilities = []
            for line in block.splitlines():
                if prx_extensions.match(line):
                    extensions = prx_comma_blank.split(
                        prx_extensions.sub('', line))
                elif prx_capabilities.match(line):
                    capabilities = prx_comma_blank.split(
                        prx_capabilities.sub('', line))
                    #
                #
            #
            if 'open' in capabilities:
                open_support.update(extensions)
            #
            if 'save' in capabilities:
                save_support.update(extensions)
            #
        #
    #
    return (open_support, save_support)


def dimension_display_ratio(image_size, canvas_size):
    """Display ratio calculated per dimension"""
    if image_size < canvas_size:
        return 1
    #
    raw_ratio = Fraction(image_size, canvas_size)
    if raw_ratio <= 3:
        return Fraction(math.ceil(raw_ratio * 4), 4)
    #
    if raw_ratio <= 5:
        return Fraction(math.ceil(raw_ratio * 2), 2)
    #
    return math.ceil(raw_ratio)


def most_frequent_color(image):
    """Return the dominant color in the image
    as a tuple of integers, or raise a ValueError
    """
    width, height = image.size
    image_color_frequencies = image.getcolors(width * height)
    most_frequent_pixel_color = image_color_frequencies[0]
    for frequency, color in image_color_frequencies:
        if frequency > most_frequent_pixel_color[0]:
            most_frequent_pixel_color = (frequency, color)
        #
    #
    selected_color = most_frequent_pixel_color[1]
    if isinstance(selected_color, int):
        if image.palette:
            if image.palette.mode == 'RGB':
                # Grab the color values from the palette
                values = []
                palette_size = int(
                    len(image.palette.palette) / len(image.palette.mode))
                logging.debug('Palette size: %r', palette_size)
                for band_index, band_name in enumerate(image.palette.mode):
                    total_index = selected_color + band_index * palette_size
                    channel_value = image.palette.palette[total_index]
                    values.append(channel_value)
                    logging.debug(
                        'Band %r index %r (total %r) value: %r',
                        band_name,
                        selected_color,
                        total_index,
                        channel_value)
                #
                return tuple(values)
            #
        elif image.mode == 'L':
            return (selected_color,) * 3
        #
    #
    if not isinstance(selected_color, tuple):
        raise ValueError(
            'Cannot handle color value {0!r} in image mode {1!r}.'.format(
                selected_color, image.mode))
    #
    return selected_color


def pixelated(original_image, tilesize=DEFAULT_TILESIZE):
    """Return a copy of the original image, pixelated"""
    original_width = original_image.width
    original_height = original_image.height
    reduced_width = original_width // tilesize + 1
    reduced_height = original_height // tilesize + 1
    oversize_width = reduced_width * tilesize
    oversize_height = reduced_height * tilesize
    oversized = Image.new(
        original_image.mode,
        (oversize_width, oversize_height),
        color=most_frequent_color(original_image))
    oversized.paste(original_image)
    reduced = oversized.resize(
        (reduced_width, reduced_height), resample=Image.BICUBIC)
    oversized = reduced.resize(
        (oversize_width, oversize_height), resample=0)
    return oversized.crop((0, 0, original_width, original_height))


#
# Classes
#


class Borg:

    """Shared state base class as documented in
    <https://www.oreilly.com/
     library/view/python-cookbook/0596001673/ch05s23.html>
     """

    _shared_state = {}

    def __init__(self):
        """Initalize shared state"""
        self.__dict__ = self._shared_state


class ShapesCache(Borg):

    """Borg cache for Mask shapes"""

    limit = 50

    def __init__(self):
        """Allocate the cache"""
        super().__init__()
        self.__last_access = {}
        self.__shapes = {}

    def get_cached(self, shape_type, size):
        """Get a cached shape or create a new one"""
        key = (shape_type, size)
        try:
            cached_shape = self.__shapes[key]
        except KeyError:
            pass
        else:
            self.__last_access[key] = time.time()
            return cached_shape
        #
        shape_image = Image.new('L', size, color=0)
        draw = ImageDraw.Draw(shape_image)
        if RECTANGLE.startswith(shape_type):
            draw_method = draw.rectangle
        elif ELLIPSE.startswith(shape_type):
            draw_method = draw.ellipse
        else:
            raise ValueError('Unsupported shape %r!' % shape_type)
        #
        width, height = size
        draw_method((0, 0, width - 1, height - 1), fill=255)
        self.__shapes[key] = shape_image
        self.__last_access[key] = time.time()
        self.delete_oldest_shapes()
        return shape_image

    def delete_oldest_shapes(self):
        """Delete the oldest shapes from the cache
        if the limit has been exceeded
        """
        if len(self.__shapes) > self.limit:
            for key in sorted(self.__last_access)[:-self.limit]:
                del self.__shapes[key]
                del self.__last_access[key]
            #
        #


class BaseImage:

    """Image base class"""

    kw_orig = 'original image'
    kw_display_ratio = 'display ratio'
    kw_tk_original = 'canvas-sized original image for tkinter'

    def __init__(self,
                 image_path,
                 canvas_size=DEFAULT_CANVAS_SIZE):
        """Allocate the internal cache"""

        self.__cache = {}
        self.__canvas_size = None
        self.set_canvas_size(canvas_size)
        self.load_image(image_path)
        #

    def lazy_evaluation(self, cache_key, producer, clear_on_miss=None):
        """Return an item from the cache or get it produced by the
        producer function"""
        try:
            return self.__cache[cache_key]
        except KeyError:
            self.__cache[cache_key] = producer()
            if clear_on_miss:
                self.cache_remove(clear_on_miss)
            #
            return self.__cache[cache_key]
        #

    def cache_remove(self, item):
        """Remove item from internal cache"""
        self.__cache.pop(item, None)

    def load_image(self, image_path):
        """Load the image"""
        self.set_original(Image.open(str(image_path)))

    def set_original(self, image):
        """Set the provided image as original image"""
        self.__cache[self.kw_orig] = image
        self.cache_remove(self.kw_display_ratio)
        self.cache_remove(self.kw_tk_original)

    def set_canvas_size(self, canvas_size):
        """Set the canvas size"""
        if self.__canvas_size != canvas_size:
            self.__canvas_size = canvas_size
            self.cache_remove(self.kw_display_ratio)
            self.cache_remove(self.kw_tk_original)
        #

    @property
    def display_ratio(self):
        """The display ratio"""
        if self.__canvas_size is None:
            return 1
        #
        return self.lazy_evaluation(
            self.kw_display_ratio, self.get_display_ratio)

    @property
    def original(self):
        """The original image"""
        return self.__cache[self.kw_orig]

    @property
    def tk_original(self):
        """The ImageTk.PhotoImage of the original
        downsized to fit the canvas
        """
        return self.lazy_evaluation(self.kw_tk_original, self.get_tk_image)

    def get_display_ratio(self):
        """Get the display ratio from the image and canvas sizes"""
        (canvas_width, canvas_height) = self.__canvas_size
        ratio_x = dimension_display_ratio(
            self.original.width, canvas_width)
        ratio_y = dimension_display_ratio(
            self.original.height, canvas_height)
        return max(ratio_x, ratio_y)

    def from_display_size(self, display_length):
        """Return the translated display size as an integer"""
        if self.display_ratio > 1:
            return int(display_length * self.display_ratio)
        #
        return display_length

    def to_display_size(self, length):
        """Return the display size of length as an integer"""
        if self.display_ratio > 1:
            return int(length / self.display_ratio)
        #
        return length

    def downsized_to_canvas(self, source_image):
        """Return the image downsized to canvas size
        (or original size if no downsizing is required)
        """
        if self.display_ratio > 1:
            return source_image.resize(
                (int(source_image.width / self.display_ratio),
                 int(source_image.height / self.display_ratio)),
                resample=Image.BICUBIC)
        #
        return source_image

    def get_tk_image(self, source_image=None):
        """Return the image downsized to canvas size and
        as a PhotoImage instance for Tkinter
        """
        if not source_image:
            source_image = self.original
        #
        return ImageTk.PhotoImage(
            self.downsized_to_canvas(source_image))


class BasePixelation(BaseImage):

    """Pixelation base class"""

    kw_px_area = 'pixelated image area'
    kw_px_mask = 'pixelated area mask'
    # kw_mask_shape = 'mask_shape'
    kw_result = 'resulting image'

    def __init__(self,
                 image_path,
                 tilesize=DEFAULT_TILESIZE,
                 canvas_size=DEFAULT_CANVAS_SIZE):
        """Allocate the internal cache"""
        super().__init__(image_path, canvas_size=canvas_size)
        self.__mask_shape = None
        self.__tilesize = 0
        self.__shapes = ShapesCache()
        self.shape_offset = (0, 0)
        self.set_tilesize(tilesize)

    def set_tilesize(self, tilesize):
        """Set the tilesize and delete the cached pixelated results"""
        if self.__tilesize != tilesize:
            self.__tilesize = tilesize
            self.cache_remove(self.kw_px_area)
            self.cache_remove(self.kw_result)
        #

    def set_shape(self, center, shape_type, size):
        """Set the shape and delete the cached results"""
        (pos_x, pos_y) = center
        (width, height) = size
        offset_x = pos_x - width // 2
        offset_y = pos_y - height // 2
        self.shape_offset = (offset_x, offset_y)
        self.cache_remove(self.kw_px_mask)
        self.cache_remove(self.kw_result)
        self.__mask_shape = self.__shapes.get_cached(shape_type, size)

    @property
    def mask_shape(self):
        """The cached mask shape"""
        if self.__mask_shape is None:
            raise ValueError('No mask shape set yet!')
        #
        return self.__mask_shape

    @property
    def tilesize(self):
        """The pixel size"""
        return self.__tilesize

    @property
    def mask(self):
        """The mask for the pixelated area"""
        return self.lazy_evaluation(self.kw_px_mask, self.get_mask)

    @property
    def pixelated_area(self):
        """The pixelated area of the original image"""
        return self.lazy_evaluation(
            self.kw_px_area,
            self.get_pixelated_area,
            clear_on_miss=self.kw_result)

    @property
    def result(self):
        """The partially pixelated image"""
        return self.lazy_evaluation(self.kw_result, self.get_result)

    def get_mask(self):
        """Return the mask for the pixelated image"""
        raise NotImplementedError

    def get_pixelated_area(self):
        """Return a copy of the original image,
        fully pixelated
        """
        raise NotImplementedError

    def get_result(self):
        """Return the result
        """
        raise NotImplementedError


class ImagePixelation(BasePixelation):

    """Image pixelation:
    The pixelation area covers the whole image;
    only the mask is re-drawn
    """

    def get_mask(self):
        """Return the mask for the pixelated image"""
        px_mask = Image.new('L', self.original.size, color=0)
        px_mask.paste(self.mask_shape, box=self.shape_offset)
        return px_mask

    def get_pixelated_area(self):
        """Return a copy of the original image,
        fully pixelated
        """
        return pixelated(self.original, tilesize=self.tilesize)

    def get_result(self):
        """Return the result
        """
        result_image = self.original.copy()
        result_image.paste(
            self.pixelated_area, box=None, mask=self.mask)
        return result_image


class FramePixelation(BasePixelation):

    """(Video) Frame pixelation:
    The pixelation is only as big as required
    """

    def set_shape(self, center, shape_type, size):
        """Set the shape and delete the cached results"""
        super().set_shape(center, shape_type, size)
        self.cache_remove(self.kw_px_area)

    def get_mask(self):
        """Return the mask for the pixelated image"""
        return self.mask_shape

    def get_pixelated_area(self):
        """Return a pixelated area of the original image
        """
        (offset_x, offset_y) = self.shape_offset
        box = (offset_x,
               offset_y,
               offset_x + self.mask_shape.width,
               offset_y + self.mask_shape.height)
        # logging.debug('Pixelation box: %r', box)
        # logging.debug('Pixelation width: %r', self.mask_shape.width)
        # logging.debug('Pixelation height: %r', self.mask_shape.height)
        return pixelated(self.original.crop(box), tilesize=self.tilesize)

    def get_result(self):
        """Return the result
        """
        result_image = self.original.copy()
        # logging.debug('Pixelated size: %r', self.pixelated_area.size)
        # logging.debug('Mask size: %r', self.mask.size)
        result_image.paste(
            self.pixelated_area, box=self.shape_offset, mask=self.mask)
        return result_image


class MultiFramePixelation:

    """Pixelate a frames sequence"""

    def __init__(self,
                 source_path,
                 target_path,
                 file_name_pattern=FRAME_PATTERN):
        """Check if both directories exist"""
        for current_path in (source_path, target_path):
            if not current_path.is_dir():
                raise ValueError('%s is not a directory!')
            #
        #
        # pylint: disable=pointless-statement ; Test for valid pattern
        file_name_pattern % 1
        # pylint: enable
        self.source_path = source_path
        self.target_path = target_path
        self.pattern = file_name_pattern
        self.start = dict()
        # self.end = dict()
        self.gradients = dict()

    def get_intermediate_value(self, item, offset):
        """Get the intermediate value
        at frame# start.frame + offset
        """
        return self.start[item] + round(self.gradients[item] * offset)

    def pixelate_frames(self, tilesize, shape, start, end):
        """Pixelate the frames and yield a progress fraction
        start and end must be Namespaces or dicts
        containing frame, center_x, center_y, width and height
        """
        start_frame = start['frame']
        end_frame = end['frame']
        frames_diff = end_frame - start_frame
        if frames_diff < 1:
            raise ValueError(
                'The end frame must be after the start frame!')
        #
        self.start = start
        self.gradients = dict()
        for item in ('center_x', 'center_y', 'width', 'height'):
            self.gradients[item] = Fraction(
                end[item] - start[item], frames_diff)
        #
        for current_frame in range(start_frame, end_frame + 1):
            file_name = self.pattern % current_frame
            source_frame = FramePixelation(
                self.source_path / file_name,
                canvas_size=None,
                tilesize=tilesize)
            offset = current_frame - start_frame
            source_frame.set_shape(
                (
                    self.get_intermediate_value('center_x', offset),
                    self.get_intermediate_value('center_y', offset)),
                shape,
                (
                    self.get_intermediate_value('width', offset),
                    self.get_intermediate_value('height', offset)))
            source_frame.result.save(self.target_path / file_name)
            logging.debug('Saved pixelated frame# %r', current_frame)
            yield round(Fraction(100 * (offset + 1), (frames_diff + 1)))
        #



# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
