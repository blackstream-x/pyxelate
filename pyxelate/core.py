# -*- coding: utf-8 -*-

"""

core.py

Core application parts of the pyxelate scripts

"""


import json
import logging
import os
import pathlib
import tkinter

from tkinter import filedialog
from tkinter import messagebox

# local modules

from pyxelate import gui


#
# Constants
#


COPYRIGHT_NOTICE = """Copyright (C) 2021 Rainer Schwarzbach

This file is part of pyxelate.

pyxelate is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

pyxelate is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with pyxelate (see LICENSE).
If not, see <http://www.gnu.org/licenses/>."""

ELLIPSE = "ellipse"
RECTANGLE = "rectangle"

OVAL = "\u2b2d ellipse"
CIRCLE = "\u25cb circle"
RECT = "\u25ad rectangle"
SQUARE = "\u25a1 square"

SHAPES = {
    OVAL: ELLIPSE,
    CIRCLE: ELLIPSE,
    RECT: RECTANGLE,
    SQUARE: RECTANGLE,
}

ELLIPTIC_SHAPES = (OVAL, CIRCLE)
RECTANGULAR_SHAPES = (RECT, SQUARE)
QUADRATIC_SHAPES = (CIRCLE, SQUARE)
ALL_SHAPES = ELLIPTIC_SHAPES + RECTANGULAR_SHAPES

DEFAULT_TILESIZE = 25
MINIMUM_TILESIZE = 10
MAXIMUM_TILESIZE = 200
TILESIZE_INCREMENT = 5

MINIMUM_SELECTION_SIZE = 20
INITIAL_SELECTION_SIZE = 50

INDICATOR_OUTLINE_WIDTH = 2

POSSIBLE_INDICATOR_COLORS = (
    "white",
    "black",
    "red",
    "green",
    "blue",
    "cyan",
    "yellow",
    "magenta",
)

# Items on the canvas
TAG_IMAGE = "image"
TAG_INDICATOR = "indicator"
TAG_RUBBERBAND = "rubberband"

# Mouse drag actions (“Drag with the mouse on the canvas to …”)
MOVE_SELECTION = "move the selection"
RESIZE_SELECTION = "resize the selection"
NEW_SELECTION = "create a new selection"
MOVE_CROP_AREA = "move the crop area"
RESIZE_CROP_AREA = "resize the crop area"
NEW_CROP_AREA = "select the crop area"
PAN_ZOOMED_IMAGE = "pan the (zoomed) image"

MOUSE_DRAG_ACTIONS = {
    # all implemented drag actions with their cursors
    MOVE_SELECTION: "fleur",
    RESIZE_SELECTION: "sizing",
    NEW_SELECTION: "plus",
    NEW_CROP_AREA: "icon",
}

# Grid parameters
BUTTONS_GRID_W = dict(padx=3, pady=3, sticky=tkinter.W)
BUTTONS_GRID_E = dict(padx=3, pady=3, sticky=tkinter.E)
GRID_FULLWIDTH = dict(padx=4, pady=2, sticky=tkinter.E + tkinter.W)
WITH_BORDER = dict(borderwidth=2, padx=5, pady=5, relief=tkinter.GROOVE)


#
# Classes
#


class Namespace(dict):

    """A dict subclass that exposes its items as attributes.

    Warning: Namespace instances only have direct access to the
    attributes defined in the visible_attributes tuple
    """

    visible_attributes = ("items", "update")

    def __repr__(self):
        """Object representation"""
        return "{0}({1})".format(type(self).__name__, super().__repr__())

    def __dir__(self):
        """Members sequence"""
        return tuple(self)

    def __getattribute__(self, name):
        """Access a visible attribute
        or return an existing dict member
        """
        if name in type(self).visible_attributes:
            return object.__getattribute__(self, name)
        #
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(
                "{0!r} object has no attribute {1!r}".format(
                    type(self).__name__, name
                )
            ) from error
        #

    def __setattr__(self, name, value):
        """Set an attribute"""
        self[name] = value

    def __delattr__(self, name):
        """Delete an attribute"""
        del self[name]

    def update(self, **kwargs):
        """Add attributes from kwargs"""
        for key, value in kwargs.items():
            self[key] = value
        #


class FrozenSelection:

    """Store a selection state"""

    variables = (
        "center_x",
        "center_y",
        "width",
        "height",
        "shape",
        "tilesize",
    )

    def __init__(self, selection):
        """Initialize values from the variables in the
        provided selection Namespace of tkinter variables
        """
        self.original_values = {
            key: selection[key].get() for key in self.variables
        }
        self.effective_values = dict(self.original_values)
        if self.effective_values["shape"] in QUADRATIC_SHAPES:
            self.effective_values["height"] = self.effective_values["width"]
        #

    def restore_to(self, px_image):
        """Restore values to the variables in the
        provided px_image Namespace of tkinter variables
        """
        for (key, value) in self.original_values.items():
            px_image[key].set(value)
        #

    def __eq__(self, other):
        """Return True if the effective values are equal"""
        for (key, value) in self.effective_values.items():
            if value != other.effective_values[key]:
                return False
            #
        #
        return True

    def __str__(
        self,
    ):
        """Effective selection representation"""
        return repr(tuple(self.effective_values.values()))


class InterfacePlugin:

    """Class instantiated with the UserInterface
    to access its varuables and widgets
    """

    def __init__(self, application):
        """Store the application"""
        self.application = application
        self.tkvars = application.tkvars
        self.vars = application.vars
        self.widgets = application.widgets
        self.main_window = application.main_window


class Callbacks(InterfacePlugin):

    """Callback methods"""

    drag_registry = {
        MOVE_SELECTION: "move_sel",
        RESIZE_SELECTION: "resize_sel",
        NEW_SELECTION: "new_sel",
        NEW_CROP_AREA: "new_crop",
    }

    def __clicked_inside_indicator(self, event):
        """Return True if the click was inside the indicator"""
        try:
            (left, top, right, bottom) = self.widgets.canvas.bbox(
                TAG_INDICATOR
            )
        except TypeError as error:
            logging.debug(error)
            return False
        #
        x_position = event.x
        y_position = event.y
        if left <= x_position <= right and top <= y_position <= bottom:
            if self.tkvars.selection.shape in RECTANGULAR_SHAPES:
                return True
            #
            # Apply the standard ellipse equation
            # (see https://en.wikipedia.org/wiki/Ellipse#Standard_equation)
            # to check if the event was inside or outside the ellipse
            center_x = (left + right) / 2
            center_y = (top + bottom) / 2
            relative_x = x_position - center_x
            relative_y = y_position - center_y
            semi_x = center_x - left
            semi_y = center_y - top
            if (relative_x ** 2 / semi_x ** 2) + (
                relative_y ** 2 / semi_y ** 2
            ) <= 1:
                return True
            #
        #
        return False

    def __get_translated_bbox(self, tag_name):
        """Get the bbox coordinates
        translated from display to image size.
        and return them in a Namespace instance.
        """
        (left, top, right, bottom) = self.widgets.canvas.bbox(tag_name)
        return Namespace(
            left=self.vars.image.from_display_size(left),
            top=self.vars.image.from_display_size(top),
            right=self.vars.image.from_display_size(right),
            bottom=self.vars.image.from_display_size(bottom),
        )

    def __get_translated_coordinates(self, tag_name):
        """Calculate dimensions and center
        from translated bbox coordinates
        and return them in a Namespace instance.
        as a Namespace containing dimensions and center.
        """
        translated = self.__get_translated_bbox(tag_name)
        return Namespace(
            width=translated.right - translated.left,
            height=translated.bottom - translated.top,
            center_x=(translated.left + translated.right) // 2,
            center_y=(translated.top + translated.bottom) // 2,
        )

    def get_traced_intvar(self, method_name, value=None):
        """Return a traced IntVar() calling
        this intance's method methodname
        """
        return gui.traced_variable(
            getattr(self, method_name), constructor=tkinter.IntVar, value=value
        )

    def get_traced_stringvar(self, method_name, value=None):
        """Return a traced IntVar() calling
        this intance's method methodname
        """
        return gui.traced_variable(getattr(self, method_name), value=value)

    def next_drag_action(self, *unused_arguments):
        """Select the next supported drag action"""
        all_drag_actions = list(MOUSE_DRAG_ACTIONS)
        old_drag_action = self.tkvars.drag_action.get()
        current_index = all_drag_actions.index(old_drag_action)
        while current_index < len(all_drag_actions) - 1:
            current_index = current_index + 1
            new_drag_action = all_drag_actions[current_index]
            if new_drag_action in self.vars.supported_drag_actions:
                self.tkvars.drag_action.set(new_drag_action)
                break
            #
        #

    def previous_drag_action(self, *unused_arguments):
        """Select the previous supported drag action"""
        all_drag_actions = list(MOUSE_DRAG_ACTIONS)
        old_drag_action = self.tkvars.drag_action.get()
        current_index = all_drag_actions.index(old_drag_action)
        while current_index:
            current_index = current_index - 1
            new_drag_action = all_drag_actions[current_index]
            if new_drag_action in self.vars.supported_drag_actions:
                self.tkvars.drag_action.set(new_drag_action)
                break
            #
        #

    def drag_move(self, event):
        """Handle dragging"""
        return self.__execute_drag_method("move", event)

    def drag_start(self, event):
        """Begin drag"""
        return self.__execute_drag_method("start", event)

    def drag_stop(self, event):
        """End drag"""
        return self.__execute_drag_method("stop", event)

    def __execute_drag_method(self, event_type, event):
        """Execute the method for the specified event type,
        reading the drag_action variable
        """
        prefix = self.drag_registry[self.tkvars.drag_action.get()]
        method = getattr(self, f"{prefix}_drag_{event_type}")
        return method(event)

    def move_sel_drag_move(self, event):
        """Handle dragging of the indicator"""
        if self.vars.drag_data.item != TAG_INDICATOR:
            return False
        #
        # compute how much the mouse has moved
        current_x = event.x
        current_y = event.y
        delta_x = current_x - self.vars.drag_data.x
        delta_y = current_y - self.vars.drag_data.y
        # move the object the appropriate amount
        self.widgets.canvas.move(self.vars.drag_data.item, delta_x, delta_y)
        # record the new position
        self.vars.drag_data.x = current_x
        self.vars.drag_data.y = current_y
        # Update the selection (position only)
        new_position = self.__get_translated_coordinates(TAG_INDICATOR)
        self.application.update_selection(
            center_x=new_position.center_x, center_y=new_position.center_y
        )
        self.application.pixelate_selection()
        return True

    def move_sel_drag_start(self, event):
        """Begin drag of the indicator"""
        if not self.__clicked_inside_indicator(event):
            return False
        #
        # record the item and its location
        self.vars.drag_data.item = TAG_INDICATOR
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def move_sel_drag_stop(self, *unused_event):
        """End drag of an object"""
        if self.vars.drag_data.item != TAG_INDICATOR:
            return False
        #
        # reset the drag information
        self.vars.drag_data.item = None
        self.vars.drag_data.x = 0
        self.vars.drag_data.y = 0
        # Trigger the selection change explicitly
        self.update_selection()
        return True

    def new_sel_drag_move(self, event):
        """Drag a new selection"""
        return self.__new_selection_drag_move(
            event.x, event.y, self.vars.drag_data.x, self.vars.drag_data.y
        )

    def new_sel_drag_start(self, event):
        """Begin dragging for a new selection"""
        # record the item and its location
        self.vars.drag_data.item = TAG_RUBBERBAND
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def new_sel_drag_stop(self, *unused_event):
        """End drag for a new selection"""
        try:
            new_selection = self.__get_translated_coordinates(TAG_RUBBERBAND)
        except TypeError:
            # No selection dragged (i.e. click without dragging)
            return False
        #
        self.widgets.canvas.delete(TAG_RUBBERBAND)
        # The selection has already been updated while dragging,
        # we only need to adjust it to the minimum sizes if necessary.
        adjusted_dimensions = {}
        for dimension in ("width", "height"):
            if new_selection[dimension] < MINIMUM_SELECTION_SIZE:
                adjusted_dimensions[dimension] = MINIMUM_SELECTION_SIZE
            #
        #
        if adjusted_dimensions:
            self.application.update_selection(**adjusted_dimensions)
        #
        # Trigger the selection change explicitly
        self.update_selection()
        return True

    def new_crop_drag_move(self, event):
        """Drag a new crop area"""
        [left, right] = sorted((event.x, self.vars.drag_data.x))
        [top, bottom] = sorted((event.y, self.vars.drag_data.y))
        self.widgets.canvas.delete(TAG_RUBBERBAND)
        current_color = self.tkvars.indicator.drag_color.get()
        self.widgets.canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            outline=current_color,
            tags=TAG_RUBBERBAND,
        )
        return True

    def new_crop_drag_start(self, event):
        """Begin dragging for a new crop area"""
        self.vars.drag_data.item = TAG_RUBBERBAND
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def new_crop_drag_stop(self, *unused_event):
        """End drag for a new crop area"""
        try:
            crop_box = self.__get_translated_bbox(TAG_RUBBERBAND)
        except TypeError:
            # No selection dragged (i.e. click without dragging)
            return False
        #
        self.widgets.canvas.delete(TAG_RUBBERBAND)
        # previous_crop_area = self.vars.crop_area
        self.vars.crop_area.update(**crop_box)
        # Switch the "crop" checkbox to "on",
        # triggering  the toggle_crop_display method implicitly
        # TODO: error handling
        self.tkvars.crop.set(1)
        return True

    def resize_sel_drag_move(self, event):
        """Drag for selection resize"""
        delta_x = event.x - self.vars.drag_data.x
        delta_y = event.y - self.vars.drag_data.y
        current_x = self.vars.drag_data.var_x + delta_x
        current_y = self.vars.drag_data.var_y + delta_y
        return self.__new_selection_drag_move(
            current_x,
            current_y,
            self.vars.drag_data.anchor_x,
            self.vars.drag_data.anchor_y,
        )

    def resize_sel_drag_start(self, event):
        """Begin dragging for selection resize"""
        # record the item and its location
        self.vars.drag_data.item = TAG_RUBBERBAND
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        (left, top, right, bottom) = self.widgets.canvas.bbox(TAG_INDICATOR)
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        # Anchor at the opposite side, seen from the selection center
        if event.x > center_x:
            self.vars.drag_data.anchor_x = left
            self.vars.drag_data.var_x = right
        else:
            self.vars.drag_data.var_x = left
            self.vars.drag_data.anchor_x = right
        #
        if event.y > center_y:
            self.vars.drag_data.anchor_y = top
            self.vars.drag_data.var_y = bottom
        else:
            self.vars.drag_data.var_y = top
            self.vars.drag_data.anchor_y = bottom
        #
        return True

    resize_sel_drag_stop = new_sel_drag_stop

    def __new_selection_drag_move(
        self, current_x, current_y, origin_x, origin_y
    ):
        """Move "rubber frame" of a new or resized selection"""
        [left, right] = sorted((current_x, origin_x))
        [top, bottom] = sorted((current_y, origin_y))
        # Respect "quadratic" shapes
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            width = right - left
            height = bottom - top
            new_size = max(width, height)
            if new_size == height:
                if current_x == left:
                    left = right - new_size
                else:
                    right = left + new_size
                #
            elif new_size == width:
                if current_y == top:
                    top = bottom - new_size
                else:
                    bottom = top + new_size
                #
            #
        #
        # Draw a new selection outline
        self.widgets.canvas.delete(TAG_RUBBERBAND)
        outer_dash = (1, 1)
        shape = self.tkvars.selection.shape.get()
        current_color = self.tkvars.indicator.drag_color.get()
        if shape in ELLIPTIC_SHAPES:
            outer_dash = (5, 5)
        #
        self.widgets.canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            dash=outer_dash,
            outline=current_color,
            tags=TAG_RUBBERBAND,
        )
        if shape in ELLIPTIC_SHAPES:
            self.widgets.canvas.create_oval(
                left,
                top,
                right,
                bottom,
                dash=(1, 1),
                outline=current_color,
                tags=TAG_RUBBERBAND,
            )
        # Update the selection
        self.application.update_selection(
            **self.__get_translated_coordinates(TAG_RUBBERBAND)
        )
        return True

    def redraw_indicator(self, *unused_arguments):
        """Trigger redrawing of the indicator"""
        try:
            self.application.draw_indicator()
        except AttributeError as error:
            logging.warning("%s", error)
        #

    def reset_crop_area(self):
        """Reset the crop area to the full image
        and set the crop checkbox to "off"
        """
        try:
            (width, height) = self.vars.image.size
        except AttributeError as error:
            logging.error("Could not reset the crop area: %s", error)
        else:
            self.vars.crop_area.update(
                left=0, top=0, right=width, bottom=height
            )
        #
        self.tkvars.crop.set(0)

    def set_canvas_cursor(self, *unused_arguments):
        """Set the cursor shown over the canvas
        to the maching cursor for the currently active drag action
        """
        gui.reconfigure_widget(
            self.widgets.canvas,
            cursor=MOUSE_DRAG_ACTIONS[self.tkvars.drag_action.get()],
        )

    def toggle_crop_display(self, *unused_arguments):
        """Toggle crop area preview update"""
        if not self.vars.trace:
            return
        #
        if self.tkvars.crop.get():
            self.vars.image.set_crop_area(self.vars.crop_area)
            self.tkvars.drag_action.set(NEW_CROP_AREA)
        else:
            self.vars.image.remove_crop_area()
        #
        self.toggle_preview()

    def toggle_preview(self, *unused_arguments):
        """Trigger preview update"""
        try:
            self.application.show_image()
        except AttributeError as error:
            logging.warning("%s", error)
        #

    def toggle_preview_checkbutton(self, *unused_arguments):
        """Trigger preview checkbutton"""
        if self.vars.disable_key_events:
            return
        #
        try:
            self.widgets.preview_active.toggle()
        except AttributeError as error:
            logging.warning("%s", error)
        else:
            self.toggle_preview()
        #

    def update_buttons(self, *unused_arguments):
        """Trigger button state updates in subclasses"""
        raise NotImplementedError

    def update_selection(self, *unused_arguments):
        """Trigger update after selection changed"""
        if self.vars.trace:
            self.application.pixelate_selection()
            self.application.draw_indicator()
        #
        self.application.toggle_height()


class Panels(InterfacePlugin):

    """Panel and panel component methods"""

    def component_shape_settings(
        self, settings_frame, allowed_shapes=ALL_SHAPES
    ):
        """Show the shape part of the settings frame"""
        self.application.heading_with_help_button(settings_frame, "Selection")
        label = tkinter.Label(settings_frame, text="Tile size:")
        tilesize = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_TILESIZE,
            to=MAXIMUM_TILESIZE,
            increment=TILESIZE_INCREMENT,
            justify=tkinter.RIGHT,
            state="readonly",
            width=4,
            textvariable=self.tkvars.selection.tilesize,
        )
        #
        label.grid(sticky=tkinter.W, column=0)
        tilesize.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(settings_frame, text="Shape:")
        shape_opts = tkinter.OptionMenu(
            settings_frame, self.tkvars.selection.shape, *allowed_shapes
        )
        label.grid(sticky=tkinter.W, column=0)
        shape_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(settings_frame, text="Width:")
        width = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_SELECTION_SIZE,
            to=self.vars.image.original.width,
            justify=tkinter.RIGHT,
            state="readonly",
            width=4,
            textvariable=self.tkvars.selection.width,
        )
        label.grid(sticky=tkinter.W, column=0)
        width.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(settings_frame, text="Height:")
        self.widgets.height = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_SELECTION_SIZE,
            to=self.vars.image.original.height,
            justify=tkinter.RIGHT,
            state="readonly",
            width=4,
            textvariable=self.tkvars.selection.height,
        )
        label.grid(sticky=tkinter.W, column=0)
        self.widgets.height.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(settings_frame, text="Center at x:")
        center_x = tkinter.Spinbox(
            settings_frame,
            from_=-self.vars.image.original.width,
            to=2 * self.vars.image.original.width,
            justify=tkinter.RIGHT,
            width=4,
            textvariable=self.tkvars.selection.center_x,
        )
        label_sep = tkinter.Label(settings_frame, text=", y:")
        center_y = tkinter.Spinbox(
            settings_frame,
            from_=-self.vars.image.original.height,
            to=2 * self.vars.image.original.height,
            justify=tkinter.RIGHT,
            width=4,
            textvariable=self.tkvars.selection.center_y,
        )
        label.grid(sticky=tkinter.W, column=0)
        center_x.grid(sticky=tkinter.W, row=gui.grid_row_of(label), column=1)
        label_sep.grid(sticky=tkinter.W, row=gui.grid_row_of(label), column=2)
        center_y.grid(sticky=tkinter.W, row=gui.grid_row_of(label), column=3)

    def component_file_info(self, parent_frame):
        """Show information about the current file"""
        self.application.heading_with_help_button(
            parent_frame, "Original file"
        )
        label = tkinter.Label(parent_frame, textvariable=self.tkvars.file_name)
        label.grid(sticky=tkinter.W, columnspan=5)
        choose_button = tkinter.Button(
            parent_frame,
            text="Choose another file",
            command=self.application.open_file,
        )
        choose_button.grid(sticky=tkinter.W, columnspan=4)

    def component_image_info(self, parent_frame):
        """Show information about the current image"""
        raise NotImplementedError

    def component_image_on_canvas(self):
        """Show the image on a canvas"""
        image_frame = tkinter.Frame(self.widgets.action_area, **WITH_BORDER)
        self.widgets.canvas = tkinter.Canvas(
            image_frame,
            width=self.vars.canvas_width,
            height=self.vars.canvas_height,
        )
        self.vars.tk_image = self.vars.image.tk_original
        self.widgets.canvas.create_image(
            0, 0, image=self.vars.tk_image, anchor=tkinter.NW, tags=TAG_IMAGE
        )
        self.widgets.canvas.grid()
        self.application.callbacks.set_canvas_cursor()
        self.application.draw_indicator()
        self.application.pixelate_selection()
        self.vars.trace = True
        # add bindings to create a new selector
        self.widgets.canvas.bind(
            "<ButtonPress-1>", self.application.callbacks.drag_start
        )
        self.widgets.canvas.bind(
            "<ButtonRelease-1>", self.application.callbacks.drag_stop
        )
        self.widgets.canvas.bind(
            "<B1-Motion>", self.application.callbacks.drag_move
        )
        image_frame.grid(row=1, column=0, rowspan=3, **GRID_FULLWIDTH)

    def component_indicator_colours(self, parent_frame):
        """Show colours selections"""
        self.application.heading_with_help_button(parent_frame, "Colours")
        label = tkinter.Label(parent_frame, text="Indicator outline:")
        color_opts = tkinter.OptionMenu(
            parent_frame,
            self.tkvars.indicator.color,
            *POSSIBLE_INDICATOR_COLORS,
        )
        label.grid(sticky=tkinter.W, column=0)
        color_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(parent_frame, text="Rubberband:")
        color_opts = tkinter.OptionMenu(
            parent_frame,
            self.tkvars.indicator.drag_color,
            *POSSIBLE_INDICATOR_COLORS,
        )
        label.grid(sticky=tkinter.W, column=0)
        color_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )

    def component_select_area(
        self,
        allowed_shapes=ALL_SHAPES,
    ):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        self.component_image_on_canvas()
        self.sidebar_settings(
            allowed_shapes=allowed_shapes,
        )

    def component_select_drag_action(
        self, parent_frame, supported_actions=tuple(MOUSE_DRAG_ACTIONS)
    ):
        """Show colours selections"""
        gui.Heading(
            parent_frame,
            text="Drag on the canvas to … (please select):",
            sticky=tkinter.W,
            columnspan=5,
        )
        self.vars.supported_drag_actions.clear()
        for single_drag_action in supported_actions:
            current_action = tkinter.Radiobutton(
                parent_frame,
                anchor=tkinter.W,
                cursor=MOUSE_DRAG_ACTIONS[single_drag_action],
                text=single_drag_action,
                value=single_drag_action,
                variable=self.tkvars.drag_action,
            )
            current_action.grid(sticky=tkinter.W, column=0, columnspan=5)
            self.vars.supported_drag_actions.append(single_drag_action)
        #

    def component_show_preview(self, parent_frame, subject="pixelation"):
        """Show the "Show preview" checkbutton"""
        self.application.heading_with_help_button(parent_frame, "Show preview")
        self.widgets.update(
            preview_active=tkinter.Checkbutton(
                parent_frame,
                anchor=tkinter.W,
                command=self.application.show_image,
                text=f"Preview {subject}",
                variable=self.tkvars.show_preview,
                indicatoron=1,
                underline=0,
            )
        )
        self.widgets.preview_active.grid(
            sticky=tkinter.W,
            column=0,
            columnspan=5,
        )

    def component_zoom_factor(self, parent_frame):
        """Show the zoom factor according to display ratio"""
        display_ratio = self.vars.image.display_ratio
        if display_ratio == int(display_ratio):
            factor = int(display_ratio)
        else:
            factor = float(display_ratio)
        #
        percentage = round(100 / display_ratio, 2)
        if percentage == int(percentage):
            percentage = int(percentage)
        #
        if display_ratio > 1:
            zoom_factor = f"{percentage}% (1:{factor})"
        else:
            zoom_factor = "100% (1:1)"
        #
        label = tkinter.Label(parent_frame, text="Zoom factor:")
        label.grid(sticky=tkinter.W, column=0)
        zoom_display = tkinter.Label(parent_frame, text=zoom_factor)
        zoom_display.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=4,
        )

    def sidebar_settings(
        self,
        allowed_shapes=ALL_SHAPES,
        preview_subject="pixelation",
    ):
        """Show the settings sidebar"""
        settings_frame = tkinter.Frame(self.widgets.action_area, **WITH_BORDER)
        self.component_file_info(settings_frame)
        self.component_image_info(settings_frame)
        self.component_select_drag_action(settings_frame)
        self.component_shape_settings(
            settings_frame,
            allowed_shapes=allowed_shapes,
        )
        self.component_show_preview(settings_frame, subject=preview_subject)
        settings_frame.columnconfigure(4, weight=100)
        settings_frame.grid(row=0, column=1, rowspan=2, **GRID_FULLWIDTH)
        self.application.toggle_height()


class UserInterface:

    """GUI using tkinter (base class for pyxelate)"""

    phase_open_file = "open_file"
    phases = (phase_open_file,)
    panel_names = {}
    looped_panels = set()

    action_class = InterfacePlugin
    callback_class = Callbacks
    panel_class = Panels
    post_panel_action_class = InterfacePlugin
    rollback_class = InterfacePlugin

    script_name = "<module pyxelate.app>"
    version = "<version>"
    homepage = "https://github.com/blackstream-x/pyxelate"
    copyright_notice = COPYRIGHT_NOTICE

    file_type = "image file"

    def __init__(
        self,
        file_path,
        options,
        script_path,
        canvas_width=900,
        canvas_height=640,
    ):
        """Build the GUI"""
        self.options = options
        self.main_window = tkinter.Tk()
        self.main_window.title(f"pyxelate: {self.script_name}")
        self.vars = Namespace(
            current_panel=None,
            errors=[],
            panel_stack=[],
            post_panel_methods={},
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            tk_image=None,
            image=None,
            original_path=file_path,
            trace=False,
            unapplied_changes=False,
            loop_counter={key: [] for key in self.looped_panels},
            undo_buffer=[],
            supported_drag_actions=[],
            drag_data=Namespace(
                x=0, y=0, anchor_x=0, anchor_y=0, var_x=0, var_y=0, item=None
            ),
            crop_area=Namespace(left=0, top=0, right=0, bottom=0),
            disable_key_events=False,
        )
        self.tkvars = Namespace()
        self.widgets = Namespace(
            action_area=None,
            # buttons_area=None,
            canvas=None,
            height=None,
            preview_active=None,
        )
        self.actions = self.action_class(self)
        self.callbacks = self.callback_class(self)
        self.panels = self.panel_class(self)
        self.post_panel_actions = self.post_panel_action_class(self)
        self.rollbacks = self.rollback_class(self)
        # Fill self.tkvars after the callbaks plugin has been initialized
        self.tkvars.update(
            file_name=tkinter.StringVar(),
            show_preview=tkinter.IntVar(),
            # Update the selection
            # after change of any of the following parameters
            selection=Namespace(
                center_x=self.callbacks.get_traced_intvar("update_selection"),
                center_y=self.callbacks.get_traced_intvar("update_selection"),
                width=self.callbacks.get_traced_intvar("update_selection"),
                height=self.callbacks.get_traced_intvar("update_selection"),
                shape=self.callbacks.get_traced_stringvar("update_selection"),
                tilesize=self.callbacks.get_traced_intvar("update_selection"),
            ),
            # Redraw the indicator
            # each time the outline color is changed
            indicator=Namespace(
                color=self.callbacks.get_traced_stringvar(
                    "redraw_indicator", value="red"
                ),
                drag_color=tkinter.StringVar(),
            ),
            crop=self.callbacks.get_traced_intvar(
                "toggle_crop_display", value=0
            ),
            drag_action=self.callbacks.get_traced_stringvar(
                "set_canvas_cursor", value=MOVE_SELECTION
            ),
        )
        self.tkvars.indicator.drag_color.set("blue")
        self.additional_variables()
        self.additional_widgets()
        #
        # Load help file
        with open(
            script_path.parent / "docs" / f"{script_path.stem}_help.json",
            mode="rt",
            encoding="utf-8",
        ) as help_file:
            self.vars.help = json.load(help_file)
        #
        self.open_file(keep_existing=True, quit_on_empty_choice=True)
        self.main_window.protocol("WM_DELETE_WINDOW", self.quit)
        self.main_window.mainloop()

    def additional_variables(self):
        """Subclass-specific post-initialization
        (additional variables)
        """
        raise NotImplementedError

    def additional_widgets(self):
        """Subclass-specific post-initialization
        (additional widgets)
        """
        raise NotImplementedError

    def execute_post_panel_action(self):
        """Execute the post panel action for the current panel"""
        try:
            method = self.vars.post_panel_methods.pop(self.vars.current_panel)
        except KeyError:
            logging.debug(
                "Post-panel action for %r not defined or already executed.",
                self.vars.current_panel,
            )
        else:
            method()
        #

    def open_file(
        self, keep_existing=False, preset_path=None, quit_on_empty_choice=False
    ):
        """Open a file via file dialog"""
        self.vars.update(current_panel=self.phase_open_file)
        file_path = self.vars.original_path
        if preset_path:
            if not preset_path.is_dir():
                initial_dir = str(preset_path.parent)
            #
        elif file_path:
            initial_dir = str(file_path.parent)
        else:
            initial_dir = os.getcwd()
        #
        while True:
            if not keep_existing or file_path is None:
                self.vars.update(disable_key_events=True)
                selected_file = filedialog.askopenfilename(
                    initialdir=initial_dir,
                    parent=self.main_window,
                    title=f"Load a {self.file_type}",
                )
                self.vars.update(disable_key_events=False)
                if not selected_file:
                    if quit_on_empty_choice:
                        self.quit()
                    #
                    return
                #
                file_path = pathlib.Path(selected_file)
            #
            # check for a supported file type,
            # and show an error dialog and retry
            # if the selected file is not an image
            if not self.check_file_type(file_path):
                messagebox.showerror(
                    "Unsupported file type",
                    f"{file_path.name!r} is not a supported file.",
                    icon=messagebox.ERROR,
                )
                initial_dir = str(file_path.parent)
                file_path = None
                continue
            #
            if self.vars.unapplied_changes or self.vars.undo_buffer:
                confirmation = messagebox.askokcancel(
                    "Unsaved Changes",
                    "Discard the chages made to"
                    f" {self.vars.original_path.name!r}?",
                    icon=messagebox.WARNING,
                )
                if not confirmation:
                    return
                #
            #
            # Set original_path and read image data
            try:
                self.load_file(file_path)
            except (OSError, ValueError) as error:
                messagebox.showerror(
                    "Load error", str(error), icon=messagebox.ERROR
                )
                initial_dir = str(file_path.parent)
                file_path = None
                continue
            #
            break
        #
        self.vars.undo_buffer.clear()
        self.next_panel()

    def check_file_type(self, file_path):
        """Return True if the file is a supported file,
        False if not
        """
        raise NotImplementedError

    def heading_with_help_button(
        self,
        parent_frame,
        subject,
        heading_column_span=4,
        parent_window=None,
    ):
        """A heading with an adjacent help button"""
        heading = gui.Heading(
            parent_frame,
            text=f"{subject}:",
            sticky=tkinter.W,
            columnspan=heading_column_span,
        )

        # Inner function for the "extra arguments" trick, see
        # <https://tkdocs.com/shipman/extra-args.html>
        def show_help(self=self, parent_window=parent_window):
            return self.show_help(topic=subject, parent_window=parent_window)

        #
        help_button = tkinter.Button(
            parent_frame,
            # text='\u2753',
            text="?",
            command=show_help,
        )
        help_button.grid(
            row=gui.grid_row_of(heading),
            column=heading_column_span,
            sticky=tkinter.E,
        )

    def load_file(self, file_path):
        """Load the file"""
        raise NotImplementedError

    def draw_indicator(self, stipple=None):
        """Draw the pixelation selector on the canvas,
        its coordinates determined by the px_* variables
        """
        canvas = self.widgets.canvas
        if not canvas:
            return
        #
        width = self.vars.image.to_display_size(
            self.tkvars.selection.width.get()
        )
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            height = width
        else:
            height = self.vars.image.to_display_size(
                self.tkvars.selection.height.get()
            )
        #
        center_x = self.vars.image.to_display_size(
            self.tkvars.selection.center_x.get()
        )
        center_y = self.vars.image.to_display_size(
            self.tkvars.selection.center_y.get()
        )
        left = center_x - width // 2
        right = left + width
        top = center_y - height // 2
        bottom = top + height
        shape = self.tkvars.selection.shape.get()
        canvas.delete(TAG_INDICATOR)
        if shape in ELLIPTIC_SHAPES:
            create_widget = canvas.create_oval
        elif shape in RECTANGULAR_SHAPES:
            create_widget = canvas.create_rectangle
        #
        current_color = self.tkvars.indicator.color.get()
        appearance = dict(
            width=INDICATOR_OUTLINE_WIDTH,
            outline=current_color,
            tags=TAG_INDICATOR,
        )
        if stipple:
            appearance.update(width=1, fill=current_color, stipple=stipple)
        #
        create_widget(left, top, right, bottom, **appearance)

    def pixelate_selection(self):
        """Apply the pixelation to the image and update the preview"""
        self.vars.image.set_tilesize(self.tkvars.selection.tilesize.get())
        width = self.tkvars.selection.width.get()
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            height = width
        else:
            height = self.tkvars.selection.height.get()
        #
        self.vars.image.set_shape(
            (
                self.tkvars.selection.center_x.get(),
                self.tkvars.selection.center_y.get(),
            ),
            SHAPES[self.tkvars.selection.shape.get()],
            (width, height),
        )
        self.show_image()

    def save_file(self):
        """Save as the selected file,
        return True if the file was saved
        """
        raise NotImplementedError

    def set_default_selection(self, tilesize=DEFAULT_TILESIZE):
        """Set default selection parameters from the following:
        shape: oval,
        width: 20% of the image width,
        height: same as width,
        position: image center
        """
        (im_width, im_height) = self.vars.image.original.size
        sel_width = self.tkvars.selection.width.get()
        if not sel_width:
            # Set initial selection width to 20% of image width
            sel_width = max(INITIAL_SELECTION_SIZE, round(im_width / 5))
        #
        sel_height = self.tkvars.selection.height.get()
        if not sel_height:
            sel_height = sel_width
        #
        center_x = self.tkvars.selection.center_x.get() or im_width // 2
        center_y = self.tkvars.selection.center_y.get() or im_height // 2
        self.update_selection(
            center_x=center_x,
            center_y=center_y,
            width=min(sel_width, im_width),
            height=min(sel_height, im_height),
            shape=self.tkvars.selection.shape.get() or CIRCLE,
            tilesize=self.tkvars.selection.tilesize.get() or tilesize,
        )

    def show_image(self):
        """Show image or preview according to the show_preview setting"""
        canvas = self.widgets.canvas
        if not canvas:
            return
        #
        canvas.delete(TAG_IMAGE)
        if self.tkvars.show_preview.get():
            self.vars.update(
                tk_image=self.vars.image.get_tk_image(self.vars.image.result)
            )
        else:
            self.vars.update(tk_image=self.vars.image.tk_original)
        #
        canvas.create_image(
            0, 0, image=self.vars.tk_image, anchor=tkinter.NW, tags=TAG_IMAGE
        )
        canvas.tag_lower(TAG_IMAGE, TAG_INDICATOR)

    def jump_to_panel(self, panel_name):
        """Jump to the specified panel
        after executing its action method
        """
        method_display = f"Action method for panel {panel_name!r}"
        try:
            action_method = getattr(self.actions, panel_name)
        except AttributeError:
            logging.debug("%s is undefined", method_display)
        else:
            try:
                action_method()
            except NotImplementedError:
                self.vars.errors.append(
                    f"{method_display} has not been implemented yet"
                )
            except ValueError as error:
                self.vars.errors.append(str(error))
            #
        #
        self.vars.update(current_phase=panel_name)
        self.__show_panel()

    def next_panel(self, *unused_arguments):
        """Go to the next panel,
        executing the old panel’s post-panel action mrthod,
        and then the new panel’s (pre-panel) action method
        before showing the new panel
        """
        self.execute_post_panel_action()
        self.vars.panel_stack.append(self.vars.current_panel)
        if self.vars.current_panel in self.looped_panels:
            panel_name = self.vars.current_panel
            self.vars.loop_counter[panel_name].append(False)
        else:
            current_index = self.phases.index(self.vars.current_panel)
            next_index = current_index + 1
            try:
                panel_name = self.phases[next_index]
            except IndexError:
                self.vars.errors.append(
                    f"Phase number #{next_index} out of range"
                )
            #
        #
        self.jump_to_panel(panel_name)

    def previous_panel(self):
        """Go to the previous panel, executing the current panel’s
        rollback method before.
        """
        panel_name = self.vars.current_panel
        phase_index = self.phases.index(panel_name)
        method_display = (
            f"Rollback method for panel #{phase_index} ({panel_name})"
        )
        try:
            rollback_method = getattr(self.rollbacks, panel_name)
        except AttributeError:
            logging.warning("%s is undefined", method_display)
        else:
            try:
                rollback_method()
            except NotImplementedError:
                self.vars.errors.append(
                    f"{method_display} has not been implemented yet"
                )
            #
            self.vars.update(current_phase=self.vars.panel_stack.pop())
        #
        self.__show_panel()

    def pre_quit_check(self):
        """Pre-quit checks eg. for files to save.
        If this method of an inherited class returns False,
        the application will NOT exit,
        """
        raise NotImplementedError

    def quit(self, event=None):
        """Exit the application"""
        del event
        if self.pre_quit_check():
            self.main_window.destroy()
        #

    def show_additional_buttons(self, buttons_area):
        """Additional buttons for the pixelate_image script.
        Return the number of rows (= the row index for th last row)
        """
        raise NotImplementedError

    def __show_about(self):
        """Show information about the application
        in a modal dialog
        """
        gui.InfoDialog(
            self.main_window,
            (
                self.script_name,
                f"Version: {self.version}\nProject homepage: {self.homepage}",
            ),
            ("Copyright/License:", self.copyright_notice),
            title="About…",
        )
        #

    def __show_errors(self):
        """Show errors if there are any"""
        if self.vars.errors:
            gui.InfoDialog(
                self.main_window,
                ("Errors:", "\n".join(self.vars.errors)),
                title="Errors occurred!",
            )
            self.vars.errors.clear()
        #

    def show_help(self, topic=None, parent_window=None):
        """Show help for the provided topic.
        The topic defaults to the current panel.
        """
        if topic is None:
            topic = self.vars.current_panel
            title = f"Panel {self.panel_names[topic]!r}"
        else:
            title = topic
        #
        try:
            info_sequence = list(self.vars.help[topic].items())
        except AttributeError:
            # Not a hash -> generate a heading
            info_sequence = [(None, self.vars.help[topic])]
        except KeyError:
            info_sequence = [("Error:", f"No help for {title} available yet")]
        #
        if parent_window is None:
            parent_window = self.main_window
        #
        gui.InfoDialog(parent_window, *info_sequence, title=f"Help ({title})")

    def __show_panel(self):
        """Show a panel.
        Add the "Previous", "Next", "Choose another relase",
        "About" and "Quit" buttons at the bottom
        """
        try:
            self.widgets.action_area.destroy()
        except AttributeError:
            pass
        #
        self.widgets.update(action_area=tkinter.Frame(self.main_window))
        try:
            panel_method = getattr(self.panels, self.vars.current_phase)
        except AttributeError:
            self.vars.errors.append(
                f"Panel for Phase {self.vars.current_phase!r}"
                " has not been implemented yet,"
                f" going back to phase {self.vars.current_panel!r}."
            )
            self.vars.update(current_phase=self.vars.current_panel)
            panel_method = getattr(self.panels, self.vars.current_phase)
        else:
            self.vars.update(current_panel=self.vars.current_phase)
        #
        self.__show_errors()
        logging.debug("Showing panel %r", self.vars.current_panel)
        try:
            self.vars.post_panel_methods[self.vars.current_phase] = getattr(
                self.post_panel_actions, self.vars.current_phase
            )
        except AttributeError:
            logging.debug(
                "No post-panel method defined for %r",
                self.vars.current_panel,
            )
        #
        gui.Heading(
            self.widgets.action_area,
            text=self.panel_names[self.vars.current_panel],
            row=0,
            column=0,
            # **GRID_FULLWIDTH,
            sticky=tkinter.E + tkinter.W,
            **WITH_BORDER,
        )
        panel_method()
        self.widgets.action_area.grid(**GRID_FULLWIDTH)
        #
        # Show global application buttons
        buttons_area = tkinter.Frame(self.widgets.action_area)
        last_row = self.show_additional_buttons(buttons_area)
        self.callbacks.update_buttons()
        help_button = tkinter.Button(
            buttons_area, text="Help", command=self.show_help
        )
        about_button = tkinter.Button(
            buttons_area, text="\u24d8 About", command=self.__show_about
        )
        quit_button = tkinter.Button(
            buttons_area, text="\u2717 Quit", command=self.quit
        )
        help_button.grid(row=last_row, column=0, **BUTTONS_GRID_E)
        about_button.grid(row=last_row, column=1, **BUTTONS_GRID_W)
        quit_button.grid(row=last_row, column=2, **BUTTONS_GRID_E)
        self.widgets.action_area.rowconfigure(2, weight=100)
        buttons_area.grid(row=3, column=1, sticky=tkinter.E)
        # Add bindings:
        # - PgUp/PgDown keys to move through the drag action selection
        self.main_window.bind_all(
            "<KeyPress-Prior>", self.callbacks.previous_drag_action
        )
        self.main_window.bind_all(
            "<KeyPress-Next>", self.callbacks.next_drag_action
        )
        # - "P" key (case insensitive) to toggle the preview checkbutton
        self.widgets.action_area.bind_all(
            "<KeyPress-P>", self.callbacks.toggle_preview_checkbutton
        )
        self.widgets.action_area.bind_all(
            "<KeyPress-p>", self.callbacks.toggle_preview_checkbutton
        )
        # - Mouse wheel to resize the selection
        self.main_window.bind_all("<Button-4>", self.increase_selection_size)
        self.main_window.bind_all("<Button-5>", self.decrease_selection_size)

    def toggle_height(self):
        """Toggle height spinbox to follow width"""
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            gui.reconfigure_widget(
                self.widgets.height,
                state=tkinter.DISABLED,
                textvariable=self.tkvars.selection.width,
            )
        else:
            gui.reconfigure_widget(
                self.widgets.height,
                state="readonly",
                textvariable=self.tkvars.selection.height,
            )
        #

    def decrease_selection_size(self, *unused_event):
        """Decrease the selection size by 1"""
        new_dimensions = {}
        for dimension in ("width", "height"):
            new_dimensions[dimension] = (
                self.tkvars.selection[dimension].get() - 1
            )
            if new_dimensions[dimension] < MINIMUM_SELECTION_SIZE:
                new_dimensions[dimension] = MINIMUM_SELECTION_SIZE
            #
        #
        self.resize_selection(**new_dimensions)

    def increase_selection_size(self, *unused_event):
        """Increase the selection size by 1"""
        new_dimensions = {}
        for dimension in ("width", "height"):
            new_dimensions[dimension] = (
                self.tkvars.selection[dimension].get() + 1
            )
        #
        self.resize_selection(**new_dimensions)

    def resize_selection(self, width=None, height=None):
        """Change selection size only"""
        self.update_selection(width=width, height=height)
        self.pixelate_selection()
        self.draw_indicator()

    def update_selection(self, **kwargs):
        """Update the selection for the provided key=value pairs"""
        self.vars.update(trace=False)
        for (key, value) in kwargs.items():
            self.tkvars.selection[key].set(value)
        #
        self.vars.update(trace=True)


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
