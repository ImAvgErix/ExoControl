from exo_control.pointer import (
    NOTCHES_LINE,
    NOTCHES_PAGE,
    WHEEL_DELTA,
    amount_to_notches,
    aim_point,
    bbox_visible,
    dy_to_notches,
    notches_to_px,
    notches_toward,
    parse_scroll,
    viewport_from_rect,
)


def test_amount_and_dy_mapping():
    assert amount_to_notches("page") == NOTCHES_PAGE
    assert amount_to_notches("line") == NOTCHES_LINE
    assert amount_to_notches(4) == 4
    assert amount_to_notches(None) == NOTCHES_LINE
    assert dy_to_notches(3) == 3
    assert dy_to_notches(-2) == -2
    assert dy_to_notches(600) == 5
    assert dy_to_notches(-240) == -2
    assert notches_to_px(5) == 5 * WHEEL_DELTA


def test_parse_scroll_prefers_notches_and_direction():
    assert parse_scroll({"notches": 4})["notches"] == 4
    assert parse_scroll({"direction": "down"})["notches"] == NOTCHES_LINE
    assert parse_scroll({"direction": "up", "amount": "page"})["notches"] == -NOTCHES_PAGE
    assert parse_scroll({"direction": "right"})["h_notches"] == NOTCHES_LINE
    assert parse_scroll({"dy": 600})["notches"] == 5
    empty = parse_scroll({})
    assert empty["notches"] == NOTCHES_LINE
    assert empty["h_notches"] == 0


def test_viewport_aim_and_visibility():
    rect = [0, 0, 800, 600]
    l, t, r, b = viewport_from_rect(rect, chrome_top=90)
    assert t == 90
    ax, ay = aim_point(rect, chrome_top=90)
    assert ax == 400
    assert ay > 90
    viewport = (0, 90, 800, 600)
    assert bbox_visible([300, 200, 400, 240], viewport)
    assert not bbox_visible([300, 10, 400, 40], viewport)
    assert notches_toward([300, 20, 400, 40], viewport) < 0
    assert notches_toward([300, 700, 400, 740], viewport) > 0
