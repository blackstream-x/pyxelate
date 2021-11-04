# -*- coding: utf-8 -*-

"""

gui.py

Common tkinter functionality

Copyright (C) 2021 Rainer Schwarzbach

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
If not, see <http://www.gnu.org/licenses/>.

"""


import tkinter

from tkinter import ttk


#
# Constants
#

GRID_KEYWORDS = (
    "column",
    "columnspan",
    "in_",
    "ipadx",
    "ipady",
    "padx",
    "pady",
    "row",
    "rowspan",
    "sticky",
)


#
# Helper functions
#


def get_widget_state(widget):
    """Get a widget state"""
    return widget.cget("state")


def grid_row_of(widget):
    """Return the grid row of the widget"""
    return widget.grid_info()["row"]


def reconfigure_widget(widget, **kwargs):
    """Reconfigure a widget, avoiding eceptions
    for nonexisting widgets
    """
    if not widget:
        return
    #
    try:
        widget.config(**kwargs)
    except tkinter.TclError:
        pass
    #


def set_state(widget, new_state):
    """Update a widget state if required"""
    try:
        old_state = get_widget_state(widget)
    except (AttributeError, tkinter.TclError):
        return
    #
    if old_state == new_state:
        return
    #
    reconfigure_widget(widget, state=new_state)


def traced_variable(
    callback, constructor=tkinter.StringVar, mode="write", value=None
):
    """Return a traced tkinter variable
    where the callback is called on trigger.
    If a value is provided, the variable is initialized with it.
    """
    tkvar = constructor()
    if value is not None:
        tkvar.set(value)
    #
    tkvar.trace_add(mode, callback)
    return tkvar


#
# Classes
#


class Heading(tkinter.Label):  # pylint: disable=too-many-ancestors

    """tkinter.Label subclass, directly positioned"""

    def __init__(self, *args, font_size=10, font_style="bold", **kwargs):
        """Extract grid arguments,
        set font size and style unless overwritten using the
        font=… keyword argument,
        draw the widget and call its .grid() method
        """
        grid_arguments = {}
        for keyword in GRID_KEYWORDS:
            try:
                grid_arguments[keyword] = kwargs.pop(keyword)
            except KeyError:
                continue
            #
        #
        kwargs.setdefault("font", (None, font_size, font_style))
        super().__init__(*args, **kwargs)
        self.grid(**grid_arguments)


class TransientWindow(tkinter.Toplevel):

    """Transient modal window, adapted from
    <https://effbot.org/tkinterbook/tkinter-dialog-windows.htm>
    """

    def __init__(self, parent, content=None, title=None):
        """Create the toplevel window"""
        super().__init__(parent)
        self.transient(parent)
        if title:
            self.title(title)
        #
        self.widgets = {}
        self.parent = parent
        self.initial_focus = self
        self.body = tkinter.Frame(self)
        try:
            self.create_content(content)
        except NotImplementedError:
            # Allow initially contentless windows
            # when using this class directly
            pass
        #
        self.body.grid(padx=5, pady=5, sticky=tkinter.E + tkinter.W)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.action_cancel)
        self.initial_focus.focus_set()

    def create_content(self, content):
        """Add content to body -> overwrite in child classes"""
        raise NotImplementedError

    def action_cancel(self, event=None):
        """Put focus back to the parent window"""
        del event
        self.parent.focus_set()
        self.destroy()


class TransientProgressDisplay(TransientWindow):

    """Show one progressbar in a transient modal window"""

    def __init__(self, parent, label=None, maximum=None, title=None):
        """Create the toplevel window"""
        self.maximum = maximum
        super().__init__(parent, content=label, title=title)

    def create_content(self, content):
        """Create a progressbar"""
        self.widgets["current_value"] = tkinter.IntVar()
        label = tkinter.Label(self.body, text=content)
        progressbar = ttk.Progressbar(
            self.body,
            length=300,
            variable=self.widgets["current_value"],
            maximum=self.maximum,
            orient=tkinter.HORIZONTAL,
        )
        label.grid(sticky=tkinter.W)
        progressbar.grid()
        self.widgets["progress"] = progressbar

    def set_current_value(self, current_value):
        """Set the current value"""
        self.widgets["current_value"].set(current_value)
        self.widgets["progress"].update()
        self.update_idletasks()


class TransientWindowWithButtons(TransientWindow):

    """Modal window with "ok" and "cancel" buttons,
    activated through the create_buttonbox(cancel_button=True|False)
    method.
    """

    def create_buttonbox(self, cancel_button=True):
        """Add standard button box."""
        box = tkinter.Frame(self)
        button = tkinter.Button(
            box,
            text="OK",
            width=10,
            command=self.action_ok,
            default=tkinter.ACTIVE,
        )
        button.grid(padx=5, pady=5, row=0, column=0, sticky=tkinter.W)
        if cancel_button:
            button = tkinter.Button(
                box, text="Cancel", width=10, command=self.action_cancel
            )
            button.grid(padx=5, pady=5, row=0, column=1, sticky=tkinter.E)
        #
        self.bind("<Return>", self.action_ok)
        box.grid(padx=5, pady=5, sticky=tkinter.E + tkinter.W)

    def create_content(self, content):
        """Add content to body -> overwrite in child classes"""
        raise NotImplementedError

    def action_ok(self, event=None):
        """Clean up"""
        del event
        self.withdraw()
        self.update_idletasks()
        self.action_cancel()


class ModalDialog(TransientWindowWithButtons):

    """Modal dialog with "ok" and "cancel" buttons,
    content is a sequence of (heading, body) strings.
    Adapted from
    <https://effbot.org/tkinterbook/tkinter-dialog-windows.htm>
    """

    def __init__(self, parent, content=None, title=None, cancel_button=True):
        """Create the toplevel window and wait until the dialog is closed"""
        super().__init__(parent, content=content, title=title)
        self.create_buttonbox(cancel_button=cancel_button)
        self.wait_window(self)

    def create_content(self, content):
        """Add content to body"""
        for (heading, paragraph) in content:
            if heading:
                Heading(
                    self.body,
                    text=heading,
                    justify=tkinter.LEFT,
                    sticky=tkinter.W,
                    padx=5,
                    pady=5,
                )
            #
            if paragraph is None:
                continue
            #
            text_widget = tkinter.Label(
                self.body, text=paragraph.strip(), justify=tkinter.LEFT
            )
            text_widget.grid(sticky=tkinter.W, padx=5, pady=5)
        #


class InfoDialog(ModalDialog):  # pylint: disable=too-many-ancestors

    """Info dialog,
    instantiated with a series of (heading, paragraph) tuples
    after the parent window
    """

    def __init__(self, parent, *content, title=None):
        """..."""
        super().__init__(
            parent, content=content, title=title, cancel_button=False
        )


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
