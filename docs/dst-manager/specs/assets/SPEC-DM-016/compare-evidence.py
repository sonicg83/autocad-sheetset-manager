#!/usr/bin/env python3
"""SPEC-DM-016 视觉证据比对工具（G4 冻结件 vs G8 生产证据）。

用途：对同名证据图做**字节 + 像素**双重比对，并在存在差异时给出差异像素数与
包围盒，供人工定位与裁决。设计约束：只用 Python 标准库（本仓库环境无 Pillow），
因此内置一个最小 PNG 解码器（8 位、非隔行，覆盖 Playwright 截图输出）。

用法：
    python compare-evidence.py                 # 比对本目录与 production/
    python compare-evidence.py A.png B.png     # 比对指定两张图

判定口径（与 README §三 一致）：
- 字节完全相同 → 通过；
- 字节不同但像素差 ≤ 20 像素且单通道最大差 ≤ 1 → 字体栅格化伪影，通过（须在
  README 记录实例）；
- 其他任何差异 → 不通过，必须定位到具体状态与元素并裁决。
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

# 已裁决的字体栅格化伪影阈值：像素数与单通道最大差
ARTIFACT_MAX_PIXELS = 20
ARTIFACT_MAX_DELTA = 1


def load_png(path: Path) -> tuple[int, int, int, bytes]:
    """解码 8 位非隔行 PNG，返回 (宽, 高, 通道数, 像素字节)。"""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"不是 PNG 文件：{path}")
    pos, idat, ihdr = 8, [], None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        chunk_type = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        if chunk_type == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", chunk)
        elif chunk_type == b"IDAT":
            idat.append(chunk)
        elif chunk_type == b"IEND":
            break
        pos += 12 + length
    if ihdr is None:
        raise ValueError(f"缺少 IHDR：{path}")
    width, height, depth, color, _comp, _filt, interlace = ihdr
    if depth != 8 or interlace != 0:
        raise ValueError(f"仅支持 8 位非隔行 PNG：{path}（depth={depth} interlace={interlace}）")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    raw = zlib.decompress(b"".join(idat))
    stride = width * channels
    out = bytearray(height * stride)
    prev = bytearray(stride)
    cursor = 0
    for row in range(height):
        filter_type = raw[cursor]
        cursor += 1
        line = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        if filter_type == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                predictor = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + predictor) & 0xFF
        out[row * stride : (row + 1) * stride] = line
        prev = line
    return width, height, channels, bytes(out)


def compare(left: Path, right: Path) -> tuple[bool, str]:
    if left.read_bytes() == right.read_bytes():
        return True, "字节完全相同（SHA-256 一致）"
    width, height, channels, a = load_png(left)
    width_b, height_b, channels_b, b = load_png(right)
    if (width, height, channels) != (width_b, height_b, channels_b):
        return False, f"尺寸/通道不同：{width}x{height}/{channels} vs {width_b}x{height_b}/{channels_b}"
    diff_pixels = 0
    max_delta = 0
    x0 = y0 = 10**9
    x1 = y1 = -1
    for y in range(height):
        row = y * width * channels
        for x in range(width):
            offset = row + x * channels
            if a[offset : offset + 3] != b[offset : offset + 3]:
                diff_pixels += 1
                max_delta = max(
                    max_delta,
                    max(abs(a[offset + i] - b[offset + i]) for i in range(3)),
                )
                x0, x1 = min(x0, x), max(x1, x)
                y0, y1 = min(y0, y), max(y1, y)
    summary = (
        f"像素差 {diff_pixels} 个，单通道最大差 {max_delta}，"
        f"包围盒 ({x0},{y0})-({x1},{y1}) 尺寸 {x1 - x0 + 1}x{y1 - y0 + 1}"
    )
    if diff_pixels <= ARTIFACT_MAX_PIXELS and max_delta <= ARTIFACT_MAX_DELTA:
        return True, f"字体栅格化伪影（已裁决阈值内）：{summary}"
    return False, f"差异超出已裁决伪影阈值，必须定位与裁决：{summary}"


def main(argv: list[str]) -> int:
    if len(argv) == 3:
        pairs = [(Path(argv[1]), Path(argv[2]))]
    else:
        root = Path(__file__).resolve().parent
        pairs = [(p, root / "production" / p.name) for p in sorted(root.glob("*.png"))]
    failures = 0
    for left, right in pairs:
        if not right.exists():
            print(f"MISSING {left.name}：缺少 {right}")
            failures += 1
            continue
        ok, message = compare(left, right)
        print(f"{'OK  ' if ok else 'FAIL'} {left.name} — {message}")
        failures += 0 if ok else 1
    print(f"\n合计 {len(pairs)} 对，通过 {len(pairs) - failures}，不通过 {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
