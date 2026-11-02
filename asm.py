"""A tiny x86-64 assembler: only the instructions the bricks need.

Code goes into `code`. Fixed texts go into a read-only data area after the code,
and writable space (variables, lists, the heap) lives in a separate empty area.
Labels name places in any of the three; link() turns them into real addresses.
"""
import struct

RAX, RCX, RDX, RBX, RSP, RBP, RSI, RDI = range(8)
R8, R9, R10, R11, R12, R13, R14, R15 = range(8, 16)
XMM0, XMM1, XMM2 = 0, 1, 2

# Conditions for jump_if()
BELOW, NOT_BELOW, EQUAL, NOT_EQUAL, NOT_ABOVE, ABOVE = 0x2, 0x3, 0x4, 0x5, 0x6, 0x7
NEGATIVE, NOT_NEGATIVE, LESS, NOT_LESS, NOT_GREATER, GREATER = 0x8, 0x9, 0xC, 0xD, 0xE, 0xF

ALU = {"add": (0x01, 0), "or": (0x09, 1), "and": (0x21, 4), "sub": (0x29, 5),
       "xor": (0x31, 6), "cmp": (0x39, 7), "test": (0x85, None)}
DECIMAL_MATHS = {"add": 0x58, "mul": 0x59, "sub": 0x5C, "div": 0x5E}


class Asm:
    def __init__(self):
        self.code = bytearray()
        self.labels = {}       # label -> position in code
        self.data = {}         # label -> fixed bytes (read-only)
        self.space = {}        # label -> size in bytes (writable, starts as zeros)
        self.jumps = []        # (position of a 4-byte distance, label)
        self.addresses = []    # (position of an 8-byte address, label)
        self.texts = {}        # text -> its data label, so each text is stored once
        self.count = 0

    # ---- labels, texts and space ----

    def new_label(self, hint="here"):
        self.count += 1
        return f"{hint}_{self.count}"

    def label(self, name):
        self.labels[name] = len(self.code)

    def text(self, s):
        """A fixed text, stored as: 8-byte length, the bytes, a zero byte."""
        if s not in self.texts:
            raw = s.encode()
            self.texts[s] = self.new_label("text")
            self.data[self.texts[s]] = struct.pack("<Q", len(raw)) + raw + b"\0"
        return self.texts[s]

    def number(self, value):
        """A fixed 8-byte decimal number."""
        label = self.new_label("decimal")
        self.data[label] = struct.pack("<d", value)
        return label

    def reserve(self, size, hint="space"):
        label = self.new_label(hint)
        self.space[label] = size
        return label

    # ---- encoding helpers ----

    def emit(self, *parts):
        for part in parts:
            self.code += bytes([part]) if isinstance(part, int) else part

    def rex(self, wide, reg, rm, force=False):
        value = 0x40 | (8 if wide else 0) | (4 if reg & 8 else 0) | (1 if rm & 8 else 0)
        if value != 0x40 or force:
            self.emit(value)

    def reg_reg(self, opcode, reg, rm, wide=True, prefix=b""):
        self.emit(prefix)
        self.rex(wide, reg, rm)
        self.emit(opcode, 0xC0 | (reg & 7) << 3 | (rm & 7))

    def reg_mem(self, opcode, reg, base, offset, wide=True, force_rex=False):
        """reg together with the memory at [base + offset]."""
        self.rex(wide, reg, base, force_rex)
        self.emit(opcode, 0x80 | (reg & 7) << 3 | (base & 7))
        if base & 7 == RSP:
            self.emit(0x24)              # rsp and r12 need one extra byte
        self.emit(struct.pack("<i", offset))

    # ---- moving numbers around ----

    def set(self, reg, value):
        """reg = a fixed number."""
        if 0 <= value < 2**32:
            self.rex(False, 0, reg)
            self.emit(0xB8 + (reg & 7), struct.pack("<I", value))
        elif -2**31 <= value < 0:
            self.rex(True, 0, reg)
            self.emit(0xC7, 0xC0 | (reg & 7), struct.pack("<i", value))
        else:
            self.rex(True, 0, reg)
            self.emit(0xB8 + (reg & 7), struct.pack("<q", value))

    def address(self, reg, label):
        """reg = the address of a label."""
        self.rex(True, 0, reg)
        self.emit(0xB8 + (reg & 7))
        self.addresses.append((len(self.code), label))
        self.emit(bytes(8))

    def mov(self, dst, src):
        self.reg_reg(0x89, src, dst)

    def load(self, reg, base, offset=0):
        self.reg_mem(0x8B, reg, base, offset)

    def store(self, base, offset, reg):
        self.reg_mem(0x89, reg, base, offset)

    def load_byte(self, reg, base, offset=0):
        self.reg_mem(b"\x0f\xb6", reg, base, offset)

    def store_byte(self, base, offset, reg):
        self.reg_mem(0x88, reg, base, offset, wide=False, force_rex=True)

    def lea(self, reg, base, offset):
        self.reg_mem(0x8D, reg, base, offset)

    def push(self, reg):
        self.rex(False, 0, reg)
        self.emit(0x50 + (reg & 7))

    def pop(self, reg):
        self.rex(False, 0, reg)
        self.emit(0x58 + (reg & 7))

    def copy_bytes(self):
        """Copy rcx bytes from [rsi] to [rdi]."""
        self.emit(0xF3, 0xA4)

    def compare_bytes(self):
        """Compare rcx bytes at [rsi] and [rdi]; EQUAL if they all match."""
        self.emit(0xF3, 0xA6)

    # ---- whole-number maths ----

    def op(self, name, dst, src):
        """add / sub / and / or / xor / cmp / test, register with register."""
        self.reg_reg(ALU[name][0], src, dst)

    def op_n(self, name, dst, n):
        """add / sub / and / or / xor / cmp, register with a fixed number."""
        self.rex(True, 0, dst)
        self.emit(0x81, 0xC0 | ALU[name][1] << 3 | (dst & 7), struct.pack("<i", n))

    def multiply(self, dst, src):
        self.reg_reg(b"\x0f\xaf", dst, src)

    def divide(self, reg, signed=False):
        """rax = rdx:rax / reg, rdx = what's left over."""
        self.reg_reg(0xF7, 7 if signed else 6, reg)

    def sign_extend(self):
        """rdx = all ones if rax is negative, else zero (ready for a signed divide)."""
        self.emit(0x48, 0x99)

    def negate(self, reg):
        self.reg_reg(0xF7, 3, reg)

    def shift_left(self, reg, n):
        self.reg_reg(0xC1, 4, reg)
        self.emit(n)

    def shift_right(self, reg, n):
        self.reg_reg(0xC1, 5, reg)
        self.emit(n)

    # ---- decimal maths (on xmm registers) ----

    def to_xmm(self, xmm, reg):
        self.reg_reg(b"\x0f\x6e", xmm, reg, prefix=b"\x66")

    def from_xmm(self, reg, xmm):
        self.reg_reg(b"\x0f\x7e", xmm, reg, prefix=b"\x66")

    def decimal_maths(self, name, dst, src):
        """ADD F2 0F 58, SUB F2 0F 5C, MUL F2 0F 59, DIV F2 0F 5E."""
        self.reg_reg(bytes([0x0F, DECIMAL_MATHS[name]]), dst, src, wide=False, prefix=b"\xf2")

    def whole_to_decimal(self, xmm, reg):
        self.reg_reg(b"\x0f\x2a", xmm, reg, prefix=b"\xf2")

    def decimal_to_whole(self, reg, xmm):
        """Drops everything after the point."""
        self.reg_reg(b"\x0f\x2c", reg, xmm, prefix=b"\xf2")

    def round_decimal(self, dst, src, mode):
        """mode: 0 nearest, 1 down, 2 up, 3 towards zero."""
        self.reg_reg(b"\x0f\x3a\x0b", dst, src, wide=False, prefix=b"\x66")
        self.emit(mode)

    def compare_decimals(self, a, b):
        """Sets BELOW / EQUAL / ABOVE."""
        self.reg_reg(b"\x0f\x2e", a, b, wide=False, prefix=b"\x66")

    # ---- jumps and calls ----

    def jump_to(self, opcode, label):
        self.emit(opcode)
        self.jumps.append((len(self.code), label))
        self.emit(bytes(4))

    def jump(self, label):
        self.jump_to(0xE9, label)

    def jump_if(self, condition, label):
        self.jump_to(bytes([0x0F, 0x80 + condition]), label)

    def call(self, label):
        """CALL E8 [distance]"""
        self.jump_to(0xE8, label)

    def ret(self):
        """RETURN C3"""
        self.emit(0xC3)

    def syscall(self):
        self.emit(0x0F, 0x05)

    # ---- putting it together ----

    def link(self, code_address, space_address):
        """Fill in every address and distance. Returns (code + data bytes, size of the space)."""
        where = {name: code_address + at for name, at in self.labels.items()}
        data = b""
        for name, raw in self.data.items():
            where[name] = code_address + len(self.code) + len(data)
            data += raw
        size = 0
        for name, length in self.space.items():
            where[name] = space_address + size
            size += (length + 15) // 16 * 16
        code = bytearray(self.code)
        for at, name in self.jumps:
            code[at:at + 4] = struct.pack("<i", where[name] - (code_address + at + 4))
        for at, name in self.addresses:
            code[at:at + 8] = struct.pack("<Q", where[name])
        return bytes(code) + data, size
