# -*- coding: utf-8 -*-

"""

gui_commons.py

Common tkinter functionality

"""


import tkinter


#
# Classes
#


class ModalDialog(tkinter.Toplevel):

    """Adapted from
    <https://effbot.org/tkinterbook/tkinter-dialog-windows.htm>
    """

    def __init__(self,
                 parent,
                 content,
                 title=None,
                 cancel_button=True):
        """Create the toplevel window and wait until the dialog is closed"""
        super().__init__(parent)
        self.transient(parent)
        if title:
            self.title(title)
        #
        self.parent = parent
        self.initial_focus = self
        self.body = tkinter.Frame(self)
        self.create_content(content)
        self.body.grid(padx=5, pady=5, sticky=tkinter.E + tkinter.W)
        self.create_buttonbox(cancel_button=cancel_button)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.action_cancel)
        self.initial_focus.focus_set()
        self.wait_window(self)

    def create_content(self, content):
        """Add content to body"""
        for (heading, paragraph) in content:
            heading_area = tkinter.Label(
                self.body,
                text=heading,
                font=(None, 11, 'bold'),
                justify=tkinter.LEFT)
            heading_area.grid(sticky=tkinter.W, padx=5, pady=10)
            text_area = tkinter.Label(
                self.body,
                text=paragraph,
                justify=tkinter.LEFT)
            text_area.grid(sticky=tkinter.W, padx=5, pady=5)
        #

    def create_buttonbox(self, cancel_button=True):
        """Add standard button box."""
        box = tkinter.Frame(self)
        button = tkinter.Button(
            box,
            text="OK",
            width=10,
            command=self.action_ok,
            default=tkinter.ACTIVE)
        button.grid(padx=5, pady=5, row=0, column=0, sticky=tkinter.W)
        if cancel_button:
            button = tkinter.Button(
                box,
                text="Cancel",
                width=10,
                command=self.action_cancel)
            button.grid(padx=5, pady=5, row=0, column=1, sticky=tkinter.E)
        #
        self.bind("<Return>", self.action_ok)
        box.grid(padx=5, pady=5, sticky=tkinter.E + tkinter.W)

    #
    # standard button semantics

    def action_ok(self, event=None):
        """Clean up"""
        del event
        self.withdraw()
        self.update_idletasks()
        self.action_cancel()

    def action_cancel(self, event=None):
        """Put focus back to the parent window"""
        del event
        self.parent.focus_set()
        self.destroy()


class InfoDialog(ModalDialog):

    """Info dialog,
    instantiated with a seriess of (heading, paragraph) tuples
    after the parent window
    """

    def __init__(self,
                 parent,
                 *content,
                 title=None):
        """..."""
        super().__init__(parent, content, title=title, cancel_button=False)


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
