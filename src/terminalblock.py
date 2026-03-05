#!/usr/bin/env python3
# encoding: utf-8

#---------|---------|---------|---------|---------|---------|---------|---------|
# Copyright (C) 2018 Raul Roda <raulroda@yahoo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#---------|---------|---------|---------|---------|---------|---------|---------|
 

# Imports
import logging as log
import re
import xml.etree.ElementTree as etree  # python3-lxml
import uuid as uuidly


class TerminalBlock:
    """This class represents a Terminal Block for a QET project.
    The list of terminals has dicts like:
        {uuid, block_name, segment, terminal_name, terminal_pos, 
        terminal_xref, terminal_type, conductor_name, cable, cable_cond, 
        terminal_color, bridge1, bridge2, bridge3, bridge4}
    """

    COLOR_MAP = {
        "orange": "orange",
        "lightblue": "cyan",
        "red": "red",
        "darkblue": "blue",
        "green": "green"
    }

    LOGO_HEIGHT = 36  #  the height of the FUSE LOGO for fuse type
    Y_OFFSET_BASE_TEXT = 22  # vertical offset between terminal and letters
    X_OFFSET_CABLE_TEXT = 4  # horizontal offset between cable and its name

    def __init__(self, tb_block_name, collec, settings=None, debug_mode=False):
        """initializer.
        @param string tb_block_name: block_name
        @param collec: collection of terminals. Only the terminals of the
            segment 'tb_id' are accepted.
        @param settings: dict with the settings
        @param debug_mode: enable debug logging to debug_drawing.txt
        """
        self.tb_block_name = tb_block_name
        self.terminals = collec
        self.num_terminals = len(self.terminals)
        self.tb_id = self.terminals[0]['block_name']
        self.debug_mode = debug_mode

        # set settings if defined or defaults
        s = settings or {}
        self.HEAD_HEIGHT = int(s.get('-CFG_A-', 120))
        self.HEAD_WIDTH = int(s.get('-CFG_B-', 44))
        self.UNION_HEIGHT = int(s.get('-CFG_C-', 70))
        self.UNION_WIDTH = int(s.get('-CFG_D-', 6))
        self.TERMINAL_HEIGHT = int(s.get('-CFG_E-', 160))
        self.TERMINAL_WIDTH = int(s.get('-CFG_F-', 20))
        self.CONDUCTOR_LENGTH = int(s.get('-CFG_G-', 70))
        self.HOSE_CONDUCTOR_START = int(s.get('-CFG_H-', 70))
        self.HOSE_LENGTH = int(s.get('-CFG_I-', 80))
        self.HOSE_CONDUCTOR_END = int(s.get('-CFG_J-', 70))

        self.HEAD_FONT = int(s.get('-CFG_HEAD_FONT-', 13))
        self.TERMINAL_FONT = int(s.get('-CFG_TERMINAL_FONT-', 9))
        self.XREF_FONT = int(s.get('-CFG_XREF_FONT-', 6))
        self.CONDUCTOR_FONT = int(s.get('-CFG_CONDUCTOR_FONT-', 6))

        self.SPLIT_SIZE = int(s.get('-CFG_SPLIT-', 30))
        self.TERMINAL_STEP = int(s.get('-CFG_K-', 20))



    def _getNum(self, x):
        """ Returns the page part as integer of a XREF. Is there isn't digits,
        return 9999. Usefull for sort reasons.
        e.g. '12-B8' """

        foo = x.split('-')[0]
        if foo.isdigit():
            return int(foo)
        else:
            return 9999


    def drawTerminalBlock(self):
        """Generates the xml code for the terminal block
        @(param) self.terminals
        @return: none"""

        # calc some values    
        name = 'TB_'+ self.tb_block_name  
        total_width = self.HEAD_WIDTH + \
                self.UNION_WIDTH + \
                self.num_terminals * self.TERMINAL_WIDTH + \
                1  # +1 to force round the next tenth
        while (total_width % 10): total_width += 1

        total_height = self.CONDUCTOR_LENGTH + \
                self.TERMINAL_HEIGHT + \
                self.HOSE_CONDUCTOR_START + \
                self.HOSE_LENGTH + \
                self.HOSE_CONDUCTOR_END + \
                1 
        while (total_height % 10): total_height += 1

        cursor = 0 
        root = etree.Element('element', name=name + '.elmt')
        
        definition = etree.SubElement(root, "definition", \
                height = str(total_height) , \
                width = str(total_width), \
                hotspot_x = '5', hotspot_y = '24', \
                link_type = 'simple', \
                orientation = 'dyyy' ,\
                version = '0.4', \
                type='element')
        self._element_definitions(definition, name)
        self._element_label(definition)
        
        informations = etree.SubElement(definition, 'informations')
        informations.text = 'Terminal block'
        description = etree.SubElement(definition, 'description')
        
        # Fixed axes for alignment
        y_center = self.CONDUCTOR_LENGTH + (self.TERMINAL_HEIGHT / 2)
        y_max_top = y_center - (self.TERMINAL_HEIGHT / 2)
        y_max_bottom = y_center + (self.TERMINAL_HEIGHT / 2)

        # draw TB header (centered)
        y1_hd = y_center - (self.HEAD_HEIGHT / 2)
        hd = self._rect (description, x=cursor, y=y1_hd, width=self.HEAD_WIDTH, height=self.HEAD_HEIGHT)
        hd_label = self._label_header(description, y=y_center, text=self.tb_block_name)
        
        # draw Union
        cursor += self.HEAD_WIDTH
        y1_un = y_center - (self.UNION_HEIGHT / 2)
        un = self._rect (description, x=cursor, y=y1_un, width=self.UNION_WIDTH, height=self.UNION_HEIGHT)
                
        cursor += self.UNION_WIDTH
        last_trmnl = {}  
        for k in self.terminals[0]: last_trmnl[k] = '' 
        last_cable_coord_x = cursor
        max_cond_name_length = max( [len(str(x.get('cable', ''))) for x in self.terminals] )
        max_hose_cond_name_length = max( [len(str(x.get('cable', ''))) for x in self.terminals] )

        last_bridge_x = {1: None, 2: None, 3: None, 4: None}
        
        for i in range(0, self.num_terminals):
            trmnl = self.terminals[i]
            x_term_center = cursor + (self.TERMINAL_WIDTH / 2)
            
            try: etage = int(trmnl.get('etage', '1'))
            except (ValueError, TypeError): etage = 1
            
            # Centered height reduction: height is E - (n-1)*K
            h_curr = self.TERMINAL_HEIGHT - (etage - 1) * self.TERMINAL_STEP
            y_top_curr = y_center - (h_curr / 2)
            y_bottom_curr = y_center + (h_curr / 2)

            # Draw terminal box
            self._rect(description, x=cursor, y=y_top_curr, width=self.TERMINAL_WIDTH, height=h_curr)
            
            # Adjusted alignment for Labels: follow the current box edges
            term_label = self._label_term(description, x=x_term_center, \
                    y=y_bottom_curr - 5, \
                    text=trmnl['terminal_name'])
            
            # XRef inside the terminal at the top
            term_xref_label = self._label_term_xref(description, x=x_term_center, \
                    y=y_top_curr + 30, \
                    text=trmnl['terminal_xref'])
            
            # Logos and bridges use the horizontal center axis
            self._type_term(description, x=x_term_center, y=y_center, trmnl=trmnl, cursor=cursor)

            for level in range(1, 5):
                b_key = f'bridge{level}'
                val = str(trmnl.get(b_key, "")).strip().upper()
                if val in ["O", "F"]:
                    y_rail = int(y_center + (level-1) * 5)
                    xc = int(x_term_center)
                    self._circle(description, x=xc-2, y=y_rail-2, diameter=4, style='line-style:normal;line-weight:normal;filling:black;color:black')
                    if last_bridge_x[level] is not None:
                        self._line(description, x1=int(last_bridge_x[level]), y1=y_rail, x2=xc, y2=y_rail, style='line-style:normal;line-weight:bold;filling:none;color:black')
                    if val == "F": last_bridge_x[level] = None
                    else: last_bridge_x[level] = xc
            
            # North conductors: start at 0, end at variable top of box
            self._line(description, x_term_center, 0, x_term_center, y_top_curr)
            # North wire label: aligned on y_max_top
            self._label_cond(description, x=x_term_center - self.CONDUCTOR_FONT - TerminalBlock.X_OFFSET_CABLE_TEXT, \
                    y=y_max_top - TerminalBlock.Y_OFFSET_BASE_TEXT + 3, \
                    text=trmnl['cable'])
            self._qet_term(description, x=cursor, y=0, orientation='n')

            # South conductors: start at variable bottom of box
            if self.debug_mode:
                try:
                    with open("debug_drawing.txt", "a") as f:
                        f.write(f"DRAWING: name={trmnl.get('terminal_name')} -> FULL_DATA: {str(trmnl)}\n")
                except Exception: pass

            # Robust key detection
            # Sometimes keys are 'hose', sometimes 'conductor_name' (legacy)
            hose_name = str(trmnl.get('hose', trmnl.get('conductor_name', ''))).strip()
            cond_num = str(trmnl.get('conductor', trmnl.get('cable_cond', ''))).strip()
            
            if hose_name.lower() in ['none', 'nan', 'null', '']: 
                hose_name = ''
            
            if self.debug_mode:
                try:
                    with open("debug_drawing.txt", "a") as f:
                        f.write(f"  SOUTH: name={trmnl.get('terminal_name')} hose='{hose_name}' cond='{cond_num}' cable='{trmnl.get('cable','')}' etage={trmnl.get('etage','1')} y_bottom_curr={y_bottom_curr} y_max_bottom={y_max_bottom}\n")
                except Exception: pass
            
            if hose_name != '': 
                y1_south = y_bottom_curr
                y1_label = y_max_bottom # Fixed alignment for labels
                y2_south = y_max_bottom + self.HOSE_CONDUCTOR_START
                
                self._line (description, x1=x_term_center, x2=x_term_center, y1 = y1_south, y2 = y2_south)
                # Cable label (601, 604...)
                self._label_cond(description , x=x_term_center - self.CONDUCTOR_FONT - 2, \
                    y=y1_label + TerminalBlock.Y_OFFSET_BASE_TEXT - 1 + (max_cond_name_length * self.CONDUCTOR_FONT), \
                    text=str(trmnl.get('cable', '')))
                
                # Conductor number (1, 2, 3...)
                self._label_cond(description , x=x_term_center - self.CONDUCTOR_FONT - 3, \
                    y=y2_south - 11, text=cond_num)
                
                # Top slash
                self._line(description, x1=x_term_center - 2, x2=x_term_center + 2, y1=y2_south - 10 - 2, y2=y2_south - 10 + 2)

                y1_hose = y2_south + self.HOSE_LENGTH
                y2_hose = y1_hose + self.HOSE_CONDUCTOR_END
                self._line (description, x_term_center, y1_hose, x_term_center, y2_hose)
                
                # Bottom conductor number (repositioned)
                self._label_cond(description , x=x_term_center - self.CONDUCTOR_FONT - 3, \
                    y=y1_hose + 39, \
                    text=cond_num)
                
                # Bottom slash
                self._line(description, x1=x_term_center-2, x2=x_term_center+2, \
                    y1=y1_hose + 10 - 2, \
                    y2=y1_hose + 10 + 2)
                self._qet_term(description, cursor, y2_hose, 's')
                
                if self.debug_mode:
                    try:
                        with open("debug_drawing.txt", "a") as f:
                            f.write(f"    -> HOSE BRANCH: line({x_term_center}, {y1_south} -> {y2_south}), cable_label='{trmnl.get('cable','')}', cond='{cond_num}', hose_line({x_term_center}, {y1_hose} -> {y2_hose})\n")
                    except Exception: pass
            else: 
                y1_indiv = y_bottom_curr
                y2_indiv = y_max_bottom + self.CONDUCTOR_LENGTH
                self._line (description, x_term_center, y1_indiv, x_term_center, y2_indiv)
                self._label_cond(description , x=x_term_center - self.CONDUCTOR_FONT - 3, \
                    y=y_max_bottom + TerminalBlock.Y_OFFSET_BASE_TEXT + (max_cond_name_length * self.CONDUCTOR_FONT), \
                    text=trmnl['cable'])
                self._qet_term(description, x=cursor, y=y2_indiv, orientation='s')
                
                if self.debug_mode:
                    try:
                        with open("debug_drawing.txt", "a") as f:
                            f.write(f"    -> SIMPLE BRANCH: line({x_term_center}, {y1_indiv} -> {y2_indiv}), cable='{trmnl['cable']}'\n")
                    except Exception: pass

            # Hose detection logic (use fixed Y for horizontal lines)
            y1_h = y_max_bottom + self.HOSE_CONDUCTOR_START
            y2_h = y1_h + self.HOSE_LENGTH
            
            curr_h_name = hose_name
            last_h_name = str(last_trmnl.get('hose', last_trmnl.get('conductor_name', ''))).strip()
            if last_h_name.lower() in ['none', 'nan', 'null']: last_h_name = ''
            
            if ( (curr_h_name != last_h_name) and (last_h_name != '') ) \
                or ( (last_h_name != '') and (i == self.num_terminals - 1) ):
                
                # We draw the horizontal lines for the PREVIOUS group
                x1 = last_cable_coord_x + (self.TERMINAL_WIDTH / 2)
                x2 = cursor - (self.TERMINAL_WIDTH / 2)
                
                # If it's the last terminal and belongs to the same group, extend x2
                if i == self.num_terminals - 1 and curr_h_name == last_h_name: 
                    x2 += self.TERMINAL_WIDTH 
                
                self._line(description, x1, y1_h, x2, y1_h) # Top hose bar
                self._line(description, x1, y2_h, x2, y2_h) # Bottom hose bar
                self._line(description, (x1+x2)/2, y1_h, (x1+x2)/2, y2_h) # Middle vertical
                
                # Hose label
                self._label_cond(description, (x1+x2)/2 - self.TERMINAL_WIDTH + 10, y1_h + ((y2_h-y1_h)/2) + len(last_h_name)*1.3 + 5, last_h_name)
            
            if curr_h_name != last_h_name: 
                last_cable_coord_x = cursor
            cursor += self.TERMINAL_WIDTH
            last_trmnl = trmnl

        return root


    def _element_definitions(self, father, name):
        sUUID = '{' + uuidly.uuid1().urn[9:] + '}'
        uuid = etree.SubElement(father, 'uuid', uuid=sUUID)
        
        names = etree.SubElement(father, 'names')
        lang1 = etree.SubElement(names, 'name', lang='de')
        lang1.text = 'Terminalblock ' + name
        lang2 = etree.SubElement(names, 'name', lang='ru')
        lang2.text = '&#x422;&#x435;&#x440;&#x43C;&#x438;&#x43D;&#x430;&#x43B;&#x44C;&#x43D;&#x44B;&#x439; &#x431;&#x43B;&#x43E;&#x43A; ' + name
        lang3 = etree.SubElement(names, 'name', lang='pt')
        lang3.text = 'Bloco terminal ' + name
        lang4 = etree.SubElement(names, 'name', lang='en')
        lang4.text = 'Terminal block ' + name
        lang5 = etree.SubElement(names, 'name', lang='it')
        lang5.text = 'Terminal block ' + name
        lang6 = etree.SubElement(names, 'name', lang='fr')
        lang6.text = 'Bornier ' + name
        lang7 = etree.SubElement(names, 'name', lang='pl')
        lang7.text = 'Blok zacisk&#xF3;w ' + name
        lang8 = etree.SubElement(names, 'name', lang='es')
        lang8.text = 'Bornero ' + name
        lang9 = etree.SubElement(names, 'name', lang='nl')
        lang9.text = 'Eindblok ' + name
        lang10 = etree.SubElement(names, 'name', lang='cs')
        lang10.text = 'Termin&#xE1;lov&#xFD; blok ' + name


    def _element_label(self, father):
        # element label
        label = etree.SubElement(father, 'dynamic_text', \
                x=str(self.HEAD_WIDTH + 5), \
                y=str(self.HEAD_HEIGHT + 5), \
                z='2', \
                text_from='ElementInfo', text_width='-1', \
                uuid = '{' + uuidly.uuid1().urn[9:] + '}', \
                font_size='10', frame='false')
        label_text = etree.SubElement(label, 'text')
        label_text.text = self.tb_id
        label_info = etree.SubElement(label, 'info_name')
        label_info.text = 'label'


    def _type_term(self, father, x, y, trmnl, cursor):
        """
        Generates a xml element that represents the logo of the terminal
        @param x: center axis of terminal
        @param y: center vertical of terminal
        @param cursor: left edge of terminal
        """
        typ = str(trmnl.get('terminal_type', '')).lower()
        color_name = trmnl.get('terminal_color', '')
        
        # Color rectangle (above symbols)
        if color_name in TerminalBlock.COLOR_MAP:
            c_qet = TerminalBlock.COLOR_MAP[color_name]
            style = f'line-style:normal;line-weight:normal;filling:{c_qet};color:black'
            # Center the color rectangle on the terminal width
            rect_y = y - 30 
            self._rect(father, x=cursor, y=rect_y, width=self.TERMINAL_WIDTH, height=10, style=style)

        if typ == 'ground':
            logo_width = 15
            y1 = y - 10
            y2 = y
            self._line(father, x, y1, x, y2) # Vertical
                        
            x1 = x - (logo_width / 2)
            x2 = x + (logo_width / 2)
            self._line(father, x1, y2, x2, y2) # Base
            self._line(father, x1+2, y2+2, x2-2, y2+2) # Mid
            self._line(father, x1+4, y2+4, x2-4, y2+4) # Small
            self._line(father, x1+6, y2+6, x2-6, y2+6) # Tip
        
        elif typ == 'fuse':
            logo_height = TerminalBlock.LOGO_HEIGHT
            x1 = x - (self.TERMINAL_WIDTH / 2) + 2
            x2 = x + (self.TERMINAL_WIDTH / 2) - 2
            y1 = y - (logo_height/2)
            y2 = y + (logo_height/2)
            self._line(father, x1, y1, x2, y1)
            self._line(father, x1, y2, x2, y2)
            
            # central square
            x1a, x2a = x - 3, x + 3
            y1a, y2a = y1 + 6, y2 - 6
            self._line(father, x1a, y1a, x2a, y1a)
            self._line(father, x1a, y2a, x2a, y2a)
            self._line(father, x1a, y1a, x1a, y2a)
            self._line(father, x2a, y1a, x2a, y2a)
            # Center wire
            self._line(father, x, y1a-3, x, y2a+3)
        else: 
            pass
            
                        
    def _circle(self, father, x, y, diameter, style=None):
        """Generates a xml element that represents a circle
        """
        if style is None:
            style = 'line-style:normal;line-weight:normal;filling:none;color:black'
        return etree.SubElement(father, 'circle', \
                        x = str(x), y = str(y), diameter = str(diameter), \
                        antialias = 'false', \
                        style = style)


    def _line(self, father, x1, y1, x2, y2, style=None):
        """Generates a xml element that represents a line  
        on the terminal
        """
        if style is None:
            style = 'line-style:normal;line-weight:normal;filling:none;color:black'
        return etree.SubElement(father, 'line', \
                        x1 = str(x1), y1 = str(y1), \
                        x2 = str(x2), y2 = str(y2), \
                        length1 = '1.5', length2 = '1.5', \
                        end1 = 'none', end2 = 'none', \
                        antialias = 'false', \
                        style = style)


    def _rect(self, father, x, y, width, height, style=None):
        """Generates a xml element that represents a line vertical centered 
        on the terminal
        """
        if style is None:
            style = 'line-style:normal;line-weight:normal;filling:none;color:black'
        return etree.SubElement(father, 'rect', \
                    x = str(x), \
                    y = str(y), \
                    width = str(width), \
                    height = str(height), \
                    antialias = 'false', \
                    style = style)


    def _qet_term(self, father, x, y, orientation):
        """Generates a xml element that represents a line verticalcentered 
        on the terminal
        """
        xc = x + self.TERMINAL_WIDTH / 2
        orth_terminal = etree.SubElement(father, 'terminal', \
                    x=str(xc), y=str(y), \
                    orientation=orientation)


    def _label_cond(self, father, x, y, text):
        """Generates a xml element that represents a label of a conductor centered
        on the terminal
        @ param father: xml node father
        @ param x: x pos. of terminal
        @ param y: y pos. of the text
        @ param text: text to show
        """
        size = self.CONDUCTOR_FONT
        xc = x - size + 1
        label = etree.SubElement(father, 'dynamic_text', \
                x=str(xc), \
                y=str(y), \
                z='3', \
                text_from='UserText', \
                uuid = '{' + uuidly.uuid1().urn[9:] + '}', \
                font_size=str(size), frame='false', \
                rotation='270')
        label_text = etree.SubElement(label, 'text')
        label_text.text = text
        #label_color = etree.SubElement(label, 'color')
        #label_color.text = '#ff0000'  
        return label          
        

    def _label_header(self, father, y, text):
        """Generates a xml element that represents a label of a conductor centered
        on the terminal. 
        @ param father: xml node father
        @ param y: y pos. of the center header
        @ param text: text to show
        """
        size = self.HEAD_FONT
        x = (self.HEAD_WIDTH / 2) - size
        y = y + (len(text) / 2) * size
        label = etree.SubElement(father, 'dynamic_text', \
                x=str(x), \
                y=str(y), \
                z='3', \
                text_from='UserText', \
                uuid = '{' + uuidly.uuid1().urn[9:] + '}', \
                font_size=str(size), frame='false', \
                rotation='270')
        label_text = etree.SubElement(label, 'text')
        label_text.text = text
        label_color = etree.SubElement(label, 'color')
        label_color.text = '#777777'
        return label


    def _label_term(self, father, x, y, text):
        """Generates a xml element that represents a label of a conductor centered
        on the terminal
        @ param father: xml node father
        @ param x: x pos. of the terminal
        @ param y: y pos. of the anchor
        @ param text: id of the terminal
        """
        size = self.TERMINAL_FONT
        x1 = x - (size * 1.1)
        y1 = y
        label = etree.SubElement(father, 'dynamic_text', \
                x=str(x1), \
                y=str(y1), \
                z='3', \
                text_from='UserText', \
                uuid = '{' + uuidly.uuid1().urn[9:] + '}', \
                font_size=str(size), frame='false', \
                rotation='270')
        label_text = etree.SubElement(label, 'text')
        label_text.text = text
        label_color = etree.SubElement(label, 'color')
        label_color.text = '#555555'
        return label


    def _label_term_xref(self, father, x, y, text):
        """Generates a xml element that represents a label of a conductor centered
        on the terminal
        @ param father: xml node father
        @ param x: x pos. of the terminal
        @ param y: y pos. of the anchor
        @ param text: id of the terminal
        """
        size = self.XREF_FONT
        x1 = x - (size * 1.1) - 3  # Aligned with ID - 3px left
        label = etree.SubElement(father, 'dynamic_text', \
                x=str(x1), \
                y=str(y), \
                z='3', \
                text_from='UserText', \
                uuid = '{' + uuidly.uuid1().urn[9:] + '}', \
                font_size=str(size), frame='false', \
                rotation='270')
        label_text = etree.SubElement(label, 'text')
        label_text.text = text
        return label