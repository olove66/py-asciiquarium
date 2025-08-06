#!/usr/bin/env python
#
#############################################################################
# Asciiquarium - An aquarium animation in ASCII art
#
# This program displays an aquarium/sea animation using ASCII art.
# It requires the 'curses' module.
#
# The original Perl version of this program is available at:
# http://robobunny.com/projects/asciiquarium
#
#############################################################################
# Author of the original Perl script:
#   Kirk Baucom <kbaucom@schizoid.com>
#
# Contributors to the original Perl script:
#   Joan Stark: most of the ASCII art
#   Claudio Matsuoka: improved marine biodiversity
#
# Python port by:
#   https://github.com/olove66
#
# License:
#
# Copyright (C) 2003 Kirk Baucom (kbaucom@schizoid.com)
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#############################################################################

import curses
import random
import time
import sys
import signal
from math import floor

# --- Configuration ---
VERSION = "1.1 (Python Port)"
NEW_FISH = True
NEW_MONSTER = True

# The Z-depth at which certain items occur
DEPTH = {
    'shark': 2,
    'fish_start': 3,
    'fish_end': 20,
    'seaweed': 21,
    'castle': 22,
    'water_line3': 2,
    'water_gap3': 3,
    'water_line2': 4,
    'water_gap2': 5,
    'water_line1': 6,
    'water_gap1': 7,
    'water_line0': 8,
    'water_gap0': 9,
}

# --- Entity and Animation Classes ---

class Entity:
    def __init__(self, anim, **kwargs):
        self.anim = anim
        self.type = kwargs.get('type', 'entity')
        self.shape = kwargs.get('shape', '')
        self.color_map = kwargs.get('color', '')
        self.position = list(kwargs.get('position', [0, 0, 0])) # [x, y, z]
        self.callback_args = kwargs.get('callback_args', [0, 0, 0, 0.1]) # [dx, dy, dz, speed]
        self.death_cb = kwargs.get('death_cb', None)
        self.callback = kwargs.get('callback', self.move_entity)
        self.coll_handler = kwargs.get('coll_handler', None)
        self.die_offscreen = kwargs.get('die_offscreen', False)
        self.physical = kwargs.get('physical', False)
        self.default_color = kwargs.get('default_color', 'WHITE')
        self.transparent = kwargs.get('transparent', ' ')
        self.auto_trans = kwargs.get('auto_trans', False)
        self.die_time = kwargs.get('die_time', None)
        self.die_frame = kwargs.get('die_frame', None)
        self.frame = 0

        if isinstance(self.shape, list):
            self.frames = self.shape
            self.shape = self.frames[0]
        else:
            self.frames = [self.shape]

        if isinstance(self.color_map, list):
            self.color_frames = self.color_map
            self.color_map = self.color_frames[0]
        else:
            self.color_frames = [self.color_map]

        self.lines = self.shape.split('\n')
        self.height = len(self.lines)
        self.width = max(len(line) for line in self.lines) if self.lines else 0
        self.collisions = []

    def update(self):
        self.frame += 1
        if self.callback:
            self.callback(self)
        if self.die_frame and self.frame >= self.die_frame:
            self.kill()
        if self.die_time and time.time() >= self.die_time:
            self.kill()

    def move_entity(self, entity):
        dx, dy, dz, speed = self.callback_args
        self.position[0] += dx * speed
        self.position[1] += dy * speed
        self.position[2] += dz * speed

        num_frames = len(self.frames)
        if num_frames > 1:
            current_frame_index = floor(self.frame * speed) % num_frames
            self.shape = self.frames[current_frame_index]
            if self.color_frames:
                self.color_map = self.color_frames[current_frame_index % len(self.color_frames)]
            self.lines = self.shape.split('\n')

    def kill(self):
        self.anim.remove_entity(self)
        if self.death_cb:
            self.death_cb(self, self.anim)

    def is_offscreen(self):
        screen_w, screen_h = self.anim.width, self.anim.height
        x, y = floor(self.position[0]), floor(self.position[1])
        return (x + self.width < 0 or x > screen_w or
                y + self.height < 0 or y > screen_h)

class Animation:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.entities = []
        self.paused = False
        self.init_curses()
        self.update_term_size()
        self.init_colors()

    def init_curses(self):
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.timeout(100) # Corresponds to Perl's halfdelay(1)

    def init_colors(self):
        curses.start_color()
        curses.use_default_colors()
        self.colors = {
            'BLACK': curses.COLOR_BLACK, 'RED': curses.COLOR_RED,
            'GREEN': curses.COLOR_GREEN, 'YELLOW': curses.COLOR_YELLOW,
            'BLUE': curses.COLOR_BLUE, 'MAGENTA': curses.COLOR_MAGENTA,
            'CYAN': curses.COLOR_CYAN, 'WHITE': curses.COLOR_WHITE,
        }
        self.color_pairs = {}
        pair_num = 1
        for name, color in self.colors.items():
            curses.init_pair(pair_num, color, -1)
            self.color_pairs[name[0].lower()] = curses.color_pair(pair_num)
            self.color_pairs[name[0].upper()] = curses.color_pair(pair_num) | curses.A_BOLD
            pair_num += 1

    def update_term_size(self):
        self.height, self.width = self.stdscr.getmaxyx()

    def add_entity(self, entity):
        self.entities.append(entity)

    def remove_entity(self, entity):
        if entity in self.entities:
            self.entities.remove(entity)

    def remove_all_entities(self):
        self.entities.clear()

    def get_entities_by_type(self, type_name):
        return [e for e in self.entities if e.type == type_name]

    def animate(self):
        if self.paused:
            return

        to_remove = []
        for entity in self.entities:
            entity.update()
            if entity.die_offscreen and entity.is_offscreen():
                to_remove.append(entity)

        for entity in to_remove:
            entity.kill()

        # Collision detection
        physical_entities = [e for e in self.entities if e.physical]
        for i in range(len(physical_entities)):
            for j in range(i + 1, len(physical_entities)):
                e1 = physical_entities[i]
                e2 = physical_entities[j]
                if self.check_collision(e1, e2):
                    e1.collisions.append(e2)
                    e2.collisions.append(e1)

        for entity in self.entities:
            if entity.collisions and entity.coll_handler:
                entity.coll_handler(entity)
            entity.collisions.clear()

    def check_collision(self, e1, e2):
        x1, y1 = floor(e1.position[0]), floor(e1.position[1])
        x2, y2 = floor(e2.position[0]), floor(e2.position[1])
        return not (x1 + e1.width < x2 or x1 > x2 + e2.width or
                    y1 + e1.height < y2 or y1 > y2 + e2.height)

    def redraw_screen(self):
        self.stdscr.erase()
        sorted_entities = sorted(self.entities, key=lambda e: e.position[2])

        for entity in sorted_entities:
            x, y = floor(entity.position[0]), floor(entity.position[1])
            color_lines = entity.color_map.split('\n')

            for i, line in enumerate(entity.lines):
                if 0 <= y + i < self.height:
                    color_line = color_lines[i] if i < len(color_lines) else ''
                    for j, char in enumerate(line):
                        if 0 <= x + j < self.width:
                            if entity.auto_trans and char == ' ':
                                continue
                            if entity.transparent and char in entity.transparent:
                                continue

                            color_char = color_line[j] if j < len(color_line) else ' '
                            attr = self.color_pairs.get(color_char, self.color_pairs.get(entity.default_color[0]))
                            try:
                                self.stdscr.addstr(y + i, x + j, char, attr)
                            except curses.error:
                                pass # Ignore errors at screen boundaries
        self.stdscr.refresh()

# --- ASCII Art and Entity Definitions ---

# Helper to convert Perl's q{...} to Python's r"""..."""
def r(text):
    return text.strip('\n')

def rand_color(color_mask):
    colors = ['c', 'C', 'r', 'R', 'y', 'Y', 'b', 'B', 'g', 'G', 'm', 'M']
    for i in range(1, 10):
        color = random.choice(colors)
        color_mask = color_mask.replace(str(i), color)
    return color_mask

def add_environment(anim):
    water_line_segment = [
        r"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        r"^^^^ ^^^  ^^^   ^^^    ^^^^      ",
        r"^^^^      ^^^^     ^^^    ^^     ",
        r"^^      ^^^^      ^^^    ^^^^^^  "
    ]
    segment_size = len(water_line_segment[0])
    segment_repeat = (anim.width // segment_size) + 1
    for i in range(len(water_line_segment)):
        water_line_segment[i] *= segment_repeat

    for i, segment in enumerate(water_line_segment):
        anim.add_entity(Entity(
            anim,
            type="waterline",
            shape=segment,
            position=[0, i + 5, DEPTH[f'water_line{i}']],
            default_color='CYAN',
            physical=True
        ))

def add_castle(anim):
    castle_image = r"""
               T~~
               |
              /^\
             /   \
 _   _   _  /     \  _   _   _
[ ]_[ ]_[ ]/ _   _ \[ ]_[ ]_[ ]
|_=__-_ =_|_[ ]_[ ]_|_=-___-__|
 | _- =  | =_ = _    |= _=   |
 |= -[]  |- = _ =    |_-=_[] |
 | =_    |= - ___    | =_ =  |
 |=  []- |-  /| |\   |=_ =[] |
 |- =_   | =| | | |  |- = -  |
 |_______|__|_|_|_|__|_______|"""

    castle_mask = r"""
                RR

              yyy
             y   y
            y     y
           y       y



              yyy
             yy yy
            y y y y
            yyyyyyy"""
    anim.add_entity(Entity(
        anim,
        shape=castle_image,
        color=castle_mask,
        position=[anim.width - 32, anim.height - 13, DEPTH['castle']],
        default_color='BLACK'
    ))

def add_all_seaweed(anim):
    seaweed_count = anim.width // 15
    for _ in range(seaweed_count):
        add_seaweed(None, anim)

def add_seaweed(old_seaweed, anim):
    height = random.randint(3, 6)
    left_side, right_side = "", ""
    for i in range(height):
        if i % 2 == 0:
            left_side += "(\n"
            right_side += " )\n"
        else:
            left_side += "(\n"
            right_side += " )\n"

    x = random.randint(1, anim.width - 2)
    y = anim.height - height
    anim_speed = random.random() * 0.05 + 0.25
    anim.add_entity(Entity(
        anim,
        shape=[left_side, right_side],
        position=[x, y, DEPTH['seaweed']],
        callback_args=[0, 0, 0, anim_speed],
        die_time=time.time() + random.randint(8 * 60, 12 * 60),
        death_cb=add_seaweed,
        default_color='GREEN'
    ))

def add_bubble(fish, anim):
    cb_args = fish.callback_args
    fish_pos = list(fish.position)
    bubble_pos = list(fish_pos)

    if cb_args[0] > 0: # Moving right
        bubble_pos[0] += fish.width
    bubble_pos[1] += fish.height // 2
    bubble_pos[2] -= 1 # Bubble on top of fish

    anim.add_entity(Entity(
        anim,
        shape=['.', 'o', 'O', 'O', 'O'],
        type='bubble',
        position=bubble_pos,
        callback_args=[0, -1, 0, 0.1],
        die_offscreen=True,
        physical=True,
        coll_handler=bubble_collision,
        default_color='CYAN'
    ))

def bubble_collision(bubble):
    for col_obj in bubble.collisions:
        if col_obj.type == 'waterline':
            bubble.kill()
            break

def add_all_fish(anim):
    screen_size = (anim.height - 9) * anim.width
    fish_count = screen_size // 350
    for _ in range(fish_count):
        add_fish(None, anim)

def add_fish(old_fish, anim):
    if NEW_FISH and random.randint(0, 11) > 8:
        add_new_fish(old_fish, anim)
    else:
        add_old_fish(old_fish, anim)

def add_fish_entity(anim, fish_images):
    fish_num = random.randrange(0, len(fish_images), 2)
    shape = fish_images[fish_num]
    color_map = fish_images[fish_num + 1]

    speed = random.random() * 1.75 + 0.25
    depth = random.randint(DEPTH['fish_start'], DEPTH['fish_end'])
    color_map = color_map.replace('4', 'W')
    color_map = rand_color(color_map)

    if fish_num % 4 >= 2: # Right-facing fish
        speed *= -1

    temp_entity = Entity(anim, shape=shape) # To get dimensions
    max_y = anim.height - temp_entity.height
    min_y = 9
    y = random.randint(min_y, max_y) if max_y > min_y else min_y

    if speed < 0:
        x = anim.width - 2
    else:
        x = 1 - temp_entity.width

    anim.add_entity(Entity(
        anim,
        type='fish',
        shape=shape,
        auto_trans=True,
        color=color_map,
        position=[x, y, depth],
        callback=fish_callback,
        callback_args=[speed, 0, 0, 1.0],
        die_offscreen=True,
        death_cb=add_fish,
        physical=True,
        coll_handler=fish_collision
    ))

def fish_callback(fish):
    if random.randint(0, 100) > 97:
        add_bubble(fish, fish.anim)
    fish.move_entity(fish)

def fish_collision(fish):
    for col_obj in fish.collisions:
        if col_obj.type == 'teeth' and fish.height <= 5:
            add_splat(fish.anim, *fish.position)
            fish.kill()
            break

def add_splat(anim, x, y, z):
    splat_images = [
        r"""

   .
  ***
   '

""", r"""

 ",*;`
 "*,**
 *"'~'

""", r"""
  , ,
 " ","'
 *" *'"
  " ; .

""", r"""
* ' , ' `
' ` * . '
 ' `' ",'
* ' " * .
" * ', '
"""
    ]
    anim.add_entity(Entity(
        anim,
        shape=splat_images,
        position=[x - 4, y - 2, z - 2],
        default_color='RED',
        callback_args=[0, 0, 0, 0.25],
        transparent=' ',
        die_frame=15
    ))

def add_shark(old_ent, anim):
    shark_images = [
        r"""
                              __
                             ( `\
  ,??????????????????????????)   `\
;' `.????????????????????????(     `\__
 ;   `.?????????????__..---''          `~~~~-._
  `.   `.____...--''                       (b  `--._
    >                     _.-'      .((      ._     )
  .`.-`--...__         .-'     -.___.....-(|/|/|/|/|/'
 ;.'?????????`. ...----`.___.',,,_______......---'
 '???????????'-'
""", r"""
                     __
                    /' )
                  /'   (??????????????????????????,
              __/'     )????????????????????????.' `;
      _.-~~~~'          ``---..__?????????????.'   ;
 _.--'  b)                       ``--...____.'   .'
(     _.      )).      `-._                     <
 `\|\|\|\|)-.....___.-     `-.         __...--'-.'.
   `---......_______,,,`.___.'----... .'?????????`.;
                                     `-`???????????`
"""
    ]
    shark_masks = [
        r"""





                                           cR
 
                                          cWWWWWWWW


""", r"""





        Rc

  WWWWWWWWc


"""
    ]

    direction = random.randint(0, 1)
    speed = 2
    y = random.randint(9, anim.height - 19)

    if direction == 1: # Moving left
        speed *= -1
        x = anim.width - 2
        teeth_x = x + 9
    else: # Moving right
        x = -53
        teeth_x = -9

    teeth_y = y + 7

    anim.add_entity(Entity(
        anim,
        type='teeth',
        shape='*',
        position=[teeth_x, teeth_y, DEPTH['shark'] + 1],
        callback_args=[speed, 0, 0, 1.0],
        physical=True
    ))

    anim.add_entity(Entity(
        anim,
        type="shark",
        shape=shark_images[direction],
        color=shark_masks[direction],
        auto_trans=True,
        position=[x, y, DEPTH['shark']],
        default_color='CYAN',
        callback_args=[speed, 0, 0, 1.0],
        die_offscreen=True,
        death_cb=shark_death
    ))

def shark_death(shark, anim):
    for teeth in anim.get_entities_by_type('teeth'):
        anim.remove_entity(teeth)
    random_object(shark, anim)

def add_ship(old_ent, anim):
    ship_images = [
        r"""
     |    |    |
    )_)  )_)  )_)
   )___))___))___)\
  )____)____)_____)\\\
_____|____|____|____\\\\\__
\                   /
""", r"""
         |    |    |
        (_(  (_(  (_(
      /(___((___((___(
    //(_____(____(____(
__///____|____|____|_____
    \                   /
"""
    ]
    ship_masks = [
        r"""
     y    y    y

                  w
                   ww
yyyyyyyyyyyyyyyyyyyywwwyy
y                   y
""", r"""
         y    y    y

      w
    ww
yywwwyyyyyyyyyyyyyyyyyyyy
    y                   y
"""
    ]

    direction = random.randint(0, 1)
    speed = 1
    if direction == 1:
        speed *= -1
        x = anim.width - 2
    else:
        x = -24

    anim.add_entity(Entity(
        anim,
        shape=ship_images[direction],
        color=ship_masks[direction],
        auto_trans=True,
        position=[x, 0, DEPTH['water_gap1']],
        callback_args=[speed, 0, 0, 1.0],
        die_offscreen=True,
        death_cb=random_object
    ))

def add_whale(old_ent, anim):
    whale_images = [
        r"""
        .-----:
      .'       `.
,????/       (o) \
\`._/          ,__)
""", r"""
    :-----.
  .'       `.
 / (o)       \????,
(__,          \_.'/
"""
    ]
    water_spout = [
        r"\n\n   :", r"\n   :\n   :", r"  . .\n  -:-\n   :",
        r"  . .\n .-:-.\n   :", r"  . .\n'.-:-.`\n'  :  '",
        r"\n .- -.\n;  :  ;", r"\n\n;     ;"
    ]

    direction = random.randint(0, 1)
    speed = 1
    x = -18
    spout_align = 11
    if direction == 1:
        speed *= -1
        x = anim.width - 2
        spout_align = 1

    whale_anim = []
    # No spout
    for _ in range(5):
        whale_anim.append("\n\n\n" + whale_images[direction])
    # With spout
    for spout_frame in water_spout:
        aligned_spout = spout_frame.replace('\n', '\n' + ' ' * spout_align)
        whale_anim.append(aligned_spout + whale_images[direction])

    anim.add_entity(Entity(
        anim,
        shape=whale_anim,
        auto_trans=True,
        position=[x, 0, DEPTH['water_gap2']],
        default_color='CYAN',
        callback_args=[speed, 0, 0, 1.0],
        die_offscreen=True,
        death_cb=random_object
    ))

def add_monster(old_ent, anim):
    if NEW_MONSTER:
        add_new_monster(old_ent, anim)
    else:
        add_old_monster(old_ent, anim)

def add_new_monster(old_ent, anim):
    monster_images = [
        [
            r"""
         _???_?????????????????????_???_???????_a_a
       _{.`=`.}_??????_???_??????_{.`=`.}_????{/ ''\\_
 _????{.'  _  '.}????{.`'`.}????{.'  _  '.}??{|  ._oo)
{ \\??{/  .'?'.  \\}??{/ .-. \\}??{/  .'?'.  \\}?{/  |
""",
            r"""
                      _???_????????????????????_a_a
  _??????_???_??????_{.`=`.}_??????_???_??????{/ ''\\_
 { \\????{.`'`.}????{.'  _  '.}????{.`'`.}????{|  ._oo)
  \\ \\??{/ .-. \\}??{/  .'?'.  \\}??{/ .-. \\}???{/  |
"""
        ], [
            r"""
   a_a_???????_???_?????????????????????_???_
 _/'' \\}????_{.`=`.}_??????_???_??????_{.`=`.}_
(oo_.  |}??{.'  _  '.}????{.`'`.}????{.'  _  '.}????_
    |  \\}?{/  .'?'.  \\}??{/ .-. \\}??{/  .'?'.  \\}??/ }
""",
            r"""
   a_a_????????????????????_   _
 _/'' \\}??????_???_??????_{.`=`.}_??????_???_??????_
(oo_.  |}????{.`'`.}????{.'  _  '.}????{.`'`.}????/ }
    |  \\}???{/ .-. \\}??{/  .'?'.  \\}??{/ .-  \\}??/ /
"""
        ]
    ]
    monster_masks = [
        r"                                                W W",
        r"   W W"
    ]
    direction = random.randint(0, 1)
    speed = 2
    if direction == 1:
        speed *= -1
        x = anim.width - 2
    else:
        x = -54

    anim.add_entity(Entity(
        anim,
        shape=monster_images[direction],
        auto_trans=True,
        color=[monster_masks[direction]] * 2,
        position=[x, 2, DEPTH['water_gap2']],
        callback_args=[speed, 0, 0, 0.25],
        death_cb=random_object,
        die_offscreen=True,
        default_color='GREEN'
    ))

def add_big_fish(old_ent, anim):
    if NEW_FISH and random.randint(0, 2) > 1:
        add_big_fish_2(old_ent, anim)
    else:
        add_big_fish_1(old_ent, anim)

def add_big_fish_1(old_ent, anim):
    big_fish_images = [
        r"""
 ______
`""-.  `````-----.....__
     `.  .      .       `-.
       :     .     .       `.
 ,?????:   .    .          _ :
: `.???:                  (@) `._
 `. `..'     .     =`-.       .__)
   ;     .        =  ~  :     .-"
 .' .'`.   .    .  =.-'  `._ .'
: .'???:               .   .'
 '???.'  .    .     .   .-'
   .'____....----''.'=.'
   ""?????????????.'.'
               ''"'`
""", r"""
                           ______
          __.....-----'''''  .-""'
       .-'       .      .  .'
     .'       .     .     :
    : _          .    .   :?????,
 _.' (@)                  :???.' :
(__.       .-'=     .     `..' .'
 "-.     :  ~  =        .     ;
   `. _.'  `-.=  .    .   .'`. `.
     `.   .               :???`. :
       `-.   .     .    .  `.???`
          `.=`.``----....____`.
            `.`.?????????????""
              '`"``
"""
    ]
    big_fish_masks = [
        rand_color(r"""
 111111
11111  11111111111111111
     11  2      2       111
       1     2     2       11
 1     1   2    2          1 1
1 11   1                  1W1 111
 11 1111     2     1111       1111
   1     2        1  1  1     111
 11 1111   2    2  1111  111 11
1 11   1               2   11
 1   11  2    2     2   111
   111111111111111111111
   11             1111
               11111
"""), rand_color(r"""
                           111111
          11111111111111111  11111
       111       2      2  11
     11       2     2     1
    1 1          2    2   1     1
 111 1W1                  1   11 1
1111       1111     2     1111 11
 111     1  1  1        2     1
   11 111  1111  2    2   1111 11
     11   2               1   11 1
       111   2     2    2  11   1
          111111111111111111111
            1111             11
              11111
""")
    ]
    direction = random.randint(0, 1)
    speed = 3
    if direction == 1:
        x = anim.width - 1
        speed *= -1
    else:
        x = -34
    y = random.randint(9, anim.height - 15)
    anim.add_entity(Entity(
        anim,
        shape=big_fish_images[direction],
        auto_trans=True,
        color=big_fish_masks[direction],
        position=[x, y, DEPTH['shark']],
        callback_args=[speed, 0, 0, 1.0],
        death_cb=random_object,
        die_offscreen=True,
        default_color='YELLOW'
    ))

def add_big_fish_2(old_ent, anim):
    big_fish_images = [
        r"""
                _ _ _
             .='\\ \\ \\`"=,
           .'\\ \\ \\ \\ \\ \\ \\
\\'=._?????/ \\ \\ \\_\\_\\_\\_\\_\\
\\'=._'.??/\\ \\,-"`- _ - _ - '-.
  \\`=._\\|'.\\/- _ - _ - _ - _- \\
  ;"= ._\\=./_ -_ -_ \{`"=_    @ \\
   ;="_-_=- _ -  _ - \{"=_"-     \\
   ;_=_--_.,          \{_.='   .-/
  ;.="` / ';\\        _.     _.-`
  /_.='/ \\/ /;._ _ _\{.-;`/"`
/._=_.'???'/ / / / /\{.= /
/.=' ??????`'./_/_.=`\{_/
""", r"""
            _ _ _
        ,="`/ / /'=.
       / / / / / / /'.
      /_/_/_/_/_/ / / \\?????_.='/
   .-' - _ - _ -`"-,/ /\\??.'_.='/
  / -_ - _ - _ - _ -\\/.'|/_.=`/
 / @    _="`\} _- _- _\\.=/_. =";
/     -"_="\} - _  - _ -=_-_"=;
\\-.   '=._\}          ,._--_=_;
 `-._     ._        /;' \\ `"=.;
     `"\\`;-.\}_ _ _.;\\ \\/ \\'=._\\
        \\ =.\}\\ \\ \\ \\ \\'???'._=_.\\
         \\_\}`=._\\_\\.'`???????'=.\\
"""
    ]
    big_fish_masks = [
        rand_color(r"""
                1 1 1
             1111 1 11111
           111 1 1 1 1 1 1
11111     1 1 1 11111111111
1111111  11 111112 2 2 2 2 111
  111111111112 2 2 2 2 2 2 22 1
  111 1111 12 22 22 11111    W 1
   11111112 2 2  2 2 111111     1
   111111111          11111   111
  11111 11111        11     1111
  111111 11 1111 1 111111111
1111111   11 1 1 1 1111 1
1111       1111111111111
"""), rand_color(r"""
            1 1 1
        11111 1 1111
       1 1 1 1 1 1 111
      11111111111 1 1 1     11111
   111 2 2 2 2 211111 11  1111111
  1 22 2 2 2 2 2 2 211111111111
 1 W    11111 22 22 2111111 111
1     111111 2 2  2 2 21111111
111   11111          111111111
 1111     11        111 1 11111
     111111111 1 1111 11 111111
        1 1111 1 1 1 11   1111111
         1111111111111       1111
""")
    ]
    direction = random.randint(0, 1)
    speed = 2.5
    if direction == 1:
        x = anim.width - 1
        speed *= -1
    else:
        x = -33
    y = random.randint(9, anim.height - 14)
    anim.add_entity(Entity(
        anim,
        shape=big_fish_images[direction],
        auto_trans=True,
        color=big_fish_masks[direction],
        position=[x, y, DEPTH['shark']],
        callback_args=[speed, 0, 0, 1.0],
        death_cb=random_object,
        die_offscreen=True,
        default_color='YELLOW'
    ))

# --- Random Object and Fish Art Data ---

RANDOM_OBJECTS = [add_ship, add_whale, add_monster, add_big_fish, add_shark]

def random_object(dead_object, anim):
    random.choice(RANDOM_OBJECTS)(dead_object, anim)

# Fish art data is quite large, so it's loaded from helper functions
from fish_art import get_old_fish_art, get_new_fish_art

def add_old_fish(old_fish, anim):
    add_fish_entity(anim, get_old_fish_art())

def add_new_fish(old_fish, anim):
    add_fish_entity(anim, get_new_fish_art())

# --- Main Loop and Signal Handling ---

def main(stdscr):
    global NEW_FISH, NEW_MONSTER
    if '-c' in sys.argv:
        NEW_FISH = False
        NEW_MONSTER = False

    anim = Animation(stdscr)
    
    # Graceful exit
    def signal_handler(sig, frame):
        curses.endwin()
        print("Asciiquarium has been closed. Goodbye!", file=sys.stderr)
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        # Setup the scene
        add_environment(anim)
        add_castle(anim)
        add_all_seaweed(anim)
        add_all_fish(anim)
        random_object(None, anim)

        anim.redraw_screen()

        # Inner loop for animation and input
        while True:
            try:
                key = stdscr.getch()
            except curses.error:
                key = -1
            
            if key != -1:
                key_char = chr(key).lower()
                if key_char == 'q':
                    return
                elif key_char == 'p':
                    anim.paused = not anim.paused
                elif key_char == 'r':
                    break # Break inner loop to redraw
            
            if key == curses.KEY_RESIZE:
                anim.update_term_size()
                break # Redraw on resize

            anim.animate()
            anim.redraw_screen()
        
        # Clear everything to restart
        anim.remove_all_entities()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except curses.error as e:
        print(f"Error running asciiquarium: {e}", file=sys.stderr)
        print("Your terminal may not support curses, or the window is too small.", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nInterrupted. Goodbye!", file=sys.stderr)
