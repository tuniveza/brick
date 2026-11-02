"""Wrap finished machine code in a minimal ELF file that Linux can run.

Layout: ELF header | 2 segment headers | code and fixed texts.
Linux loads the file at FILE_ADDRESS (read + run) and gives an empty,
writable area at SPACE_ADDRESS for variables, lists and new texts.
"""
import struct

FILE_ADDRESS = 0x400000
SPACE_ADDRESS = 0x10000000
HEADERS_SIZE = 64 + 2 * 56


def wrap(asm):
    body, space_size = asm.link(FILE_ADDRESS + HEADERS_SIZE, SPACE_ADDRESS)
    file_size = HEADERS_SIZE + len(body)
    elf = struct.pack(
        "<16sHHIQQQIHHHHHH",
        b"\x7fELF\x02\x01\x01",          # ELF, 64-bit, little-endian, version 1
        2, 0x3E, 1,                       # runnable program, x86-64, version 1
        FILE_ADDRESS + HEADERS_SIZE,      # start running right after the headers
        64, 0, 0,                         # segment headers follow; no section headers; no flags
        64, 56, 2, 0, 0, 0)
    code = struct.pack("<IIQQQQQQ", 1, 5, 0, FILE_ADDRESS, FILE_ADDRESS,
                       file_size, file_size, 0x1000)                  # read + run
    space = struct.pack("<IIQQQQQQ", 1, 6, 0, SPACE_ADDRESS, SPACE_ADDRESS,
                        0, max(space_size, 16), 0x1000)               # read + write, starts empty
    return elf + code + space + body
