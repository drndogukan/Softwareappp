import os
import struct
import zlib


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", _crc32(chunk_type + data))
    )


def _encode_png_rgba(width: int, height: int, pixels: bytes) -> bytes:
    # pixels: RGBA bytes, row-major, len = width*height*4
    raw = bytearray()
    row_bytes = width * 4
    for y in range(height):
        raw.append(0)  # filter 0
        start = y * row_bytes
        raw.extend(pixels[start : start + row_bytes])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # RGBA
    idat = zlib.compress(bytes(raw), level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


_FONT_7X9 = {
    # 7x9 bitmaps (7-bit rows), 9 rows.
    "Y": [0b1000001, 0b0100010, 0b0010100, 0b0001000, 0b0001000, 0b0001000, 0b0001000, 0b0001000, 0b0001000],
    "D": [0b1111100, 0b1000010, 0b1000001, 0b1000001, 0b1000001, 0b1000001, 0b1000001, 0b1000010, 0b1111100],
    "E": [0b1111111, 0b1000000, 0b1000000, 0b1111110, 0b1000000, 0b1000000, 0b1000000, 0b1000000, 0b1111111],
}


def _hex_rgba(hex_str: str, a: int = 255) -> tuple[int, int, int, int]:
    hex_str = hex_str.strip().lstrip("#")
    return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), a


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _make_gradient(width: int, height: int, c1, c2, c3) -> bytearray:
    px = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            # diagonal-ish blend
            t = (x / max(1, width - 1)) * 0.55 + (y / max(1, height - 1)) * 0.45
            t = max(0.0, min(1.0, t))
            if t < 0.5:
                u = t / 0.5
                r = _lerp(c1[0], c2[0], u)
                g = _lerp(c1[1], c2[1], u)
                b = _lerp(c1[2], c2[2], u)
            else:
                u = (t - 0.5) / 0.5
                r = _lerp(c2[0], c3[0], u)
                g = _lerp(c2[1], c3[1], u)
                b = _lerp(c2[2], c3[2], u)
            i = (y * width + x) * 4
            px[i : i + 4] = bytes((r, g, b, 255))
    return px


def _draw_text_7x9(pixels: bytearray, width: int, height: int, text: str, fg) -> None:
    text = text.upper()
    glyph_w, glyph_h = 7, 9
    spacing = 2
    raw_w = len(text) * glyph_w + max(0, len(text) - 1) * spacing

    scale = min(max(1, width // (raw_w + 8)), max(1, height // (glyph_h + 8)))
    scale = min(scale, 18)

    draw_w = raw_w * scale
    draw_h = glyph_h * scale
    x0 = (width - draw_w) // 2
    y0 = (height - draw_h) // 2

    x = x0
    for ch in text:
        rows = _FONT_7X9.get(ch)
        if rows is None:
            x += (glyph_w + spacing) * scale
            continue
        for ry, row in enumerate(rows):
            for rx in range(glyph_w):
                on = (row >> (glyph_w - 1 - rx)) & 1
                if not on:
                    continue
                px0 = x + rx * scale
                py0 = y0 + ry * scale
                for dy in range(scale):
                    for dx in range(scale):
                        px_x = px0 + dx
                        px_y = py0 + dy
                        if 0 <= px_x < width and 0 <= px_y < height:
                            i = (px_y * width + px_x) * 4
                            pixels[i : i + 4] = bytes(fg)
        x += (glyph_w + spacing) * scale


def write_png(path: str, width: int, height: int, rgba_pixels: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(_encode_png_rgba(width, height, rgba_pixels))


def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.join(root, "assets", "branding")

    bg1 = _hex_rgba("#07090D")
    bg2 = _hex_rgba("#0F1620")
    accent = _hex_rgba("#62B6CB")
    fg = _hex_rgba("#CAE9FF")

    # Full icon 1024x1024
    icon = _make_gradient(1024, 1024, bg1, bg2, accent)
    _draw_text_7x9(icon, 1024, 1024, "YDE", fg)
    write_png(os.path.join(out_dir, "app_icon.png"), 1024, 1024, bytes(icon))

    # Foreground for adaptive icons (transparent bg)
    fg_px = bytearray([0, 0, 0, 0] * (1024 * 1024))
    _draw_text_7x9(fg_px, 1024, 1024, "YDE", _hex_rgba("#62B6CB"))
    write_png(os.path.join(out_dir, "app_icon_foreground.png"), 1024, 1024, bytes(fg_px))

    # Splash image 512x512
    splash = _make_gradient(512, 512, bg1, bg2, accent)
    _draw_text_7x9(splash, 512, 512, "YDE", fg)
    write_png(os.path.join(out_dir, "splash.png"), 512, 512, bytes(splash))


if __name__ == "__main__":
    main()

