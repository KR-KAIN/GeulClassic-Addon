"""Rendering helpers. They affect presentation, not translated message content."""
from __future__ import annotations
import re

_CONTINUOUS_TOKEN=re.compile(r'\S{26,}',re.UNICODE)

def soft_break_long_tokens(text: str, width: int=22) -> str:
    """Add invisible wrap opportunities inside unspaced item/ASCII strings.

    No visible characters are changed. Original message remains unchanged in
    the message store and OBS JSON. The zero-width spaces are UI-only.
    """
    width=max(8,min(40,int(width)))
    return _CONTINUOUS_TOKEN.sub(lambda m:'\u200b'.join(
        m.group(0)[i:i+width] for i in range(0,len(m.group(0)),width)), str(text))


def colored_item_html(text, color='', body_color=''):
    """Safe per-link colour, without changing stored message text."""
    import html
    chunks=re.split(r'(\[[^\[\]\n]+\])',soft_break_long_tokens(text))
    valid=bool(re.fullmatch(r'#[0-9a-fA-F]{6}',str(color)))
    body_valid=bool(re.fullmatch(r'#[0-9a-fA-F]{6}',str(body_color)))
    output=[]
    for i,chunk in enumerate(chunks):
        selected=color if i%2 and valid else body_color if body_valid else ''
        escaped=html.escape(chunk)
        output.append(f'<span style="color:{selected};">{escaped}</span>' if selected else escaped)
    return ''.join(output)
