//  Copyright 2023 Hel Industries, all rights reserved.
//
//  For licensing terms, Please find the licensing terms in the closest
//  LICENSE.txt in this repository file going up the directory tree.
//

#pragma once

#include <span>

/**
 * This define can be used to declare to a buffer read from a file
 */
#define BPDataBuffer(TData, Name, Path) constexpr auto Name = \
    std::span<TData, Name##_DataSize>(Name##_Data)

/**
 * This define can be used to declare to a compression preprocessor to define and compress the buffer
 */
#define BPCompressedBuffer(TData, Name, Compression, ...) constexpr auto Name = \
    std::span<TData, Name##_CompressedSize>(Name##_Compressed)

/**
 * This define can be used to declare an image. The source can be any image format supported by Python's
 * image library. The image will be converted and compressed to the indicated format. Since we don't want
 * to take away from the flexibility of loading different formats and don't want to take up additional space,
 * we just use a wrapper template, that can later be used to fill a texture. As such, and as with the other,
 * buffers, we only declare the span, width and height need to be resolved from the buffer.
 */
#define BPImageBuffer(TData, Name, Format, Path) constexpr auto Name = \
    std::span<TData, Name##_ImageSize>(Name##_Image)

/**
 * This define can be used to declare a font, the source needs to be a black-and-white or grey-scale
 * image, where fully black is fully transparent. Transparency will be 4-bit. if indicated, otherwise 1-bit.
 */
#define BPFixedFontBuffer(TData, Name, Offset, Count, Width, Height, Bits, ColorType, Path) constexpr auto Name = \
    HIFixedWidthFont(std::span<TData, Name##_FixedFontSize>(Name##_FixedFont), Offset, Width, Height, Bits)

/**
 * This define can be used to declare a font, the source needs to be a black-and-white or grey-scale
 * image, where fully black is fully transparent. Transparency will be 4-bit. if indicated, otherwise 1-bit.
 * Since the font is variable width, it is assumed, that a full column of transparent pixels is an indicator
 * for the end of a character. This works for most characters except for space, which is defined in the font
 */
#define BPVariableFontBuffer(TData, Name, Offset, Count, Height, Bits, ColorType, Path) constexpr auto Name = \
    HIVariableWidthFont(std::span<TData, Name##_VariableFontSize>(Name##_VariableFont), Offset, Height, Bits)

/**
 * This define can be used to declare a MPFF-format font. The source needs to point to a proper TTF or OTF font path.
 */
#define BPMpffBuffer(TData, Name, Path) constexpr auto Name = \
    HIMpffFont(std::span<TData, Name##_MpffSize>(Name##_Mpff))

/**
 * This define can be used to declare, define and compress a JTAG stream buffer to the internal command.
 */
#define BPJtagBuffer(TData, Name, Type, Compression, Path) constexpr auto Name = \
    std::span<TData, Name##_JtagSize>(Name##_Jtag)
