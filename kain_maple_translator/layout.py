"""Deterministic screen/client layout math; no Qt, Win32, or OCR dependencies."""
from __future__ import annotations

GAME_RESOLUTIONS = ("auto", "800x600", "1024x768", "1152x864", "1280x720",
                    "1280x800", "1280x960", "1366x768", "1440x900", "1600x900",
                    "1680x1050", "1920x1080", "2560x1440")


def resolution_size(value: str) -> tuple[int, int] | None:
    if value not in GAME_RESOLUTIONS or value == "auto":
        return None
    x, y = value.split("x", 1)
    return int(x), int(y)


def game_ui_scale(width: int, height: int) -> float:
    """How much MapleStory enlarges its own interface for a client size.

    Measured on the windowed client with UI size '기본 비율': the game scales
    its HUD by client height and never below 1.0 (1280x720 and 1366x768 ->
    1.0, 1920x1080 -> 1.406, 1920x1200 -> 1.5625, 2560x1440 -> 1.875).
    '최적 비율' uses whole numbers instead; auto detection measures that.
    """
    return max(1.0, float(height) / 768.0) if height > 0 else 1.0


# The bottom chat area at UI scale 1.0, from the client's bottom centre:
# text starts 395 px left of centre and is 558x69 px; its top is 134 px
# above the client bottom (just above the blue chat-target button).
CHAT_LEFT_FROM_CENTRE = 395
CHAT_TOP_FROM_BOTTOM = 134
CHAT_WIDTH = 558
CHAT_HEIGHT = 69


def _resolution_scale(gw: int, gh: int, resolution: str) -> float:
    selected = resolution_size(resolution)
    if selected:
        # A chosen resolution only matters for a game stretched over a bigger
        # screen (fullscreen at a lower resolution: same shape, larger). A
        # windowed client is never stretched, so a different size means the
        # setting is out of date and the real client rectangle wins.
        sx, sy = gw / selected[0], gh / selected[1]
        if sx >= .99 and sy >= .99 and abs(sx - sy) <= .02:
            return game_ui_scale(*selected) * min(sx, sy)
    return game_ui_scale(gw, gh)


def estimate_chat_area(game: tuple[int, int, int, int], resolution: str = "auto",
                       ui_scale: float | None = None) -> tuple[int, int, int, int]:
    """Return an *estimated* bottom HUD text rectangle, never an assertion.

    The bottom control bar is centred on the game client and scaled by the
    game's UI scale; chat text occupies its upper-left 558x69 px at scale 1.
    ui_scale overrides the guess (auto detection measures it on screen).
    Manual OCR-region selection is always available to override this guess.
    """
    gx, gy, gw, gh = map(int, game)
    if min(gw, gh) <= 0:
        raise ValueError('Invalid game client geometry')
    scale = float(ui_scale) if ui_scale else _resolution_scale(gw, gh, resolution)
    text_w = max(160, min(gw, int(round(CHAT_WIDTH * scale))))
    text_h = max(35, min(160, int(round(CHAT_HEIGHT * scale))))
    left = gx + int(round(gw / 2 - CHAT_LEFT_FROM_CENTRE * scale))
    # Top is measured from the real client BOTTOM, not monitor origin.
    top = gy + gh - int(round(CHAT_TOP_FROM_BOTTOM * scale))
    left = max(gx, min(left, gx + gw - text_w))
    top = max(gy, min(top, gy + gh - text_h))
    return left, top, text_w, text_h


def hud_relative_region(relative: dict, reference: dict,
                        game: tuple[int, int, int, int]) -> dict:
    """Move a chat crop chosen at one game size to another game size.

    The game keeps its chat HUD at the bottom centre and scales it by its UI
    scale, not by the window size. relative holds fractions (x, y, w, h) of
    the reference client (width, height, scale); the crop keeps its place
    relative to the bottom centre and grows or shrinks with the UI scale.
    """
    gx, gy, gw, gh = map(int, game)
    w0, h0 = float(reference['width']), float(reference['height'])
    s0 = float(reference.get('scale') or game_ui_scale(int(w0), int(h0)))
    s1 = game_ui_scale(gw, gh)
    k = s1 / s0 if s0 > 0 else 1.0
    x0, y0 = float(relative['x']) * w0, float(relative['y']) * h0
    rw, rh = float(relative['w']) * w0 * k, float(relative['h']) * h0 * k
    left = gw / 2 - (w0 / 2 - x0) * k
    top = gh - (h0 - y0) * k
    width = max(25, min(gw, int(round(rw))))
    height = max(15, min(gh, int(round(rh))))
    left = max(0, min(int(round(left)), gw - width))
    top = max(0, min(int(round(top)), gh - height))
    return {'left': gx + left, 'top': gy + top, 'width': width, 'height': height}


def dock_to_side(game: tuple[int,int,int,int], monitor: tuple[int,int,int,int],
                 width: int, height: int, side: str, match_height: bool=True, gap: int=7):
    """(x,y,w,h), status. Anchors to full game client height, not OCR area."""
    gx, gy, gw, gh = map(int, game)
    mx, my, mw, mh = map(int, monitor)
    if side not in ('left','right') or min(gw,gh,mw,mh) <= 0:
        raise ValueError('Invalid side or rectangle')
    width = max(180, int(width))
    height = gh if match_height else max(55, int(height))
    x = gx + gw + gap if side == 'right' else gx - width - gap
    y = gy
    if (x >= mx and x+width <= mx+mw and y >= my and y+height <= my+mh):
        return (x,y,width,height), 'outside'
    # No off-screen disappearance: use inside edge only as an explicit fallback.
    # This cannot satisfy an *outside* dock with a fullscreen game.
    width = min(width, gw)
    height = min(height, gh)
    x = gx + gw-width if side == 'right' else gx
    return (x,gy,width,height), 'inside-fallback'


PANEL_MIN_WIDTH = 155   # the side panels' fit_bottom_hud never goes narrower


def hud_panel_geometry(game: tuple[int,int,int,int],
                       monitor: tuple[int,int,int,int],
                       chat_region: dict | None = None,
                       left_preferred: int = 360,
                       right_preferred: int = 326,
                       side_gap: int = 0,
                       ui_scale: float | None = None) -> tuple[tuple[int,int,int,int], tuple[int,int,int,int]]:
    """Fit the LEFT settings controller and RIGHT EN input to Maple's bottom HUD.

    The floating TRANSLATED CHAT window is not modified by this helper.
    Client and chat rectangles must be SCREEN coordinates. The first OCR text
    line normally begins around 10 px below the main HUD upper edge.
    """
    gx,gy,gw,gh = map(int,game)
    mx,my,mw,mh = map(int,monitor)
    if min(gw,gh,mw,mh) <= 0:
        raise ValueError('Invalid Maple/monitor rectangle')
    scale = float(ui_scale) if ui_scale else game_ui_scale(gw, gh)
    game_bottom = gy+gh
    visual_bottom = min(game_bottom, my+mh)
    fallback_height = max(100, min(280, round(151*scale)))
    top = game_bottom-fallback_height
    if isinstance(chat_region,dict):
        try:
            rx,ry,rw,rh=(int(chat_region[k]) for k in ('left','top','width','height'))
            # Never use an old absolute OCR crop outside the detected game.
            inside=(gx<=rx<gx+gw and gy<=ry<gy+gh and rw>0 and rh>0
                    and rx+rw<=gx+gw and ry+rh<=gy+gh
                    and ry>=gy+int(gh*.55))
            if inside:
                candidate=ry-round(11*scale)
                # An OCR crop of only the last text line should not create
                # tiny windows. Also reject stale selections far above HUD.
                if 100 <= game_bottom-candidate <= min(320,round(235*max(1.0,scale))):
                    top=candidate
        except (TypeError,ValueError,KeyError):
            pass
    top=max(gy, min(top,visual_bottom-95))
    h=max(95,visual_bottom-top)
    # V0.4.40 integrated bottom HUD: snap mini panels directly to the
    # *actual central Maple button block*.  No ornamental 7 px side gutters
    # or preferred-width cap; fill the available strips on both sides.
    # The game client itself remains untouched (these are overlay windows).
    hud_width=min(gw,round(803*scale))
    # Maple's right action rail shifts the visual central HUD ~3px left.
    hud_left=max(gx,gx+(gw-hud_width)//2-round(3.4*scale))
    hud_right=hud_left+hud_width
    gap=max(0,int(side_gap))
    lx=gx
    lw=max(1,hud_left-gx-gap)
    rx=hud_right+gap
    rw=max(1,gx+gw-rx)
    # A client partly beyond the monitor must not strand its HUD controls.
    left_limit=max(mx,gx)
    right_limit=min(mx+mw,gx+gw)
    lx=max(lx,left_limit)
    rx=min(rx,right_limit)
    lw=max(1,min(lw,hud_left-lx-gap))
    rw=max(1,min(rw,right_limit-rx))
    # Below 1280 px the game's HUD fills (almost) the whole width. The panels
    # then keep their smallest usable width and cover the HUD's outer edges.
    if lw<PANEL_MIN_WIDTH:
        lw=max(1,min(PANEL_MIN_WIDTH,right_limit-lx))
    if rw<PANEL_MIN_WIDTH:
        rx=max(left_limit,right_limit-PANEL_MIN_WIDTH)
        rw=max(1,right_limit-rx)
    # BOTH panels have the same top/bottom edges.  The legacy right-hand
    # 88-pixel cap caused the floating input tool to look tacked on.
    # 126 px at 1920x1080; a larger game UI gets proportionally taller panels.
    shared_h=min(h,max(126,round(126*scale/(1080/768))))
    lh=shared_h
    rh=shared_h
    return (lx,visual_bottom-lh,lw,lh),(rx,visual_bottom-rh,rw,rh)
