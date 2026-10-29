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


def estimate_chat_area(game: tuple[int, int, int, int], resolution: str = "auto") -> tuple[int, int, int, int]:
    """Return an *estimated* bottom HUD text rectangle, never an assertion.

    On a Maple-style HUD, the bottom control bar has a roughly 800px footprint
    centered on the game client; chat text occupies its upper-left ~560px.
    Scale a 1366x768 reference against the actual client, using the selected
    native resolution only to correct a window that has been stretched.
    Manual OCR-region selection is always available to override this guess.
    """
    gx, gy, gw, gh = map(int, game)
    if min(gw, gh) <= 0:
        raise ValueError('Invalid game client geometry')
    selected = resolution_size(resolution)
    if selected:
        # Resolution is a *scale hint*; monitor/game origin is always real Win32.
        scale = min(gw / selected[0], gh / selected[1])
        scaled_hud = 800.0 * scale
        scaled_chat = 558.0 * scale
        scaled_top_offset = 130.0 * scale
        scaled_height = 69.0 * scale
    else:
        scale = min(gw / 1366.0, gh / 768.0)
        scaled_hud = 800.0 * scale
        scaled_chat = 558.0 * scale
        scaled_top_offset = 130.0 * scale
        scaled_height = 69.0 * scale
    hud_w = max(240, min(gw, int(round(scaled_hud))))
    text_w = max(160, min(hud_w - 12, int(round(scaled_chat))))
    text_h = max(35, min(160, int(round(scaled_height))))
    left = gx + (gw - hud_w) // 2 + min(6, max(1, int(scale * 6)))
    # Top is measured from the real client BOTTOM, not monitor origin.
    top = gy + gh - int(round(scaled_top_offset))
    left = max(gx, min(left, gx + gw - text_w))
    top = max(gy, min(top, gy + gh - text_h))
    return left, top, text_w, text_h


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


def hud_panel_geometry(game: tuple[int,int,int,int],
                       monitor: tuple[int,int,int,int],
                       chat_region: dict | None = None,
                       left_preferred: int = 360,
                       right_preferred: int = 326,
                       side_gap: int = 0) -> tuple[tuple[int,int,int,int], tuple[int,int,int,int]]:
    """Fit the LEFT settings controller and RIGHT EN input to Maple's bottom HUD.

    The floating TRANSLATED CHAT window is not modified by this helper.
    Client and chat rectangles must be SCREEN coordinates. The first OCR text
    line normally begins around 10 px below the main HUD upper edge.
    """
    gx,gy,gw,gh = map(int,game)
    mx,my,mw,mh = map(int,monitor)
    if min(gw,gh,mw,mh) <= 0:
        raise ValueError('Invalid Maple/monitor rectangle')
    scale = min(gw/1366.0, gh/768.0)
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
    # BOTH panels have the same top/bottom edges.  The legacy right-hand
    # 88-pixel cap caused the floating input tool to look tacked on.
    shared_h=min(h,126)
    lh=shared_h
    rh=shared_h
    return (lx,visual_bottom-lh,lw,lh),(rx,visual_bottom-rh,rw,rh)
