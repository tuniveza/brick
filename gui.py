"""A window for brick: write plain English on the left, build and run it, and watch how it's made.

  brick gui                   opens it in your web browser (python3 gui.py works too)
  brick gui game.txt          opens it with game.txt loaded
  brick gui --app             opens it in a window of its own (a browser app window), and closes
                              itself a few minutes after that window is closed (the launcher uses this)

Save .brick (in the window) or `brick export game.txt` writes game.brick: the program and everything
the window shows about it, as plain text, to hand to someone (or Claude) to read.

It's a small web page served from this computer only (http://127.0.0.1:8766). The page is gui.html.
Building looks just like `brick build`; running happens in a console inside the page, or in a
console window of its own. Watching the build: a Compiler that notes, line by line, how each line
was split and tidied and which machine code it made, then objdump turns the bytes back into
instructions we can read.
"""
import base64
import fcntl
import json
import os
import pty
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import brick  # noqa: E402
import review  # noqa: E402
import dictionary  # noqa: E402
import runtime  # noqa: E402
import screen  # noqa: E402
from actions import COLOURS, STARTERS, help_text  # noqa: E402
from compiler import FILLER, Compiler  # noqa: E402
from elf import FILE_ADDRESS, HEADERS_SIZE, SPACE_ADDRESS, wrap  # noqa: E402
from expressions import Problem  # noqa: E402
from reader import group_parts, split_line  # noqa: E402

PORT = 8766
NOWHERE = "class:^brick-gui-no-window$"     # a run inside the page has no window of its own to move


# ---- watching a build ----

class Watching(Compiler):
    """A Compiler that writes down what it did with each line."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spans = []                # (depth, line number, code start, code end)
        self.splits = {}               # line number -> [{"joined": "then", "words": "write hi"}, ...]
        self.tidied = {}               # line number -> [(as typed, as understood), ...]
        self.places = {}               # space label -> (name, kind)
        self.actions = []              # (depth, line number, the direction's words, code start, code end)
        self.action_depth = 0
        self.depth = 0
        self.program_at = None         # where the lines' code starts and stops
        self.program_end = None

    def compile_items(self, items, problems):
        top = self.program_at is None
        if top:
            self.program_at = len(self.a.code)
        super().compile_items(items, problems)
        if top:
            self.program_end = len(self.a.code)

    def compile_item(self, items, k, problems, line=None):
        start = len(self.a.code)
        self.depth += 1
        try:
            return super().compile_item(items, k, problems, line)
        finally:
            self.depth -= 1
            self.spans.append((self.depth, items[k][0], start, len(self.a.code)))

    def compile_action(self, words):
        start = len(self.a.code)
        self.action_depth += 1
        try:
            return super().compile_action(words)
        finally:
            self.action_depth -= 1
            if len(self.a.code) > start:
                self.actions.append((self.action_depth, self.line_number, " ".join(w.raw for w in words),
                                     start, len(self.a.code)))

    def compile_line(self, line, block=None, otherwise=None):
        try:
            pieces = split_line(line, self.starts_action)
            self.splits.setdefault(self.line_number, []).extend(
                [{"joined": p.joined_by, "words": " ".join(w.raw for w in p.words)} for p in pieces])
        except Exception:
            pass
        return super().compile_line(line, block, otherwise)

    def tidy(self, actions):
        tidied = super().tidy(actions)
        typed = [a for a in actions if not all(w.word in FILLER for w in a)]
        for before, after in zip(typed, tidied):
            self.tidied.setdefault(self.line_number, []).append(
                (" ".join(w.raw for w in before), " ".join(w.raw for w in after)))
        return tidied

    def new_var(self, name, kind, scope=None):
        var = super().new_var(name, kind, scope)
        self.places[var.place] = (name.replace("_", " "), kind)
        return var



def owners(spans, size):
    """Which line made each byte of code: the innermost line wins."""
    owner = [None] * size
    for depth, number, start, end in sorted(spans, key=lambda s: s[0]):
        for i in range(start, min(end, size)):
            owner[i] = number
    return owner


def addresses(asm):
    """Every label's address once linked, as asm.link() works them out."""
    code_at = FILE_ADDRESS + HEADERS_SIZE
    where = {name: code_at + at for name, at in asm.labels.items()}
    data_at = code_at + len(asm.code)
    for name, raw in asm.data.items():
        where[name] = data_at
        data_at += len(raw)
    size = 0
    for name, length in asm.space.items():
        where[name] = SPACE_ADDRESS + size
        size += (length + 15) // 16 * 16
    return where


def describe_labels(compiler):
    """label -> what a person would call it."""
    asm = compiler.a
    names = {}
    for text, label in asm.texts.items():
        shown = text if len(text) <= 40 else text[:37] + "..."
        names[label] = "text " + json.dumps(shown)
    for label, raw in asm.data.items():
        if label.startswith("decimal_"):
            names[label] = "the number " + repr(struct.unpack("<d", raw)[0])
    for label, (name, kind) in compiler.places.items():
        names[label] = f"{name} ({kind})" if name != "it" else "it (the latest answer)"
    for label in list(asm.labels) + list(asm.space):
        names.setdefault(label, label)
    return names


def routine_notes():
    """A runtime routine's label -> the first line of its docstring."""
    notes = {}
    for module in (runtime, screen):
        for name in dir(module):
            thing = getattr(module, name)
            if callable(thing) and getattr(thing, "__doc__", None) and getattr(thing, "__module__", "") == module.__name__:
                notes[name] = thing.__doc__.strip().splitlines()[0]
    return notes


def disassemble(code, at):
    """objdump's view of the code: [(address, bytes as hex, instruction)]. [] if objdump isn't there."""
    if not shutil.which("objdump") or not code:
        return []
    with tempfile.NamedTemporaryFile(suffix=".bin") as f:
        f.write(code)
        f.flush()
        out = subprocess.run(["objdump", "-D", "-b", "binary", "-m", "i386:x86-64", "-M", "intel",
                              "--insn-width=16", f"--adjust-vma={at:#x}", f.name],
                             capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines():
        m = re.match(r"\s+([0-9a-f]+):\t([0-9a-f ]+?)\s*\t(.*)", line)
        if m:
            found.append((int(m[1], 16), m[2].strip(), m[3].strip()))
    return found


def watch(text, folder):
    """Build text as `brick` would, writing down how. Returns everything the page shows."""
    words_file = os.path.join(folder, "mywords.txt")
    with tempfile.TemporaryDirectory() as scratch:                  # new words seen while typing stay out of mywords.txt
        mine = os.path.join(scratch, "mywords.txt")
        if os.path.isfile(words_file):
            shutil.copy(words_file, mine)
        compiler = Watching(mine, ask_user=lambda question: "yes")
        problems, program = [], None
        import neural
        neural.patient = False          # while you type: never wait for the model (it answers in the background)
        started = time.perf_counter()
        try:
            program = compiler.compile(text)
        except Problem as problem:
            problems = str(problem).split("\n")
        except Exception as error:                                   # a compiler bug shouldn't kill the window
            problems = [f"Line {compiler.line_number}: (brick itself tripped up here)", f"    {type(error).__name__}: {error}"]
        took = time.perf_counter() - started
        neural.patient = True
    return report(compiler, text, program, problems, took)


def report(compiler, text, program, problems, took):
    asm = compiler.a
    size = len(asm.code)
    program_at = compiler.program_at or 0
    program_end = compiler.program_end if compiler.program_end is not None else size
    owner = owners(compiler.spans, size)
    where = addresses(asm)
    names = describe_labels(compiler)
    by_address = {}
    for label, address in where.items():
        by_address.setdefault(address, names.get(label, label))
    code_labels = {at: label for label, at in asm.labels.items()}
    notes = routine_notes()
    called = {label for at, label in asm.jumps if at > 0 and asm.code[at - 1] == 0xE8}     # 0xE8: call
    routine_starts = {label for label in asm.labels
                      if label in called or label in notes or label.startswith("word_")}

    # problems, by line
    trouble = {}
    current = None
    for line in problems:
        m = re.match(r"Line (\d+): ", line)
        if m:
            current = int(m[1])
            trouble.setdefault(current, [])
        elif current is not None:
            trouble[current].append(line.strip())

    # the code, cut into runs: startup, a line's code, the end, then each runtime routine
    instructions = []
    linked = None
    if size:
        try:
            body, _ = asm.link(FILE_ADDRESS + HEADERS_SIZE, SPACE_ADDRESS)
            linked = body[:size]
        except KeyError:                    # a jump to a label that never got made (only when it didn't build)
            linked = bytes(asm.code)
    for address, raw, op in disassemble(linked, FILE_ADDRESS + HEADERS_SIZE) if linked else []:
        at = address - FILE_ADDRESS - HEADERS_SIZE
        if at < 0 or at >= size:
            continue
        said = ""
        for hexed in re.findall(r"0x[0-9a-f]+", op):
            value = int(hexed, 16)
            if value in by_address:
                said = by_address[value]
                if op.split()[0] in ("call", "jmp") or op.split()[0].startswith("j"):
                    op = op.replace(hexed, by_address[value])
                    said = ""
                break
        if op.split()[0] == "syscall":
            said = "ask Linux to do something (which thing: the number in rax)"
        instructions.append({"at": at, "address": f"{address:x}", "bytes": raw, "op": op, "note": said,
                             "label": code_labels.get(at), "line": owner[at] if at < len(owner) else None})

    runs = []
    for ins in instructions:
        at = ins["at"]
        if at < program_at:
            kind, key = "start", "start"
        elif at < program_end:
            kind, key = ("line", ins["line"]) if ins["line"] is not None else ("glue", "glue")
        else:
            label = ins["label"]
            if label in routine_starts and (not runs or runs[-1]["kind"] != "routine" or runs[-1]["name"] != label):
                kind, key = "routine", label
            elif runs and runs[-1]["kind"] in ("routine", "end"):
                kind, key = runs[-1]["kind"], runs[-1]["key"]
            else:
                kind, key = "end", "end"
        if not runs or runs[-1]["key"] != key or runs[-1]["kind"] != kind:
            runs.append({"kind": kind, "key": key, "name": key if kind == "routine" else None,
                         "note": notes.get(key, "") if kind == "routine" else "", "code": []})
        runs[-1]["code"].append(ins)

    # the lines
    lines = []
    made = {}
    for ins in instructions:
        if ins["line"] is not None and program_at <= ins["at"] < program_end:
            made[ins["line"]] = made.get(ins["line"], 0) + len(ins["bytes"].split())
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        lines.append({
            "number": number, "text": raw, "indent": len(raw.expandtabs(4)) - len(raw.expandtabs(4).lstrip()),
            "kind": "blank" if not stripped else "note" if stripped.startswith("#") else "line",
            "pieces": compiler.splits.get(number, []),
            "tidied": [{"typed": a, "meant": b} for a, b in compiler.tidied.get(number, [])],
            "bytes": made.get(number, 0), "problems": trouble.get(number),
        })

    # the literal bytes of the file, and what made each stretch of them
    try:
        whole = program or wrap(asm)
    except KeyError:
        whole = None
    regions = [[0, 64, "header", "ELF header: says this is a 64-bit Linux program and where to start", None],
               [64, 120, "header", "segment header 1: load the file at 0x400000 (read + run)", None],
               [120, HEADERS_SIZE, "header", "segment header 2: an empty space at 0x10000000 (read + write)", None]]
    for run in runs:
        first, last = run["code"][0], run["code"][-1]
        start, end = HEADERS_SIZE + first["at"], HEADERS_SIZE + last["at"] + len(last["bytes"].split())
        if run["kind"] == "line":
            said = f"line {run['key']}"
        elif run["kind"] == "routine":
            said = f"toolbox routine {run['key']}" + (f": {run['note']}" if run["note"] else "")
        else:
            said = {"start": "startup: note the environment, set up the heap",
                    "end": "the end: put colours back, exit", "glue": "glue between lines"}[run["kind"]]
        regions.append([start, end, run["kind"], said, run["key"] if run["kind"] == "line" else None])
    at = HEADERS_SIZE + size
    text_of = {label: t for t, label in asm.texts.items()}
    stored = []                                # [file start, file end, the text] for each text in the file
    for label, raw in asm.data.items():
        if label in text_of:
            stored.append([at, at + len(raw), text_of[label]])
        at += len(raw)
    at = HEADERS_SIZE + size
    for label, raw in asm.data.items():
        regions.append([at, at + len(raw), "data", names.get(label, label) + " (stored: 8-byte length, the letters, a 0)"
                        if label.startswith("text_") else names.get(label, label), None])
        at += len(raw)

    data_size = sum(len(raw) for raw in asm.data.values())
    space = []
    for label, length in asm.space.items():
        space.append({"name": names.get(label, label), "label": label, "size": length,
                      "address": f"{where[label]:x}", "yours": label in compiler.places})
    texts = [{"text": t, "address": f"{where[label]:x}", "size": len(asm.data[label])}
             for t, label in asm.texts.items()]
    routines = [r for r in runs if r["kind"] == "routine"]
    return {
        "ok": program is not None, "problems": problems, "notes": compiler.notes, "took": round(took * 1000, 1),
        "lines": lines, "runs": runs, "uses_window": compiler.uses_window,
        "layout": {
            "headers": HEADERS_SIZE, "start": program_at, "program": program_end - program_at,
            "end": (routines[0]["code"][0]["at"] if routines else size) - program_end,
            "runtime": size - (routines[0]["code"][0]["at"] if routines else size),
            "data": data_size, "space": sum((n + 15) // 16 * 16 for n in asm.space.values()),
            "file": len(program) if program else HEADERS_SIZE + size + data_size,
            "file_address": f"{FILE_ADDRESS:x}", "space_address": f"{SPACE_ADDRESS:x}",
            "entry": f"{FILE_ADDRESS + HEADERS_SIZE:x}",
        },
        "space": space, "texts": texts,
        "file_bytes": base64.b64encode(whole).decode() if whole else None, "regions": regions,
        # which direction made each stretch of code (file offsets; deeper = inside another, like a taught word)
        "actions": [[depth, line, words, HEADERS_SIZE + start, HEADERS_SIZE + end]
                    for depth, line, words, start, end in getattr(compiler, "actions", [])],
        "stored": stored,
        "counts": {"lines": sum(1 for l in lines if l["kind"] == "line"),
                   "actions": sum(len(l["tidied"]) for l in lines),
                   "instructions": len(instructions), "routines": len(routines)},
    }


# ---- a .brick file: everything the window knows about a program, as plain text ----

ABOUT_BRICK = """\
# This is a .brick file: a program written in plain English for brick, and everything brick made from it.
# brick is a compiler that turns everyday English sentences (one direction per line) into a small 64-bit
# Linux program (an ELF file) with no libraries: just its own machine code and a toolbox of routines.
# Reading this? Start with SOURCE (what the person wrote) and LINES (how brick understood each line).
# The later sections are the program itself: its memory, its machine code line by line, and every byte.
"""


def export(text, path=None, console=None):
    """The whole of what the window shows for this program, as one plain-text .brick file."""
    folder = os.path.dirname(path) if path else os.getcwd()
    r = watch(text, folder)
    out = [ABOUT_BRICK, f"file: {path or 'untitled (not saved)'}", f"made: {time.strftime('%Y-%m-%d %H:%M')}", ""]

    def section(title):
        out.extend(["", f"== {title} ==", ""])

    section("SOURCE (what was written)")
    for line in r["lines"]:
        out.append(f"{line['number']:4} | {line['text']}")

    section("BUILD")
    out.append(f"built: {'yes' if r['ok'] else 'no'}  ({r['took']} ms)")
    out.append(f"opens a console window of its own (window words): {'yes' if r['uses_window'] else 'no'}")
    out.extend(f"problem: {p}" for p in r["problems"])
    out.extend(f"note: {n}" for n in r["notes"])
    out.append("counts: " + ", ".join(f"{v:,} {k}" for k, v in r["counts"].items()))

    section("LINES (how brick understood each line)")
    for line in r["lines"]:
        if line["kind"] == "blank":
            continue
        out.append(f"line {line['number']}: {line['text'].strip()}")
        if line["kind"] == "note":
            out.append("    a note for people (# ...): makes no code")
        if len(line["pieces"]) > 1:
            for piece in line["pieces"]:
                out.append(f"    piece{' (joined by ' + repr(piece['joined']) + ')' if piece['joined'] else ''}: {piece['words']}")
        for step in line["tidied"]:
            if step["typed"] == step["meant"]:
                out.append(f"    does: {step['meant']}")
            else:
                out.append(f"    does: {step['meant']}    (as typed: {step['typed']})")
        if line["bytes"]:
            out.append(f"    machine code: {line['bytes']:,} bytes")
        out.extend(f"    PROBLEM: {p}" for p in line["problems"] or ())

    section("LAYOUT (sizes in bytes)")
    layout = r["layout"]
    out.extend([f"whole file: {layout['file']:,}", f"headers: {layout['headers']:,}", f"startup code: {layout['start']:,}",
                f"your lines' code: {layout['program']:,}", f"ending code: {layout['end']:,}",
                f"toolbox routines: {layout['runtime']:,}", f"stored data (texts, numbers): {layout['data']:,}",
                f"empty space for memory, made when it starts: {layout['space']:,}",
                f"loaded at 0x{layout['file_address']}, starts running at 0x{layout['entry']}, "
                f"memory space at 0x{layout['space_address']}"])

    section("MEMORY (the empty space, and what each part is for)")
    for place in r["space"]:
        out.append(f"0x{place['address']}  {place['size']:>8,} bytes  {place['name']}{'  (one of yours)' if place['yours'] else ''}")

    section("TEXTS (stored in the program file)")
    for t in r["texts"]:
        out.append(f"0x{t['address']}  {json.dumps(t['text'])}")

    section("MACHINE CODE (x86-64, Intel syntax; address  bytes  instruction  ; what it means)")
    lines_by_number = {l["number"]: l["text"].strip() for l in r["lines"]}
    for run in r["runs"]:
        if run["kind"] == "line":
            heading = f"line {run['key']}: {lines_by_number.get(run['key'], '')}"
        elif run["kind"] == "routine":
            heading = f"toolbox routine {run['key']}" + (f": {run['note']}" if run["note"] else "")
        else:
            heading = {"start": "startup: note the environment, set up the heap", "end": "the end: put colours back, exit",
                       "glue": "glue between lines"}[run["kind"]]
        out.append(f"-- {heading} --")
        for ins in run["code"]:
            out.append(f"  {ins['address']}  {ins['bytes']:<30} {ins['op']}" + (f"    ; {ins['note']}" if ins["note"] else ""))
    if not r["runs"]:
        out.append("(none: it didn't build, or objdump isn't installed)")

    section("FILE REGIONS (byte offsets in the program file: what made each stretch)")
    for start, end, kind, said, _ in r["regions"]:
        out.append(f"{start:>7,} - {end:<7,} {kind:<8} {said}")

    section("FILE BYTES (every byte of the program file, in hex)")
    whole = base64.b64decode(r["file_bytes"]) if r["file_bytes"] else b""
    for at in range(0, len(whole), 16):
        chunk = whole[at:at + 16]
        shown = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{at:08x}  {chunk.hex(' '):<47}  |{shown}|")
    if not whole:
        out.append("(none: it didn't build)")

    if console is not None:
        section("CONSOLE (what the console in the window showed last)")
        out.append(console.rstrip() or "(empty)")
    return "\n".join(out) + "\n"


def brick_path(path, folder):
    """game.txt -> game.brick, next to it; an unsaved program -> untitled.brick in the folder brick gui started in."""
    return (os.path.splitext(path)[0] if path else os.path.join(folder, "untitled")) + ".brick"


# ---- the program's bytes as brick materials: game.sand, game.clay, game.shale, game.cement ----

MATERIALS = {
    "sand": "the bare 1s and 0s, one unbroken stream",
    "clay": "the 1s and 0s row by row, each stretch labelled with what made it",
    "shale": "the same rows in hex",
    "cement": "the actual program file itself, byte for byte",
}


def material_path(path, folder, kind):
    """game.txt -> game.clay (or .sand, .shale, .cement), next to it (like brick_path)."""
    return brick_path(path, folder)[:-len(".brick")] + "." + kind


def materials(text, path=None, kinds=tuple(MATERIALS)):
    """{kind: bytes to write} for each material, all from one build so they agree. None if it doesn't build."""
    folder = os.path.dirname(path) if path else os.getcwd()
    r = watch(text, folder)
    if not r["file_bytes"]:
        return None
    whole = base64.b64decode(r["file_bytes"])
    made = {}
    for kind in kinds:
        if kind == "cement":
            made[kind] = whole
        elif kind == "sand":
            made[kind] = ("".join(f"{b:08b}" for b in whole) + "\n").encode()
        else:
            made[kind] = layers(r, whole, path, kind).encode()
    return made


def layers(r, whole, path, kind):
    """clay (bits, 8 bytes a row) or shale (hex, 16 a row): rows of the file under what made each stretch."""
    per_row, show = (8, lambda b: f"{b:08b}") if kind == "clay" else (16, lambda b: f"{b:02x}")
    said = {line["number"]: line["text"].strip() for line in r["lines"]}
    out = [f"# {kind}: the program file made from {path or 'an unsaved program'}, as "
           + ("the 1s and 0s it really is." if kind == "clay" else "hex (each pair is one byte)."),
           f"# {len(whole):,} bytes = {len(whole) * 8:,} ones and zeros. Each row: where in the file (hex), "
           f"up to {per_row} bytes, and those bytes as letters (. for ones that aren't letters).",
           f"# made: {time.strftime('%Y-%m-%d %H:%M')}", ""]
    width = per_row * (len(show(0)) + 1) - 1

    def rows(start, end):
        for at in range(start, end, per_row):
            chunk = whole[at:min(at + per_row, end)]
            shown = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            out.append(f"{at:08x}  {' '.join(show(b) for b in chunk):<{width}}  |{shown}|")

    at = 0
    for start, end, kind_of, about, key in sorted(r["regions"]):
        if start > at:                         # bytes no region claims (there shouldn't be any)
            out.extend(["", "-- (other bytes) --"])
            rows(at, start)
        if kind_of == "line" and key in said:
            about += f": {said[key]}"
        out.extend(["", f"-- {about} --"])
        rows(start, end)
        at = max(at, end)
    if at < len(whole):
        out.extend(["", "-- (other bytes) --"])
        rows(at, len(whole))
    return "\n".join(out) + "\n"


def write_materials(text, path, folder, kinds=tuple(MATERIALS)):
    """Write the materials next to the program. Returns the paths written, or None if it doesn't build."""
    made = materials(text, path, kinds)
    if made is None:
        return None
    written = []
    for kind, data in made.items():
        where = material_path(path, folder, kind)
        with open(where, "wb") as f:
            f.write(data)
        if kind == "cement":
            os.chmod(where, 0o755)             # it's the real program: ./game.cement runs it
        written.append(where)
    return written


# ---- running a program in the page ----

class Session:
    """One running program, in a pseudo-terminal. The page fetches what it writes and sends keys."""

    def __init__(self, program, folder, rows, cols):
        self.output = bytearray()
        self.done = None                       # its exit code once it stops
        self.changed = threading.Condition()
        keyboard, terminal = pty.openpty()
        fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        env = dict(os.environ, BRICK_WINDOW=NOWHERE, TERM="xterm-256color")
        self.process = subprocess.Popen([program], stdin=terminal, stdout=terminal, stderr=terminal,
                                        cwd=folder, env=env, start_new_session=True)
        os.close(terminal)
        self.keyboard = keyboard
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        while True:
            try:
                chunk = os.read(self.keyboard, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            with self.changed:
                self.output += chunk
                self.changed.notify_all()
        code = self.process.wait()
        with self.changed:
            self.done = code if code >= 0 else 128 - code
            self.changed.notify_all()
        os.close(self.keyboard)

    def since(self, offset, seconds=20):
        with self.changed:
            self.changed.wait_for(lambda: len(self.output) > offset or self.done is not None, seconds)
            return bytes(self.output[offset:]), self.done

    def type(self, data):
        if self.done is None:
            try:
                os.write(self.keyboard, data)
            except OSError:
                pass

    def resize(self, rows, cols):
        if self.done is None:
            try:
                fcntl.ioctl(self.keyboard, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                os.killpg(self.process.pid, signal.SIGWINCH)
            except OSError:
                pass

    def stop(self):
        if self.done is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except OSError:
                pass


sessions = {}
lock = threading.Lock()
last_id = [0]
scratch = []                                # one folder for unsaved programs, made when first needed


def build_for_running(text, path):
    """Build the text next to its file (as `brick build` would), or in a scratch folder if it's not saved.
    Returns (program, folder, problems, notes)."""
    if not path and not scratch:
        scratch.append(tempfile.mkdtemp(prefix="brick-gui-"))
    folder = os.path.dirname(path) if path else scratch[0]
    output = os.path.splitext(path)[0] if path else os.path.join(folder, "program")
    if path and output == path:
        output += ".program"
    compiler = Compiler(os.path.join(folder, "mywords.txt"), ask_user=lambda question: "yes")
    import factory
    where = os.path.basename(path) if path else "a program in brick gui"
    try:
        program = compiler.compile(text)
    except Problem as problem:
        factory.after_build(text, compiler, str(problem), where)          # brick keeps working on it
        return None, folder, str(problem).split("\n"), compiler.notes
    factory.after_build(text, compiler, where=where)                       # what it fixed, it learns to keep
    if os.path.isdir(output):
        return None, folder, [f"There's already a folder called {output}. Rename the .txt file or the folder."], []
    with open(output, "wb") as f:
        f.write(program)
    os.chmod(output, 0o755)
    return output, folder, [], compiler.notes + [f"Built {output} ({len(program):,} bytes)."]


# ---- 'Not what I meant' ----

def fix_options(text, number, words_file):
    """For one line: what brick does with it now, and other readings that make a different program."""
    import universe
    lines = text.split("\n")
    line = lines[number - 1].strip() if 0 < number <= len(lines) else ""
    compiler = Compiler(universe.trial_words(words_file), ask_user=lambda question: "no")
    try:
        compiler.compile(text)
    except Exception:
        pass
    told = next((n.split(" read as: ", 1)[1].replace(" (as you said)", "") for n in compiler.notes
                 if n.startswith(f"Note: line {number} read as: ")), None)
    told_lines = lines[:number - 1] + [told or line] + lines[number:]
    made = {review.build("\n".join(told_lines), compiler.words_file)}
    others = []
    for way in universe.tellings(line) + ([universe.sure(line)] if universe.sure(line) else []):
        program = review.build("\n".join(lines[:number - 1] + [way] + lines[number:]), compiler.words_file)
        if way and program and program not in made:
            made.add(program)
            others.append(way)
    return {"line": line, "told": told, "others": others[:5]}


def keep_general(line, meant, words_file):
    """After a correction: if it can be made a general pattern (and the tests agree), lines like it are
    fixed too. Runs in the background: the tests take a little while."""
    try:
        import factory
        entry = review.generalise(line, meant, words_file)
        if entry:
            ok, message = factory.teach(entry)
            import outliers
            outliers.note(("learned from your correction: " if ok else "couldn't keep: ") + entry)
    except Exception:
        pass


# ---- the web server ----

def examples():
    folder = os.path.join(HERE, "texts", "examples")
    found = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".txt"):
            with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as f:
                found.append({"name": name[:-4], "path": os.path.join(folder, name), "text": f.read()})
    return found


def files_here(folder):
    try:
        return sorted(n for n in os.listdir(folder) if n.endswith(".txt") and os.path.isfile(os.path.join(folder, n)))
    except OSError:
        return []


APP_IDLE = 180                                  # --app: seconds with no word from the page before it closes
last_seen = [time.monotonic()]                  # when the page last asked for anything


def open_app(address):
    """Open the page as an app window (no tabs or address bar) in a Chromium-type browser, else a tab."""
    for browser in (os.path.expanduser("~/.local/bin/emberline-helium"), "helium", "chromium",
                    "google-chrome-stable", "brave", "thorium-browser"):
        found = browser if os.path.isfile(browser) and os.access(browser, os.X_OK) else shutil.which(browser)
        if found:
            subprocess.Popen([found, f"--app={address}"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return
    webbrowser.open(address)


def close_when_idle(server):
    """--app: the window pings every 20 seconds (once a minute at worst while hidden); once it's
    been quiet for APP_IDLE, the window has gone, so stop (and the factory stops with brick gui)."""
    while True:
        time.sleep(15)
        if time.monotonic() - last_seen[0] > APP_IDLE:
            print("The brick window has closed, so brick gui is closing too.", flush=True)
            server.shutdown()
            return


class Handler(BaseHTTPRequestHandler):
    start_folder = os.getcwd()
    reviewing = False
    start_file = None

    def log_message(self, *args):
        pass

    def send(self, body, kind="application/json", status=200):
        last_seen[0] = time.monotonic()
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def asked(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def full_path(self, path):
        path = os.path.expanduser(path.strip())
        return os.path.abspath(os.path.join(self.start_folder, path))

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/alive":                 # the window is still open
            return self.send({"ok": True})
        if url.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "gui.html"), "rb") as f:
                return self.send(f.read(), "text/html; charset=utf-8")
        if url.path == "/api/start":
            text = ""
            if self.start_file and os.path.isfile(self.start_file):
                with open(self.start_file, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            colours = {name: code.split(";", 2)[2].replace(";", ",") for name, (code, _) in dictionary.colour_table().items()
                       if code.startswith("38;2;")}
            colours.update({name: code.split(";", 2)[2].replace(";", ",") for name, code in COLOURS.items()
                            if code.startswith("38;2;")})
            return self.send({"folder": self.start_folder, "file": self.start_file, "text": text,
                              "starters": sorted(STARTERS), "colours": colours,
                              "files": files_here(self.start_folder), "examples": examples()})
        if url.path == "/api/decisions":
            import factory
            import outliers
            log = os.path.join(factory.FOLDER, "log.txt")
            activity = []
            if os.path.isfile(log):
                with open(log, encoding="utf-8", errors="replace") as f:
                    activity = [line.rstrip() for line in f][-40:][::-1]
            return self.send({"running": factory.running(), "activity": activity, "items": outliers.entries(),
                              "director": len(outliers.entries(outliers.FOR_DIRECTOR))})
        if url.path == "/api/bricks":
            import bricks
            return self.send({"groups": bricks.palette()})
        if url.path == "/api/help":
            return self.send({"phrases": help_text(), "dictionary": dictionary.listing(None)})
        if url.path == "/api/output":
            session = sessions.get(query.get("id"))
            if not session:
                return self.send({"error": "That program isn't running."}, status=404)
            data, done = session.since(int(query.get("from", 0)))
            return self.send({"data": base64.b64encode(data).decode(), "done": done})
        return self.send({"error": "not here"}, status=404)

    def do_POST(self):
        url = urlparse(self.path)
        asked = self.asked()
        if url.path == "/api/watch":
            folder = os.path.dirname(asked["path"]) if asked.get("path") else self.start_folder
            return self.send(watch(asked.get("text", ""), folder))
        if url.path == "/api/open":
            path = self.full_path(asked["path"])
            if not os.path.isfile(path) and os.path.isfile(path + ".txt"):
                path += ".txt"
            if not os.path.isfile(path):
                return self.send({"error": f"I can't find {path}."})
            with open(path, encoding="utf-8", errors="replace") as f:
                return self.send({"path": path, "text": f.read()})
        if url.path == "/api/save":
            path = self.full_path(asked["path"])
            if not path.endswith(".txt"):
                path += ".txt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(asked.get("text", ""))
            return self.send({"path": path, "files": files_here(os.path.dirname(path))})
        if url.path == "/api/fix_options":
            # 'Not what I meant' on a line: what brick does with it now, and the other ways to read it
            folder = os.path.dirname(asked["path"]) if asked.get("path") else self.start_folder
            return self.send(fix_options(asked.get("text", ""), int(asked.get("number", 1)),
                                         os.path.join(folder, "mywords.txt")))
        if url.path == "/api/fix":
            folder = os.path.dirname(asked["path"]) if asked.get("path") else self.start_folder
            words = os.path.join(folder, "mywords.txt")
            text, number, meant = asked.get("text", ""), int(asked.get("number", 1)), asked.get("meant", "").strip()
            problem = review.correct(text, number, meant, words) if meant else "Say what it means first."
            if problem:
                return self.send({"ok": False, "message": problem})
            line = text.split("\n")[number - 1].strip()
            threading.Thread(target=keep_general, args=(line, meant, words), daemon=True).start()
            return self.send({"ok": True, "message": f"Kept: brick reads '{line}' as '{meant}' from now on."})
        if url.path == "/api/read_line":
            import bricks
            return self.send({"directions": bricks.read_line(asked.get("line", ""))})
        if url.path == "/api/read_lines":
            # the whole program as bricks, line by line (the Brick wall)
            import bricks
            lines = []
            for number, raw in enumerate(asked.get("text", "").split("\n"), 1):
                stripped = raw.strip()
                kind = "blank" if not stripped else "note" if stripped.startswith("#") else "line"
                lines.append({"number": number, "text": raw, "kind": kind,
                              "indent": len(raw.expandtabs(4)) - len(raw.expandtabs(4).lstrip()),
                              "directions": bricks.read_line(raw) if kind == "line" else []})
            return self.send({"lines": lines})
        if url.path == "/api/decide":
            import outliers
            ok, message = outliers.decide(asked.get("id", ""), asked.get("action", ""), asked.get("meaning", "").strip())
            return self.send({"ok": ok, "message": message})
        if url.path == "/api/guessed":
            folder = os.path.dirname(asked["path"]) if asked.get("path") else self.start_folder
            return self.send({"guessed": review.guessed(asked.get("text", ""), os.path.join(folder, "mywords.txt"))})
        if url.path == "/api/review":
            # each answer: {"number", "line", "told", "meant"}; meant == told means 'yes, that's right'
            folder = os.path.dirname(asked["path"]) if asked.get("path") else self.start_folder
            problems = {}
            for answer in asked.get("answers", []):
                if answer["meant"].strip() == answer["told"]:
                    review.confirm(answer["line"], answer["told"])
                else:
                    problem = review.correct(asked.get("text", ""), int(answer["number"]), answer["meant"].strip(),
                                             os.path.join(folder, "mywords.txt"))
                    if problem:
                        problems[answer["number"]] = problem
            if self.reviewing and not problems:       # opened just for this review: close in a moment
                threading.Timer(3, self.server.shutdown).start()
            return self.send({"problems": problems, "closing": self.reviewing and not problems})
        if url.path == "/api/export":
            where = brick_path(asked.get("path"), self.start_folder)
            with open(where, "w", encoding="utf-8") as f:
                f.write(export(asked.get("text", ""), asked.get("path"), asked.get("console")))
            return self.send({"path": where})
        if url.path == "/api/bits":
            written = write_materials(asked.get("text", ""), asked.get("path"), self.start_folder)
            if written is None:
                return self.send({"error": "It didn't build, so there are no bits yet."})
            return self.send({"paths": written})
        if url.path == "/api/run":
            program, folder, problems, notes = build_for_running(asked.get("text", ""), asked.get("path"))
            if not program:
                return self.send({"problems": problems, "notes": notes})
            if asked.get("where") == "build":
                return self.send({"built": program, "notes": notes})
            if asked.get("where") == "window":
                if brick.open_window(program, os.path.basename(program), asked.get("path")):
                    return self.send({"window": True, "notes": notes})
                notes.append("(No graphical desktop here, so it runs inside this page instead.)")
            notes_guessed = review.guessed(asked.get("text", ""), os.path.join(folder, "mywords.txt"))
            session = Session(program, folder, int(asked.get("rows", 24)), int(asked.get("cols", 80)))
            with lock:
                last_id[0] += 1
                key = str(last_id[0])
                sessions[key] = session
            return self.send({"id": key, "notes": notes, "guessed": notes_guessed})
        if url.path in ("/api/type", "/api/resize", "/api/stop"):
            session = sessions.get(str(asked.get("id")))
            if not session:
                return self.send({"error": "That program isn't running."}, status=404)
            if url.path == "/api/type":
                session.type(asked.get("data", "").encode())
            elif url.path == "/api/resize":
                session.resize(int(asked["rows"]), int(asked["cols"]))
            else:
                session.stop()
            return self.send({"ok": True})
        return self.send({"error": "not here"}, status=404)


def main(args=None):
    args = sys.argv[1:] if args is None else args
    show = "--no-browser" not in args
    app = "--app" in args                           # a window of its own, from the launcher
    Handler.reviewing = "--review" in args          # opened just for a review: it closes once that's done
    args = [a for a in args if a not in ("--no-browser", "--review", "--app")]
    if args:
        source = brick.find_source(args[0])
        if source is None:
            print(f"I can't find {args[0]} in {os.getcwd()}. Check the name, or cd to its folder first.")
            sys.exit(1)
        Handler.start_file = os.path.abspath(source)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"Something is already using port {PORT}; brick gui may be open already: http://127.0.0.1:{PORT}")
        (open_app if app else webbrowser.open)(f"http://127.0.0.1:{PORT}")
        return
    server.daemon_threads = True
    address = f"http://127.0.0.1:{PORT}" + (f"/?file={quote(Handler.start_file)}&review=1" if Handler.reviewing else "")
    print(f"brick gui is at {address}  (press Ctrl+C here to close it)")
    if show:
        threading.Timer(0.3, lambda: (open_app if app else webbrowser.open)(address)).start()
    if app:
        threading.Thread(target=close_when_idle, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        for session in sessions.values():
            session.stop()


if __name__ == "__main__":
    main()
