"""Built-in bricks: small machine-code routines the program calls.

How they're called: inputs in rax, rcx, rdx; the answer comes back in rax.
A routine may change any register except rsp.

A text is stored as: 8-byte length, the letters, a zero byte.
A list is stored as: 8-byte count, then up to LIST_LIMIT 8-byte items.
New texts come from the heap and are never reused, so they start as zeros.
"""
import screen
from asm import (ABOVE, BELOW, EQUAL, GREATER, LESS, NOT_EQUAL, NOT_GREATER, NOT_LESS, NOT_NEGATIVE,
                 R8, R9, R10, R11, R12, R13, R14, R15, RAX, RCX, RDI, RDX, RSI, XMM0, XMM1)

TEXT_LIMIT = 256          # longest typed answer
LIST_LIMIT = 1000         # most items in a list
LIST_SIZE = 8 + LIST_LIMIT * 8
HEAP_SIZE = 64 * 1024 * 1024
FILE_LIMIT = 65536        # biggest file we read
BILLION = 1_000_000_000
RESET = "\x1b[0m"           # back to normal colours


def add_all(a):
    a.space["heap"] = HEAP_SIZE
    a.space["heap_end"] = 16      # right after the heap, so its address is where the heap stops
    for brick in [alloc, new_text, write_text, join, number_to_text, decimal_to_text,
                  text_to_number, same_letters, text_equal, match_at, contains, starts_with, ends_with,
                  change_case("upper", ord("a"), -32), change_case("lower", ord("A"), 32),
                  letter, split, letters, reverse_text, reverse_list, read_line, read_number, wait_key, sleep, random, now, elapsed, time_text,
                  push, push_front, remove_first, remove_last, item, list_has, list_to_text, list_copy,
                  file_save, file_load, file_delete]:
        brick(a)
    screen.add_all(a)


def say_fixed(a, s):
    a.address(RAX, a.text(s))
    a.call("write_text")


def start(a):
    """Runs first: note where the environment is, and point the heap at its start."""
    screen.remember_environment(a)
    a.address(RAX, "heap")
    a.address(RCX, "heap_next")
    a.store(RCX, 0, RAX)
    a.space["heap_next"] = 8


def finish(a, code=0):
    """EXIT"""
    a.set(RAX, 60)
    a.set(RDI, code)
    a.syscall()


# ---- memory and texts ----

def alloc(a):
    """rcx = bytes wanted -> rax = where they are."""
    a.label("alloc")
    a.op_n("add", RCX, 7)
    a.op_n("and", RCX, -8)
    a.address(RDX, "heap_next")
    a.load(RAX, RDX)
    a.mov(R8, RAX)
    a.op("add", R8, RCX)
    a.address(R9, "heap_end")
    a.op("cmp", R8, R9)
    a.jump_if(ABOVE, "out_of_memory")
    a.store(RDX, 0, R8)
    a.ret()
    a.label("out_of_memory")
    say_fixed(a, "\nOut of memory: the program made too many texts.\n")
    finish(a, 1)


def new_text(a):
    """rcx = length -> rax = a new, empty text of that length."""
    a.label("new_text")
    a.push(RCX)
    a.op_n("add", RCX, 9)
    a.call("alloc")
    a.pop(RCX)
    a.store(RAX, 0, RCX)
    a.ret()


def write_text(a):
    """rax = text -> shown on screen."""
    a.label("write_text")
    a.lea(RSI, RAX, 8)
    a.load(RDX, RAX)
    a.set(RAX, 1)
    a.set(RDI, 1)
    a.syscall()
    a.ret()


def join(a):
    """rax = first text, rcx = second text -> rax = both, one after the other."""
    a.label("join")
    a.push(RAX)
    a.push(RCX)
    a.load(RDX, RAX)
    a.load(R8, RCX)
    a.op("add", RDX, R8)
    a.mov(RCX, RDX)
    a.call("new_text")
    a.pop(R9)
    a.pop(R8)
    a.lea(RDI, RAX, 8)
    a.lea(RSI, R8, 8)
    a.load(RCX, R8)
    a.copy_bytes()
    a.lea(RSI, R9, 8)
    a.load(RCX, R9)
    a.copy_bytes()
    a.ret()


def number_to_text(a):
    """rax = whole number -> rax = it written as a text."""
    buffer = a.reserve(32, "digits")
    a.label("number_to_text")
    a.mov(R8, RAX)
    a.address(R9, buffer)
    a.op_n("add", R9, 32)
    a.set(R10, 0)
    a.op("test", R8, R8)
    a.jump_if(NOT_LESS, "ntt_digits")
    a.negate(R8)
    a.set(R10, 1)
    a.label("ntt_digits")
    a.set(RCX, 10)
    a.mov(RAX, R8)
    a.set(RDX, 0)
    a.divide(RCX)
    a.mov(R8, RAX)
    a.op_n("add", RDX, ord("0"))
    a.op_n("sub", R9, 1)
    a.store_byte(R9, 0, RDX)
    a.op("test", R8, R8)
    a.jump_if(NOT_EQUAL, "ntt_digits")
    a.op("test", R10, R10)
    a.jump_if(EQUAL, "ntt_copy")
    a.op_n("sub", R9, 1)
    a.set(RDX, ord("-"))
    a.store_byte(R9, 0, RDX)
    a.label("ntt_copy")
    a.address(RCX, buffer)
    a.op_n("add", RCX, 32)
    a.op("sub", RCX, R9)
    a.push(R9)
    a.call("new_text")
    a.pop(RSI)
    a.load(RCX, RAX)
    a.lea(RDI, RAX, 8)
    a.copy_bytes()
    a.ret()


def decimal_to_text(a):
    """rax = decimal, rcx = places after the point (-1: none if it's whole, else 2) -> rax = text."""
    v = a.reserve(48, "decimal_vars")    # 0 number, 8 places, 16 negative?, 24 scale, 32 scaled, 40 text
    half = a.number(0.5)
    a.label("decimal_to_text")
    a.mov(R8, RAX)                       # infinity (from dividing by 0) and "not a number" first
    a.shift_left(R8, 1)
    a.shift_right(R8, 1)
    a.set(R9, 0x7FF0000000000000)
    a.op("cmp", R8, R9)
    a.jump_if(BELOW, "dtt_normal")
    a.jump_if(ABOVE, "dtt_nan")
    a.op("test", RAX, RAX)
    a.address(RAX, a.text("infinity"))
    a.jump_if(NOT_NEGATIVE, "dtt_end")
    a.address(RAX, a.text("minus infinity"))
    a.ret()
    a.label("dtt_nan")
    a.address(RAX, a.text("not a number"))
    a.label("dtt_end")
    a.ret()
    a.label("dtt_normal")
    a.address(R11, v)
    a.mov(R8, RAX)
    a.shift_right(R8, 63)
    a.store(R11, 16, R8)
    a.shift_left(RAX, 1)                 # drop the sign
    a.shift_right(RAX, 1)
    a.store(R11, 0, RAX)
    a.op_n("cmp", RCX, -1)
    a.jump_if(NOT_EQUAL, "dtt_places")
    a.to_xmm(XMM0, RAX)
    a.round_decimal(XMM1, XMM0, 3)
    a.compare_decimals(XMM0, XMM1)
    a.set(RCX, 0)
    a.jump_if(EQUAL, "dtt_places")
    a.set(RCX, 2)
    a.label("dtt_places")
    a.store(R11, 8, RCX)
    a.set(RAX, 1)                        # scale = 10 x 10 x ... (places times)
    a.set(RDX, 10)
    a.label("dtt_scale")
    a.op("test", RCX, RCX)
    a.jump_if(EQUAL, "dtt_scaled")
    a.multiply(RAX, RDX)
    a.op_n("sub", RCX, 1)
    a.jump("dtt_scale")
    a.label("dtt_scaled")
    a.store(R11, 24, RAX)
    a.whole_to_decimal(XMM1, RAX)        # scaled = number x scale + 0.5, point dropped
    a.load(RAX, R11, 0)
    a.to_xmm(XMM0, RAX)
    a.decimal_maths("mul", XMM0, XMM1)
    a.address(RAX, half)
    a.load(RAX, RAX)
    a.to_xmm(XMM1, RAX)
    a.decimal_maths("add", XMM0, XMM1)
    a.decimal_to_whole(RAX, XMM0)
    a.store(R11, 32, RAX)
    a.load(RCX, R11, 24)                 # whole part and what's after the point
    a.set(RDX, 0)
    a.divide(RCX)
    a.push(RDX)
    a.call("number_to_text")
    a.pop(RDX)
    a.address(R11, v)
    a.store(R11, 40, RAX)
    a.load(R8, R11, 16)                  # put a minus sign in front, unless it rounds to zero
    a.op("test", R8, R8)
    a.jump_if(EQUAL, "dtt_after_sign")
    a.load(R8, R11, 32)
    a.op("test", R8, R8)
    a.jump_if(EQUAL, "dtt_after_sign")
    a.push(RDX)
    a.address(RAX, a.text("-"))
    a.load(RCX, R11, 40)
    a.call("join")
    a.pop(RDX)
    a.address(R11, v)
    a.store(R11, 40, RAX)
    a.label("dtt_after_sign")
    a.load(RCX, R11, 8)
    a.op("test", RCX, RCX)
    a.jump_if(EQUAL, "dtt_done")
    a.load(RAX, R11, 24)                 # scale + rest gives "1" then the digits, zeros kept;
    a.op("add", RAX, RDX)                # the "1" is then swapped for the point
    a.call("number_to_text")
    a.set(RCX, ord("."))
    a.store_byte(RAX, 8, RCX)
    a.mov(RCX, RAX)
    a.address(R11, v)
    a.load(RAX, R11, 40)
    a.jump("join")
    a.label("dtt_done")
    a.load(RAX, R11, 40)
    a.ret()


def text_to_number(a):
    """rax = text -> rax = the whole number at its start (0 if none)."""
    a.label("text_to_number")
    a.load(RCX, RAX)
    a.lea(RSI, RAX, 8)
    a.set(R8, 0)
    a.set(R9, 0)
    a.set(R10, 10)
    a.label("ttn_spaces")
    a.op("test", RCX, RCX)
    a.jump_if(EQUAL, "ttn_done")
    a.load_byte(RDX, RSI)
    a.op_n("cmp", RDX, ord(" "))
    a.jump_if(NOT_EQUAL, "ttn_sign")
    a.op_n("add", RSI, 1)
    a.op_n("sub", RCX, 1)
    a.jump("ttn_spaces")
    a.label("ttn_sign")
    a.op_n("cmp", RDX, ord("-"))
    a.jump_if(NOT_EQUAL, "ttn_digits")
    a.set(R9, 1)
    a.op_n("add", RSI, 1)
    a.op_n("sub", RCX, 1)
    a.label("ttn_digits")
    a.op("test", RCX, RCX)
    a.jump_if(EQUAL, "ttn_done")
    a.load_byte(RDX, RSI)
    a.op_n("sub", RDX, ord("0"))
    a.op_n("cmp", RDX, 9)
    a.jump_if(ABOVE, "ttn_done")
    a.multiply(R8, R10)
    a.op("add", R8, RDX)
    a.op_n("add", RSI, 1)
    a.op_n("sub", RCX, 1)
    a.jump("ttn_digits")
    a.label("ttn_done")
    a.mov(RAX, R8)
    a.op("test", R9, R9)
    a.jump_if(EQUAL, "ttn_end")
    a.negate(RAX)
    a.label("ttn_end")
    a.ret()


def same_letters(a):
    """rsi, rdi = where two runs of letters start, rcx = how many -> rax = 1 if they match.
    Capitals don't matter: "YES" matches "yes"."""
    def make_small(reg):
        skip = a.new_label("small")
        a.mov(R10, reg)
        a.op_n("sub", R10, ord("A"))
        a.op_n("cmp", R10, 25)
        a.jump_if(ABOVE, skip)
        a.op_n("add", reg, 32)
        a.label(skip)

    a.label("same_letters")
    a.op("test", RCX, RCX)
    a.jump_if(EQUAL, "sl_yes")
    a.load_byte(RAX, RSI)
    a.load_byte(RDX, RDI)
    make_small(RAX)
    make_small(RDX)
    a.op("cmp", RAX, RDX)
    a.jump_if(NOT_EQUAL, "sl_no")
    a.op_n("add", RSI, 1)
    a.op_n("add", RDI, 1)
    a.op_n("sub", RCX, 1)
    a.jump("same_letters")
    a.label("sl_yes")
    a.set(RAX, 1)
    a.ret()
    a.label("sl_no")
    a.set(RAX, 0)
    a.ret()


def text_equal(a):
    """rax, rcx = texts -> rax = 1 if they're the same (capitals don't matter), else 0."""
    a.label("text_equal")
    a.load(RDX, RAX)
    a.load(R8, RCX)
    a.op("cmp", RDX, R8)
    a.jump_if(NOT_EQUAL, "te_no")
    a.lea(RSI, RAX, 8)
    a.lea(RDI, RCX, 8)
    a.mov(RCX, RDX)
    a.jump("same_letters")
    a.label("te_no")
    a.set(RAX, 0)
    a.ret()


def match_at(a):
    """rax = text, rcx = smaller text, rdx = position -> rax = 1 if the smaller one is there."""
    a.label("match_at")
    a.op("test", RDX, RDX)
    a.jump_if(LESS, "ma_no")
    a.load(R8, RAX)
    a.load(R9, RCX)
    a.mov(R10, RDX)
    a.op("add", R10, R9)
    a.op("cmp", R10, R8)
    a.jump_if(GREATER, "ma_no")
    a.lea(RSI, RAX, 8)
    a.op("add", RSI, RDX)
    a.lea(RDI, RCX, 8)
    a.mov(RCX, R9)
    a.jump("same_letters")
    a.label("ma_no")
    a.set(RAX, 0)
    a.ret()


def contains(a):
    """rax = text, rcx = smaller text -> rax = 1 if it appears anywhere."""
    v = a.reserve(24, "contains_vars")   # 0 text, 8 smaller text, 16 position
    a.label("contains")
    a.address(R11, v)
    a.store(R11, 0, RAX)
    a.store(R11, 8, RCX)
    a.set(RDX, 0)
    a.label("contains_try")
    a.store(R11, 16, RDX)
    a.load(R8, RAX)
    a.load(R9, RCX)
    a.op("sub", R8, R9)
    a.op("cmp", RDX, R8)
    a.jump_if(GREATER, "contains_no")
    a.call("match_at")
    a.op("test", RAX, RAX)
    a.jump_if(NOT_EQUAL, "contains_yes")
    a.address(R11, v)
    a.load(RAX, R11, 0)
    a.load(RCX, R11, 8)
    a.load(RDX, R11, 16)
    a.op_n("add", RDX, 1)
    a.jump("contains_try")
    a.label("contains_no")
    a.set(RAX, 0)
    a.label("contains_yes")
    a.ret()


def starts_with(a):
    a.label("starts_with")
    a.set(RDX, 0)
    a.jump("match_at")


def ends_with(a):
    a.label("ends_with")
    a.load(RDX, RAX)
    a.load(R8, RCX)
    a.op("sub", RDX, R8)
    a.jump("match_at")


def change_case(name, first, shift):
    """Make a routine that shifts letters first..first+25 by shift (to capitals or to small)."""
    def brick(a):
        a.label(name)
        a.push(RAX)
        a.load(RCX, RAX)
        a.call("new_text")
        a.pop(RSI)
        a.load(RCX, RSI)
        a.lea(R8, RSI, 8)
        a.lea(R9, RAX, 8)
        a.label(f"{name}_next")
        a.op("test", RCX, RCX)
        a.jump_if(EQUAL, f"{name}_done")
        a.load_byte(RDX, R8)
        a.mov(R10, RDX)
        a.op_n("sub", R10, first)
        a.op_n("cmp", R10, 25)
        a.jump_if(ABOVE, f"{name}_keep")
        a.op_n("add", RDX, shift)
        a.label(f"{name}_keep")
        a.store_byte(R9, 0, RDX)
        a.op_n("add", R8, 1)
        a.op_n("add", R9, 1)
        a.op_n("sub", RCX, 1)
        a.jump(f"{name}_next")
        a.label(f"{name}_done")
        a.ret()
    return brick


def letter(a):
    """rax = text, rcx = N -> rax = its Nth letter (counting from 1), or empty if there isn't one."""
    a.label("letter")
    a.op_n("sub", RCX, 1)
    a.jump_if(LESS, "letter_none")
    a.load(RDX, RAX)
    a.op("cmp", RCX, RDX)
    a.jump_if(NOT_LESS, "letter_none")
    a.push(RAX)
    a.push(RCX)
    a.set(RCX, 1)
    a.call("new_text")
    a.pop(RCX)
    a.pop(RSI)
    a.op("add", RSI, RCX)
    a.load_byte(RDX, RSI, 8)
    a.store_byte(RAX, 8, RDX)
    a.ret()
    a.label("letter_none")
    a.set(RCX, 0)
    a.jump("new_text")


def split(a):
    """rax = text, rcx = list, rdx = the letter to split at, r8 = 1 to turn pieces into numbers.
    The list is emptied, then gets one item per piece (empty pieces are skipped)."""
    v = a.reserve(48, "split_vars")   # 0 text, 8 list, 16 split letter, 24 numbers?, 32 position, 40 piece start
    a.label("split")
    a.address(R11, v)
    a.store(R11, 0, RAX)
    a.store(R11, 8, RCX)
    a.store(R11, 16, RDX)
    a.store(R11, 24, R8)
    a.set(RDX, 0)
    a.store(RCX, 0, RDX)
    a.store(R11, 32, RDX)
    a.store(R11, 40, RDX)
    a.label("split_look")
    a.address(R11, v)
    a.load(RAX, R11, 0)
    a.load(RDX, R11, 32)
    a.load(RCX, RAX)
    a.op("cmp", RDX, RCX)
    a.jump_if(EQUAL, "split_last")
    a.op("add", RAX, RDX)
    a.load_byte(RAX, RAX, 8)
    a.load(RCX, R11, 16)
    a.op("cmp", RAX, RCX)
    a.jump_if(EQUAL, "split_cut")
    a.op_n("add", RDX, 1)
    a.store(R11, 32, RDX)
    a.jump("split_look")
    a.label("split_cut")
    a.call("split_piece")
    a.address(R11, v)
    a.load(RDX, R11, 32)
    a.op_n("add", RDX, 1)
    a.store(R11, 32, RDX)
    a.store(R11, 40, RDX)
    a.jump("split_look")
    a.label("split_last")
    a.call("split_piece")
    a.ret()
    # The piece runs from 'piece start' up to 'position'.
    a.label("split_piece")
    a.address(R11, v)
    a.load(RCX, R11, 32)
    a.load(RDX, R11, 40)
    a.op("sub", RCX, RDX)
    a.jump_if(EQUAL, "split_skip")
    a.call("new_text")
    a.address(R11, v)
    a.load(RCX, RAX)
    a.lea(RDI, RAX, 8)
    a.load(RSI, R11, 0)
    a.load(RDX, R11, 40)
    a.op("add", RSI, RDX)
    a.op_n("add", RSI, 8)
    a.copy_bytes()
    a.load(R8, R11, 24)
    a.op("test", R8, R8)
    a.jump_if(EQUAL, "split_keep_text")
    a.call("text_to_number")
    a.label("split_keep_text")
    a.mov(RCX, RAX)
    a.address(R11, v)
    a.load(RAX, R11, 8)
    a.jump("push")
    a.label("split_skip")
    a.ret()


def letters(a):
    """rax = text, rcx = list -> the list is emptied, then gets each letter as an item."""
    v = a.reserve(24, "letters_vars")   # 0 text, 8 list, 16 position
    a.label("letters")
    a.address(R11, v)
    a.store(R11, 0, RAX)
    a.store(R11, 8, RCX)
    a.set(RDX, 0)
    a.store(RCX, 0, RDX)
    a.set(RDX, 1)
    a.label("letters_next")
    a.store(R11, 16, RDX)
    a.load(RAX, R11, 0)
    a.load(RCX, RAX)
    a.op("cmp", RDX, RCX)
    a.jump_if(GREATER, "letters_done")
    a.mov(RCX, RDX)
    a.call("letter")
    a.mov(RCX, RAX)
    a.address(R11, v)
    a.load(RAX, R11, 8)
    a.call("push")
    a.address(R11, v)
    a.load(RDX, R11, 16)
    a.op_n("add", RDX, 1)
    a.jump("letters_next")
    a.label("letters_done")
    a.ret()


def reverse_text(a):
    """rax = text -> rax = a new text with its letters the other way round.
    A letter made of several bytes (like é) keeps its bytes in order."""
    a.label("reverse_text")
    a.push(RAX)
    a.load(RCX, RAX)
    a.call("new_text")
    a.pop(RSI)
    a.load(R8, RSI)
    a.op_n("add", RSI, 8)                  # the letters
    a.lea(R9, RAX, 8)                      # where they go
    a.op_n("sub", R8, 1)                   # the last byte
    a.label("revt_next")
    a.op_n("cmp", R8, 0)
    a.jump_if(LESS, "revt_done")
    a.mov(R10, R8)
    a.label("revt_start")                    # back to the first byte of this letter
    a.op_n("cmp", R10, 0)
    a.jump_if(EQUAL, "revt_copy")
    a.mov(R11, RSI)
    a.op("add", R11, R10)
    a.load_byte(RDX, R11)
    a.op_n("and", RDX, 0xC0)
    a.op_n("cmp", RDX, 0x80)
    a.jump_if(NOT_EQUAL, "revt_copy")
    a.op_n("sub", R10, 1)
    a.jump("revt_start")
    a.label("revt_copy")
    a.mov(R11, R10)
    a.label("revt_byte")
    a.op("cmp", R11, R8)
    a.jump_if(GREATER, "revt_moved")
    a.mov(RCX, RSI)
    a.op("add", RCX, R11)
    a.load_byte(RDX, RCX)
    a.store_byte(R9, 0, RDX)
    a.op_n("add", R9, 1)
    a.op_n("add", R11, 1)
    a.jump("revt_byte")
    a.label("revt_moved")
    a.mov(R8, R10)
    a.op_n("sub", R8, 1)
    a.jump("revt_next")
    a.label("revt_done")
    a.ret()


def reverse_list(a):
    """rax = list, rcx = space for a list -> rax = that space, holding the items the other way round."""
    a.label("reverse_list")
    a.load(RDX, RAX)
    a.store(RCX, 0, RDX)
    a.set(R8, 0)
    a.label("revl_next")
    a.op("cmp", R8, RDX)
    a.jump_if(NOT_LESS, "revl_done")
    a.mov(R9, RDX)
    a.op("sub", R9, R8)
    a.op_n("sub", R9, 1)
    a.shift_left(R9, 3)
    a.op("add", R9, RAX)
    a.load(R10, R9, 8)
    a.mov(R11, R8)
    a.shift_left(R11, 3)
    a.op("add", R11, RCX)
    a.store(R11, 8, R10)
    a.op_n("add", R8, 1)
    a.jump("revl_next")
    a.label("revl_done")
    a.mov(RAX, RCX)
    a.ret()


# ---- keyboard, clock, chance ----

def read_line(a):
    """-> rax = the text typed before Enter (up to TEXT_LIMIT letters, spaces at the end dropped).
    If the input has ended and nothing was typed, the program ends: there's nothing left to wait for."""
    a.label("read_line")
    a.set(RCX, TEXT_LIMIT)
    a.call("new_text")
    a.push(RAX)
    a.lea(R12, RAX, 8)                 # where the next key goes
    a.mov(R14, R12)                    # where the answer starts
    a.lea(R13, RAX, 8 + TEXT_LIMIT)    # end of the box
    a.label("rl_next")
    a.set(RAX, 0)
    a.set(RDI, 0)
    a.mov(RSI, R12)
    a.set(RDX, 1)
    a.syscall()
    a.op_n("cmp", RAX, 1)
    a.jump_if(NOT_EQUAL, "rl_ended")
    a.load_byte(RDX, R12)
    a.op_n("cmp", RDX, 10)
    a.jump_if(EQUAL, "rl_trim")
    a.op_n("add", R12, 1)
    a.op("cmp", R12, R13)
    a.jump_if(BELOW, "rl_next")
    a.jump("rl_trim")
    a.label("rl_ended")
    a.op("cmp", R12, R14)
    a.jump_if(EQUAL, "input_ended")
    a.label("rl_trim")                 # drop spaces (and Windows line endings) at the end
    a.op("cmp", R12, R14)
    a.jump_if(EQUAL, "rl_done")
    a.load_byte(RDX, R12, -1)
    a.op_n("cmp", RDX, ord(" "))
    a.jump_if(EQUAL, "rl_back")
    a.op_n("cmp", RDX, 13)
    a.jump_if(NOT_EQUAL, "rl_done")
    a.label("rl_back")
    a.op_n("sub", R12, 1)
    a.jump("rl_trim")
    a.label("rl_done")
    a.set(RDX, 0)
    a.store_byte(R12, 0, RDX)          # the Enter key isn't part of the answer
    a.pop(RAX)
    a.mov(RCX, R12)
    a.op("sub", RCX, RAX)
    a.op_n("sub", RCX, 8)
    a.store(RAX, 0, RCX)
    a.ret()
    a.label("input_ended")
    say_fixed(a, RESET + "\n")
    finish(a, 0)


def read_number(a):
    """-> rax = a whole number typed by the user. Asks again until it gets one."""
    a.label("read_number")
    a.call("read_line")
    a.lea(RSI, RAX, 8)
    a.load(RCX, RAX)
    a.label("rn_spaces")
    a.op("test", RCX, RCX)
    a.jump_if(EQUAL, "rn_again")
    a.load_byte(RDX, RSI)
    a.op_n("add", RSI, 1)
    a.op_n("sub", RCX, 1)
    a.op_n("cmp", RDX, ord(" "))
    a.jump_if(EQUAL, "rn_spaces")
    a.op_n("cmp", RDX, ord("-"))
    a.jump_if(NOT_EQUAL, "rn_digit")
    a.op("test", RCX, RCX)
    a.jump_if(EQUAL, "rn_again")
    a.load_byte(RDX, RSI)
    a.label("rn_digit")
    a.op_n("sub", RDX, ord("0"))
    a.op_n("cmp", RDX, 9)
    a.jump_if(ABOVE, "rn_again")
    a.jump("text_to_number")
    a.label("rn_again")
    say_fixed(a, "Please type a number: ")
    a.jump("read_number")


def wait_key(a):
    """-> rax = the one key pressed (no Enter needed when it's a real terminal)."""
    saved = a.reserve(64, "terminal_settings")
    keys_now = a.reserve(64, "terminal_keys_now")
    a.label("wait_key")
    a.set(RAX, 16)                     # ioctl: get the terminal settings
    a.set(RDI, 0)
    a.set(RSI, 0x5401)
    a.address(RDX, saved)
    a.syscall()
    a.mov(R14, RAX)                    # 0 means it's a real terminal
    a.op("test", R14, R14)
    a.jump_if(NOT_EQUAL, "wk_read")
    a.address(RSI, saved)
    a.address(RDI, keys_now)
    a.set(RCX, 64)
    a.copy_bytes()
    a.address(RDI, keys_now)
    a.load_byte(RDX, RDI, 12)          # switch off line-at-a-time, echo, and Ctrl+C stopping us
    a.op_n("and", RDX, ~0x0B)          # (we handle Ctrl+C ourselves, after putting the terminal back)
    a.store_byte(RDI, 12, RDX)
    a.set(RDX, 1)
    a.store_byte(RDI, 17 + 6, RDX)     # wait for 1 key
    a.set(RDX, 0)
    a.store_byte(RDI, 17 + 5, RDX)     # with no time limit
    a.set(RAX, 16)                     # ioctl: use the new settings
    a.set(RDI, 0)
    a.set(RSI, 0x5402)
    a.address(RDX, keys_now)
    a.syscall()
    a.label("wk_read")
    a.set(RCX, 1)
    a.call("new_text")
    a.push(RAX)
    a.lea(RSI, RAX, 8)
    a.set(RAX, 0)
    a.set(RDI, 0)
    a.set(RDX, 1)
    a.syscall()
    a.mov(R15, RAX)
    a.op("test", R14, R14)
    a.jump_if(NOT_EQUAL, "wk_done")
    a.set(RAX, 16)                     # ioctl: put the settings back
    a.set(RDI, 0)
    a.set(RSI, 0x5402)
    a.address(RDX, saved)
    a.syscall()
    a.label("wk_done")
    a.pop(RAX)
    a.op_n("cmp", R15, 1)
    a.jump_if(NOT_EQUAL, "input_ended")
    a.load_byte(RDX, RAX, 8)
    a.op_n("cmp", RDX, 3)              # Ctrl+C
    a.jump_if(NOT_EQUAL, "wk_end")
    say_fixed(a, RESET + "\n")
    finish(a, 130)
    a.label("wk_end")
    a.ret()


def sleep(a):
    """rax = nanoseconds to wait."""
    when = a.reserve(16, "sleep_time")
    a.label("sleep")
    a.op("test", RAX, RAX)
    a.jump_if(NOT_GREATER, "sleep_done")
    a.set(RDX, 0)
    a.set(RCX, BILLION)
    a.divide(RCX)
    a.address(RDI, when)
    a.store(RDI, 0, RAX)
    a.store(RDI, 8, RDX)
    a.set(RSI, 0)
    a.set(RAX, 35)
    a.syscall()
    a.label("sleep_done")
    a.ret()


def random(a):
    """rax = lowest, rcx = highest -> rax = a random whole number from lowest to highest."""
    chance = a.reserve(8, "random_bytes")
    a.label("random")
    a.push(RAX)
    a.push(RCX)
    a.set(RAX, 318)                    # getrandom
    a.address(RDI, chance)
    a.set(RSI, 8)
    a.set(RDX, 0)
    a.syscall()
    a.pop(RCX)
    a.pop(R8)
    a.op("sub", RCX, R8)
    a.op_n("add", RCX, 1)
    a.jump_if(NOT_GREATER, "random_lowest")
    a.address(RDI, chance)
    a.load(RAX, RDI)
    a.set(RDX, 0)
    a.divide(RCX)
    a.mov(RAX, RDX)
    a.op("add", RAX, R8)
    a.ret()
    a.label("random_lowest")
    a.mov(RAX, R8)
    a.ret()


def now(a):
    """rdi = which clock (0 time of day, 1 stopwatch) -> rax = nanoseconds."""
    when = a.reserve(16, "clock_reading")
    a.label("now")
    a.set(RAX, 228)                    # CLOCK  B8 E4 00 00 00 ... 48 BE [where] 0F 05
    a.address(RSI, when)
    a.syscall()
    a.address(RSI, when)
    a.load(RAX, RSI)
    a.set(RCX, BILLION)
    a.multiply(RAX, RCX)
    a.load(RCX, RSI, 8)
    a.op("add", RAX, RCX)
    a.ret()


def elapsed(a):
    """rax = a stopwatch start -> rax = seconds since then, as a decimal."""
    billion = a.number(BILLION)
    a.label("elapsed")
    a.push(RAX)
    a.set(RDI, 1)
    a.call("now")
    a.pop(RCX)
    a.op("sub", RAX, RCX)
    a.whole_to_decimal(XMM0, RAX)
    a.address(RAX, billion)
    a.load(RAX, RAX)
    a.to_xmm(XMM1, RAX)
    a.decimal_maths("div", XMM0, XMM1)
    a.from_xmm(RAX, XMM0)
    a.ret()


def time_text(a):
    """-> rax = the time of day as HH:MM:SS (UTC)."""
    def two_digits(offset):
        a.set(RDX, 0)
        a.set(RCX, 10)
        a.divide(RCX)
        a.op_n("add", RAX, ord("0"))
        a.store_byte(R13, offset, RAX)
        a.op_n("add", RDX, ord("0"))
        a.store_byte(R13, offset + 1, RDX)

    a.label("time_text")
    a.set(RDI, 0)
    a.call("now")
    a.set(RDX, 0)
    a.set(RCX, BILLION)
    a.divide(RCX)
    a.set(RDX, 0)
    a.set(RCX, 86400)
    a.divide(RCX)
    a.mov(R12, RDX)                    # seconds since midnight
    a.set(RCX, 8)
    a.call("new_text")
    a.mov(R13, RAX)
    a.set(RCX, ord(":"))
    a.store_byte(R13, 10, RCX)
    a.store_byte(R13, 13, RCX)
    a.mov(RAX, R12)
    a.set(RDX, 0)
    a.set(RCX, 3600)
    a.divide(RCX)
    a.mov(R12, RDX)
    two_digits(8)
    a.mov(RAX, R12)
    a.set(RDX, 0)
    a.set(RCX, 60)
    a.divide(RCX)
    a.mov(R12, RDX)
    two_digits(11)
    a.mov(RAX, R12)
    two_digits(14)
    a.mov(RAX, R13)
    a.ret()


# ---- lists ----

def push(a):
    """rax = list, rcx = item -> item added on the end.
    LOAD COUNT, STORE AT start + count x 8, ADD 1 TO COUNT."""
    a.label("push")
    a.load(RDX, RAX)
    a.op_n("cmp", RDX, LIST_LIMIT)
    a.jump_if(NOT_LESS, "list_full")
    a.mov(R8, RDX)
    a.shift_left(R8, 3)
    a.op("add", R8, RAX)
    a.store(R8, 8, RCX)
    a.op_n("add", RDX, 1)
    a.store(RAX, 0, RDX)
    a.ret()
    a.label("list_full")
    say_fixed(a, f"(That list is full: {LIST_LIMIT:,} items is the most it can hold.)\n")
    a.ret()


def push_front(a):
    """rax = list, rcx = item -> item added at the front."""
    a.label("push_front")
    a.load(RDX, RAX)
    a.op_n("cmp", RDX, LIST_LIMIT)
    a.jump_if(NOT_LESS, "list_full")
    a.mov(R8, RDX)
    a.label("pf_move")
    a.op("test", R8, R8)
    a.jump_if(EQUAL, "pf_put")
    a.mov(R9, R8)
    a.shift_left(R9, 3)
    a.op("add", R9, RAX)
    a.load(R10, R9)
    a.store(R9, 8, R10)
    a.op_n("sub", R8, 1)
    a.jump("pf_move")
    a.label("pf_put")
    a.store(RAX, 8, RCX)
    a.op_n("add", RDX, 1)
    a.store(RAX, 0, RDX)
    a.ret()


def remove_first(a):
    """rax = list, rcx = what to give back if it's empty -> rax = the first item, now removed."""
    a.label("remove_first")
    a.load(RDX, RAX)
    a.op("test", RDX, RDX)
    a.jump_if(EQUAL, "list_empty")
    a.load(R10, RAX, 8)
    a.op_n("sub", RDX, 1)
    a.store(RAX, 0, RDX)
    a.lea(RDI, RAX, 8)
    a.lea(RSI, RAX, 16)
    a.mov(RCX, RDX)
    a.shift_left(RCX, 3)
    a.copy_bytes()
    a.mov(RAX, R10)
    a.ret()
    a.label("list_empty")
    a.mov(RAX, RCX)
    a.ret()


def remove_last(a):
    """rax = list, rcx = what to give back if it's empty -> rax = the last item, now removed."""
    a.label("remove_last")
    a.load(RDX, RAX)
    a.op("test", RDX, RDX)
    a.jump_if(EQUAL, "list_empty")
    a.op_n("sub", RDX, 1)
    a.store(RAX, 0, RDX)
    a.shift_left(RDX, 3)
    a.op("add", RAX, RDX)
    a.load(RAX, RAX, 8)
    a.ret()


def item(a):
    """rax = list, rcx = N, rdx = what to give back if there's no item N -> rax = item N."""
    a.label("item")
    a.op_n("sub", RCX, 1)
    a.jump_if(LESS, "item_none")
    a.load(R8, RAX)
    a.op("cmp", RCX, R8)
    a.jump_if(NOT_LESS, "item_none")
    a.shift_left(RCX, 3)
    a.op("add", RAX, RCX)
    a.load(RAX, RAX, 8)
    a.ret()
    a.label("item_none")
    a.mov(RAX, RDX)
    a.ret()


def list_has(a):
    """rax = list, rcx = thing, rdx = 1 if the items are texts -> rax = 1 if the thing is in the list."""
    v = a.reserve(32, "has_vars")   # 0 list, 8 thing, 16 texts?, 24 position
    a.label("list_has")
    a.address(R11, v)
    a.store(R11, 0, RAX)
    a.store(R11, 8, RCX)
    a.store(R11, 16, RDX)
    a.set(R8, 0)
    a.label("has_next")
    a.address(R11, v)
    a.store(R11, 24, R8)
    a.load(RAX, R11, 0)
    a.load(R9, RAX)
    a.op("cmp", R8, R9)
    a.jump_if(NOT_LESS, "has_no")
    a.shift_left(R8, 3)
    a.op("add", RAX, R8)
    a.load(RAX, RAX, 8)
    a.load(RCX, R11, 8)
    a.load(RDX, R11, 16)
    a.op("test", RDX, RDX)
    a.jump_if(EQUAL, "has_numbers")
    a.call("text_equal")
    a.op("test", RAX, RAX)
    a.jump_if(NOT_EQUAL, "has_yes")
    a.jump("has_again")
    a.label("has_numbers")
    a.op("cmp", RAX, RCX)
    a.jump_if(EQUAL, "has_yes")
    a.label("has_again")
    a.address(R11, v)
    a.load(R8, R11, 24)
    a.op_n("add", R8, 1)
    a.jump("has_next")
    a.label("has_yes")
    a.set(RAX, 1)
    a.ret()
    a.label("has_no")
    a.set(RAX, 0)
    a.ret()


def list_to_text(a):
    """rax = list, rcx = kind (0 whole numbers, 1 decimals, 2 texts), rdx = text to put between
    -> rax = all the items as one text."""
    v = a.reserve(40, "ltt_vars")   # 0 list, 8 kind, 16 between, 24 position, 32 result
    a.label("list_to_text")
    a.address(R11, v)
    a.store(R11, 0, RAX)
    a.store(R11, 8, RCX)
    a.store(R11, 16, RDX)
    a.address(RAX, a.text(""))
    a.store(R11, 32, RAX)
    a.set(R8, 0)
    a.label("ltt_next")
    a.address(R11, v)
    a.store(R11, 24, R8)
    a.load(RAX, R11, 0)
    a.load(R9, RAX)
    a.op("cmp", R8, R9)
    a.jump_if(NOT_LESS, "ltt_done")
    a.op("test", R8, R8)
    a.jump_if(EQUAL, "ltt_item")
    a.load(RAX, R11, 32)
    a.load(RCX, R11, 16)
    a.call("join")
    a.address(R11, v)
    a.store(R11, 32, RAX)
    a.label("ltt_item")
    a.load(RAX, R11, 0)
    a.load(R8, R11, 24)
    a.shift_left(R8, 3)
    a.op("add", RAX, R8)
    a.load(RAX, RAX, 8)
    a.load(RCX, R11, 8)
    a.op_n("cmp", RCX, 1)
    a.jump_if(ABOVE, "ltt_join")
    a.jump_if(EQUAL, "ltt_decimal")
    a.call("number_to_text")
    a.jump("ltt_join")
    a.label("ltt_decimal")
    a.set(RCX, -1)
    a.call("decimal_to_text")
    a.label("ltt_join")
    a.mov(RCX, RAX)
    a.address(R11, v)
    a.load(RAX, R11, 32)
    a.call("join")
    a.address(R11, v)
    a.store(R11, 32, RAX)
    a.load(R8, R11, 24)
    a.op_n("add", R8, 1)
    a.jump("ltt_next")
    a.label("ltt_done")
    a.load(RAX, R11, 32)
    a.ret()


def list_copy(a):
    """rax = from list, rcx = to list -> the to list becomes the same as the from list."""
    a.label("list_copy")
    a.mov(RSI, RAX)
    a.mov(RDI, RCX)
    a.set(RCX, LIST_SIZE)
    a.copy_bytes()
    a.ret()


# ---- files (in the folder the program runs from) ----

def file_save(a):
    """rax = file name, rcx = text, rdx = how to open (replace or add to the end) -> 1 if it worked."""
    a.label("file_save")
    a.push(RCX)
    a.lea(RDI, RAX, 8)                 # OPEN  B8 02 00 00 00 ... BA A4 01 00 00 0F 05
    a.mov(RSI, RDX)
    a.set(RDX, 0o644)
    a.set(RAX, 2)
    a.syscall()
    a.pop(RCX)
    a.op("test", RAX, RAX)
    a.jump_if(LESS, "fs_failed")
    a.mov(R12, RAX)
    a.lea(RSI, RCX, 8)                 # WRITE the text
    a.load(RDX, RCX)
    a.set(RAX, 1)
    a.mov(RDI, R12)
    a.syscall()
    a.address(RSI, a.text("\n"))       # and end the line
    a.op_n("add", RSI, 8)
    a.set(RDX, 1)
    a.set(RAX, 1)
    a.mov(RDI, R12)
    a.syscall()
    a.set(RAX, 3)                      # CLOSE  B8 03 00 00 00 ... 0F 05
    a.mov(RDI, R12)
    a.syscall()
    a.set(RAX, 1)
    a.ret()
    a.label("fs_failed")
    say_fixed(a, "(Couldn't save that file.)\n")
    a.set(RAX, 0)
    a.ret()


def file_load(a):
    """rax = file name -> rax = everything in it as a text (last line ending dropped), or 0 if there's no such file."""
    a.label("file_load")
    a.lea(RDI, RAX, 8)
    a.set(RSI, 0)
    a.set(RDX, 0)
    a.set(RAX, 2)
    a.syscall()
    a.op("test", RAX, RAX)
    a.jump_if(LESS, "fl_missing")
    a.mov(R12, RAX)
    a.set(RCX, FILE_LIMIT)
    a.call("new_text")
    a.mov(R13, RAX)
    a.set(R14, 0)                      # bytes read so far
    a.label("fl_read")
    a.set(RDX, FILE_LIMIT)
    a.op("sub", RDX, R14)
    a.jump_if(EQUAL, "fl_close")
    a.lea(RSI, R13, 8)
    a.op("add", RSI, R14)
    a.mov(RDI, R12)
    a.set(RAX, 0)
    a.syscall()
    a.op("test", RAX, RAX)
    a.jump_if(NOT_GREATER, "fl_close")
    a.op("add", R14, RAX)
    a.jump("fl_read")
    a.label("fl_close")
    a.set(RAX, 3)
    a.mov(RDI, R12)
    a.syscall()
    a.op("test", R14, R14)
    a.jump_if(EQUAL, "fl_size")
    a.mov(R8, R13)
    a.op("add", R8, R14)
    a.load_byte(RDX, R8, 7)
    a.op_n("cmp", RDX, 10)
    a.jump_if(NOT_EQUAL, "fl_size")
    a.op_n("sub", R14, 1)
    a.set(RDX, 0)
    a.store_byte(R8, 7, RDX)
    a.label("fl_size")
    a.store(R13, 0, R14)
    a.mov(RAX, R13)
    a.ret()
    a.label("fl_missing")
    a.set(RAX, 0)
    a.ret()


def file_delete(a):
    """rax = file name -> asks "are you sure?" first, then deletes it."""
    name = a.reserve(8, "delete_name")
    a.label("file_delete")
    a.address(R11, name)
    a.store(R11, 0, RAX)
    say_fixed(a, "Are you sure you want to delete ")
    a.address(R11, name)
    a.load(RAX, R11)
    a.call("write_text")
    say_fixed(a, "? (yes/no) ")
    a.call("read_line")
    a.load_byte(RDX, RAX, 8)
    a.op_n("or", RDX, 0x20)            # Y or y
    a.op_n("cmp", RDX, ord("y"))
    a.jump_if(NOT_EQUAL, "fd_keep")
    a.address(R11, name)
    a.load(RAX, R11)
    a.lea(RDI, RAX, 8)                 # DELETE  B8 57 00 00 00 ... 0F 05
    a.set(RAX, 87)
    a.syscall()
    a.op("test", RAX, RAX)
    a.jump_if(LESS, "fd_missing")
    say_fixed(a, "Deleted.\n")
    a.ret()
    a.label("fd_missing")
    say_fixed(a, "(There was no such file.)\n")
    a.ret()
    a.label("fd_keep")
    say_fixed(a, "OK, I kept it.\n")
    a.ret()
