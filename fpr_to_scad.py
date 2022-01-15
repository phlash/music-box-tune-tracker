#!/usr/bin/env python3
import os
import sys
import argparse
import time, datetime
from pathlib import Path
import scad
import const

from record import Record

parser = argparse.ArgumentParser()
parser.add_argument("--fpr", help="name of fpr file", required=True)
parser.add_argument("--fprbis", help="name of fpr file for second side")
parser.add_argument("--scad", help="name of scad file to output")
parser.add_argument(
    "--thickness", help="thickness in mm. Defaults to 3 if one side or 5 if two sides"
)
parser.add_argument("--beats",help="number of beats to translate (default:86) 0 => all beats")
parser.add_argument("--beatsbis",help="number of beats to translate for second side (default:86) 0 => all beats")

args = parser.parse_args()

fpr_file = args.fpr
fpr_file_bis = args.fprbis
scad_file = args.scad or os.path.splitext(fpr_file)[0] + ".scad"
thickness = None
if args.thickness:
    thickness = float(args.thickness)
else:
    thickness = 5 if fpr_file_bis else 3
beat_cut = const.BEAT_COUNT
if args.beats:
    beat_cut = int(args.beats)
beat_cut_bis = const.BEAT_COUNT
if args.beatsbis:
    beat_cut_bis = int(args.beatsbis)

if not Path(fpr_file).is_file():
    print("Cannot find " + fpr_file)
    sys.exit()

record = Record(0, const.TRACK_COUNT)
record.filename = fpr_file
record.load()
if beat_cut>0:
    record.resize_beats(beat_cut)

record_bis = None
if fpr_file_bis is not None:
    if not Path(fpr_file_bis).is_file():
        print("Cannot find " + fpr_file_bis)
        sys.exit()

    record_bis = Record(0, const.TRACK_COUNT)
    record_bis.filename = fpr_file_bis
    record_bis.load()
    if beat_cut_bis>0:
        record_bis.resize_beats(beat_cut_bis)


VERSION = "1.0"
date_time = datetime.datetime.now().strftime("%d %b %Y %H:%M")
has_second_side = fpr_file_bis is None

scad_output = scad.to_scad(VERSION, date_time, thickness, record, record_bis)
myfile = open(scad_file, "w")
myfile.write(scad_output)
myfile.close()
