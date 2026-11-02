"""Frozen machine-byte pieces for Linux x86-64. Bricks are built from these.

Each piece is a list of plain bytes and blanks. A blank is a (kind, label) pair
the wrapper fills in once it knows where everything lives:
  ("text", s)          8-byte address of the text s
  ("size", s)          4-byte length of the text s, in bytes
  ("answer", name)     8-byte address of the box that holds an answer
  ("answer_end", name) 8-byte address just past the end of that box
  ("answer_size", name) 8-byte address of the slot holding the answer's length
"""
code = bytes.fromhex


def show(text):
    """Write a fixed text to the screen."""
    return [
        code("B8 01 00 00 00"),         # eax = 1 (write)
        code("BF 01 00 00 00"),         # edi = 1 (the screen)
        code("48 BE"), ("text", text),  # rsi = address of the text
        code("BA"), ("size", text),     # edx = length of the text
        code("0F 05"),                  # syscall
    ]


def show_answer(name):
    """Write a saved answer to the screen."""
    return [
        code("48 A1"), ("answer_size", name),  # rax = the answer's length
        code("48 89 C2"),                      # rdx = rax
        code("B8 01 00 00 00"),                # eax = 1 (write)
        code("BF 01 00 00 00"),                # edi = 1 (the screen)
        code("48 BE"), ("answer", name),       # rsi = address of the answer
        code("0F 05"),                         # syscall
    ]


def read_answer(name):
    """Read typed keys one at a time until Enter (or the box is full); save them as name."""
    return [
        code("49 BC"), ("answer", name),    # r12 = where the next key goes
        # loop:
        code("B8 00 00 00 00"),             # eax = 0 (read)
        code("BF 00 00 00 00"),             # edi = 0 (the keyboard)
        code("4C 89 E6"),                   # rsi = r12
        code("BA 01 00 00 00"),             # edx = 1 (one key)
        code("0F 05"),                      # syscall
        code("48 83 F8 01"),                # did we get exactly one key?
        code("75 19"),                      # no (input ended) -> done
        code("41 80 3C 24 0A"),             # was it Enter?
        code("74 12"),                      # yes -> done
        code("49 FF C4"),                   # r12 = r12 + 1
        code("48 B8"), ("answer_end", name),  # rax = end of the box
        code("49 39 C4"),                   # is r12 still inside the box?
        code("72 CD"),                      # yes -> loop
        # done:
        code("48 B8"), ("answer", name),    # rax = start of the box
        code("49 29 C4"),                   # r12 = r12 - rax (the answer's length)
        code("4C 89 E0"),                   # rax = r12
        code("48 A3"), ("answer_size", name),  # save the length
    ]


def end():
    """End the program with exit code 0."""
    return [
        code("B8 3C 00 00 00"),  # eax = 60 (exit)
        code("31 FF"),           # edi = 0 (all went well)
        code("0F 05"),           # syscall
    ]
