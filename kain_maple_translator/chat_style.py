"""Sanitized, shared color/weight options for PySide and OBS browser source."""
from __future__ import annotations
import re

DEFAULT_STYLE={
    'nickname_color':'#b5d6ff',
    'message_color':'#ffffff',
    'megaphone_nickname_color':'#fff38a',
    'megaphone_message_color':'#ffffff',
    'background_color':'#111d31',
    'nickname_bold':False,
    'nickname_underline':False,
    'message_bold':False,
    'message_underline':False,
}
HEX_COLOR=re.compile(r'^#[0-9a-fA-F]{6}$')


def normalize_style(value: dict | None) -> dict:
    value=value if isinstance(value,dict) else {}
    out={}
    for key,default in DEFAULT_STYLE.items():
        candidate=value.get(key,default)
        if key.endswith('_color'):
            out[key]=candidate.lower() if isinstance(candidate,str) and HEX_COLOR.fullmatch(candidate) else default
        else:
            out[key]=candidate if isinstance(candidate,bool) else default
    return out


def rgba_color(hex_color:str, opacity:int)->str:
    c=hex_color if HEX_COLOR.fullmatch(str(hex_color)) else DEFAULT_STYLE['background_color']
    opacity=max(0,min(100,int(opacity)))
    return f'rgba({int(c[1:3],16)},{int(c[3:5],16)},{int(c[5:7],16)},{opacity/100:.3f})'


def text_css(style:dict, kind:str)->str:
    s=normalize_style(style)
    prefix=kind if kind in ('megaphone_nickname','megaphone_message') else ('nickname' if kind=='nickname' else 'message')
    color_key=(prefix+'_color') if prefix.startswith('megaphone') else (prefix+'_color')
    weight_prefix='nickname' if prefix.endswith('nickname') else 'message'
    return (f'color:{s[color_key]};'
            f'font-weight:{"bold" if s[weight_prefix+"_bold"] else "normal"};'
            f'text-decoration:{"underline" if s[weight_prefix+"_underline"] else "none"};')


def effective_font_color(style: dict, kind: str, source_colors: bool = True, source_color: str = '') -> str:
    """General chat always uses settings; megaphone uses source only until customized.

    This avoids unreadable dark/black OCR palette on transparent general chat
    and allows a user's color choice to override the source-color option.
    """
    s = normalize_style(style)
    key = ('megaphone_nickname_color' if kind == 'megaphone_nickname' else
           'megaphone_message_color' if kind == 'megaphone_message' else
           'nickname_color' if kind == 'nickname' else 'message_color')
    configured = s[key]
    if (key.startswith('megaphone_') and source_colors
            and configured == DEFAULT_STYLE[key]
            and isinstance(source_color, str) and HEX_COLOR.fullmatch(source_color)):
        return source_color.lower()
    return configured


def qt_rgba_color(hex_color: str, opacity: int) -> str:
    """Qt stylesheet wants alpha 0..255, unlike OBS/CSS fractional alpha."""
    c=hex_color if HEX_COLOR.fullmatch(str(hex_color)) else DEFAULT_STYLE['background_color']
    alpha=round(max(0,min(100,int(opacity))) * 255 / 100)
    return f'rgba({int(c[1:3],16)},{int(c[3:5],16)},{int(c[5:7],16)},{alpha})'
