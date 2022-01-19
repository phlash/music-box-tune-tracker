#!/usr/bin/env python3

import sys
import os
import argparse
import time
import threading, queue

import mido
from mido import MidiFile
import curses
import curses.textpad
from curses.textpad import rectangle

import const
from record import Record
from input import Input


def export_to_mid(record, program):
    ticks = 480
    mid = mido.MidiFile(type=0, ticks_per_beat=ticks)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    track.append(mido.Message("program_change", program=program, time=0))

    for beat_index in range(record.beats_count):
        for track_index in range(record.tracks_count):
            if record.has_note(beat_index, track_index):
                track.append(
                    mido.Message("note_on", note=record.NOTES[track_index], time=0)
                )
        track.append(mido.Message("note_off", time=ticks))

    mid.save(record.title + ".mid")


def import_from_mid(record, filename):
    record.filename = os.path.splitext(filename)[0] + ".fpr"
    record.title = os.path.basename(filename)
    record.comment = "Imported from " + os.path.basename(filename)

    beat_index = 0
    track_index = 0

    for msg in MidiFile(filename):
        if not msg.is_meta:
            if msg.type == "note_on":
                track_index = record.NOTES.index(msg.note)
                record.set_note(beat_index, track_index, True)
            if msg.time > 0:
                beat_index += 1
        if beat_index >= const.BEAT_COUNT:
            break


def draw_after_scroll(input):
    input.draw_partition()
    input.draw_player_start_at()
    input.draw_beat_index()

def main(stdscr, port, input, program):
    cursor_y = input.start_y + input.offset_y
    cursor_x = input.start_x + input.offset_x

    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(const.PAIR_NOTE, curses.COLOR_RED, curses.COLOR_YELLOW)
    curses.init_pair(const.PAIR_INPUT_A, -1, curses.COLOR_CYAN)
    curses.init_pair(const.PAIR_INPUT_B, -1, curses.COLOR_BLACK)
    curses.init_pair(const.PAIR_HIGHLIGHT, curses.COLOR_RED, -1)

    record = input.record
    input.window = stdscr
    input.draw(cursor_x, cursor_y)

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
                input.draw_player_start_at(play_beat)
                stdscr.refresh()  # force fast refresh before sleeping..
            time.sleep(0.01)

        elif ch == curses.KEY_UP:
            next_y = cursor_y - 1
            if input.can_move(next_y, cursor_x):
                cursor_y = next_y
                input.draw_tones(cursor_y)
        elif ch == curses.KEY_DOWN:
            next_y = cursor_y + 1
            if input.can_move(next_y, cursor_x):
                cursor_y = next_y
                input.draw_tones(cursor_y)
        elif ch == curses.KEY_LEFT:
            next_x = cursor_x - 1
            if input.can_move(cursor_y, next_x):
                cursor_x = next_x
            elif input.display_from > 0:
                input.display_from -= 1
                draw_after_scroll(input)
        elif ch == curses.KEY_RIGHT:
            next_x = cursor_x + 1
            if input.can_move(cursor_y, next_x):
                cursor_x = next_x
            elif input.display_from + cursor_x < record.beats_count:
                input.display_from += 1
                draw_after_scroll(input)
        elif ch == curses.KEY_SLEFT or ch == curses.KEY_PPAGE:
            input.display_from -= input.beats_count
            if input.display_from < 0:
                input.display_from = 0
            draw_after_scroll(input)
        elif ch == curses.KEY_SRIGHT or ch == curses.KEY_NPAGE:
            input.display_from += input.beats_count
            if input.display_from > record.beats_count - input.beats_count:
                input.display_from = record.beats_count - input.beats_count
            draw_after_scroll(input)
        elif ch == curses.KEY_HOME:
            input.display_from = 0
            cursor_x = input.start_x + input.offset_x
            draw_after_scroll(input)
        elif ch == curses.KEY_END:
            input.display_from = record.beats_count - input.beats_count
            cursor_x = input.start_x + input.offset_x + input.beats_count - 1
            draw_after_scroll(input)
        elif ch == ord("x"):
            export_to_mid(record, program)
        elif ch == ord("o"):
            input.player_start_at_value(input.display_from + cursor_x - 1)
            input.draw_player_start_at()
        elif ch == ord("u"):
            input.player_start_at_dec()
            input.draw_player_start_at()
        elif ch == ord("i"):
            input.player_start_at_inc()
            input.draw_player_start_at()
        elif ch == ord("+"):
            record.right_shift(cursor_x - 1)
            input.draw_partition()
        elif ch == ord("-"):
            record.left_shift(cursor_x - 1)
            input.draw_partition()
        elif ch == ord("e"):
            box.edit()
            title = box.gather()
            input.record.title = title
            input.draw(cursor_x, cursor_y)
        elif ch == ord(" "):
            x = input.display_from + cursor_x - 1
            y = cursor_y - 1
            if input.tone_descending:
                y = input.tracks_count - 1 - y
            record.reverse_note(x, y)
            input.draw_partition()
        elif ch == ord("t"):
            track_index = cursor_y - (input.start_y + input.offset_y)
            if input.tone_descending:
                track_index = input.tracks_count - 1 - track_index
            port.send(mido.Message("note_on", note=record.NOTES[track_index]))
        elif ch == ord("r"):
            beats = record.get_beats(cursor_x - 1)
            for track_index in range(len(beats)):
                if beats[track_index]:
                    port.send(mido.Message("note_on", note=record.NOTES[track_index]))
        elif ch == ord("p"):
            if thread_player is not None and thread_player.is_alive():
                thread_player.do_run = False
                thread_player.join()
            else:
                thread_player = threading.Thread(
                    target=play, args=(play_q, port, record, input)
                )
                thread_player.start()
        elif ch == ord("s"):
            record.save()
        elif ch == ord("l"):
            record.load()
            input.draw(cursor_x, cursor_y)
        elif ch == ord("q"):
            break

    if thread_player is not None and thread_player.is_alive():
        thread_player.do_run = False
        thread_player.join()

    port.close()


def play(play_q, port, record, input):
    t = threading.currentThread()
    FPR_SEC_BETWEEN_BEATS = (25.0 / record.beats_count) if input.wholedisc else 0.5

    for beat_index in range(input.player_start_at, record.beats_count):
        if getattr(t, "do_run", True) == False:
            break
        for track_index in range(input.tracks_count):
            if record.has_note(beat_index, track_index):
                port.send(mido.Message("note_on", note=record.NOTES[track_index]))
        time.sleep(FPR_SEC_BETWEEN_BEATS)
        for track_index in range(input.tracks_count):
            if record.has_note(beat_index, track_index):
                port.send(mido.Message("note_off", note=record.NOTES[track_index]))
        # update progress indicator
        play_q.put(beat_index)
    play_q.put(-1)


if __name__ == "__main__":
    portname = None
    program = 10
    record = Record(0, const.TRACK_COUNT)

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="name of the midi port to use")
    parser.add_argument("--fpr", help=".fpr file to open")
    parser.add_argument(
        "--mid", help="import from .mid file created with music box tune tracker"
    )
    parser.add_argument("--program", help="midi instrument code")
    parser.add_argument("--title", help="set the title of a new tune")
    parser.add_argument(
        "--low", help="display low pitch notes first", action="store_true"
    )
    parser.add_argument(
        "--wholedisc", help="assume FPR occupies the whole disc", action="store_true"
    )

    args = parser.parse_args()
    if args.port:
        portname = args.port
    if args.fpr:
        record.filename = args.fpr
    if args.title:
        record.title = args.title
    if args.program:
        program = int(args.program)

    # midi port
    port = None

    if record.filename:
        record.load()
    elif args.mid is not None:
        import_from_mid(record, args.mid)
    else:
        record.filename = record.title + ".fpr"

    if record.beats_count < const.BEAT_COUNT:
        record.resize_beats(const.BEAT_COUNT)

    try:
        port = mido.open_output(portname)
    except:
        port = mido.open_output()

    port.send(mido.Message("program_change", program=program))

    input = Input(record)
    if args.low:
        input.tone_descending = False
    if args.wholedisc:
        input.wholedisc = True

    try:
        curses.wrapper(main, port, input, program)
    except curses.error:
        sys.exit("Error when drawing to terminal (is the terminal too small ? )")
