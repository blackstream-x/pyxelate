# -*- coding: utf-8 -*-

"""

pixelations.py

Module for pixelating parts of images

"""


import logging
import math
import time

from fractions import Fraction

from PIL import Image, ImageDraw, ImageTk


#
# Constants
#


DEFAULT_TILESIZE = 10
DEFAULT_CANVAS_SIZE = (720, 405)


#
# Helper functions
#


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
    reduced = oversized.resize((reduced_width, reduced_height), resample=0)
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
        if 'rectangle'.startswith(shape_type):
            draw_method = draw.rectangle
        elif 'ellipse'.startswith(shape_type):
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


class BasePixelation:

    """Pixelation base class"""

    kw_orig = 'original image'
    kw_px_area = 'pixelated image area'
    kw_px_mask = 'pixelated area mask'
    kw_mask_shape = 'mask_shape'
    kw_result = 'resulting image'
    kw_display_ratio = 'display ratio'

    def __init__(self,
                 image_path,
                 tilesize=DEFAULT_TILESIZE,
                 canvas_size=DEFAULT_CANVAS_SIZE):
        """Allocate the internal cache"""

        self.__cache = {}
        self.__tilesize = 0
        self.__canvas_size = (0, 0)
        self.__shapes = ShapesCache()
        self.shape_offset = (0, 0)
        self.set_tilesize(tilesize)
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
                self.__cache.pop(clear_on_miss, None)
            #
            return self.__cache[cache_key]
        #

    def load_image(self, image_path):
        """Load the image"""
        self.__cache[self.kw_orig] = Image.open(str(image_path))

    def set_tilesize(self, tilesize):
        """Set the tilesize and delete the cached pixelated results"""
        if self.__tilesize != tilesize:
            self.__tilesize = tilesize
            self.__cache.pop(self.kw_px_area, None)
            self.__cache.pop(self.kw_result, None)
        #

    def set_canvas_size(self, canvas_size):
        """Set the canvas size"""
        if self.__canvas_size != canvas_size:
            self.__canvas_size = canvas_size
            self.__cache.pop(self.kw_display_ratio, None)
        #

    def set_shape(self, center, shape_type, size):
        """Set the shape and delete the cached results"""
        (pos_x, pos_y) = center
        (width, height) = size
        offset_x = pos_x - width // 2
        offset_y = pos_y - height // 2
        self.shape_offset = (offset_x, offset_y)
        self.__cache.pop(self.kw_px_mask, None)
        self.__cache.pop(self.kw_result, None)
        self.__cache[self.kw_mask_shape] = self.__shapes.get_cached(
            shape_type, size)

    @property
    def mask_shape(self):
        """The cached mask shape"""
        try:
            return self.__cache[self.kw_mask_shape]
        except KeyError as error:
            raise ValueError('No mask shape set yet!') from error
        #

    @property
    def tilesize(self):
        """The pixel size"""
        return self.__tilesize

    @property
    def display_ratio(self):
        """The display ratio"""
        return self.lazy_evaluation(
            self.kw_display_ratio, self.get_display_ratio)

    @property
    def original(self):
        """The original image"""
        return self.__cache[self.kw_orig]

    @property
    def pixelated_area(self):
        """The pixelated area of the original image"""
        return self.lazy_evaluation(
            self.kw_px_area,
            self.get_pixelated_area,
            clear_on_miss=self.kw_result)

    @property
    def mask(self):
        """The mask for the pixelated area"""
        return self.lazy_evaluation(self.kw_px_mask, self.get_mask)

    @property
    def result(self):
        """The partially pixelated image"""
        return self.lazy_evaluation(self.kw_result, self.get_result)

    def get_display_ratio(self):
        """Get the display ratio from the image and canvas sizes"""
        (canvas_width, canvas_height) = self.__canvas_size
        ratio_x = dimension_display_ratio(
            self.original.width, canvas_width)
        ratio_y = dimension_display_ratio(
            self.original.height, canvas_height)
        return max(ratio_x, ratio_y)

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

    def resized_to_canvas(self, source_image):
        """Return the image resized to canvas size (or original size)"""
        if self.display_ratio > 1:
            return source_image.resize(
                (int(source_image.width / self.display_ratio),
                 int(source_image.height / self.display_ratio)),
                resample=Image.BICUBIC)
        #
        return source_image

    def get_tk_image(self, source_image):
        """Return the image resized to canvas size and
        as a PhotoImage instance for Tkinter
        """
        return ImageTk.PhotoImage(
            self.resized_to_canvas(source_image))


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

    def get_mask(self):
        """Return the mask for the pixelated image"""
        return self.mask_shape

    def get_pixelated_area(self):
        """Return a copy of the original image,
        fully pixelated
        """
        (offset_x, offset_y) = self.shape_offset
        box = (offset_x,
               offset_y,
               offset_x + self.mask_shape.width,
               offset_y + self.mask_shape.height)
        return pixelated(self.original.crop(box), tilesize=self.tilesize)

    def get_result(self):
        """Return the result
        """
        result_image = self.original.copy()
        result_image.paste(
            self.pixelated_area, box=self.shape_offset, mask=self.mask)
        return result_image


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
