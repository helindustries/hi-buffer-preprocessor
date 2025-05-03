# Buffer Preprocessor

A tool to process and compress various types of data into C++ buffer declarations. This utility can handle images,
fonts, JTAG streams, and arbitrary data with different compression algorithms. This tool is still largely under
development, but was released for reference for anyone who is able to adapt it to their use-case.

The library is used to generate asset data for temporary tests and direct in-rom integration, as well as to compress
a large (4MB) JTAG SVF stream for FPGA programming into a more manageable size (~120KB). It is used with the
Makefile-based build system. The tool will honour build arguments, simple preprocessor conditions and the like, but
does not support more complex constructs.

## Features

- Generate C++ header files with optimized buffer representations
- Multiple data formats support:
    - Raw data files
    - Images with various pixel formats (RGB565, RGBA8888, BC1, etc.)
    - Fixed and variable width fonts
    - TTF/OTF font conversion to MPFF format
    - JTAG SVF stream conversion
- Compression algorithms:
    - LZSS with configurable window size and match length with automatic optimization
    - RLE with configurable data width
- Smart buffer generation with optimized line length

## Setup

```
pip install pyinstaller fontTools pillow
```

## Usage

The project must define a header with the following defines:

- #define BPDataBuffer(TData, Name, Path)
    A simple data buffer without compression, populated from a file.
- #define BPCompressedBuffer(TData, Name, Compression, ...)
    A compressed data buffer, populated from a file or an uncomressed array definition
- #define BPImageBuffer(TData, Name, Format, Path)
    An image buffer, populated from a file.
- #define BPFixedFontBuffer(TData, Name, Offset, Count, Width, Height, Bits, ColorType, Path)
    A fixed-width font buffer, populated from a file.
- #define BPVariableFontBuffer(TData, Name, Offset, Count, Height, Bits, ColorType, Path)
    A variable-width font buffer, populated from a file.
- #define BPMpffBuffer(TData, Name, Path)
    A MicroPython Font Format buffer, populated from a file.
- #define BPJtagBuffer(TData, Name, Type, Compression, Path)
    A JTAG stream buffer, populated from a file.

The resulting header will define <Name>_<Type> and <Name>_<Type>Size constexpr arrays of the specified <TData> types.
in the namespace of the original definition. Only the defines that are actually in use are required to be defined.
See the example for more details. The tool can then be used as follows to parse the file and generate the desired
output.

```bash
python buffer_utility.py <mode> [options] [compiler_args]
```

### Modes

- `generate`: Create buffer header files from source files
- `filter`: List files containing buffer declarations
- `deps`: List data file dependencies for buffer declarations

### Options

- `--max-values`: Maximum number of values per line in generated C++ code
- `-S/--search`: Search paths for data files

### Examples

Generate a header from a source file:
```bash
python buffer_utility.py generate source.cpp output.h -DMY_DEFINE=1
```

Filter source files containing buffer declarations:
```bash
python buffer_utility.py filter *.cpp *.h
```

List data file dependencies:
```bash
python buffer_utility.py deps source.cpp
```

## Buffer Declaration Syntax

Buffers are declared using macros:
```cpp
BP<Type>Buffer(<c_type>, <name>, <args>);
```
