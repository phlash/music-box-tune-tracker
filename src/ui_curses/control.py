#!/usr/bin/env python3

import sys
import threading, queue, time

import curses

try:
    import mido
    import rtmidi
    from midi import Midi
except ImportError:
    pass

from sound import play_note, play
import ui_curses.const
from record import Record

def draw_after_scroll(display, cursor_x):
    display.draw_partition()
    display.draw_player_start_at()
    display.draw_beat_index(cursor_x)

def run_curses(stdscr, display, midi, audio):
    cursor_y = display.start_y + display.offset_y
    cursor_x = display.start_x + display.offset_x

    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(ui_curses.const.PAIR_NOTE, curses.COLOR_RED, curses.COLOR_YELLOW)
    curses.init_pair(ui_curses.const.PAIR_INPUT_A, -1, curses.COLOR_CYAN)
    curses.init_pair(ui_curses.const.PAIR_INPUT_B, -1, curses.COLOR_BLACK)
    curses.init_pair(ui_curses.const.PAIR_HIGHLIGHT, curses.COLOR_RED, -1)

    record = display.record
    display.window = stdscr
    display.set_size()
    display.draw(cursor_x, cursor_y)

    # edit box
    editwin = curses.newwin(1, 79, 20, 1)
    editwin.addstr(0, 0, record.title)
    box = curses.textpad.Textbox(editwin, insert_mode=True)

    thread_player = None  # thread to play music in background
    stdscr.nodelay(True)  # poll for keys, so we can process player thread updates
    play_q = queue.Queue() # update messages (position) from player

    while True:
        ch = stdscr.getch(cursor_y, cursor_x)

        if ch == curses.ERR:
            # no keys pressed, process player thread updates then sleep for a few msec
            while not play_q.empty():
                play_beat = play_q.get()
                display.draw_player_start_at(play_beat)
                stdscr.refresh()  # force fast refresh before sleeping..
            time.sleep(0.01) 
        elif ch == curses.KEY_UP:
            next_y = cursor_y - 1
            if display.can_move(next_y, cursor_x):
                cursor_y = next_y
                display.draw_tones(cursor_y)
        elif ch == curses.KEY_DOWN:
            next_y = cursor_y + 1
            if display.can_move(next_y, cursor_x):
                cursor_y = next_y
                display.draw_tones(cursor_y)
        elif ch == curses.KEY_LEFT:
            next_x = cursor_x - 1
            if display.can_move(cursor_y, next_x):
                cursor_x = next_x
                display.draw_beat_index(cursor_x)
            elif display.display_from > 0:
                display.display_from -= 1
                draw_after_scroll(display, cursor_x)
        elif ch == curses.KEY_RIGHT:
            next_x = cursor_x + 1
            if display.can_move(cursor_y, next_x):
                cursor_x = next_x
                display.draw_beat_index(cursor_x)
            elif display.display_from + cursor_x < record.beats_count:
                display.display_from += 1
                draw_after_scroll(display, cursor_x)
        elif ch == curses.KEY_SLEFT or ch == curses.KEY_PPAGE:
            display.display_from -= display.beats_count
            if display.display_from < 0:
                display.display_from = 0
            draw_after_scroll(display, cursor_x)
        elif ch == curses.KEY_SRIGHT or ch == curses.KEY_NPAGE:
            display.display_from += display.beats_count
            if display.display_from > record.beats_count - display.beats_count:
                display.display_from = record.beats_count - display.beats_count
            draw_after_scroll(display, cursor_x)
        elif ch == curses.KEY_HOME:
            display.display_from = 0
            cursor_x = display.start_x + display.offset_x
            draw_after_scroll(display, cursor_x)
        elif ch == curses.KEY_END:
            display.display_from = record.beats_count - display.beats_count
            cursor_x = display.start_x + display.offset_x + display.beats_count - 1
            draw_after_scroll(display, cursor_x)
        elif ch == ord("x"):
            if "mido" in sys.modules:
                midi.export_to_mid(record)
        elif ch == ord("o"):
            display.player_start_at_value(display.display_from + cursor_x - 1)
            display.draw_player_start_at()
        elif ch == ord("u"):
            display.player_start_at_dec()
            display.draw_player_start_at()
        elif ch == ord("i"):
            display.player_start_at_inc()
            display.draw_player_start_at()
        elif ch == ord("+"):
            record.right_shift(cursor_x - 1)
            display.draw_partition()
        elif ch == ord("-"):
            record.left_shift(cursor_x - 1)
            display.draw_partition()
        elif ch == ord("e"):
            box.edit()
            title = box.gather()
            display.record.title = title
            display.draw(cursor_x, cursor_y)
        elif ch == ord(" "):
            x = display.display_from + cursor_x - 1
            y = cursor_y - 1

            if x >= record.beats_count:
                record.resize_beats(x + 1)

            if display.tone_descending:
                y = Record.TONES_COUNT - 1 - y
            record.reverse_note(x, y)
            display.draw_partition()
        elif ch == ord("t"):
            tone_index = cursor_y - (display.start_y + display.offset_y)
            if display.tone_descending:
                tone_index = Record.TONES_COUNT - 1 - tone_index
            play_note(record.NOTES[tone_index], audio, midi)
        elif ch == ord("r"):
            beats = record.get_beats(cursor_x - 1)
            for tone_index in range(len(beats)):
                if beats[tone_index]:
                    play_note(record.NOTES[tone_index], audio, midi)
        elif ch == ord("p"):
            if thread_player is not None and thread_player.is_alive():
                thread_player.do_run = False
                thread_player.join()
            else:
                thread_player = threading.Thread(
                    target=play,
                    args=(
                        audio,
                        midi,
                        record,
                        display.player_start_at,
                        play_q,
                    ),
                )
                thread_player.start()
        elif ch == ord("s"):
            record.save()
        elif ch == ord("l"):
            record.load()
            display.draw(cursor_x, cursor_y)
        elif ch == ord("q"):
            break
        elif ch == curses.KEY_RESIZE:
            display.set_size()
            stdscr.erase()
            display.draw(cursor_x, cursor_y)

    if thread_player is not None and thread_player.is_alive():
        thread_player.do_run = False
        thread_player.join()
