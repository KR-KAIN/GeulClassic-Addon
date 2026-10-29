"""UTF-8 CLI output on Windows, including redirected build transcripts."""
import sys


def configure_utf8_console():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
