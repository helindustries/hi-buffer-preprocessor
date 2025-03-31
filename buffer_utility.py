#  Copyright 2025 $author, All rights reserved.
import os.path
import re
import struct
import sys

import math
from array import array
from dataclasses import dataclass
from fontTools.ttLib import TTFont
from PIL import Image
from typing import Tuple, Any, Iterable, Optional, Callable, Union

from buffer_processor.bitstream import Bitstream
from Tools.PythonUtilities.cpp import filter_code, parse_compiler_args, CompilerArgs
from Tools.PythonUtilities.placeholders import apply_placeholders
from buffer_processor.compress import LZSSCodec, RLECodec, CompressionRunner
from buffer_processor.utilities import get_data_width

# <editor-fold desc="Source Code Parsing">
# We use the Tiny<prefix>Buffer(type, name, ...args) macros to compress the data, it can span multiple lines though.
_buffer_start_re: re.Pattern[str] = re.compile(r"^\s*BP(?P<suffix>[A-Za-z]+)Buffer\((?P<type>[a-zA-Z0-9_]+),\s*(?P<name>[a-zA-Z0-9_]+),\s*(?P<args>.+?)\s*(?P<end>\);)?$")
_buffer_line_re: re.Pattern[str] = re.compile(r"^\s*(?P<args>.*?)\s*(?P<end>\);)?$")
_value_re: re.Pattern[str] = re.compile(r"(?P<hex>0x[0-9a-fA-F]+)|(?P<int>[+-]?[0-9]+)|((?P<number>[+-]?[0-9]+)?\.(?P<decimal>[0-9]+)(?P<float>f)?)")
_namespace_re: re.Pattern[str] = re.compile(r"namespace\s+(?P<namespace>[a-zA-Z0-9:_]+)\s*(\{)?")

@dataclass
class Buffer:
    namespace: str
    type: str
    name: str
    suffix: str
    args_str: str
    source_data: Optional[Union[bytes, Image.Image, TTFont]] = None
    target_data: Optional[list[int]] = None

def analyze_file(inputfile, **defines) -> Iterable[Buffer]:
    with open(inputfile, "r") as fd:
        namespace = None
        buffer = None
        for line_index, line in enumerate(filter_code(fd.readlines(), **defines)):
            if match := _namespace_re.match(line):
                namespace = match.group("namespace")
            elif match := _buffer_start_re.match(line):
                if buffer:
                    raise Exception(f"{inputfile}:{line_index}: Error: Buffer {buffer.name} in namespace {buffer.namespace} not closed.")
                namespace_str = "" if namespace is None else namespace
                buffer = Buffer(namespace_str, match.group("type"), match.group("name"), match.group("suffix"), match.group("args"))
                if match.group("end") is not None:
                    yield buffer
                    buffer = None
            elif buffer is not None and (match := _buffer_line_re.match(line)):
                buffer.args_str += match.group("args")
                if match.group("end") is not None:
                    yield buffer
                    buffer = None
# </editor-fold>

# <editor-fold desc="Code Generators">
cpp_header_file_template = """// auto-generated file
#pragma once

#include <cstdint>

${cpp_namespaces}
"""
cpp_namespace_template = """namespace ${namespace}
{
    ${cpp_buffers:keep_indent}
}
"""
cpp_single_line_buffer_template = """    constexpr std::size_t ${name}_${suffix}Size = ${size};
    constexpr ${type} ${name}_${suffix}[${name}_${suffix}Size] = {${data}};
"""
cpp_multi_line_buffer_template = """    constexpr std::size_t ${name}_${suffix}Size = ${size};
    constexpr ${type} ${name}_${suffix}[${name}_${suffix}Size] = 
    {
        ${cpp_buffer_lines:keep_indent}
    };
"""
cpp_buffer_line = """${data:keep_indent}"""

def get_buffer_data(buffer: Buffer, data) -> Iterable[str]:
    data_width = get_data_width(buffer.type)
    for start_byte in range((len(data) + data_width - 1) // data_width):
        value = 0
        for i in range(data_width):
            byte_index = start_byte * data_width + i
            value <<= 8
            if byte_index < len(data):
                value |= data[byte_index]
        fmt = f"0{data_width * 2}X"
        yield f"0x{format(value, fmt)}"
def generate_buffers(namespace: str, buffers: Iterable[Buffer], max_line_length: int) -> Iterable[str]:
    for buffer in buffers:
        if buffer.namespace == namespace:
            # Assuming the declaration is worth about 4 values no matter what type
            data_width = get_data_width(buffer.type)
            value_count = (len(buffer.target_data) + data_width - 1) // data_width
            # Base per value is 2 characters, overhead per value is 2 chars for comma and 2 for 0x.
            max_values = max_line_length // (data_width * 2 + 4) * (data_width * 2)
            if len(buffer.target_data) < max_values - 4:
                buffer_data = ", ".join(get_buffer_data(buffer, buffer.target_data))
                yield apply_placeholders(cpp_single_line_buffer_template, type=buffer.type, name=buffer.name, suffix=buffer.suffix, size=value_count, data=buffer_data)
            else:
                buffer_lines = []
                for i in range(0, len(buffer.target_data), max_values):
                    buffer_data = ", ".join(get_buffer_data(buffer, buffer.target_data[i:i + max_values]))
                    if i + max_values < len(buffer.target_data):
                        buffer_data += ","
                    buffer_lines.append(apply_placeholders(cpp_buffer_line, data=buffer_data))
                buffer_lines_str = "\n".join(buffer_lines)
                yield apply_placeholders(cpp_multi_line_buffer_template, type=buffer.type, name=buffer.name, suffix=buffer.suffix, size=value_count, cpp_buffer_lines=buffer_lines_str)
def generate_namespaces(buffers: Iterable[Buffer], max_line_length: int) -> Iterable[str]:
    buffer_list = list(buffers)
    namespaces = set(buffer.namespace for buffer in buffer_list)
    for namespace in namespaces:
        buffers_str = "".join(generate_buffers(namespace, buffer_list, max_line_length))
        yield apply_placeholders(cpp_namespace_template, namespace=namespace, cpp_buffers=buffers_str)
def generate_source_file(buffers: Iterable[Buffer], max_line_length: int) -> str:
    cpp_namespaces = "".join(generate_namespaces(buffers, max_line_length))
    return apply_placeholders(cpp_header_file_template, cpp_namespaces=cpp_namespaces)
#</editor-fold>

# <editor-fold desc="Data Sources">
def generate_data(buffer: Buffer, args: str) -> None:
    data_bytes = get_data_width(buffer.type)
    data: bytearray = bytearray()
    for entry in args:
        entry = entry.strip().strip("\"'")
        match = _value_re.match(entry)
        if match is None:
            raise Exception(f"Invalid data entry {entry}")
        if match.group("hex"):
            value = int(match.group("hex"), 16)
        elif match.group("int"):
            value = int(match.group("int"))
        elif match.group("decimal"):
            value = float(entry)
        else:
            raise Exception(f"Invalid data entry {entry}")

        if data_bytes == 1:
            data.append(value & 0xFF)
        elif data_bytes == 2:
            data.append((value >> 8) & 0xFF)
            data.append(value & 0xFF)
        elif data_bytes == 4:
            data.append((value >> 24) & 0xFF)
            data.append((value >> 16) & 0xFF)
            data.append((value >> 8) & 0xFF)
            data.append(value & 0xFF)
        elif data_bytes == 8:
            data.append((value >> 56) & 0xFF)
            data.append((value >> 48) & 0xFF)
            data.append((value >> 40) & 0xFF)
            data.append((value >> 32) & 0xFF)
            data.append((value >> 24) & 0xFF)
            data.append((value >> 16) & 0xFF)
            data.append((value >> 8) & 0xFF)
            data.append(value & 0xFF)
    buffer.source_data = bytes(data)
    print (f"Generated Data {buffer.name} from C++ declaration with {len(data)} bytes.")
def load_data(buffer: Buffer, path, *search_paths: str) -> None:
    try:
        with open(find_path(path, *search_paths), "rb") as fd:
            buffer.source_data = fd.read()
            print (f"Loaded Data {buffer.name} from {path} with {len(buffer.source_data)} bytes.")
    except Exception as e:
        print(f"{e}", file=sys.stderr)
        buffer.source_data = bytes()
def load_image(buffer: Buffer, path: str, *search_paths: str) -> None:
    try:
        path = find_path(path, *search_paths)
        image = Image.open(path)
        buffer.source_data = image.convert("RGBA")
        print(f"Loaded Image {buffer.name} from {path} with {image.width}x{image.height} pixels.")
    except Exception as e:
        print(f"{e}", file=sys.stderr)
        buffer.source_data = Image.new("RGBA", (0, 0))
def load_font(buffer: Buffer, path: str, *search_paths: str) -> None:
    try:
        with open(find_path(path, *search_paths), "rb") as fd:
            buffer.source_data = TTFont(fd)
            print(f"Loaded Font {buffer.name} from {path}.")
    except Exception as e:
        print(f"{e}", file=sys.stderr)
        buffer.source_data = bytes()
# </editor-fold>

# <editor-fold desc="Buffer Infrastructure">
def parse_args(args_str: str, *types: Any) -> Union[Tuple, Any]:
    args = args_str.split(",")
    if types[-1] == list or types[-1] == tuple:
        result = list(t(arg) for arg, t in zip(args, types[:-1]))
        result.append(types[-1](args[len(types) - 1:]))
        return tuple(result)
    if len(args) == 1 and len(types) == 1:
        return types[0](args[0])
    if len(args) == len(types):
        return tuple(t(arg) for arg, t in zip(args, types))
    raise Exception(f"Invalid number of arguments {args_str}")
def find_path(path: str, *search_paths: str) -> str:
    path = path.strip().strip("\"'")
    if os.path.isfile(path):
        return path
    for search_path in search_paths:
        full_path = os.path.join(search_path, path)
        if os.path.isfile(full_path):
            return full_path
    raise Exception(f"Failed to find data file {path}")
def process_buffers(buffers: Iterable[Buffer], search_paths: Union[list[str], tuple[str]], **defines) -> Iterable[Buffer]:
    for buffer in buffers:
        buffer.args_str = buffer.args_str.strip()
        buffer.args_str = apply_placeholders(buffer.args_str, **defines)

        if buffer.suffix == "FixedFont":
            offset, count, width, height, bits, color_type, path = parse_args(buffer.args_str, int, int, int, int, int, str, str)
            load_image(buffer, path, *search_paths)
            generate_fixed_font(buffer, color_type, count, width, height, bits)
        elif buffer.suffix == "VariableFont":
            offset, count, height, bits, color_type, path = parse_args(buffer.args_str, int, int, int, int, str, str)
            load_image(buffer, path, *search_paths)
            generate_variable_font(buffer, color_type, count, height, bits)
        elif buffer.suffix == "Mpff":
            path = parse_args(buffer.args_str, str)
            load_font(buffer, path, *search_paths)
            generate_mpff(buffer)
        elif buffer.suffix == "Compressed":
            compression, data = parse_args(buffer.args_str, str, list)
            if len(data) > 1:
                generate_data(buffer, data)
            else:
                load_data(buffer, data[0], *search_paths)
            compress_buffer(buffer, compression)
        elif buffer.suffix == "Jtag":
            stream_type, compression, path = parse_args(buffer.args_str, str, str, str)
            load_jtag(buffer, stream_type, path, *search_paths)
            if compression.lower() == "none":
                buffer.target_data = buffer.source_data
            else:
                compress_buffer(buffer, compression)
        elif buffer.suffix == "Image":
            format, path = parse_args(buffer.args_str, str, str)
            load_image(buffer, path, *search_paths)
            compress_image(buffer, format)
        elif buffer.suffix == "Data":
            path = parse_args(buffer.args_str, str)
            load_data(buffer, path, *search_paths)
            print(f"Using Data {buffer.name} unchanged.")
            buffer.target_data = buffer.source_data
        else:
            raise Exception(f"Unknown buffer type {buffer.suffix}")
        yield buffer
# </editor-fold>

# <editor-fold desc="Font Data Generation">
def get_font_value(color_type: str, color: Tuple[int, int, int, int]) -> int:
    color_type = color_type.strip().strip("\"").lower()
    if color_type == "rgb":
        return (color[0] + color[1] + color[2] + 2) // 3
    elif color_type == "a":
        return color[3]
    raise Exception(f"Unknown color type {color_type}")
def generate_fixed_characters(image: Image.Image, width: int, height: int) -> Iterable[Image.Image]:
    characters_per_column = image.width // width
    characters_per_row = image.height // height
    for row in range(characters_per_row):
        for column in range(characters_per_column):
            offset_x = column * width
            offset_y = row * height
            yield image.crop((offset_x, offset_y, offset_x + width, offset_y + height))
def generate_variable_characters(image: Image.Image, color_type: str, height: int) -> Iterable[Image.Image]:
    characters_per_row = image.height // height
    for row in range(characters_per_row):
        offset_y = row * height
        offset_x = 0
        in_character = False # looking for the first pixel
        for x in range(image.width):
            for y in range(height):
                if get_font_value(color_type, image.getpixel((x, offset_y + y))) > 0:
                    if not in_character:
                        in_character = True  # found the first pixel
                        offset_x = x
                    break
            else:
                if in_character:
                    in_character = False
                    yield image.crop((offset_x, offset_y, x, offset_y + height))
def generate_character_buffer(image: Image.Image, color_type: str, bits: int) -> array:
    # Writing the data in byte columns, as it is more efficient to store since fonts are usually higher than
    # wide and because then color sizes less than 8 bit have a chance to be copied in 1-2 operations.
    data = array("B")
    byte_end_mask = (8 // bits) - 1
    color_shift = 8 - bits
    for x in range(image.width):
        column = 0
        y = 0
        for y in range(image.height):
            color = get_font_value(color_type, image.getpixel((x, y))) >> color_shift
            bit_offset = (y & byte_end_mask) * bits
            column = (color << bit_offset) | column
            if (y & byte_end_mask) == byte_end_mask:
                data.append(column)
                column = 0
        if y & byte_end_mask != byte_end_mask:
            data.append(column)
    return data
def generate_fixed_font(buffer: Buffer, color_type: str, count: int, width: int, height: int, bits: int) -> None:
    data = array("B")
    for character_image in generate_fixed_characters(buffer.source_data, width, height):
        data.extend(generate_character_buffer(character_image, color_type, bits))
        count -= 1
        if count == 0:
            break
    buffer.target_data = data
    print(f"Generated Fixed Width Font {buffer.name} with {len(data)} bytes.")
def generate_variable_font(buffer: Buffer, color_type: str, count: int, height: int, bits: int) -> None:
    data = array("B")
    offset_table = []
    current_offset = 0
    for character_image in generate_variable_characters(buffer.source_data, color_type, height):
        character = generate_character_buffer(character_image, color_type, bits)
        data.extend(character)
        current_offset += len(character)
        offset_table.append(current_offset)
        count -= 1
        if count == 0:
            break
    offsets = array("B")
    for offset in offset_table:
        # with 16 bit offsets, assuming a character is on average 2x high as wide and we have 96 characters, we can
        # store with on average 682 bytes per character, so at 4 bit per pixel, 50x25 pixels per character, at 1 bit,
        # 100x50 pixels per character. That should be fine!
        offsets.append(offset >> 8)
        offsets.append(offset & 0xFF)
    buffer.target_data = offsets.tobytes() + data.tobytes()
    print(f"Generated Variable Width Font {buffer.name} with {len(data)} bytes and {len(offsets)} offsets.")
def generate_mpff(buffer: Buffer) -> None:
    # Access glyph outlines
    glyf_table = buffer.source_data["glyf"]
    cmap_table = buffer.source_data["cmap"]

    # Map Unicode characters to glyph names
    glyph_data = {}
    for cmap in cmap_table.tables:
        for codepoint, glyph_name in cmap.cmap.items():
            glyph = glyf_table[glyph_name]
            glyph_data[chr(codepoint)] = {
                "glyph_name": glyph_name,
                "outline": glyph.getCoordinates(glyf_table)
            }

    data = array("B")
    data.extend(b"MPFF")
    data.extend(struct.pack("<H", len(glyph_data)))
    for c, d in glyph_data.items():
        coords = d["outline"][0]
        data.extend(c.encode("utf-8"))
        data.extend(struct.pack("<H", len(coords)))
        for x, y in coords:
            data.extend(struct.pack("<hh", x, y))
    buffer.target_data = data
    print(f"Generated MPFF Font {buffer.name} with {len(data)} bytes.")
# </editor-fold>

# <editor-fold desc="Compression">
def compress_buffer(buffer: Buffer, compression_str: str) -> None:
    compression_type = compression_str.strip().strip("\"'").lower().split("_")
    compression = compression_type[0].lower()
    if not isinstance(buffer.source_data, bytes):
        buffer.source_data = bytes(buffer.source_data.tobytes())
    if compression == "lzss":
        if len(compression_type) == 3:
            window = int(compression_type[1])
            length = int(compression_type[2])
            codec = LZSSCodec(window, length)
            compressed, statistics = codec.compress(buffer.source_data)
            buffer.target_data = codec.to_binary(compressed)
            print(f"Compressed {buffer.name} with window {window} and length {length} to {len(buffer.target_data)} bytes.")
        elif len(compression_type) == 1 or (len(compression_type) > 1 and compression_type[1] == "auto"):
            max_window_bits = 16
            max_length_bits = 16
            if len(compression_type) == 4:
                max_window_bits = int(compression_type[2])
                max_length_bits = int(compression_type[3])
            elif len(compression_type) > 2:
                raise Exception(f"Invalid LZSS compression type {compression_str}")
            runner = CompressionRunner(LZSSCodec, buffer.source_data, max_window_bits, max_length_bits, 6)
            buffer.target_data, result = runner.find_best_compression()
            print(f"Compressed {buffer.name} with window {result.window_bits} and length {result.length_bits} to {len(buffer.target_data)} bytes.")
        else:
            raise Exception(f"Invalid LZSS compression type {compression_str}")
    elif compression == "rle":
        if len(compression_type) > 2:
            raise Exception(f"Invalid RLE compression type {compression_str}")
        elif len(compression_type) == 1:
            data_width = 8
        else:
            data_width = int(compression_type[1])
        codec = RLECodec(data_width)
        compressed, statistics = codec.compress(buffer.source_data)
        buffer.target_data = codec.to_binary(compressed, statistics)
        print(f"Compressed {buffer.name} with RLE {data_width} to {len(buffer.target_data)} bytes.")
    else:
        raise Exception(f"Unknown compression type {compression_str}")
# </editor-fold>

# <editor-fold desc="Image Data Generation">
def pixel_to_rgba8888(r: int, g: int, b: int, a: int) -> tuple[int, int]:
    return 32, (r << 24) | (g << 16) | (b << 8) | a
def pixel_to_rgb888(r: int, g: int, b: int, a: int) -> tuple[int, int]:
    return 24, (r << 16) | (g << 8) | b
def pixel_to_rgb565(r: int, g: int, b: int, a: int) -> tuple[int, int]:
    return 16, ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
def pixel_to_rgba4444(r: int, g: int, b: int, a: int) -> tuple[int, int]:
    return 16, ((r & 0xF0) << 8) | ((g & 0xF0) << 4) | (b & 0xF0) | ((a & 0xF0) >> 4)
def pixel_to_rgab5515(r: int, g: int, b: int, a: int) -> tuple[int, int]:
    return 16, ((r & 0xF8) << 8) | ((g & 0xF8) << 3) | (b >> 3) | (0x20 if a > 0 else 0)
def pixel_to_r4(r: int, g: int, b: int, a: int) -> tuple[int, int]:
    return 4, ((r + g + b + 2) // 3) >> 4
def pixel_to_a4(r: int, g: int, b: int, a: int) -> tuple[int, int]:
    return 4, a >> 4
def pixel_to_r1(r: int, g: int, b: int, a: int) -> tuple[int, int]:
    return 1, r + g + b > 384
def pixel_to_a1(r: int, g: int, b: int, a: int) -> tuple[int, int]:
    return 1, 1 if a > 0 else 0
def image_to_bitmap(image: Image.Image, *args: str) -> array:
    if len(args) < 1:
        format = "rgb565"
    elif len(args) > 1:
        raise Exception("Too many arguments for bitmap format")
    else:
        format = args[0].lower()
    width, height = image.size
    format_converter: Optional[Callable[[int, int, int, int], tuple[int, int]]] = globals().get(f"pixel_to_{format}", None)
    if format_converter is None:
        raise Exception(f"Unknown pixel format {format}")

    data = Bitstream()
    for y in range(height):
        for x in range(width):
            r, g, b, a = image.getpixel((x, y))
            data.append(*format_converter(r, g, b, a))
    return data.to_array()
def bc1_compress_block(block: list[Tuple[int, int, int, int]]) -> array:
    has_alpha = any(a < 255 for r, g, b, a in block)
    max_r, max_g, max_b = (0, 0, 0)
    min_r, min_g, min_b = (255, 255, 255)

    for r, g, b, a in block:
        min_r = min(min_r, r)
        min_g = min(min_g, g)
        min_b = min(min_b, b)
        max_r = max(max_r, r)
        max_g = max(max_g, g)
        max_b = max(max_b, b)

    colors = [(max_r, max_g, max_b)]
    colors.append((min_r, min_g, min_b))
    if has_alpha:
        colors[1], colors[0] = colors[0], colors[1]
        colors.append(((min_r + max_r) // 2, (min_g + max_g) // 2, (min_b + max_b) // 2))
        colors.append((0, 0, 0))
    else:
        colors.append(((min_r + max_r) // 3, (min_g + max_g) // 3, (min_b + max_b) // 3))
        colors.append((((min_r + max_r) * 2) // 3, ((min_g + max_g) * 2) // 3, ((min_b + max_b) * 2) // 3))

    data = Bitstream()
    for r, g, b, a in block:
        if has_alpha and a < 128:
            data.append(2, 3)
        else:
            best_distance = float("inf")
            best_index = 0
            for i, color in enumerate(colors[:-1] if has_alpha else colors):
                distance = sum((c1 - c2) ** 2 for c1, c2 in zip((r, g, b), color))
                if distance < best_distance:
                    best_distance = distance
                    best_index = i
            data.append(2, best_index)
    color0 = pixel_to_rgb565(*colors[0] + tuple([0]))
    color1 = pixel_to_rgb565(*colors[1] + tuple([0]))
    data.append(*color0)
    data.append(*color1)
    return data.to_array()
def image_to_bc1(image: Image.Image) -> array:
    width, height = image.size
    data = array("B")
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            block = []
            for yb in range(4):
                for xb in range(4):
                    if x + xb < width and y + yb < height:
                        r, g, b, a = image.getpixel((x + xb, y + yb))
                    else:
                        r, g, b, a = 0, 0, 0, 0
                    block.append((r, g, b, a))
            data.extend(bc1_compress_block(block))
    return data
def compress_image(buffer: Buffer, format: str) -> None:
    if not isinstance(buffer.source_data, Image.Image):
        raise Exception("Image compression requires an image source")
    format_args = format.split("_")
    format_converter: Optional[Callable[[Image.Image, str], None]] = globals().get(f"image_to_{format_args[0].lower()}", None)
    if format_converter is None:
        raise Exception(f"Unknown image format {format_args[0]}")
    buffer.target_data = format_converter(buffer.source_data, *format_args[1:])
    print(f"Compressed {buffer.name} using {format_args[0]} to {len(buffer.target_data)} bytes.")
# </editor-fold>

# <editor-fold desc="JTAG Data Generation">
# ! Bitstream CRC: 0x65EA
# STATE   RESET;
# RUNTEST IDLE  2 TCK 1.00E-002 SEC;
# HDR 0;
# HIR 0;
# TDR 0;
# TIR 0;
# ENDDR DRPAUSE;
# ENDIR IRPAUSE;
# FREQUENCY 1.00e+006 HZ;
# SIR 8  TDI (E0);
# SDR 32 TDI (00000000)
#        TDO (41113043)
#        MASK (FFFFFFFF);
# <editor-fold desc="JTAG Parsing">
_jtag_skip_line_re: re.Pattern[str] = re.compile(r"^\s*(!.*)?$")
_jtag_state_re: re.Pattern[str] = re.compile(r"^\s*(?P<cmd>STATE)\s+(?P<state>(RESET)|(IDLE))\s*;\s*$")
_jtag_end_re: re.Pattern[str] = re.compile(r"^\s*(?P<cmd>(ENDDR)|(ENDIR))\s+(?P<instr>[0-9A-Za-z]+)\s*;\s*$")
_jtag_frequency_re: re.Pattern[str] = re.compile(r"^\s*(?P<cmd>FREQUENCY)\s+(?P<frequency>[0-9.eE+]+)\s+HZ\s*;\s*$")
_jtag_number_re: re.Pattern[str] = re.compile(r"^\s*(?P<number>[0-9]+)\.(?P<decimal>[0-9]+)[eE](?P<dir>[+-])(?P<exp>[0-9]+)\s*$")
_jtag_runtest_re: re.Pattern[str] = re.compile(r"^\s*(?P<cmd>RUNTEST)\s+(?P<state>IDLE)\s+(?P<edges>[0-9]+)\s*TCK\s+(?P<time>[0-9.eE-]+)\s+SEC\s*;\s*$")
_jtag_cmd_re: re.Pattern[str] = re.compile(r"^\s*(?P<cmd>(SIR)|(SDR)|(HIR)|(HDR)|(TIR)|(TDR))\s+(?P<bits>[0-9]+)((\s*(?P<end>;)\s*)|(\s+(?P<args>.*)))$")
_jtag_cmd_arg_re: re.Pattern[str] = re.compile(r"^\s*(?P<pin>(TDI)|(TDO)|(MASK))\s+\(\s*(?P<data>.+)$")
_jtag_cmd_arg_data_re: re.Pattern[str] = re.compile(r"^\s*(?P<data>[0-9A-Za-z]+)\s*(?P<closing>\))?\s*(?P<end>;)?\s*$")
_jtag_commands = {"STATE": 0x01, "HDR": 0x02, "HIR": 0x03, "TDR": 0x04, "TIR": 0x05, "ENDDR": 0x06,
                  "ENDIR": 0x07, "FREQUENCY": 0x08, "RUNTEST": 0x0B, "SIR": 0x0D, "SDR": 0x0E}
_jtag_states = {"RESET": 0x01, "IDLE": 0x02, "DRPAUSE": 0x03, "IRPAUSE": 0x04}
_jtag_args = {"TDI": 0x0C, "TDO": 0x0D, "MASK": 0x0E}
# </editor-fold>
# <editor-fold desc="JTAG Data Generation">
def emit_state(data: array, state: str) -> None:
    data.append(_jtag_commands["STATE"])
    data.append(_jtag_states[state])
def emit_end_command(data: array, command: str, instr: str) -> None:
    data.append(_jtag_commands[command])
    data.append(_jtag_states[instr])
def emit_frequency(data: array, number: int, decimal: int, negative: bool, exponent: int) -> None:
    data.append(_jtag_commands["FREQUENCY"])
    frequency = math.floor(float(f"{number}.{decimal}") * 10 ** (exponent * (-1 if negative else 1)))
    data.append((frequency >> 24) & 0xFF)
    data.append((frequency >> 16) & 0xFF)
    data.append((frequency >> 8) & 0xFF)
    data.append(frequency & 0xFF)
def emit_runtest(data: array, state: str, edges: int, number: int, decimal: int, negative: bool, exponent: int) -> None:
    data.append(_jtag_commands["RUNTEST"])
    data.append(_jtag_states[state])
    data.append(edges >> 8)
    data.append(edges & 0xFF)
    time = math.floor(float(f"{number}.{decimal}") * 10 ** (exponent * (-1 if negative else 1)) * 10000000)
    data.append((time >> 24) & 0xFF)
    data.append((time >> 16) & 0xFF)
    data.append((time >> 8) & 0xFF)
    data.append(time & 0xFF)
def emit_command(data: array, command: str, bits: int, *args: tuple[str, str]) -> None:
    data.append(_jtag_commands[command])
    data.append((bits >> 24) & 0xFF)
    data.append((bits >> 16) & 0xFF)
    data.append((bits >> 8) & 0xFF)
    data.append(bits & 0xFF)

    # We are inverting the args, so we receive the big buffer to send last in the loader
    # implementation on the firmware side and use it to trigger the transfer. Since we
    # are never going to read any data, we can use this as a trigger.
    args = sorted(args, key=lambda arg: _jtag_args[arg[0]], reverse=True)
    for arg, value in args:
        data.append(_jtag_args[arg])
        length = len(value)
        byte_length = (length + 1) // 2
        data.append((byte_length >> 24) & 0xFF)
        data.append((byte_length >> 16) & 0xFF)
        data.append((byte_length >> 8) & 0xFF)
        data.append(byte_length & 0xFF)
        for i in range(0, len(value), 2):
            data.append(int(value[i:i + 2], 16))
# </editor-fold>

def convert_svf_stream(buffer: Buffer, path, *search_paths: str) -> None:
    data = array("B")
    try:
        with open(find_path(path, *search_paths), "r") as fd:
            cmd_match: Optional[re.Match[str]] = None
            arg_matches: Optional[list[tuple[re.Match[str], Optional[str]]]] = None
            arg_match: Optional[re.Match[str]] = None
            arg_data: Optional[str] = None
            def _emit_cmd(data, cmd_match: re.Match[str], *arg_matches: Tuple[re.Match[str], str]) -> tuple[None, list]:
                cmd = cmd_match.group("cmd")
                bits = int(cmd_match.group("bits"))
                args: list[tuple[str, str]] = []
                for arg_match, arg_data in arg_matches:
                    args.append((arg_match.group("pin"), arg_data))
                emit_command(data, cmd, bits, *args)
                return None, []

            for i, line in enumerate(fd.readlines()):
                line = line.strip()
                if _jtag_skip_line_re.match(line):
                    pass
                elif match := _jtag_state_re.match(line):
                    emit_state(data, match.group("state"))
                elif match := _jtag_end_re.match(line):
                    emit_end_command(data, match.group("cmd"), match.group("instr"))
                elif match := _jtag_frequency_re.match(line):
                    number_match = _jtag_number_re.match(match.group("frequency"))
                    if number_match is None:
                        raise Exception(f"{path}:{i}: Error: Invalid number format.")
                    emit_frequency(data, int(number_match.group("number")), int(number_match.group("decimal")), number_match.group("dir") == "-", int(number_match.group("exp")))
                elif match := _jtag_runtest_re.match(line):
                    number_match = _jtag_number_re.match(match.group("time"))
                    if number_match is None:
                        raise Exception(f"{path}:{i}: Error: Invalid number format.")
                    emit_runtest(data, match.group("state"), int(match.group("edges")), int(number_match.group("number")), int(number_match.group("decimal")), number_match.group("dir") == "-", int(number_match.group("exp")))
                elif match := _jtag_cmd_re.match(line):
                    if cmd_match is not None:
                        raise Exception(f"{path}:{i}: Error: JTAG command {cmd_match.group('cmd')} incomplete.")
                    if match.group("end") is not None:
                        cmd_match, arg_matches = _emit_cmd(data, match)
                    else:
                        cmd_match = match
                        arg_matches = []
                        line = cmd_match.group("args")
                elif cmd_match is None:
                    raise Exception(f"{path}:{i}: Error: Unknown JTAG command '{line}'.")
                if match := _jtag_cmd_arg_re.match(line):
                    if arg_match is not None:
                        raise Exception(f"{path}:{i}: Error: JTAG command {cmd_match.group('cmd')} has an incomplete argument in '{line}'.")
                    arg_match = match
                    arg_data = ""
                    line = arg_match.group("data")
                if match := _jtag_cmd_arg_data_re.match(line):
                    arg_data += match.group("data")
                    if match.group("closing") is not None:
                        arg_matches.append((arg_match, arg_data))
                        arg_match = None
                        arg_data = None
                        if match.group("end") is not None:
                            cmd_match, arg_matches = _emit_cmd(data, cmd_match, *arg_matches)
                    elif match.group("end") is not None:
                        raise Exception(f"{path}:{i}: Error: JTAG command {cmd_match.group('cmd')} has an incomplete argument.")
    except Exception as e:
        print(f"{e}", file=sys.stderr)
    buffer.source_data = data
def load_jtag(buffer: Buffer, input_type: str, path: str, *search_paths: str) -> None:
    input_type = input_type.lower()
    if input_type == "svf":
        convert_svf_stream(buffer, path, *search_paths)
        print(f"Converted {buffer.name} using SVF {path} to JTAG stream of {len(buffer.source_data)}b.")
    else:
        raise Exception(f"Unknown JTAG input type {input_type}")
# </editor-fold>

def generate_buffer_files(inputfile: str, outputfile: str, compiler_args: CompilerArgs, max_values: int):
    buffers: Iterable[Buffer] = process_buffers(analyze_file(inputfile, **compiler_args.defines), compiler_args.header_paths, **compiler_args.defines)
    with open(outputfile, "w") as fd:
        fd.write(generate_source_file(buffers, max_values))

def filter_files(compiler_args: CompilerArgs) -> None:
    for inputfile in compiler_args.files:
        if next(iter(analyze_file(inputfile, **compiler_args.defines)), None) is not None:
            print(inputfile)

def list_dependencies(compiler_args: CompilerArgs) -> None:
    for inputfile in compiler_args.files:
        for buffer in analyze_file(inputfile, **compiler_args.defines):
            args = buffer.args_str.split(",")
            if buffer.suffix == "Compressed" and len(args) != 2:
                continue
            elif buffer.suffix not in ["Compressed", "FixedFont", "VariableFont", "Mpff", "Jtag", "Image", "Data"]:
                continue
            print(args[-1])

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Buffer Compressor')
    parser.add_argument('mode', choices=['generate', 'filter', 'deps'], help='Utility mode')
    parser.add_argument('--max-values', type=int, default=50, help='maximum number of values per line in the generated C++ header file')
    parser.add_argument('-S', '--search', action='append', help='include path for data files')
    parser.add_argument('compiler_args', nargs=argparse.REMAINDER, help='Compiler arguments, including files (e.g., -DVAR=value)')
    args = parser.parse_args()

    compiler_args = parse_compiler_args(args.compiler_args)
    compiler_args.header_paths.extend([apply_placeholders(arg, **args.defines) for arg in args.search] if args.search is not None else [])
    if args.mode == 'generate':
        if len(compiler_args.files) != 2:
            print("Error: Need an input and an output file.", file=sys.stderr)
            sys.exit(1)
        print(compiler_args.files[0], compiler_args.files[1])
        compiler_args.header_paths.append(os.path.dirname(compiler_args.files[0]))
        generate_buffer_files(compiler_args.files[0], compiler_args.files[1], compiler_args, args.max_values)
    elif args.mode == 'filter':
        filter_files(compiler_args)
    elif args.mode == 'deps':
        list_dependencies(compiler_args)
