"""The wrapper: fills in the blanks and wraps the bytes in a minimal ELF file Linux can run.

The file is laid out as:  ELF header | 2 segment headers | code | texts
Linux loads the whole file at FILE_ADDRESS (read + run), and gives us an empty,
writable area at BOXES_ADDRESS for typed answers (read + write).
"""
import struct

FILE_ADDRESS = 0x400000
BOXES_ADDRESS = 0x600000
BOX_SIZE = 256                      # longest answer, in bytes
HEADERS_SIZE = 64 + 2 * 56          # one ELF header + two segment headers
BLANK_SIZES = {"text": 8, "size": 4, "answer": 8, "answer_end": 8, "answer_size": 8}


def wrap(bricks):
    """Turn a list of bricks into the bytes of a runnable ELF file."""
    items = [item for brick in bricks for piece in brick.parts for item in piece]
    blanks = [item for item in items if isinstance(item, tuple)]
    texts = unique(label for kind, label in blanks if kind in ("text", "size"))
    answers = unique(label for kind, label in blanks if kind.startswith("answer"))

    code_size = sum(item_size(item) for item in items)
    text_at, text_bytes = place_texts(texts, FILE_ADDRESS + HEADERS_SIZE + code_size)
    box_at = {name: BOXES_ADDRESS + i * (BOX_SIZE + 8) for i, name in enumerate(answers)}

    code = b"".join(fill(item, text_at, box_at) for item in items)
    body = code + text_bytes
    boxes_size = max(1, len(answers) * (BOX_SIZE + 8))
    return headers(HEADERS_SIZE + len(body), boxes_size) + body


def unique(labels):
    """The labels in first-seen order, each once."""
    return list(dict.fromkeys(labels))


def item_size(item):
    return BLANK_SIZES[item[0]] if isinstance(item, tuple) else len(item)


def place_texts(texts, start):
    """Put the texts one after another from address start. Returns (address of each, all their bytes)."""
    text_at, data = {}, b""
    for text in texts:
        text_at[text] = start + len(data)
        data += text.encode()
    return text_at, data


def fill(item, text_at, box_at):
    """Plain bytes stay as they are; a blank becomes the number it stands for."""
    if not isinstance(item, tuple):
        return item
    kind, label = item
    if kind == "text":
        return struct.pack("<Q", text_at[label])
    if kind == "size":
        return struct.pack("<I", len(label.encode()))
    if kind == "answer":
        return struct.pack("<Q", box_at[label])
    # The length slot sits straight after the box, so the box's end and its length slot share an address.
    return struct.pack("<Q", box_at[label] + BOX_SIZE)


def headers(file_size, boxes_size):
    """The ELF header plus two segment headers: the file itself, and the answer boxes."""
    elf = struct.pack(
        "<16sHHIQQQIHHHHHH",
        b"\x7fELF\x02\x01\x01",       # ELF, 64-bit, little-endian, version 1
        2, 0x3E, 1,                    # runnable program, x86-64, version 1
        FILE_ADDRESS + HEADERS_SIZE,   # start running right after the headers
        64, 0, 0,                      # segment headers follow; no section headers; no flags
        64, 56, 2, 0, 0, 0)            # sizes and counts
    code_segment = struct.pack("<IIQQQQQQ", 1, 5, 0, FILE_ADDRESS, FILE_ADDRESS,
                               file_size, file_size, 0x1000)      # load, read + run
    box_segment = struct.pack("<IIQQQQQQ", 1, 6, 0, BOXES_ADDRESS, BOXES_ADDRESS,
                              0, boxes_size, 0x1000)              # load, read + write, starts empty
    return elf + code_segment + box_segment
