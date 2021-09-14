# File manager integration

The [autoselect.py](../autoselect.py) script can be integrated with
some file managers to call pixelation scrips using a click into the
context menu after selecting a file.

## Nautilus (GNOME)

Install Nautilus script integration:

```
autoselect.py --install-nautilus-script
```

This will install [autoselect.py](../autoselect.py) as a Nautilus script (located in the
contect menu under `Scripts`).

If you provide a name after `--install-nautilus-script`, the script will be
installed with that name, otherwise as `Pixelate`.

## Thunar (XFCE)

Add the command `autoselect.py %f` (with its full path as printed by `readlink -f`)
to Thunar using a custom action as documented in
<https://docs.xfce.org/xfce/thunar/custom-actions>.

Select "Image files" and "Video files" on the "Appearance Conditions" tab.

## Windows Explorer

_(tba)_
