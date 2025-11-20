# imghdr.py
# Minimal stub to satisfy imports on Python 3.13 where imghdr may be missing.
# This stub intentionally returns None for unknown files (safe fallback).

def what(file, h=None):
    """
    Minimal replacement for imghdr.what.
    Returns None for all inputs (safe fallback).
    """
    try:
        # if 'file' is a filename, try to read header bytes
        if isinstance(file, str):
            with open(file, "rb") as f:
                header = f.read(32)
            # basic checks for common formats (optional)
            if header.startswith(b'\xff\xd8'):
                return "jpeg"
            if header[:8] == b'\x89PNG\r\n\x1a\n':
                return "png"
            if header[:6] in (b'GIF87a', b'GIF89a'):
                return "gif"
            # other formats not detected - return None
            return None
        else:
            # if file-like object
            if hasattr(file, "read"):
                pos = file.tell() if hasattr(file, "tell") else None
                header = file.read(32)
                if pos is not None:
                    try:
                        file.seek(pos)
                    except:
                        pass
                if header.startswith(b'\xff\xd8'):
                    return "jpeg"
            return None
    except Exception:
        return None
