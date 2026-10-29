"""Classic (pre-Big Bang) MapleStory window look, shared by every Qt panel.

Colours come from the in-game CHARACTER STAT window: white title strip,
light steel frame, coloured label pills (pink / lime / blue), beige value
cells and a steel-blue bottom strip. The OBS output only uses the radius.
"""
from __future__ import annotations

import sys
from pathlib import Path

VARIANTS=('rounded','square')

# Folder with the small dropdown arrows (works from source and from the exe).
_ARROW=(Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'resources'/'classic_ui').as_posix()

# CHARACTER STAT window palette
OUTLINE='#4b5a68'      # thin dark edge around the window
FRAME='#c3cfdb'        # light steel frame
BODY='#f5f6f7'         # window body
TITLE_LINE='#c0cddb'
TEXT='#2e3a46'
SUBTLE='#66727e'
VALUE='#e4e2d8'        # beige value cell
VALUE_EDGE='#d2cfc2'
PINK='#c8527f';PINK_DARK='#a3416a'
LIME='#b4c23c';LIME_DARK='#8f9c2a'
BLUE='#5a88b6';BLUE_DARK='#3f6890'
STRIP='#94a9bd';STRIP_DARK='#7d93a8'   # bottom "ABILITY POINT" strip
CLOSE='#2889bd'
USED='#c4202a'


def normalize_variant(value)->str:
    return value if value in VARIANTS else 'rounded'

def radius_px(value)->int:
    return 12 if normalize_variant(value)=='rounded' else 0


def pill_css(colour:str, dark:str, radius:int=3)->str:
    """A label pill like NAME / STR / ATTACK in the stat window."""
    return (f'background-color:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {colour},stop:1 {dark});'
            f'color:#ffffff;font-weight:bold;border:1px solid {dark};border-radius:{radius}px;'
            'padding:1px 5px;')


def button_css(selector:str, colour:str, dark:str, radius:int)->str:
    return (f'{selector}{{color:#ffffff;font-weight:bold;'
            f'background-color:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {colour},stop:1 {dark});'
            f'border:1px solid {dark};border-radius:{radius}px;padding:4px 8px;}}'
            f'{selector}:hover{{background-color:{colour};border-color:#ffffff;}}'
            f'{selector}:pressed{{background-color:{dark};}}'
            f'{selector}:disabled{{background-color:#b8bec4;border-color:#a2a9b0;color:#eef0f2;}}')


def game_buttons()->str:
    """Qt push buttons drawn with the game's own button sprites (R19, MCW
    data via scripts/fetch_button_ui.py): blue = CONFIRM, orange CANCEL,
    lime = ADD / DELETE, orange = MY STATUS, each with the game's own
    mouse-over / pressed / grey disabled picture, stretched by its ends."""
    def img(name, state=''):
        suffix=f'_{state}' if state else ''
        return (f'border-image:url("{_ARROW}/qss_btn_{name}{suffix}.png") 4 4 4 4 stretch stretch;'
                'border-width:4px;')
    def kind(sel, name, fixed_state=None):
        if fixed_state:
            return f'{sel}{{{img(name,fixed_state)}}}'
        return '\n'.join([f'{sel}{{{img(name)}}}',
                          f'{sel}:hover{{{img(name,"hover")}}}',
                          f'{sel}:pressed{{{img(name,"pressed")}padding-top:1px;padding-left:9px;}}',
                          f'{sel}:disabled{{{img(name,"disabled")}color:#d6d6d6;}}'])
    return '\n'.join([
        'QPushButton{color:#ffffff;font-weight:bold;font-size:12px;padding:0px 8px;min-height:14px;}',
        kind('QPushButton', 'blue'),              # blue, like CONFIRM
        kind('QPushButton:checked', 'lime'),
        kind('QPushButton#action', 'orange'),     # like MY STATUS
        kind('QPushButton#cancel', 'cancel'),     # orange, like CANCEL
        kind('QPushButton#primary', 'lime'),      # like ADD
        kind('QPushButton#danger', 'lime'),       # like DELETE / CLEAR ALL
        kind('QPushButton#gray', 'lime', 'disabled'),
    ])


def panel_stylesheet(value)->str:
    r=radius_px(value)
    w=3 if r else 0
    return f"""
QWidget {{color:{TEXT}; font-family:'Malgun Gothic','Segoe UI'; font-size:11px;}}
QFrame#glass {{ background-color:{BODY}; border:1px solid {OUTLINE}; border-radius:{r}px; }}
QDialog {{background-color:{BODY}; border:1px solid {OUTLINE};}}
QFrame#section {{background-color:#ffffff; border:1px solid {FRAME}; border-radius:{w}px;}}
QLabel#eyebrow {{color:{PINK_DARK}; font-size:10px; font-weight:bold;}}
QLabel#sectionTitle {{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #dfe6ee,stop:1 #c6d2dd);color:#34414d;font-weight:bold;font-size:11px;border:1px solid #aebdcc;border-radius:2px;padding:3px 8px;}}
QCheckBox::indicator {{width:15px;height:15px;image:url("{_ARROW}/check_off.png");border:0;}}
QCheckBox::indicator:checked {{image:url("{_ARROW}/check_on.png");}}
QSlider::groove:horizontal {{height:6px;background:{VALUE};border:1px solid {VALUE_EDGE};border-radius:3px;}}
QSlider::handle:horizontal {{width:12px;margin:-5px 0;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {BLUE},stop:1 {BLUE_DARK});border:1px solid {BLUE_DARK};border-radius:3px;}}
QMenu {{background:#ffffff;color:{TEXT};border:1px solid {FRAME};}}
QMenu::item:selected {{background:{BLUE};color:#ffffff;}}
QLabel#subtle {{color:{SUBTLE};}}
QLabel#brand {{font-size:14px;font-weight:bold;color:{TEXT};}}
{game_buttons()}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{background-color:#ffffff; color:{TEXT}; border:1px solid {FRAME}; border-radius:{w}px; padding:5px; selection-background-color:{BLUE};selection-color:#ffffff;}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{border:1px solid {BLUE};}}
QComboBox {{background-color:#fbf1e2;color:#222222;border:1px solid #a8a8a8;border-radius:0px;padding:4px 6px;}}
QComboBox::drop-down {{subcontrol-origin:padding;subcontrol-position:center right;width:15px;height:15px;margin-right:3px;
    border:1px solid #9a9a9a;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #e2e2e2);}}
QComboBox::down-arrow {{image:url("{_ARROW}/arrow_red.png");width:9px;height:5px;}}
QSpinBox::up-arrow {{image:url("{_ARROW}/arrow_up.png");width:9px;height:5px;}}
QSpinBox::down-arrow {{image:url("{_ARROW}/arrow_down.png");width:9px;height:5px;}}
QComboBox QAbstractItemView {{background-color:#ffffff;color:{TEXT};selection-background-color:{BLUE};selection-color:#ffffff;outline:0;}}
QComboBox QAbstractItemView::item {{min-height:24px;padding:3px 6px;}}
QCheckBox {{spacing:8px;}}
QTabWidget::pane {{border:1px solid {FRAME};background:{BODY};border-radius:{w}px;}}
QTabBar::tab {{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #b9b9b9,stop:1 #8f8f8f);color:#ffffff;font-weight:bold;
    padding:5px 14px;margin-right:1px;border:1px solid #4a4a4a;border-bottom:0;
    border-top-left-radius:4px;border-top-right-radius:4px;min-width:80px;}}
QTabBar::tab:selected {{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f0607f,stop:1 #c8304f);border-color:#6a1a2a;}}
QTabBar::tab:hover:!selected {{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #cacaca,stop:1 #a0a0a0);}}
QScrollArea {{border:0;background:transparent;}}
QScrollBar:horizontal {{height:0px;background:transparent;border:0;}}
QScrollBar:vertical {{width:20px;margin:20px 0px 20px 0px;border:0px;
    border-image:url("{_ARROW}/qss_scroll_track.png") 0 0 0 0 stretch stretch;}}
QScrollBar::handle:vertical {{min-height:26px;border-width:7px 0px 7px 0px;
    border-image:url("{_ARROW}/qss_scroll_thumb.png") 7 0 7 0 stretch stretch;}}
QScrollBar::sub-line:vertical {{height:20px;subcontrol-position:top;subcontrol-origin:margin;
    border-image:url("{_ARROW}/qss_scroll_up.png") 0 0 0 0 stretch stretch;}}
QScrollBar::add-line:vertical {{height:20px;subcontrol-position:bottom;subcontrol-origin:margin;
    border-image:url("{_ARROW}/qss_scroll_down.png") 0 0 0 0 stretch stretch;}}
QScrollBar::up-arrow:vertical,QScrollBar::down-arrow:vertical {{width:0px;height:0px;}}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:none;}}
QToolTip {{color:{TEXT};background-color:#ffffff;border:1px solid {FRAME};}}
"""


def strip_stylesheet(side:str)->str:
    """Bottom side panels. The panel is painted from the game's CHARACTER
    STAT pieces (classic_ui.hud_pixmap), so the frame itself stays
    transparent. Inputs look like the stat window's beige value cells."""
    edge='border-right:0px;' if side=='left' else 'border-left:0px;'
    return ('QFrame#glass{background:transparent;border:0px;'+edge+'border-radius:0px;}'
            'QLabel{color:#000000;background:transparent;}'
            'QLineEdit{background-color:#e1dfd5;color:#000000;border:1px solid #d2cfc2;border-radius:0px;'
            "font-family:'Gulim';font-size:16px;padding:1px 3px;selection-background-color:#5a88b6;}")


def settings_stylesheet(value)->str:
    """Settings dialog: the inventory window's steel-blue around the tabs
    and along the bottom; the tab pages stay the light stat-window body."""
    # the window itself is painted from the game's frame pieces
    return panel_stylesheet(value)+'QDialog{background:transparent;border:0px;}'
