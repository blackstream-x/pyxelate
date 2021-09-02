# -*- coding: utf-8 -*-

"""

pixelate.py

Module for pixelating parts of images

"""


import logging

from PIL import Image, ImageDraw


#
# Constants
#


DEFAULT_PIXELSIZE = 10


#
# Helper functions
#


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


#
# Classes
#


class ImageData:

    """Hold original image data as well as the pixelated data"""

    kw_orig = 'original image'
    kw_px_full = 'pixelated full image'
    kw_px_mask = 'pixelated image mask'
    kw_mask_shape = 'mask_shape'
    kw_result = 'resulting image'

    def __init__(self, image_path, pixelsize=DEFAULT_PIXELSIZE):
        """Allocate the internal cache"""

        self.__cache = {}
        self.__pixelsize = DEFAULT_PIXELSIZE
        self.__shapes = {}
        self.__shape_offset = (0, 0)
        self.load_image(image_path)
        self.set_pixelsize(pixelsize)
        #

    def load_image(self, image_path):
        """Load the image"""
        self.__cache[self.kw_orig] = Image.open(str(image_path))

    def set_pixelsize(self, pixelsize):
        """Set the pixelsize and delete the cached pixelated results"""
        if self.__pixelsize != pixelsize:
            self.__pixelsize = pixelsize
            self.__cache.pop(self.kw_px_full, None)
            self.__cache.pop(self.kw_result, None)
        #

    def set_shape(self, offset, shape_type, size):
        """Set the shape and delete the cached results"""
        self.__shape_offset = offset
        self.__cache.pop(self.kw_px_mask, None)
        self.__cache.pop(self.kw_result, None)
        self.__cache[self.kw_mask_shape] = self.get_cached_shape(
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
    def original(self):
        """The original image"""
        return self.__cache[self.kw_orig]

    @property
    def pixelated_full(self):
        """The fully pixelated version of the original image"""
        try:
            return self.__cache[self.kw_px_full]
        except KeyError:
            return self.__cache.setdefault(
                self.kw_px_full,
                self.get_pixelated_full_image())
        #

    @property
    def pixelated_mask(self):
        """The Mask for the pixelation"""
        try:
            return self.__cache[self.kw_px_mask]
        except KeyError:
            return self.__cache.setdefault(
                self.kw_px_mask,
                self.get_pixelated_mask())
        #

    @property
    def result(self):
        """The partially pixelated image"""
        try:
            return self.__cache[self.kw_result]
        except KeyError:
            return self.__cache.setdefault(
                self.kw_result,
                self.get_result())
        #

    def get_cached_shape(self, shape_type, size):
        """Get a cached shape or create a new one"""
        try:
            return self.__shapes[(shape_type, size)]
        except KeyError:
            pass
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
        return self.__shapes.setdefault((shape_type, size), shape_image)

    def get_pixelated_mask(self):
        """Return the mask for the pixelation
        """
        mask = Image.new('L', self.original.size, color=0)
        mask.paste(self.mask_shape, box=self.__shape_offset)
        return mask

    def get_pixelated_full_image(self):
        """Return a copy of the original image,
        fully pixelated
        """
        original_width = self.original.width
        original_height = self.original.height
        reduced_width = original_width // self.__pixelsize + 1
        reduced_height = original_height // self.__pixelsize + 1
        oversize_width = reduced_width * self.__pixelsize
        oversize_height = reduced_height * self.__pixelsize
        oversized = Image.new(
            self.original.mode,
            (oversize_width, oversize_height),
            color=most_frequent_color(self.original))
        oversized.paste(self.original)
        reduced = oversized.resize((reduced_width, reduced_height), resample=0)
        oversized = reduced.resize(
            (oversize_width, oversize_height), resample=0)
        self.__cache.pop(self.kw_result, None)
        return oversized.crop((0, 0, original_width, original_height))

    def get_result(self):
        """Return the result
        """
        result_image = self.original.copy()
        result_image.paste(
            self.pixelated_full, box=None, mask=self.pixelated_mask)
        return result_image


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python: