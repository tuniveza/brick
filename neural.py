"""The neural reader: a pretrained language model, running on this computer, that suggests what a line means
in brick's own words, for lines brick and its universe can't settle by themselves.

It's a local model (Qwen 2.5 by default) served by Ollama on the graphics card. brick starts Ollama when
it needs it and stops it with brick, like the factory. Nothing is sent anywhere.

  when brick is stuck on a line, or the universe isn't sure of it, the model suggests readings
  when brick would print a direction word for word ('write hello in blue at the x 20 and y 20' showing all
  of that), the model is asked whether it's really words to show or a direction
Every suggestion is built before it's used, like any other reading; the note says what brick did, and
the review asks afterwards. Answers are remembered per line (texts/factory/neural.json), so it's fast.

    brick neural                   is it ready? which model?
    brick neural setup             start Ollama and download the model (once)
    brick neural model NAME        use another model (qwen2.5:7b is smarter, and slower)
    brick neural off / on          stop or start using it
"""
import atexit
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(HERE, "texts", "factory", "neural-settings.json")
CACHE = os.path.join(HERE, "texts", "factory", "neural.json")
SERVER = "http://127.0.0.1:11434"
MODEL = "qwen2.5:3b"
patient = True                   # False while brick gui previews as you type: never wait for the model then

GUIDE = """You translate loose, messy English into brick, a tiny programming language written in plain English.
brick can do only these things, written exactly like this:
  write WORDS                          write WORDS in COLOUR              write WORDS in bold
  write WORDS at the top | at the bottom | on the left | on the right | in the middle | at the top-left ...
  write WORDS at row R column C        (x is how far across = column, y is how far down = row)
  write WORDS N times                  after N seconds write WORDS        wait N seconds
  clear the screen                     beep                               stop
  set the background colour to COLOUR  set the colour to COLOUR           make it say WORDS
  make it disappear after N seconds    put the window on the left side of the screen (or right, top, bottom)
  make the window bigger | smaller | full screen                          set the title to WORDS
  ask "QUESTION" as NAME               set NAME to VALUE                  add N to NAME
  repeat N times: DIRECTION            if NAME is VALUE, DIRECTION        for each X in LIST, DIRECTION
Rules:
- Keep every direction the person gave, in order, joined with " then ".
- "after N seconds" always goes at the very start of its direction: after 2 seconds write hi in red.
- Use "write", not "make it say", unless something was just shown and the person wants it changed.
- Keep the words to show exactly as the person wrote them; never add words they didn't write.
- If the line really is just words to show, the reading is: write THOSE WORDS.
Reply with JSON only: {"readings": ["best reading", "second best", "third best"]}"""

EXAMPLES = [
    ("put text at left side of screen with red color", 'write "text" in red on the left'),
    ("bg red", "set the background colour to red"),
    ("hi x3", "write hi 3 times"),
    ("2 secs wait", "wait 2 seconds"),
    ("window left", "put the window on the left side of the screen"),
    ("can you put at the top of the screen a blue text that says hi there", "write hi there in blue at the top"),
    ("write hello in blue at the x 20 and y 20", "write hello in blue at row 20 column 20"),
    ("make text navy", "set the colour to navy"),
    ("splash the screen red", "set the background colour to red"),
    ("write I live in a red house", "write I live in a red house"),
    ("on top the words see you soon cyan say after 2 sec", "after 2 seconds write see you soon in cyan at the top"),
    ("bg orange then saying lets go in green bottom", "set the background colour to orange then write lets go in green at the bottom"),
]
VERSION = 2                      # the guide's version: answers to an older guide are asked again


# ---------------- settings ----------------

def settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return {"on": True, "model": MODEL, **json.load(f)}
    except (OSError, ValueError):
        return {"on": True, "model": MODEL}


def save_settings(**changes):
    found = {**settings(), **changes}
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(found, f)


def off():
    """Not used in the tests (BRICK_MEMORY=off or BRICK_NEURAL=off), when switched off, or when Ollama isn't here."""
    return os.environ.get("BRICK_NEURAL") == "off" or os.environ.get("BRICK_MEMORY") == "off" or \
        not settings()["on"] or not shutil.which("ollama")


# ---------------- Ollama, started with brick ----------------

_server, _ready = None, None


def call(path, body=None, seconds=60):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(SERVER + path, data, {"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(request, timeout=seconds) as response:
        return json.loads(response.read() or b"{}")


def running():
    try:
        call("/api/tags", seconds=1)
        return True
    except Exception:
        return False


def start():
    """Ollama running, started by brick if need be (and stopped when brick stops). False if it can't be."""
    global _server
    if running():
        return True
    if not shutil.which("ollama"):
        return False
    if _server is None:
        # Ollama lives only as long as this brick: a watchdog stops it the moment brick's process is gone,
        # even if brick is killed outright; and brick stops it itself when it ends normally.
        watch = 'ollama serve & s=$!; while kill -0 "$0" 2>/dev/null && kill -0 $s 2>/dev/null; do sleep 2; done; ' \
                'kill $s 2>/dev/null'
        _server = subprocess.Popen(["sh", "-c", watch, str(os.getpid())], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                                   env=dict(os.environ, OLLAMA_KEEP_ALIVE="3m"))    # off the graphics card when idle
        atexit.register(lambda: os.killpg(_server.pid, 15) if _server.poll() is None else None)
    for _ in range(40):
        if running():
            return True
        time.sleep(0.25)
    return False


def have_model():
    try:
        names = {m.get("name", "") for m in call("/api/tags", seconds=3).get("models", [])}
    except Exception:
        return False
    want = settings()["model"]
    return want in names or f"{want}:latest" in names


def ready():
    """Can the model be asked right now? (Starts Ollama the first time, if it's installed.)"""
    global _ready
    if off():
        return False
    if _ready is None:
        _ready = start() and have_model()
    return _ready


# ---------------- asking ----------------

_cache = None
_asking = set()
_lock = threading.Lock()


def cache():
    global _cache
    if _cache is None:
        try:
            with open(CACHE, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def remember(key, readings):
    with _lock:
        cache()[key] = readings
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE + ".new", "w", encoding="utf-8") as f:
            json.dump(cache(), f)
        os.replace(CACHE + ".new", CACHE)


def readings(line, before=""):
    """What the model thinks the line means, in brick's words (best first), or [] if it can't say now.
    before: the lines just before it, for context. Remembered, so each line is only asked about once.
    When brick mustn't wait (typing in brick gui), it asks in the background and says [] for now."""
    line = line.strip()
    if not line or off():
        return []
    key = f"{settings()['model']}|{VERSION}|{before.strip()[-200:]}|{line}"
    if key in cache():
        return cache()[key]
    if not patient:
        if key not in _asking and not off():
            _asking.add(key)
            threading.Thread(target=ask, args=(line, before, key), daemon=True).start()
        return []
    return ask(line, before, key)


def ask(line, before, key):
    try:
        if not ready():
            return []
        messages = [{"role": "system", "content": GUIDE}]
        for said, meant in EXAMPLES:
            messages += [{"role": "user", "content": said},
                         {"role": "assistant", "content": json.dumps({"readings": [meant]})}]
        asked = (f"(the lines before it: {before.strip()[-200:]})\n" if before.strip() else "") + line
        messages.append({"role": "user", "content": asked})
        answer = call("/api/chat", {"model": settings()["model"], "messages": messages, "stream": False,
                                    "format": "json", "options": {"temperature": 0.1, "num_predict": 200}})
        found = json.loads(answer.get("message", {}).get("content", "{}")).get("readings", [])
        found = [re.sub(r"\s+", " ", r).strip().strip(".") for r in found if isinstance(r, str) and r.strip()]
        found = [r for r in found if only_known_words(r, line)][:4]
        remember(key, found)
        return found
    except Exception:
        return []
    finally:
        _asking.discard(key)


JUDGE = """You judge what a person meant. They wrote a line for brick, a tiny programming language written in
plain English (it can write words, colour them, place them on the screen, wait, beep, clear the screen, set
the background colour, move its window, repeat things). Below are possible readings of their line in brick's
own words. Pick the one that does what the person most likely wanted. Words that look like instructions
(splash, paint, shout, ding, wipe ... off) are usually instructions, not words to show.
Reply with JSON only: {"choice": NUMBER}"""


def choose(line, ways, before=""):
    """Which of these readings did the person mean? -> its index, or None if the model can't say now.
    Remembered, like readings."""
    if not ways or off():
        return None
    key = f"choose|{settings()['model']}|{VERSION}|{before.strip()[-200:]}|{line}|" + "||".join(ways)
    if key in cache():
        return cache()[key]
    if not patient:
        return None
    try:
        if not ready():
            return None
        listed = "\n".join(f"{k + 1}. {way}" for k, way in enumerate(ways))
        asked = (f"(the lines before it: {before.strip()[-200:]})\n" if before.strip() else "") + \
            f"They wrote: {line}\nReadings:\n{listed}"
        answer = call("/api/chat", {"model": settings()["model"], "stream": False, "format": "json",
                                    "messages": [{"role": "system", "content": JUDGE}, {"role": "user", "content": asked}],
                                    "options": {"temperature": 0, "num_predict": 20}})
        picked = json.loads(answer.get("message", {}).get("content", "{}")).get("choice")
        picked = int(picked) - 1 if str(picked).isdigit() and 0 < int(picked) <= len(ways) else None
        remember(key, picked)
        return picked
    except Exception:
        return None


def only_known_words(reading, line):
    """A reading may use brick's own words and the person's words (or near slips of them), nothing else:
    a model can copy words from its examples ('I live in a red house'), and that must never get through."""
    import universe
    from actions import STARTERS
    theirs = set(re.findall(r"[a-z0-9']+", line.lower()))
    brick = set(universe.universe().words) | set(STARTERS) | set(re.findall(r"[a-z]+", GUIDE.lower()) if False else ())
    brick |= {"write", "the", "a", "in", "at", "on", "to", "of", "row", "column", "colour", "background", "set",
              "wait", "seconds", "second", "times", "after", "then", "put", "window", "side", "screen", "clear",
              "make", "bold", "capitals", "top", "bottom", "left", "right", "middle", "it", "say", "beep", "stop",
              "bigger", "smaller", "full", "title", "disappear", "ask", "as", "add", "repeat", "if", "is", "for", "each"}
    for word in re.findall(r"[a-z0-9']+", reading.lower()):
        if word in theirs or word in brick or word.isdigit():
            continue
        if any(universe.apart(word, w) <= 2 for w in theirs if abs(len(w) - len(word)) <= 2):
            continue                              # the spelling fixed: 'riht' -> right
        return False
    return True


# ---------------- brick neural ... ----------------

def command(args):
    if args[:1] == ["off"] or args[:1] == ["on"]:
        save_settings(on=args[0] == "on")
        print(f"The neural reader is {'on' if args[0] == 'on' else 'off'}.")
        return
    if args[:1] == ["model"] and len(args) == 2:
        save_settings(model=args[1])
        print(f"The neural reader will use {args[1]}. Run brick neural setup to download it if it's new.")
        return
    if not shutil.which("ollama"):
        print("The neural reader needs Ollama, which isn't installed. Install it once with:\n"
              "    sudo pacman -S ollama-cuda\n"
              "then run: brick neural setup   (brick starts and stops Ollama by itself; no service needed)")
        return
    if not start():
        print("Ollama is installed, but wouldn't start. Try running 'ollama serve' to see why.")
        return
    model = settings()["model"]
    if args[:1] == ["setup"] and not have_model():
        print(f"Downloading {model} (once; a few GB)...", flush=True)
        request = urllib.request.Request(SERVER + "/api/pull", json.dumps({"model": model}).encode(),
                                         {"Content-Type": "application/json"})
        shown = ""
        with urllib.request.urlopen(request, timeout=3600) as response:
            for raw in response:
                step = json.loads(raw or b"{}")
                note = step.get("status", "")
                if step.get("total"):
                    note += f" {100 * step.get('completed', 0) // step['total']}%"
                if note != shown:
                    print("  " + note, flush=True)
                    shown = note
    if not have_model():
        print(f"Ollama is ready, but the model {model} isn't downloaded yet: brick neural setup")
        return
    started = time.time()
    tried = ask("write hello in blue at the x 20 and y 20", "", "check")
    print(f"The neural reader is {'on' if settings()['on'] else 'off'}, using {model} on this computer.")
    print(f"Asked it about 'write hello in blue at the x 20 and y 20' ({time.time() - started:.1f}s): {tried}")
