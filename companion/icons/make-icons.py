#!/usr/bin/env python3
"""**아이콘 원본 하나** — 여기서 모든 파생물이 난다.

표면마다 로고가 갈라지지 않게, 앱 아이콘도 menu bar 표식도 이 파일의 같은 글자꼴에서
난다. 글꼴에 기대지 않고 도형으로 그리는 이유는 굵기와 자간을 우리가 쥐고 있어야 22pt
에서도 세 글자가 서로 붙지 않기 때문이다.

표기는 **소문자 `gil`** 이다. 따옴표를 넣지 않고, 단독 대문자 `G` 를 쓰지 않는다 —
어느 회사의 표식으로 오인될 자리를 남기지 않는다.

    python3 companion/icons/make-icons.py

가 `icon.png` · `trayTemplate.png` · `trayTemplate@2x.png` 를 다시 만든다.
"""

import math
import os
import struct
import zlib

# ── 글자꼴 ────────────────────────────────────────────────────────────
#
# 좌표는 정규 공간, 기준선(baseline)이 y=0 이고 위가 +다.

T = 12.0        # 획 두께
XH = 46.0       # x-height — g 의 배, i 의 몸통
ASC = 76.0      # l 의 키
DESC = 28.0     # g 의 꼬리 깊이

G_R = XH / 2
G_CX = G_R
G_CY = G_R
I_X = 62.0      # i 의 줄기
L_X = 84.0      # l 의 줄기
DOT_GAP = 10.0  # i 의 몸통과 점 사이

LEFT, RIGHT = 0.0, L_X + T / 2
TOP, BOTTOM = ASC, -DESC
MARK_W = RIGHT - LEFT
MARK_H = TOP - BOTTOM


def _bar(x, y, x0, x1, y0, y1):
    return x0 <= x <= x1 and y0 <= y <= y1


def ink(x, y):
    """이 자리가 글자 안인가."""
    half = T / 2
    # g — 배(고리) · 오른쪽 줄기 · 왼쪽으로 도는 꼬리
    if abs(math.hypot(x - G_CX, y - G_CY) - (G_R - half)) <= half:
        return True
    if _bar(x, y, G_CX + G_R - T, G_CX + G_R, -DESC + T, G_CY):
        return True
    if _bar(x, y, G_CX - G_R + T * 0.4, G_CX + G_R, -DESC, -DESC + T):
        return True
    # i — 몸통 · 점
    if _bar(x, y, I_X - half, I_X + half, 0.0, XH):
        return True
    if _bar(x, y, I_X - half, I_X + half, XH + DOT_GAP, XH + DOT_GAP + T):
        return True
    # l — 키 큰 줄기
    if _bar(x, y, L_X - half, L_X + half, 0.0, ASC):
        return True
    return False


def placement(box_w, box_h, pad):
    """워드마크를 상자에 **비율을 지켜** 앉힌다. 늘이면 획 굵기가 가로세로로 달라진다."""
    scale = min(box_w * (1 - 2 * pad) / MARK_W, box_h * (1 - 2 * pad) / MARK_H)
    off_x = (box_w - MARK_W * scale) / 2
    off_y = (box_h - MARK_H * scale) / 2

    def at(px, py):
        return LEFT + (px - off_x) / scale, TOP - (py - off_y) / scale

    return at


# ── 그리기 ────────────────────────────────────────────────────────────

SAMPLES = 4  # 픽셀 하나를 4×4 로 재 계단을 없앤다


def coverage(px, py, inside):
    hit = 0
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            if inside(px + (sx + 0.5) / SAMPLES, py + (sy + 0.5) / SAMPLES):
                hit += 1
    return hit / (SAMPLES * SAMPLES)


def write_png(path, w, h, pixel):
    raw = b"".join(
        b"\x00" + bytes(v for x in range(w) for v in pixel(x, y)) for y in range(h)
    )

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    open(path, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def rounded(x, y, x0, y0, size, radius):
    """둥근 사각형 안인가 — 안쪽 모서리까지 본다."""
    ix = min(x - x0, x0 + size - x)
    iy = min(y - y0, y0 + size - y)
    if ix < 0 or iy < 0:
        return False
    if ix >= radius or iy >= radius:
        return True
    return math.hypot(radius - ix, radius - iy) <= radius


# ── 앱 아이콘 ─────────────────────────────────────────────────────────
#
# 파란 둥근 사각형 안에 흰 `gil`. 캔버스 가장자리에서 넉넉히 물러나 둔다 — macOS 가
# 아이콘을 깎고 줄이는 자리가 있기 때문이다.

CANVAS = 1024
INSET = 96                      # 캔버스 가장자리에서 물러나는 거리
PLATE = CANVAS - INSET * 2      # 파란 판의 한 변
CORNER = int(PLATE * 0.225)     # macOS 의 둥근 정도에 가깝게
WORD_PAD = 0.17                 # 판 안에서 글자가 물러나는 비율 (안전 여백)
BLUE = (0x56, 0x6F, 0xE8)

_word_at = placement(PLATE, PLATE, WORD_PAD)


def app_pixel(x, y):
    plate = coverage(x, y, lambda px, py: rounded(px, py, INSET, INSET, PLATE, CORNER))
    if plate <= 0:
        return (0, 0, 0, 0)
    letters = coverage(x, y, lambda px, py: ink(*_word_at(px - INSET, py - INSET)))
    # 파란 판 위에 흰 글자를 얹는다.
    r = BLUE[0] + (255 - BLUE[0]) * letters
    g = BLUE[1] + (255 - BLUE[1]) * letters
    b = BLUE[2] + (255 - BLUE[2]) * letters
    return (round(r), round(g), round(b), round(plate * 255))


# ── menu bar 표식 ─────────────────────────────────────────────────────
#
# **template image** 다 — 색을 담지 않고 알파만 담는다. macOS 가 밝기에 맞춰 칠하므로
# light·dark 어느 쪽에서도 읽힌다. 색을 넣으면 한쪽에서 뭉개진 덩어리가 된다.

TRAY_PAD = 0.10


def tray_pixel_for(size):
    at = placement(size, size, TRAY_PAD)

    def pixel(x, y):
        alpha = coverage(x, y, lambda px, py: ink(*at(px, py)))
        return (0, 0, 0, round(alpha * 255))

    return pixel


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    write_png(os.path.join(here, "icon.png"), CANVAS, CANVAS, app_pixel)
    write_png(os.path.join(here, "trayTemplate.png"), 44, 44, tray_pixel_for(44))
    write_png(os.path.join(here, "trayTemplate@2x.png"), 88, 88, tray_pixel_for(88))
    print("icon.png 1024 · trayTemplate.png 44 · trayTemplate@2x.png 88")


if __name__ == "__main__":
    main()
