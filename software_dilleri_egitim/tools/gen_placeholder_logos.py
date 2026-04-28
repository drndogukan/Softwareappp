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


def _encode_png_rgb(width: int, height: int, pixels: bytes) -> bytes:
    # pixels: RGB bytes, row-major, no alpha (len = width*height*3)
    raw = bytearray()
    row_bytes = width * 3
    for y in range(height):
        raw.append(0)  # filter type 0
        start = y * row_bytes
        raw.extend(pixels[start : start + row_bytes])

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # RGB
    idat = zlib.compress(bytes(raw), level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


_FONT_5X7 = {
    # 5x7 bitmap font. Each int is 5-bit row, top-to-bottom, 7 rows.
    "A": [0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
    "C": [0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110],
    "H": [0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001],
    "J": [0b00111, 0b00010, 0b00010, 0b00010, 0b00010, 0b10010, 0b01100],
    "L": [0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111],
    "M": [0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001],
    "Q": [0b01110, 0b10001, 0b10001, 0b10001, 0b10101, 0b10010, 0b01101],
    "R": [0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001],
    "S": [0b01111, 0b10000, 0b10000, 0b01110, 0b00001, 0b00001, 0b11110],
    "T": [0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100],
    "U": [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110],
    "V": [0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100],
    "#": [0b01010, 0b11111, 0b01010, 0b01010, 0b11111, 0b01010, 0b01010],
    "+": [0b00100, 0b00100, 0b00100, 0b11111, 0b00100, 0b00100, 0b00100],
    " ": [0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000],
}


def _draw_text(
    width: int,
    height: int,
    text: str,
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
) -> bytes:
    # Scale and center the 5x7 glyphs.
    text = text.upper()
    glyph_w, glyph_h = 5, 7
    spacing = 1
    raw_w = len(text) * glyph_w + max(0, len(text) - 1) * spacing

    # Choose scale based on width/height.
    scale = min(max(1, width // (raw_w + 4)), max(1, height // (glyph_h + 4)))
    scale = min(scale, 12)

    canvas = bytearray([bg[0], bg[1], bg[2]] * (width * height))

    draw_w = raw_w * scale
    draw_h = glyph_h * scale
    x0 = (width - draw_w) // 2
    y0 = (height - draw_h) // 2

    x = x0
    for ch in text:
        rows = _FONT_5X7.get(ch, _FONT_5X7[" "])
        for ry, row in enumerate(rows):
            for rx in range(glyph_w):
                on = (row >> (glyph_w - 1 - rx)) & 1
                if not on:
                    continue
                px0 = x + rx * scale
                py0 = y0 + ry * scale
                for dy in range(scale):
                    for dx in range(scale):
                        px = px0 + dx
                        py = py0 + dy
                        if 0 <= px < width and 0 <= py < height:
                            idx = (py * width + px) * 3
                            canvas[idx : idx + 3] = bytes(fg)
        x += (glyph_w + spacing) * scale

    return bytes(canvas)


def _hex_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.strip().lstrip("#")
    return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)


def write_logo(path: str, text: str, bg_hex: str, fg_hex: str = "FFFFFF", size: int = 128) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bg = _hex_rgb(bg_hex)
    fg = _hex_rgb(fg_hex)
    pixels = _draw_text(size, size, text=text, fg=fg, bg=bg)
    png = _encode_png_rgb(size, size, pixels)
    with open(path, "wb") as f:
        f.write(png)


def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.join(root, "assets", "logos")

    # Only generate missing ones (do not overwrite real logos).
    targets = {
        "java.png": ("JAVA", "E76F00", "000000"),
        "rust.png": ("RUST", "B7410E", "FFFFFF"),
        "typescript.png": ("TS", "3178C6", "FFFFFF"),
        "csharp.png": ("C#", "7B1FA2", "FFFFFF"),
        "r.png": ("R", "276DC3", "FFFFFF"),
        "matlab.png": ("M", "FF7A00", "000000"),
        "sql.png": ("SQL", "2E7D32", "FFFFFF"),
        "html.png": ("HTML", "E34F26", "000000"),
        "css.png": ("CSS", "1572B6", "FFFFFF"),
    }

    for filename, (text, bg, fg) in targets.items():
        p = os.path.join(out_dir, filename)
        if os.path.exists(p):
            continue
        write_logo(p, text=text, bg_hex=bg, fg_hex=fg, size=128)


if __name__ == "__main__":
    main()

