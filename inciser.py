
# Python script to use the xTool D1 Pro laser engraver for incising timber
# Idea is to drill small holes into the wood so it can be impregnated better.
#
# As xTool engravers lack the dwell command (G4), we need to run the
# engraver synchronously, meaning we time and wait for it to move and burn
# and only issue the next command once it has completed the previous.
#
# This script is quite hackish but does the job
#
# There are no command line arguments or interactivity, you need to build
# the program by hand instead
#
# On an xTool D1 Pro 20W I can burn about three 5-15mm holes per second
#
# If I did this project again I'd probably try to get a different engraver.
# xTool has their own proprietary firmware and only supports a subset of
# GRBL codes.

# Devices to try to connect to
DEVICES = ['/dev/cu.usbserial-14110', '/dev/ttyUSB0']
BAUDRATE = 230400
PARALLEL_COUNT = 20
VERBOSE = False

# XTool D1 Pro laser engraver init commands
INIT_SETTINGS=[
    # Init machine movement and get firmware info (won't move without this command)
    "$I",
    # startup sequence (from xTool, turns on laser fan? set power to 0?)
    "M106 S0",
    # we work in XY plane
    "G17",
    # reset radius compensation
    "G40",
    # use millimeters and set work offset
    "G21 G54",
    # use relative coordinates
    "G91",
    # use variable power
    "M4",
    # Query current position
    "?",
]

import serial
import sys
import sys
import subprocess
import os
import time
import math
import re

# Control software going into suspend while burning is not a good thing
# I wonder if Linux laptops have something similar?
if 'darwin' in sys.platform:
    print("Running 'caffeinate' on macOS/OSX to prevent the system from sleeping")
    subprocess.Popen('caffeinate -w %d' % (os.getpid(),), shell=True)

class Laser(object):
    def __init__(self, device, baudrate, parallel_count=20, verbose=False):
        self.soft_scale_x = 1.0
        self.soft_scale_y = 1.0
        self.x = 0.0
        self.y = 0.0
        self.parameters = {}
        self.ser = serial.Serial(device, BAUDRATE)
        self.active_count = 0
        self.max_active_count = parallel_count
        self.ser.write(b"\r\n\r\n");
        # wait for garbage if in the pipes
        time.sleep(1)
        # 400mm/s = 24000mm/min
        self.move_speed = 24000
        # empty the buffer so that ok count is correct
        while self.ser.in_waiting:
            print('LASER/STARTUP: %s' % (self.ser.readline().decode('ascii').strip(),))
            time.sleep(0.1)
        self.verbose = verbose
        self.active_power = 1
        self.last_power = None
        self.active_speed = 1000
        self.last_speed = None

        # Startup settings
        for cmd in INIT_SETTINGS:
            self.send_command(cmd)
            self.sync()

    def set_soft_origin(self):
        self.x = 0
        self.y = 0

    def set_scaling(self, x, y):
        # This does absolutely nothing on xTool D1 Pro
        print('WARNING: set_scaling does not work')
        self.send_command(f"$100={x*100.0}")
        self.send_command(f"$101={y*100.0}")

    def set_soft_scaling(self, x, y):
        self.soft_scale_x = x
        self.soft_scale_y = y

    def disable_hard_limits(self):
        print('WARNING: disabling physical limit switches for machine working area bounds')
        # This appears to work on xTool D1 Pro, even if the value is not reflect in response of '$$'
        self.send_command("$21=0")

    def set_move_speed(self, speed):
        self.move_speed = speed

    def send_command(self, cmd):
        self.read_responses()
        assert self.active_count < self.max_active_count
        self.active_count += 1
        if self.verbose:
            print('LASER/SEND: %s' % (cmd,))
        self.ser.write(bytes("%s\r\n" % (cmd,), 'ascii'))
        self.ser.flush()

    def read_responses(self, sync=False, block=False):
        while self.ser.in_waiting > 0 or self.active_count >= self.max_active_count or sync and self.active_count > 0 or block:
            block = False # only block on first read
            line = self.ser.readline().decode('ascii').strip()
            if self.verbose:
                print('LASER/READ: %s' % (line,))
            if line.startswith('<MPos'):
                self.last_mpos = line
                pattern = r"<MPos:(-?\d+\.\d+),(-?\d+\.\d+),(-?\d+\.\d+),(-?\d+\.\d+)>"
                # Use re.match to find the match
                match = re.match(pattern, line)
                assert match is not None
                self.mpos = [float(num) for num in match.groups()]
                #print(self.mpos)
                continue
            if line == 'ok':
                self.active_count -= 1
                if self.active_count < 0:
                    print(line)
            elif line.startswith('$'):
                pattern = r"\$([1-9][0-9]*)=(.*)"
                match = re.match(pattern, line)
                if match is not None:
                    self.parameters[match.group(1)] = match.group(2)
            else:
                print(line)
                assert not line.startswith('err')
                # sometimes I get "okok". what does this mean?!? newline goes missing/off by one bug? buffer overrun and missing data?
                # xTool software engineering is not that great I guess
                if line.count('ok')*2 == len(line):
                    self.active_count -= line.count('ok')

    def sync(self):
        self.read_responses(sync=True)

    def format_dxdy(self, dx = 0, dy = 0):
        dx = dx * self.soft_scale_x
        dy = dy * self.soft_scale_y
        if dx == 0 and dy == 0:
            return ""
        elif dy == 0:
            return "X%f" % (dx,)
        elif dx == 0:
            return "Y%f" % (dy,)
        else:
            return "X%fY%f" % (dx, dy)

    # This function assumes that laser is stationary
    # This function only finishes once laser is stationary
    def move_sync(self, dx=0, dy=0):
        if dx == 0 and dy == 0:
            return
        # get current pose
        self.last_mpos = None
        self.send_command('?')
        while self.last_mpos == None:
            time.sleep(0.01) # wait for response
            self.read_responses(block=True)
        self.sync()
        desired_x = self.mpos[0] + self.soft_scale_x * dx
        desired_y = self.mpos[1] + self.soft_scale_y * dy
        #print(f'Move to: {self.mpos[0]}, {self.mpos[1]} -> {desired_x}, {desired_y}')

        self.move(dx, dy)
        #self.send_command('G0')
        self.sync()
        time.sleep(0.1)

        while True:
            self.last_mpos = None
            self.send_command('?')
            self.sync()
            while self.last_mpos == None:
                time.sleep(0.01) # wait for response
                self.read_responses(block=True)
            if abs(desired_x - self.mpos[0]) < 0.01 and abs(desired_y - self.mpos[1]) < 0.01:
                break
            # Spamming anything too much seems to block D1 processing.
            time.sleep(0.05)

    def move(self, dx=0, dy=0):
        if True:
            old_speed = self.active_speed
            old_power = self.active_power
            self.burn(dx=dx, dy=dy, speed=self.move_speed, power=0) # 400mm/s = 24000mm/min
            self.active_speed = old_speed
            self.active_power = old_power
        else:
            self.x = self.x + dx
            self.y = self.y + dy
            self.send_command("G0%s" % (self.format_dxdy(dx, dy)))

    def move_abs(self, x, y):
        self.move(dx = x - self.x, dy = y - self.y)

    def move_abs_sync(self, x, y):
        self.move_sync(dx = x - self.x, dy = y - self.y)

    def set_constant_power(self):
        # I've noticed no difference between M3/M4 on D1 Pro
        self.send_command("M3")

    def set_variable_power(self):
        self.send_command("M4")

    def set_speed(self, speed):
        self.active_speed = speed

    def set_power(self, power):
        self.active_power = power

    def burn(self, dx=0, dy=0, speed=None, power=None):
        if power is not None:
            self.set_power(power)
        if speed is not None:
            self.set_speed(speed)
        power_set = ''
        if self.active_power != self.last_power:
            power_set = 'S%d' % (self.active_power,)
            self.last_power = self.active_power
        speed_set = ''
        if self.active_speed != self.last_speed:
            speed_set = 'F%d' % (self.active_speed,)
            self.last_speed = self.active_speed
        self.x = self.x + dx
        self.y = self.y + dy
        self.send_command("G1%s%s%s" % (self.format_dxdy(dx, dy), power_set, speed_set))

    def burn_stationary(self, duration, power=None):
        self.burn(power = power)
        self.sync()
        now = time.time()
        burn_until = now + duration
        while True:
            if now >= burn_until:
                break
            sleep_slice = min(0.25, burn_until - now)
            time.sleep(sleep_slice)
            # repeat the command as it times out (safety feature)
            self.burn(power=power)
            now = time.time()
        # end burn
        self.send_command("G0")
        self.sync()

    def burn_rectangle(self, dx, dy, power=None, speed=None):
        if power is not None:
            self.set_power(power)
        if speed is not None:
            self.set_speed(speed)
        self.burn(dy=dy)
        self.burn(dx=dx)
        self.burn(dy=-dy)
        self.burn(dx=-dx)
        self.burn(power=0)

    def burn_holes(self, holes, power, duration, first_row_only=False):
        # Turn the laser on
        self.send_command("M3")
        start_x, start_y = self.x, self.y
        d = {}
        for h in holes:
            d.setdefault(h[1], []).append(h[0])
        d = [(k, sorted(v)) for k, v in d.items()]
        d.sort(key=lambda x: x[0])
        d = [(k, list(reversed(v)) if index & 1 else v) for index, (k, v) in enumerate(d)]
        # can use this for framing, kind of
        if first_row_only:
            d = d[0:1]
        start_time = time.time()
        for index, (y, row) in enumerate(d):
            t = time.time()
            for x in row:
                self.move_abs_sync(x, y)
                #print(x, y)
                self.burn_stationary(duration, power = power)
            dt = time.time() - t
            elapsed_time = time.time() - start_time
            speed = elapsed_time / (index + 1)
            print(f'Burned row {index+1} / {len(d)}, elapsed {elapsed_time}s, dt={dt}, left ~{speed*(len(d) - index - 1)}s)')
        self.move_abs(start_x, start_y)
        # Turn the laser off
        self.send_command("M5")

    def get_parameters(self):
        self.parameters = {}
        laser.send_command('$$')
        laser.sync()
        return self.parameters

class PiecewiseBlock(object):
    # Segments is a list of points in the form of tuple (x, y, width)
    # y must be sorted
    def __init__(self, segments, margin=0):
        self.segments = segments
        assert len(segments) >= 2, "need at least two coordinates for a piecewise block"
        assert all(segments[i][1] < segments[i+1][1] for i in range(len(segments) - 1)), "segments y coordinate is not ordered"
        self.margin = margin
        self.y = segments[0][1]
        self.height = segments[-1][1] - segments[0][1]

    def edge(self, y):
        if y <= self.segments[0][1]:
            return (self.segments[0][0], self.segments[0][2])
        if y >= self.segments[-1][1]:
            return (self.segments[-1][0], self.segments[-1][2])

        last_seg = self.segments[0]
        for seg in self.segments[1:]:
            if y >= last_seg[1] and y <= seg[1]:
                segment_height = seg[1] - last_seg[1]
                dy = y - last_seg[0]
                f = dy / segment_height
                width = last_seg[2] * (1 - f) + seg[2] * f
                x0 = last_seg[0] * (1 - f) + seg[0] * f
                return (x0, width)
            last_seg = seg

        assert False

    def holes(self, interval, keep_y_quantized=True):
        ret = []
        xdim0 = self.segments[0][2] - 2 * self.margin
        xrange = max(2, int(round(xdim0 / interval) + 1))
        ydim = self.height - 2 * self.margin
        yrange = max(2, int(round(ydim / interval) + 1))
        if keep_y_quantized:
            dy = interval
            if dy * yrange > ydim:
                yrange = yrange - 1
        else:
            dy = ydim / yrange
        for yi in range(0, yrange + 1):
            y = self.y + self.margin + yi * dy
            odd = True if yi & 1 else False
            x0, width = self.edge(y)
            xdim = width - 2 * self.margin
            dx = xdim / xrange
            for xi in range(0, xrange if odd else xrange + 1):
                x = x0 + self.margin + xi * dx + (dx / 2 if odd else 0)
                ret.append((x, y))
        return ret

laser = None
for device in DEVICES:
    if os.path.exists(device):
        print(f'Connecting to {device}')
        laser = Laser(device, BAUDRATE, parallel_count=PARALLEL_COUNT, verbose=VERBOSE)
        break
assert laser is not None, 'No serial devices found!'

laser.set_move_speed(400*60)

#laser.disable_hard_limits()

# I have built a custom 5m y axis rails so need a different scale
# 1.03 for slipping?
#laser.set_soft_scaling(1.0, 1.03 * 120.0 / 140.0)

#laser.move_sync(0, -100)

# note: 50=5% power, 1000 would be 100% of power
#laser.burn_rectangle(30, 30, speed=50*60, power=50)

#print(laser.get_parameters())

# Describe the shape and size of the timber blocks on the table (as timber is never straight)
shapes = [
    # Entries are (x, y, width). y must be increasing.
    #PiecewiseBlock([(0, 0, 140), (8, 1200, 140), (8, 3875, 140)], margin=7),
    PiecewiseBlock([(0, 0, 50), (-10, 50, 70)], margin=7),
]

all_holes = []
for shape in shapes:
    all_holes.extend(shape.holes(8))

print('Total holes:', len(all_holes))

# note: 50=5% power (useful for framing), 1000 would be 100% of power
laser.burn_holes(all_holes, power=50, duration=0.20, first_row_only=True)

time.sleep(1);
laser.sync()

