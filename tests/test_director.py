"""Tests for English found by the English Director: each builds and runs a real program.

Usage: python3 tests/test_director.py
"""
import os
import subprocess
import sys

from terminal import build, folder, run

RESET = "\x1b[0m"


def output(text, typing=()):
    screen, code, _ = run(build(text, folder()), typing)
    assert code == 0, (code, screen)
    return screen


def refusal(text):
    from expressions import Problem
    try:
        build(text, folder())
    except Problem as problem:
        return str(problem)
    raise AssertionError(f"{text!r} should have been refused")


def test_lists_made_with_their_items():
    assert output("make a list called colours with red, green and blue\n"
                  "for each colour in colours write colour") == "red\ngreen\nblue\n"
    assert output("make a list of fruits: apple, banana, cherry\nwrite fruits") == "apple, banana, cherry\n"
    assert output("make a list called nums with 1, 2 and 3\nwrite item 2 of nums plus 10") == "12\n"
    assert output('make a list of names: "Ann Lee", Bob\nfor each name in names write hi name') == \
        "hi Ann Lee\nhi Bob\n"


def test_making_a_variable():
    assert output("make a variable called score and set it to 5\nadd 1 to score\nwrite score") == "6\n"
    assert output("make a variable called score\nwrite score") == "0\n"
    assert output("create a number named lives set to 3\nwrite lives") == "3\n"


def test_times_before_a_colour():
    red = f"\x1b[38;2;255;0;0mhello{RESET}\n"
    assert output("write hello 3 times in red") == red * 3
    green = f"\x1b[38;2;0;192;0mI like apples and pears{RESET}\n"
    assert output("write I like apples and pears 2 times in green") == green * 2


def test_light_and_dark_colours():
    assert output("write hi in light blue") == f"\x1b[38;2;102;102;255mhi{RESET}\n"
    assert output("write hi in dark green") == f"\x1b[38;2;0;115;0mhi{RESET}\n"
    assert output("write hi on a light blue background") == f"\x1b[48;2;102;102;255mhi{RESET}\n"
    assert output("set the text colour to light blue\nwrite hi") == f"\x1b[38;2;102;102;255mhi\n{RESET}"
    assert output("write the light is on in red") == f"\x1b[38;2;255;0;0mthe light is on{RESET}\n"


def test_plus_joins_words():
    assert output('set score to 4\nwrite "Score: " + score') == "Score: 4\n"
    assert output('set name to "Ann"\nwrite "Hello, " + name + "!"') == "Hello, Ann!\n"
    assert output('write "5" + 3') == "8\n"
    assert output("set a to 2\nset b to 3\nwrite a + b") == "5\n"


def test_adding_and_taking_away():
    assert output("set lives to 3. take away 1 from lives. write lives") == "2\n"
    assert output("set score to 2\nadd 5 points to score\nwrite score") == "7\n"
    assert output("set score to 2\nincrease score by 10 points\nwrite score") == "12\n"


def test_naming_the_answer():
    assert output("ask for a number and call it guess\nwrite guess plus 1", [("Number? ", "4\n")]).endswith("5\n")
    assert output("ask your name and call it n\nwrite hi n", [("Name? ", "Al\n")]).endswith("hi Al\n")
    assert output("ask a number and save it as guess\nwrite guess plus 1", [("Number? ", "4\n")]).endswith("5\n")
    assert output("ask the player's name\nwrite hi name", [("Name? ", "Bo\n")]).endswith("hi Bo\n")
    assert output("write hi, call it greet\ngreet") == "hi\n"           # still teaches a word


def test_asking_until():
    screen = output("ask a number as guess until guess is 7\nwrite yes", [("Number? ", "3\n"), ("Number? ", "7\n")])
    assert screen.endswith("Number? 7\nyes\n"), repr(screen)
    screen = output('ask "Guess:" as guess until guess is 3\nwrite well done!',
                    [("Guess: ", "1\n"), ("Guess: ", "3\n")])
    assert screen.endswith("well done!\n"), repr(screen)
    screen = output("keep asking for a number until it is 5\nwrite done", [("Number? ", "3\n"), ("Number? ", "5\n")])
    assert screen.endswith("Number? 5\ndone\n"), repr(screen)
    assert output("keep writing hi 2 times") == "hi\nhi\n"


def test_checks_that_share_their_subject():
    assert output("set guess to 8\nif guess is 7 or 8 write close") == "close\n"
    assert output("set x to 5\nif x is 1 or 2 or 5 write found") == "found\n"
    assert output("set age to 15\nif age is more than 12 and less than 20 write teen") == "teen\n"
    assert output("set x to 5\nif x is not 1 and not 2 write fine") == "fine\n"
    assert output("set x to 3\nset y to 5\nif x is 3 and not y is 4 write both") == "both\n"
    screen = output('ask "Answer?" as a, if a is yes or y write ok, otherwise write no', [("? ", "y\n")])
    assert screen.endswith("ok\n"), repr(screen)


def test_plural_checks():
    assert output("set score to 20\nset lives to 2\n"
                  "if score is bigger than 10 and lives are more than 0 write yes") == "yes\n"
    assert output("make a list called pets\nadd cat to pets\nif pets contain cat write yes") == "yes\n"


def test_counting_a_list():
    pets = "make a list called pets\nadd cat to pets\nadd dog to pets\n"
    assert output(pets + "write how many pets there are") == "2\n"
    assert output(pets + "write the number of pets") == "2\n"
    assert output(pets + "show all the pets") == "cat, dog\n"
    assert output("write all done") == "all done\n"


def test_helpful_messages():
    assert "Put it on the same line, after the colon" in refusal("repeat 2 times:\nwrite a")


# ---- batch 2: files, words, your own words, typos and messages ----

def with_files(files, text, typing=()):
    """Run text in a folder that already has these files -> (screen, what's in each file afterwards)."""
    here = folder()
    for name, content in files.items():
        with open(os.path.join(here, name), "w") as f:
            f.write(content)
    screen, code, _ = run(build(text, here), typing)
    assert code == 0, (code, screen)
    after = {name: open(os.path.join(here, name)).read() for name in os.listdir(here) if name.endswith(".txt")
             and name != "mywords.txt"}
    return screen, after


SHOPPING = {"shopping.txt": "apple\npear\n"}


def test_saving_words_in_a_file():
    assert output("save hello world to notes.txt\nload notes.txt as notes\nwrite notes") == "hello world\n"
    assert output("write hello to greeting.txt\nread greeting.txt and write it") == "hello\n"
    assert output("set score to 5\nsave the score in a file called best.txt\nload best.txt as best\n"
                  "write best") == "5\n"
    assert output("save hi to the file called notes.txt\nwrite what's in notes.txt") == "hi\n"
    assert output("set name to Al\nwrite hello name to notes.txt\nwrite the contents of notes.txt") == "hello Al\n"
    assert output("write the time in log.txt\nwrite how many lines are in log.txt") == "1\n"


def test_reading_a_file():
    for line in ("show the file shopping.txt", "write what's in shopping.txt", "write the contents of shopping.txt",
                 "for each line in shopping.txt write line", "show everything in shopping.txt"):
        assert with_files(SHOPPING, line) == ("apple\npear\n", SHOPPING), line
    assert with_files(SHOPPING, "write how many lines are in shopping.txt")[0] == "2\n"
    assert with_files(SHOPPING, "for each line in the file shopping.txt write I need line")[0] == \
        "I need apple\nI need pear\n"


def test_loading_a_file_into_a_list():
    assert with_files(SHOPPING, "load shopping.txt into a list called items\nwrite how many items")[0] == "2\n"
    assert with_files(SHOPPING, "load shopping.txt as a list called food\nwrite food")[0] == "apple, pear\n"
    assert with_files(SHOPPING, "load the list food from shopping.txt\nwrite the last in food")[0] == "pear\n"


def test_appending():
    assert output("append pear to fruits.txt\nappend fig to fruits.txt\nfor each line in fruits.txt write line") == \
        "pear\nfig\n"
    assert output("add apple to shopping.txt\nadd pear to shopping.txt\nwrite the file shopping.txt") == "apple\npear\n"
    assert output("make a list called fruits\nappend pear to fruits\nwrite fruits") == "pear\n"


def test_adding_to_a_number_from_a_file():
    screen, files = with_files({"best.txt": "5\n"}, "load best.txt as best\nadd 1 to best\nsave best to best.txt\n"
                                                    "write best")
    assert (screen, files) == ("6\n", {"best.txt": "6\n"})
    assert output("set word to hi\nadd 1 to word\nwrite word") == "hi1\n"


def test_words_in_a_text():
    sentence = 'set sentence to "the cat sat on the mat"\n'
    assert output(sentence + "write how many words are in sentence") == "6\n"
    assert output(sentence + "write the number of words in sentence") == "6\n"
    assert output(sentence + "write the first word of sentence") == "the\n"
    assert output(sentence + "write the last word in sentence") == "mat\n"
    assert output(sentence + "write word 2 of sentence") == "cat\n"
    assert output(sentence + "write the third word of sentence") == "sat\n"
    assert output("set word to hello\nwrite the second letter of word, the 5th letter of word") == "e, o\n"


def test_items_by_their_place():
    scores = "make a list called scores with 5, 7 and 9\n"
    assert output(scores + "write the second item in scores") == "7\n"
    assert output(scores + "write the 3rd in scores") == "9\n"
    names = "make a list called names with Ann, Bob\n"
    assert output(names + "write how many names there are") == "2\n"
    assert output(names + "write how many names are in names") == "2\n"


def test_looking_for_a_letter():
    assert output("set word to banana\nif word contains the letter n write yes") == "yes\n"
    assert output("set word to banana\nif word has an a in it write yes") == "yes\n"
    assert output("set word to banana\nif word starts with the letter b write yes") == "yes\n"


def test_your_own_words():
    assert output("to double a number means write the number times 2\ndouble 4") == "8\n"
    assert output("to greet somebody means write hi somebody\ngreet Ann") == "hi Ann\n"
    assert output("to introduce someone to somebody means write someone meet somebody\nintroduce Ann to Bob") == \
        "Ann meet Bob\n"
    assert output("when I say hi, write hello\nhi") == "hello\n"
    assert output('when I say "bye", write see you\nbye') == "see you\n"
    assert output("teach me to dance: move left then move right\ndance") == "\x1b[1D\x1b[1C"
    assert output("teach the computer to greet someone: write hi someone\ngreet Al") == "hi Al\n"


def test_other_small_things():
    assert output("set score to 10\nremove 3 from score\nwrite score") == "7\n"
    assert output("set name to Al\nwrite hello, name") == "hello, Al\n"
    assert output("ask you're name\nwrite hi name", [("Name? ", "Al\n")]).endswith("hi Al\n")
    assert output("write the word means") == "the word means\n"
    assert output("set answer to better\nif answer is better than ever write odd") == ""


def test_messages_for_mistakes():
    greet = "to greet someone means write hello someone\n"
    assert "Did you mean 'greet'?" in refusal(greet + "greeet Bob")
    assert "Your word 'greet' needs more after it: greet someone. For example: greet Sam" in refusal(greet + "greet")
    assert "What does 'greet someone' mean? Put the actions after 'means'" in refusal("to greet someone means")
    assert "Did you mean 'seconds'?" in refusal("wait 2 secnds")
    assert "Did you mean 'more than'?" in refusal("if 3 is mroe than 2 write yes")
    assert "Did you mean 'equal to'?" in refusal("set x to 3\nif x is equel to 3 write yes")
    assert "I don't know 'scor' yet. Did you mean 'score'?" in refusal("set score to 5\nadd 1 to scor")
    assert "yet. Did you mean 'score'?\n    You can say:" in refusal("set score to 1\nsave scroe to best.txt")
    assert "Save what? Try: save score to best.txt" in refusal("save to best.txt")
    assert "Save which thing?" in refusal("save everything in notes.txt")
    assert "Make the list first, like: make a list called names" in refusal("for each name in names write name")
    assert "If what? Put a check after 'if'" in refusal("if then write hi")
    assert "I can only remove the first or the last from a list" in \
        refusal("make a list called names\nremove Bob from names")


# ---- batch 3: the owner's decisions, then mixing them with everything else ----

BRICK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brick.py")


def notes(text):
    """The notes brick prints about likely typos, for a program that still builds."""
    from compiler import Compiler
    compiler = Compiler(os.path.join(folder(), "mywords.txt"), lambda question: "no")
    compiler.compile(text)
    return compiler.notes


def test_setting_the_colour():
    assert output("set the colour to red\nwrite hi") == f"\x1b[38;2;255;0;0mhi\n{RESET}"
    assert output("change the colour to light blue\nwrite hi") == f"\x1b[38;2;102;102;255mhi\n{RESET}"
    assert output("change the color to green\nwrite a\nset the colour to normal\nwrite b") == \
        f"\x1b[38;2;0;192;0ma\n{RESET}b\n{RESET}"
    assert output("set colour to red\nset the colour to blue\nwrite colour") == "blue\n"     # your own colour
    assert output("set the colour to banana\nwrite the colour") == "banana\n"


def test_indented_lines_belong_to_the_line_above():
    assert output("repeat 3 times:\n    write hi\nwrite done") == "hi\nhi\nhi\ndone\n"
    choice = "if score is more than 5:\n    write big\n    write very big\notherwise:\n    write small\nwrite end"
    assert output("set score to 7\n" + choice) == "big\nvery big\nend\n"
    assert output("set score to 3\n" + choice) == "small\nend\n"
    assert output("make a list called names with Ann and Bob\nfor each name in names:\n    write hello name") == \
        "hello Ann\nhello Bob\n"
    assert output("set x to 1\nwhile x is less than 4:\n    write x\n    add 1 to x") == "1\n2\n3\n"
    assert output("for each n from 1 to 2:\n\twrite n") == "1\n2\n"
    assert output("repeat 3 times\n    write hi") == "hi\nhi\nhi\n"            # the colon can be left off
    assert output("write the scores:\n    write 1\n    write 2") == "the scores:\n1\n2\n"    # not a loop


def test_blocks_inside_blocks():
    assert output("repeat 2 times:\n    write a\n    repeat 2 times:\n        write b\n    write c") == \
        "a\nb\nb\nc\n" * 2
    assert output("make a list called names with Ann and Bob\nfor each name in names:\n    if name is Bob:\n"
                  "        write hi Bob\n    otherwise:\n        write who is name") == "who is Ann\nhi Bob\n"
    chain = "if x is 1:\n    write one\notherwise if x is 2:\n    write two\notherwise:\n    write other"
    assert [output(f"set x to {x}\n" + chain) for x in (1, 2, 3)] == ["one\n", "two\n", "other\n"]
    assert output("set x to 9\nif x is 1:\n    write one\nelse:\n    write other") == "other\n"
    screen = output("repeat forever:\n    ask a number as n\n    if n is 0, leave the loop\n    write n times 2\n"
                    "write bye", [("Number? ", "3\n"), ("Number? ", "0\n")])
    assert screen == "Number? 3\n6\nNumber? 0\nbye\n", repr(screen)


def test_otherwise_on_the_next_line():
    assert output("set x to 4\nif x is 4, write four\notherwise write not four") == "four\n"
    assert output("set x to 5\nif x is 4, write four\notherwise write not four") == "not four\n"
    assert output("set x to 1\nif x is 1, write a, otherwise:\n    write b") == "a\n"


def test_messages_for_blocks():
    assert "Or put it on the lines below, each one indented" in refusal("repeat 2 times:\nwrite a")
    assert "Or put it on the lines below, each one indented" in refusal("if 1 is 1:\nwrite a")
    problem = refusal("set x to 1\nif x is 1:\n    write a\n    wirte b\nwrite c")
    assert problem.startswith("Line 4: wirte b\n") and "Did you mean 'write'?" in problem, problem
    assert refusal("write hi\notherwise write no").startswith("Line 2: otherwise write no\n    'otherwise' needs an 'if'")
    assert "Otherwise what?" in refusal("set x to 1\nif x is 1:\n    write a\notherwise:\notherwise:\n    write b")


def test_writing_the_numbers():
    assert output("write the numbers from 1 to 3") == "1\n2\n3\n"
    assert output("write all the numbers from 3 to 1 in green") == f"\x1b[38;2;0;192;0m3\n2\n1\n{RESET}"
    assert output("show the numbers 1 to 2") == "1\n2\n"


def test_big_letters():
    assert output("write hello in big red letters") == f"\x1b[1m\x1b[38;2;255;0;0mhello{RESET}\n"
    assert output("write hello in big letters") == f"\x1b[1mhello{RESET}\n"
    assert output("write in big red letters GAME OVER") == f"\x1b[1m\x1b[38;2;255;0;0mGAME OVER{RESET}\n"
    assert output("write we are in big trouble") == "we are in big trouble\n"


def test_a_name_after_the_stays_a_word():
    assert output("set total to 6\nwrite the total is total") == "the total is 6\n"
    assert output("set total to 6\nwrite the total is the total") == "the total is 6\n"
    assert output("set score to 6\nwrite the score: score") == "the score: 6\n"
    assert output("set high score to 9\nwrite the high score is high score") == "the high score is 9\n"
    assert output("ask your answer\nwrite the answer is answer", [("Answer? ", "yes\n")]).endswith(
        "the answer is yes\n")
    # unchanged: a name after 'the' still fills in when nothing says it's just words
    assert output("set score to 6\nwrite the score") == "6\n"
    assert output("set score to 6\nset lives to 3\nwrite the score and the lives") == "6 and 3\n"
    names = "make a list called names with Ann and Bob\n"
    assert output(names + "write the first in names\nwrite the winner is the first in names") == \
        "Ann\nthe winner is Ann\n"


def test_x_for_times():
    assert output("write 7 x 6") == "42\n"
    assert output("set price to 3\nwrite price X 4 plus 1") == "13\n"
    assert output("write 3 × 4") == "12\n"
    assert output("set x to 2\nwrite 7 x 6") == "7 2 6\n"          # your own x
    assert output("write x marks the spot") == "x marks the spot\n"


def test_backwards():
    assert output("set word to hello\nwrite word backwards\nwrite the backwards of word\n"
                  "write the reverse of word") == "olleh\n" * 3
    assert output('set word to "héllo wörld"\nwrite word backwards') == "dlröw olléh\n"
    assert output('write "abc" backwards') == "cba\n"
    assert output("set word to level\nif word backwards is word write same both ways") == "same both ways\n"
    names = "make a list called names with Ann, Bob and Cy\n"
    assert output(names + "write names backwards") == "Cy, Bob, Ann\n"
    assert output(names + "for each name in names reversed write name") == "Cy\nBob\nAnn\n"


def test_biggest_smallest_total_average():
    scores = "make a list called scores with 3, 9 and 5\n"
    assert output(scores + "write the biggest in scores, the largest in scores and the smallest in scores") == \
        "9, 9 and 3\n"
    assert output(scores + "write the total of scores, the sum of scores and the average of scores") == \
        "17, 17 and 5.67\n"
    assert output(scores + "write the highest score in scores") == "9\n"
    assert output("make a list called nums with 2 and 4\nwrite the average of nums") == "3\n"
    prices = "make a list called prices with 2.5, 1.25 and 4\n"
    assert output(prices + "write the biggest in prices, the smallest in prices, the total of prices") == \
        "4.00, 1.25, 7.75\n"
    assert output("make a list called things\nwrite the biggest in things, the average of things") == "0, 0\n"
    assert output("make a list called scores with -3, -9 and -5\nwrite the biggest in scores") == "-3\n"
    assert with_files({"scores.txt": "4\n10\n7\n"}, "load scores.txt as a list called scores\n"
                      "write the biggest in scores and the total of scores")[0] == "10 and 21\n"
    assert output("set total to 5\nif total is 5 write five") == "five\n"      # your own total
    assert "That needs a list of numbers" in refusal("set word to hi\nwrite the biggest in word")


def test_showing_a_file_by_its_name():
    assert with_files(SHOPPING, "show shopping.txt") == ("apple\npear\n", SHOPPING)
    assert with_files(SHOPPING, "display shopping.txt in green")[0] == f"\x1b[38;2;0;192;0mapple\npear{RESET}\n"
    assert with_files({"my list.txt": "a\n"}, 'show "my list.txt"')[0] == "a\n"


def test_showing_a_file_that_isnt_there():
    assert output("show shopping.txt\nwrite done") == "(shopping.txt doesn't exist yet.)\ndone\n"
    assert output("write what's in notes.txt") == "(notes.txt doesn't exist yet.)\n"
    assert output("show the file called notes.txt") == "(notes.txt doesn't exist yet.)\n"


def test_notes_about_likely_typos():
    assert notes("set score to 1\nwrite scroe") == ["Note: line 2: 'scroe' looks like 'score'."]
    assert notes("write hello in gren") == ["Note: line 1: 'gren' looks like 'green'."]
    assert notes("write hello on a bleu background") == ["Note: line 1: 'bleu' looks like 'blue'."]
    assert notes("set score to 5\nset scroe to 6") == ["Note: line 2: 'scroe' looks like 'score'."]
    assert notes("set total to 3\n\nwrite totl") == ["Note: line 3: 'totl' looks like 'total'."]
    # ordinary words close to a name are left alone
    assert notes("set lives to 3\nwrite I live here and he lies") == []
    assert notes("set score to 1\nwrite my store is sore") == []
    assert notes("set name to Al\nmake a list called names\nwrite one name") == []
    here = folder()
    with open(os.path.join(here, "typo.txt"), "w") as f:
        f.write("set score to 1\nwrite scroe\n")
    built = subprocess.run([sys.executable, BRICK, "build", "typo.txt"], capture_output=True, text=True, cwd=here)
    assert built.stdout.startswith("Note: line 2: 'scroe' looks like 'score'.\nBuilt typo"), built.stdout



def test_more_ways_to_open_a_block():
    assert output("set score to 7\nif score is more than 5 then:\n    write big") == "big\n"
    assert output("set score to 7\nif score is more than 5 :\n    write big") == "big\n"
    assert output("please repeat 2 times:\n    write hi") == "hi\nhi\n"
    problem = refusal("set x to 1\nif x is 1:\n    write one\n    otherwise:\n        write other")
    assert problem.startswith("Line 4: otherwise:\n") and "lined up with it" in problem, problem


def test_new_words_with_their_lines_below():
    assert output("to greet someone means:\n    write hi someone\n    write bye someone\ngreet Al") == "hi Al\nbye Al\n"
    assert output("teach me to dance:\n    write left\n    write right\ndance") == "left\nright\n"
    assert output("when I say hi:\n    write hello\n    write there\nhi") == "hello\nthere\n"
    assert "can't have their own indented lines yet" in \
        refusal("to check a number means:\n    if number is 1:\n        write one")


def test_the_writing_colour_stays():
    assert output("set the colour to red\nwrite a\nset the colour back to normal\nwrite b") == \
        f"\x1b[38;2;255;0;0ma\n{RESET}b\n{RESET}"
    assert output("set the colour to red\nwrite a in green\nwrite b") == \
        f"\x1b[38;2;255;0;0m\x1b[38;2;0;192;0ma{RESET}\x1b[38;2;255;0;0m\nb\n{RESET}"
    assert output("set the colour to red\nask your name in green\nwrite hi name", [("Name? ", "Al\n")]) == \
        f"\x1b[38;2;255;0;0m\x1b[38;2;0;192;0mName? {RESET}\x1b[38;2;255;0;0mAl\nhi Al\n{RESET}"
    assert output("write a in green\nwrite b") == f"\x1b[38;2;0;192;0ma{RESET}\nb\n"          # no writing colour: as before


def test_counting_backwards():
    assert output("write the numbers from 1 to 3 backwards") == "3\n2\n1\n"
    for line in ("count backwards from 3 to 1", "count down from 3", "count to 3 backwards", "count down from 3 to 1"):
        assert output(line) == "3\n2\n1\n", line
    assert output("count from 1 up to 3") == "1\n2\n3\n"
    assert output("set word to hello\nwrite the numbers from 1 to the length of word") == "1\n2\n3\n4\n5\n"


def test_x_inside_a_sentence_stays_as_typed():
    assert output("write what is 7 x 6?") == "what is 7 x 6?\n"
    assert output("ask a number as n\nfor each number from 1 to 2:\n    write number x n is number times n",
                  [("Number? ", "3\n")]).endswith("1 x 3 is 3\n2 x 3 is 6\n")
    assert output("make a list called scores with 3, 9 and 5\nwrite the biggest in scores x 2") == "18\n"


def test_lists_and_menus_as_typed():
    assert with_files({"shopping.txt": "milk\neggs\n"}, "load shopping.txt as a list called items\n"
                      "for each item in items:\n    write - item")[0] == "- milk\n- eggs\n"
    screen = output("write 1. Play\nwrite 2. Quit\nask a number as choice\nif choice is 1:\n    write let's play!\n"
                    "otherwise:\n    write bye", [("Number? ", "1\n")])
    assert screen == "1. Play\n2. Quit\nNumber? 1\nlet's play!\n", repr(screen)
    assert output("write -5\nwrite 3 - 1") == "-5\n2\n"
    assert output("set tries to 3\nwrite you got it in tries tries!") == "you got it in 3 tries!\n"
    assert output("set lives to 2\nwrite Lives lives left") == "2 lives left\n"


def test_until_a_name_the_loop_makes():
    game = ("set secret to 4\nset guesses to 0\nrepeat until guess is secret:\n    ask a number as guess\n"
            "    add 1 to guesses\n    if guess is more than secret:\n        write too high\n"
            "    otherwise if guess is less than secret:\n        write too low\nwrite you got it in guesses guesses!")
    screen = output(game, [("Number? ", "9\n"), ("Number? ", "1\n"), ("Number? ", "4\n")])
    assert screen.endswith("Number? 4\nyou got it in 3 guesses!\n"), repr(screen)
    assert output("repeat until n is 2, ask a number as n", [("Number? ", "2\n")]) == "Number? 2\n"
    assert "Did you mean 'guess'?" in refusal("repeat until gues is 3:\n    ask a number as guess")


def test_checking_a_file_is_there():
    assert with_files({"shopping.txt": "milk\n"}, "if shopping.txt exists, write yes\n"
                      "if the file notes.txt doesn't exist, write no notes")[0] == "yes\nno notes\n"
    screen = output("save hi to notes.txt\ndelete notes.txt\nshow notes.txt", [("(yes/no) ", "yes\n")])
    assert screen.endswith("Deleted.\n(notes.txt doesn't exist yet.)\n"), repr(screen)



def test_background_colour():
    assert output("set the background colour to blue\nwrite hi\nwrite ho in red") == \
        f"\x1b[48;2;0;0;255m\x1b[2J\x1b[Hhi\n\x1b[38;2;255;0;0mho{RESET}\x1b[48;2;0;0;255m\n{RESET}"
    assert output("set the colour to red\nset the background to blue\nwrite hi in green\n"
                  "set the background back to normal\nwrite ho") == \
        f"\x1b[38;2;255;0;0m\x1b[48;2;0;0;255m\x1b[2J\x1b[H\x1b[38;2;0;192;0mhi{RESET}\x1b[38;2;255;0;0m\x1b[48;2;0;0;255m\n{RESET}\x1b[38;2;255;0;0mho\n{RESET}"
    assert output("set background to blue\nwrite background") == "blue\n"
    assert notes("set the colour to gren") == ["Note: line 1: 'gren' looks like 'green'."]


def test_a_block_after_and():
    assert output("set x to 1 and repeat until x is 3:\n    write x\n    add 1 to x") == "1\n2\n"
    assert output("write ready, then repeat 2 times:\n    write go") == "ready\ngo\ngo\n"



def test_a_name_used_as_its_own_label():
    six = "set score to 6\n"
    assert output(six + "write the final score is score") == "the final score is 6\n"
    assert output(six + "write score is score") == "score is 6\n"
    assert output(six + "write your score is score") == "your score is 6\n"
    assert output(six + "write score: score") == "score: 6\n"
    assert output(six + "write score is more than 5") == "6 is more than 5\n"      # unchanged
    assert output(six + "set n to 3\nwrite score x n is score times n") == "6 x 3 is 18\n"


def test_and_inside_a_sentence():
    assert output("set total to 10\nwrite the total is total, and the average is total divided by 4") == \
        "the total is 10, and the average is 2.50\n"
    assert output("write hi, and bye") == "hi, and bye\n"
    assert output("write a, and write b") == "a\nb\n"



def test_placing_text_at_a_named_row():
    assert output("for each n from 1 to 2 write n at row n column 5") == "\x1b[1;5H1\n\x1b[2;5H2\n"
    assert output("set r to 2\nwrite hi at row r column 5") == "\x1b[2;5Hhi\n"
    assert output("for each n from 1 to 2:\n    write hi at row 2 column n") == "\x1b[2;1Hhi\n\x1b[2;2Hhi\n"


def test_a_loop_name_after_its_loop():
    problem = refusal("make a list called nums with 1 and 2\nfor each n in nums write n\nset x to n plus 1")
    assert "'n' only exists inside the loop" in problem and "Did you mean 'n'" not in problem, problem



# ---- batch 4: the owner's last four decisions ----

def test_lines_under_a_finished_if_belong_to_it():
    assert output("if 1 is more than 2, write a\n    write b\nwrite c") == "c\n"
    assert output("if 2 is more than 1, write a\n    write b\nwrite c") == "a\nb\nc\n"
    assert output("if 1 is more than 2, write a\n    write b\notherwise write c\nwrite d") == "c\nd\n"
    assert output("if 1 is more than 2 write a\n    write b\nwrite c") == "c\n"
    assert output("if 1 is more than 2, write a, otherwise write b\n    write c") == "b\nc\n"   # unchanged


def test_numbers_on_the_same_line():
    assert output("write the numbers from 1 to 3 on the same line\nwrite go") == "1 2 3\ngo\n"
    assert output("write the numbers from 3 to 1 on the same line") == "3 2 1\n"
    assert output("write the numbers from 1 to 3") == "1\n2\n3\n"                  # unchanged


def test_the_biggest_of_two_values():
    assert output("set a to 4\nset b to 9\nwrite the biggest of a and b\nwrite the smallest of a and b") == "9\n4\n"
    assert output("write the smallest of 3, 8 and 2") == "2\n"
    assert output("write the biggest of 2.5 and 2") == "2.50\n"
    assert output("write the total of 2 and 3\nwrite the average of 2 and 3") == "5\n2.50\n"
    assert output("make a list called scores with 3 and 9\nwrite the total of scores and the average of scores") \
        == "12 and 6\n"                                                             # lists unchanged


def test_times_stays_in_a_question():
    assert output("write what is 7 times 6?") == "what is 7 times 6?\n"
    assert output("write 7 times 6") == "42\n"                                       # unchanged


# ---- batch 4: the dictionary ----

def test_the_dictionary_reads_cleanly():
    import dictionary
    lines = [line for line in open(dictionary.PATH, encoding="utf-8") if "=" in line and not line.startswith("#")]
    entries = dictionary.entries()
    assert len(entries) == len(lines) and len(entries) > 600, (len(entries), len(lines))
    keys = [(e.key, e.kind) for e in entries]
    assert len(keys) == len(set(keys)), [k for k in keys if keys.count(k) > 1]
    kinds = {e.key: e.kind for e in entries}
    for word, kind in [("scribble", "action"), ("crimson", "colour"), ("exceeds", "check"), ("hours", "time"),
                       ("top-left", "place"), ("inventory", "list"), ("thrice", "loop"), ("greatest", "value"),
                       ("dead centre", "place"), ("each turn", "action")]:
        assert kinds[word] == kind, (word, kinds[word])
    assert {e.group for e in entries} >= {"Showing", "Asking", "Waiting", "Colours", "Loops", "Stopping"}


def test_dictionary_showing():
    assert output("scribble hello") == "hello\n"
    assert output("Please jot down hello there") == "hello there\n"
    assert output("print out hello") == "hello\n"
    assert output("announce the game has begun") == "the game has begun\n"
    assert output("shout hello there") == "HELLO THERE\n"
    assert output("set name to \"Bo\"\nyell hi name 2 times") == "HI BO\nHI BO\n"
    assert output("whisper Hello There") == "hello there\n"
    assert output("skip a line, write after") == "\nafter\n"
    assert output("ding") == "\a"
    assert output("wipe the screen") == "\x1b[2J\x1b[H"
    assert output("erase the screen") == "\x1b[2J\x1b[H"
    assert output("make a list called names with Al and Bo\nlist names") == "Al, Bo\n"
    assert output("save hi to notes.txt\nview notes.txt\nlook at notes.txt") == "hi\nhi\n"


def test_dictionary_asking():
    assert output("inquire your name\nwrite hi name", [("Name? ", "Bo\n")]) == "Name? Bo\nhi Bo\n"
    assert output("request a number as n\nwrite n plus 1", [("Number? ", "4\n")]) == "Number? 4\n5\n"
    assert output("find out their name", [("Name? ", "Cy\n")]) == "Name? Cy\n"
    assert output("get the user's name\nwrite hi name", [("Name? ", "Di\n")]) == "Name? Di\nhi Di\n"
    assert output("get a number from the user\nwrite it times 2", [("Number? ", "5\n")]) == "Number? 5\n10\n"
    assert output("query your age", [("Age? ", "7\n")]) == "Age? 7\n"


def test_dictionary_waiting():
    import time
    start = time.time()
    assert output("linger for a quarter of a second\nhold on a tenth of a second\nwrite done") == "done\n"
    assert time.time() - start >= 0.35
    assert output("hit enter\nwrite go", [("", "\n")]) == "\ngo\n"
    build("wait 2 hours\nwait an hour\nafter 2 hours write hi\nwait a while", folder())     # builds; not run


def test_dictionary_setting_and_adding():
    assert output("set score to 1\nupdate score to 5\nwrite score") == "5\n"
    assert output("set lives to 3\ndecrement lives\nwrite lives") == "2\n"
    assert output("set score to 3\nboost score by 4\nwrite score") == "7\n"
    assert output("set lives to 5\ndeduct 2 from lives\nwrite lives") == "3\n"
    assert output("set score to 1\naward 5 points to score\nwrite score") == "6\n"
    assert output("set score to 4\ndouble score\nwrite score") == "8\n"
    assert output("set x to 9\nmultiply x by 3\nwrite x\ndivide x by 9\nwrite x") == "27\n3\n"
    assert output("make a list called fruits\ninsert apple into fruits\nput pear in fruits\nwrite fruits") == \
        "apple, pear\n"


def test_dictionary_lists_and_files():
    assert output("make an inventory called items with sword and shield\nwrite items") == "sword, shield\n"
    assert output("make a deck called cards\nadd ace to cards\nwrite the amount of items in cards") == "1\n"
    assert output("make a list called names with a, b, c, d, e, f, g, h, i, j, k, l\n"
                  "write the eleventh item in names\nwrite the final item in names") == "k\nl\n"
    assert output("save 5 to best.txt\nfetch best.txt as best\nadd 1 to best\nwrite best") == "6\n"
    assert output("stash 3 in n.txt\nretrieve n.txt as n\nwrite n") == "3\n"


def test_dictionary_maths():
    assert output("write 10 take away 3\nwrite 7 times by 6") == "7\n42\n"
    assert output("set score to 5\nwrite score doubled\nwrite 9 halved") == "10\n4.50\n"
    assert output("set name to \"bob\"\nwrite name in caps\nwrite name back to front") == "BOB\nbob\n"
    assert output("set eggs to a dozen\nwrite eggs\nwrite hi a couple of times") == "12\nhi\nhi\n"
    assert output("set p to 2.6\nwrite p rounded off\nwrite pi times 2") == "3\n6.28\n"
    assert output("set r to a dice roll\nif r is at least 1 and r is at most 6, write ok") == "ok\n"


def test_dictionary_checks():
    assert output("set score to 11\nif score exceeds 10, write big, otherwise write small") == "big\n"
    assert output("set lives to 3\nif lives are fewer than 5, write few") == "few\n"
    assert output("set x to 5\nif x is no more than 5, write ok\nif x is different from 4, write diff") == \
        "ok\ndiff\n"
    assert output("set name to \"Bob\"\nif name matches \"Bob\", write same") == "same\n"
    assert output("make a list called names with Al and Bo\nif names holds \"Al\", write yes\n"
                  "if \"Cy\" is missing from names, write no Cy") == "yes\nno Cy\n"
    assert output("set word to \"cats\"\nif word ends in s, write plural") == "plural\n"
    assert output("set x to -3\nif x is negative, write neg") == "neg\n"
    assert output("set x to 7\nif x exceeds 5 and falls below 10, write middle") == "middle\n"
    assert output("set x to 6\nif x is 1 or is more than 5, write yes, otherwise write no") == "yes\n"
    assert output("set lives to 1\nif lives drop below 2, write low\nif lives go over 0, write some") == "low\nsome\n"


def test_dictionary_places_and_moving():
    assert output("write hi at the top-left") == "\x1b[1;1Hhi\n"
    assert output("write hi at the far right") == "\x1b[79Ghi\n"
    assert output("write GO in the dead centre of the screen") == "\x1b[12;40HGO\n"
    assert output("write hi at row 2 col 5") == "\x1b[2;5Hhi\n"
    assert output("move upwards 2\nstep left\nslide down") == "\x1b[2A\x1b[1D\x1b[1B"


def test_dictionary_window_words():
    env = dict(os.environ, BRICK_WINDOW="pid:1")      # names a process that has no window: nothing moves
    for line, screen in [("go full screen, write ok", "\x1b[9;1tok\n"),
                         ("fullscreen the window, write ok", "\x1b[9;1tok\n"),
                         ("title the window My Game", "\x1b]2;My Game\a"),
                         ("enlarge the window, write ok", "ok\n"),
                         ("snap the window to the left, write ok", "ok\n")]:
        shown, code, _ = run(build(line, folder()), env=env)
        assert (shown, code) == (screen, 0), (line, shown, code)


def test_dictionary_stopping():
    assert output("write a\nhalt\nwrite b") == f"a\n{RESET}"
    assert output("repeat 3 times:\n    write hi\n    get out of the loop\nwrite done") == "hi\ndone\n"
    assert output("set x to 0\nrepeat forever: add 1 to x and if x is 3, escape\nwrite x") == "3\n"


def test_dictionary_loops():
    assert output("beep thrice") == "\a\a\a"
    assert output("play 2 rounds: write go") == "go\ngo\n"
    assert output("repeat 2 rounds: write hi") == "hi\nhi\n"
    assert output("set z to 0, add 1 to z and if z is 5 leave the loop over and over, write z") == "5\n"
    assert output("set x to 0\nadd 1 to x till x is 3\nwrite x") == "3\n"
    assert output("set x to 0\nas long as x is less than 3, add 1 to x\nwrite x") == "3\n"
    assert output("set lives to 1\nunless lives is 0, write alive") == "alive\n"
    assert output("set score to 10\nwhen score is 10, write ten") == "ten\n"
    assert output("keep on asking for a number until it is 5", [("Number? ", "5\n")]) == "Number? 5\n"


def test_dictionary_colours():
    assert output("write hi in crimson") == f"\x1b[38;2;220;20;60mhi{RESET}\n"
    assert output("echo hi in teal") == f"\x1b[38;2;0;128;128mhi{RESET}\n"
    assert output("set the colour to navy\nwrite hi") == f"\x1b[38;2;0;0;128mhi\n{RESET}"
    assert output("write hi in light sea green") == f"\x1b[38;2;32;178;170mhi{RESET}\n"
    assert output("write hi in seagreen") == f"\x1b[38;2;46;139;87mhi{RESET}\n"
    assert output("write hi in bold crimson") == f"\x1b[1m\x1b[38;2;220;20;60mhi{RESET}\n"
    assert output("set the background colour to navy\nwrite hi") == f"\x1b[48;2;0;0;128m\x1b[2J\x1b[Hhi\n{RESET}"
    assert output("write hi in fuchsia") == f"\x1b[38;2;255;0;255mhi{RESET}\n"
    assert output("write hi in aqua") == f"\x1b[38;2;0;255;255mhi{RESET}\n"
    assert output("write hi in red") == f"\x1b[38;2;255;0;0mhi{RESET}\n"           # built in
    assert output("write hi in light blue") == f"\x1b[38;2;102;102;255mhi{RESET}\n"


def test_colours_are_exact():
    # exact shades, not the terminal's 16 theme colours: whatever the theme, green is green
    assert output("write hi in green") == f"\x1b[38;2;0;192;0mhi{RESET}\n"
    assert output("write hi in crimson") == f"\x1b[38;2;220;20;60mhi{RESET}\n"         # #dc143c
    assert output("write hi on a green background") == f"\x1b[48;2;0;192;0mhi{RESET}\n"
    assert output("write hi in light red") == f"\x1b[38;2;255;102;102mhi{RESET}\n"
    assert output("write hi in dark crimson") == f"\x1b[38;2;132;12;36mhi{RESET}\n"


def test_colours_that_are_also_things():
    assert output("write I live in peru") == "I live in peru\n"
    assert output("write I like soup in salmon") == "I like soup in salmon\n"
    assert output("write hi in peru colour") == f"\x1b[38;2;205;133;63mhi{RESET}\n"
    assert output("write hi in the colour salmon") == f"\x1b[38;2;250;128;114mhi{RESET}\n"
    assert output("write hi on a salmon background") == f"\x1b[48;2;250;128;114mhi{RESET}\n"
    assert output("turn salmon\nwrite hi") == f"\x1b[38;2;250;128;114mhi\n{RESET}"


def test_turn():
    assert output("turn green\nwrite hi") == f"\x1b[38;2;0;192;0mhi\n{RESET}"
    assert output("turn the text red\nwrite hi") == f"\x1b[38;2;255;0;0mhi\n{RESET}"
    assert output("turn the background blue\nwrite hi") == f"\x1b[48;2;0;0;255m\x1b[2J\x1b[Hhi\n{RESET}"
    assert output("turn crimson\nwrite hi") == f"\x1b[38;2;220;20;60mhi\n{RESET}"
    assert output("turn green\nturn off the colour\nwrite plain") == f"\x1b[38;2;0;192;0m{RESET}plain\n{RESET}"
    assert output("turn left") == "\x1b[1D"
    assert output("turn right 3") == "\x1b[3C"
    assert output('turn "42" into a number\nwrite it plus 1') == "43\n"
    assert output("set score to 7\nturn score into words\nwrite score\nwrite it") == "7\n7\n"
    assert output('set name to "ann"\nturn name into capitals\nwrite name') == "ANN\n"
    assert output('set word to "stressed"\nturn word backwards\nwrite word') == "desserts\n"
    assert output("each turn, ask a number as n and if n is 0, leave the loop\nwrite bye",
                  [("Number? ", "3\n"), ("Number? ", "0\n")]) == "Number? 3\nNumber? 0\nbye\n"
    assert output("each turn:\n    ask a number as n\n    if n is 0, leave the loop\nwrite bye",
                  [("Number? ", "0\n")]) == "Number? 0\nbye\n"
    assert output("take 2 turns:\n    write go") == "go\ngo\n"
    assert output("take 3 turns, beep") == "\a\a\a"
    assert output("change the text purple\nwrite hi") == f"\x1b[38;2;160;32;240mhi\n{RESET}"


def test_turn_stays_your_own_word():
    asked = []
    here = folder()
    path = build("to turn something means write something in red\nturn hi", here,
                 lambda question: asked.append(question) or "no")
    screen, _, _ = run(path, folder=here)
    assert screen == f"\x1b[38;2;255;0;0mhi{RESET}\n" and asked == [], (screen, asked)
    assert output("a turn means move left then beep\ndo a turn\nturn green\nwrite hi") == \
        f"\x1b[1D\a\x1b[38;2;0;192;0mhi\n{RESET}"
    assert output("to scribble something means write something backwards\nscribble hello") == "olleh\n"
    assert output("set turn to 3\nwrite turn") == "3\n"
    assert output("delay = 2\nstep is now 3\nwrite delay plus step") == "5\n"


def test_dictionary_words_stay_as_typed_in_sentences():
    assert output("write I scribbled a crimson note") == "I scribbled a crimson note\n"
    assert output("write it is your turn\nwrite turn left at the lights") == \
        "it is your turn\nturn left at the lights\n"
    assert output("write salt and pepper, list and view") == "salt and pepper, list and view\n"
    assert output("write stop, drop and roll") == "stop, drop and roll\n"
    assert output("write call me, when you can") == "call me, when you can\n"
    assert output("write the greatest show on earth") == "the greatest show on earth\n"
    assert output("write you have 3 turns\nwrite we play nonstop") == "you have 3 turns\nwe play nonstop\n"
    assert output("write it costs a dozen eggs\nwrite till we meet again") == \
        "it costs a dozen eggs\ntill we meet again\n"
    assert output("add a blank line to notes.txt\nshow notes.txt") == "a blank line\n"
    assert output("make a list called turns with a and b\neach turn in turns write turn") == "a\nb\n"


def test_dictionary_messages():
    problem = refusal("turn")
    assert "What should 'turn' do here? You can say: turn green  |  turn left" in problem, problem
    assert "Did you mean 'crimson'?" in refusal("turn the text crimsom")
    assert "Did you mean 'scribble'?" in refusal("scribbel hi")
    assert "I can change it into: a number, words, capitals" in refusal("set x to 3\nturn x into pancakes")
    problem = refusal("each turn hi")
    assert "To go through a list, say: for each name in names" in problem and "Did you mean 'each'" not in problem


def test_capitals_for_a_whole_sentence():
    assert output("write hello in capitals") == "HELLO\n"
    assert output("write in capitals hello there") == "HELLO THERE\n"
    assert output('set secret to "abc"\nwrite it starts with first letter of secret in capitals') == \
        "it starts with A\n"                                                       # unchanged: just the value
    assert output("tell the user that the game is over") == "the game is over\n"


def test_brick_help_dictionary():
    brick = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brick.py")
    shown = subprocess.run([sys.executable, brick, "help"], capture_output=True, text=True).stdout
    assert "The dictionary:" in shown and "brick help dictionary" in shown and "turn green" in shown
    listing = subprocess.run([sys.executable, brick, "help", "dictionary"], capture_output=True, text=True).stdout
    assert "Showing\n    write: scribble, scrawl, jot" in listing and "Colours\n" in listing, listing[:500]
    colours = subprocess.run([sys.executable, brick, "dictionary", "colours"], capture_output=True, text=True).stdout
    assert "crimson" in colours and "scribble" not in colours

if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"passed: {test.__name__}")
        except Exception as problem:
            failed += 1
            print(f"FAILED: {test.__name__}: {type(problem).__name__}: {problem}")
    print(f"{len(tests) - failed} of {len(tests)} tests passed.")
    sys.exit(1 if failed else 0)
