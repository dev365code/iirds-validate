"""The document element of the iiRDS/H content list."""
from __future__ import annotations


def _list_root(ctx):
    # Imported at use: content and container both consume this reader.
    from .container import CONTENT_LIST
    from .content import _walk

    return dict(_walk(ctx)).get(CONTENT_LIST)


def _first_list_tag(ctx):
    from .container import CONTENT_LIST
    from .content import _bytes_of, _doctype_at, _name_at, _space_at, _xml_prefix

    text = _xml_prefix(_bytes_of(ctx, CONTENT_LIST)[0])
    position = 0
    while position < len(text):
        position = _space_at(text, position)
        if text.startswith("<?xml", position):
            end = text.find("?>", position + 5)
            if end < 0:
                return None
            position = end + 2
        elif text.startswith("<!--", position):
            end = text.find("-->", position + 4)
            if end < 0:
                return None
            position = end + 3
        elif text[position:position + 9].upper() == "<!DOCTYPE":
            position = _doctype_at(text, position, {})
            if position is None:
                return None
        else:
            break
    if text.startswith("<", position):
        name, end = _name_at(text, position + 1)
        if name and (end == len(text) or text[end] in " \t\r\n/>"):
            return name
    return None


def content_list_document(ctx):
    from .content import _local

    root = _list_root(ctx)
    if root is not None:
        name = _local(root.tag)
        return name.lower() == "html", "document element is %s" % name
    name = _first_list_tag(ctx)
    return (name is not None and name.lower() == "html",
            "first tag is %s" % name if name else "no element found")
