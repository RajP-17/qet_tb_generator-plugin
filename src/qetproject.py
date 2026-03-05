#!/usr/bin/env python3
# encoding: utf-8

#---------|---------|---------|---------|---------|---------|---------|---------|
# Copyright (C) 2018 Raul Roda <raulroda8@gmail.com>
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
import operator
import re
import xml.etree.ElementTree as etree  # python3-lxml
from collections import OrderedDict
import tempfile
import os
from io import BytesIO


class QETProject:
    """This class works with the XML source file of a QET Project.
    The list of terminals has dicts like:
        {uuid, block_name, terminal_name, terminal_pos, 
        terminal_xref, terminal_type, conductor_name, cable, cable_cond} 
    where:
      - uuid: identificador of the terminal in the QET xml file.
      - block_name: terminal block that belong the terminal.
      - terminal_name: comes from the diagram
      - terminal_xref: location calculated of the element.
      - terminal_pos: position. Specified in the plugin. For sorterin purposes.
      - terminal_type: STANDARD, GROUND, FUSE. For representing purposes.
      - cable_cond: name of the cable of the electric hose.
      - conductor_name: Name of the electric hose.
      - bridge: True/False for a bridge to next terminal
      - num_reserve: Config for entire terminal block. Num of reserve terminals
      - reserve_positions: Config for entire terminal block. List of 
            positions for the reserve terminals.
    
    The tags for every key have the form %_ (are specified above)
    """

    # class attributes
    QET_COL_ROW_SIZE = 25  # pixels offset for elements coord
    QET_BLOCK_TERMINAL_SIZE = 30  # pixels offset for elements coord

    # Pre-compiled regex patterns for metadata parsing (performance)
    _RE_POS = re.compile(r'%p(\d+)(%|$)')
    _RE_TYPE = re.compile(r'%t([^%]*)(%|$)')
    _RE_HOSE = re.compile(r'%h([^%]*)(%|$)')
    _RE_CONDUCTOR = re.compile(r'%n([^%]*)(%|$)')
    _RE_BRIDGE1 = re.compile(r'%b1([^%]*)(%|$)')
    _RE_BRIDGE_OLD = re.compile(r'%b([^%1234][^%]*)(%|$)')
    _RE_BRIDGE_EMPTY = re.compile(r'%b(%|$)')
    _RE_BRIDGE2 = re.compile(r'%b2([^%]*)(%|$)')
    _RE_BRIDGE3 = re.compile(r'%b3([^%]*)(%|$)')
    _RE_BRIDGE4 = re.compile(r'%b4([^%]*)(%|$)')
    _RE_RESERVE = re.compile(r'%r(\d+)(%|$)')
    _RE_RESERVE_POS = re.compile(r'%z([^%]*)(%|$)')
    _RE_SIZE = re.compile(r'%s(\d+)(%|$)')
    _RE_ETAGE = re.compile(r'%v(\d+)(%|$)')
    _RE_COLOR = re.compile(r'%c([^%]*)(%|$)')
    _RE_VALID_TERMINAL = re.compile(r'^(.+):(.+)$')



    def __init__(self, project_file, fromPage='', \
            toPage = '', searchImplicitsConnections = False):
        """class initializer. Parses the QET XML file.
        @param project_file: file of the QET project
        @param folio_reference_type: how to calc XRefs when recover project info:
           'A' auto. Same xref as configured in the QET diagram project.
           'D' default (%f-%l%c) i.e. 15-F4
        @param fromPage: first page in range to be processed
        @param toPage: last page in range to be processed
        @param searchImplicitsConnections: True for search implicit connections in TB creation"""

        # Defines namespaces if exists. When changes the project logo in QET appears ns
        # but are not defined in the head, like:  xmlns:ns0="ns0".
        # If namespaces are not defines, etree cannot parse the XML file.

        
        # with open(project_file, 'r' ,encoding='utf8') as f:
        #     xml = f.read()
        #     ns = re.findall( '[\s<]{1}(\w+):', xml )  # namesapaces
        # if ns:
        #     ns = [ x for x in dict.fromkeys(ns) if \
        #             x.startswith('ns') or x.startswith('dc') or x.startswith('rdf')   ]  # delete duplicates, and filtar
        #     ns_def = ''
        #     for n in ns:
        #         ns_str = 'xmlns:{}='.format(n)
        #         this_ns = re.findall( ns_str, xml )  # if found, no add ns definition again
        #         if not this_ns:
        #             ns_def += 'xmlns:{}="{}" '.format(n,n)
        #     if ns_def:
        #         xml = re.sub('>', ' ' + ns_def + '>', xml, 1)  #replaces first ocurrence
        #         with open(project_file, 'w' ,encoding='utf8') as f:
        #             f.write(xml)
        
        # Creates a copy of original project because of the LOGO section usually has not defined namespaces
        # and etree launches an error
        regex_logos = '(<logos>[\s\S]+<\/logos>)'
        with open(project_file, 'r' ,encoding='utf8') as f:
            xml = f.read()
            logo = re.findall( regex_logos, xml )  # namesapaces
        if logo:
            self.original_logo_section = logo
            xml = re.sub(regex_logos, '<logos />', xml, 1)  #replaces first ocurrence
        else:
            self.original_logo_section = ''
        tmpf = tempfile.NamedTemporaryFile(mode='w', encoding='utf8', delete=False)
        tmpf.write(xml)
        tmpf.close()
        log.info ("Generate temp file {}".format(tmpf.name))

        try:
            # starting...
            self._qet_tree = etree.parse(tmpf.name)
            self.qet_project_file = project_file
            self.qet_project = self._qet_tree.getroot()

            # determine xref format to use or default
            self.folio_reference_type = self.qet_project.find('.//newdiagrams'). \
                    find('report').attrib['label']

            # XML version
            self.xml_version = self.qet_project.attrib['version']

            # pageOffset for folio numbers.
            # From version 0.8 of Qelectrotech, this attribute doesn't exist.
            # folioSheetQuantity ==> offset table of contents
            if 'folioSheetQuantity' in self.qet_project.attrib:
                self.pageOffset = int (self.qet_project.attrib['folioSheetQuantity'])
            else:
                log.info ("Attribute 'folioSheetQuantity' doesn't exist. Assuming 0")
                self.pageOffset = 0


            # general project info
            self._totalPages = len (self.qet_project.findall('.//diagram')) + \
                    self.pageOffset

            # elements type of terminal (use set for O(1) lookup)
            self._terminalElements = self._getListOfElementsByType( 'terminal' )
            self._terminalElementsSet = set(self._terminalElements)

            # finds all terminals. A list of dicts
            self._set_used_terminals()
        finally:
            # Always clean up temp file
            os.unlink(tmpf.name)
            log.info ("Deleted temp file {}".format(tmpf.name))



    def _getListOfElementsByType(self, element_type):
        """Return a list of component in library(collection) that
        have 'link_type' as element_type parameter.

        @return [] list with el names of elements that
                   are terminal as 'like_type'"""

        ret = []  # return list

        collection = self.qet_project.find('collection')
        if collection is None:
            return []

        for element in collection.iter('element'):
            definition = element[0]
            if 'link_type' in definition.attrib:
                if definition.attrib['link_type'] == element_type:
                    ret.append(element.attrib['name'])

        return list(set(ret))  # remove duplicates


    def _getElementName (self, element):
        """Returns the name of a terminal element.
        The name comes from 'dynamic_text' section.
        If not exists, the name is specified in elementInformation/label or 
        elementInformation/formula. 
        return: name of terminal"""

        dt = element.find('dynamic_texts')
        if dt:
            for d in dt.findall('dynamic_elmt_text'):
                if d.attrib['text_from'] == 'ElementInfo':
                    return d.findtext('text')

        ## old version of QET XML diagram doesn't have dynamic text.
        label = formula = ''
        elinfos = element.find('elementInformations')
        if elinfos:
            for t in elinfos.findall('elementInformation'):
                if t.attrib['name'] == 'label':
                    label = t.text
                if t.attrib['name'] == 'formula':
                    formula = t.text
        
        if label == None:  # attrib returns None if empty.
            label = ''
        if formula == None:
            formula = ''

        return [label, formula][label == '']


    def _getElementMetadata (self, element):
        """Returns the metadata of the terminal element.
        All the info is Function field under 'elementInformation'
        return: {} with the content of every key"""

        meta = ''
        ret = {}
    
        ## Get meta string
        for t in element.find('elementInformations').findall('elementInformation'):
            if t.attrib['name'] == 'function':
                meta = t.text
                break
        
        ## Getting data (using pre-compiled regex for performance)
        if meta is None:
            meta = ''

        foo = QETProject._RE_POS.search(meta)
        ret['terminal_pos'] = foo.group(1) if foo else ''

        foo = QETProject._RE_TYPE.search(meta)
        tp = foo.group(1) if foo else ''
        ret['terminal_type'] = tp if tp != '' else 'STANDARD'
    
        foo = QETProject._RE_HOSE.search(meta)
        ret['hose'] = foo.group(1) if foo else ''

        foo = QETProject._RE_CONDUCTOR.search(meta)
        ret['conductor'] = foo.group(1) if foo else ''
                
        foo = QETProject._RE_BRIDGE1.search(meta)
        if not foo:
             foo = QETProject._RE_BRIDGE_OLD.search(meta)
             if not foo: foo = QETProject._RE_BRIDGE_EMPTY.search(meta)
        ret['bridge1'] = foo.group(1) if foo else ''

        foo = QETProject._RE_BRIDGE2.search(meta)
        ret['bridge2'] = foo.group(1) if foo else ''

        foo = QETProject._RE_BRIDGE3.search(meta)
        ret['bridge3'] = foo.group(1) if foo else ''

        foo = QETProject._RE_BRIDGE4.search(meta)
        ret['bridge4'] = foo.group(1) if foo else ''

        foo = QETProject._RE_RESERVE.search(meta)
        tp = foo.group(1) if foo else ''
        ret['num_reserve'] = tp if tp != '' else 0

        foo = QETProject._RE_RESERVE_POS.search(meta)
        ret['reserve_positions'] = foo.group(1) if foo else ''

        foo = QETProject._RE_SIZE.search(meta)
        tp = foo.group(1) if foo else ''
        ret['size'] = tp if tp != '' else QETProject.QET_BLOCK_TERMINAL_SIZE

        foo = QETProject._RE_ETAGE.search(meta)
        ret['etage'] = foo.group(1) if foo else '1'

        foo = QETProject._RE_COLOR.search(meta)
        ret['terminal_color'] = foo.group(1) if foo else ''

        return ret


    def _isValidTerminal (self, element, element_name=None):
        """ An element is valid if type is 'terminal' and label is like 'X1:1'
        @param element:  element  (XML etree object)
        @param element_name: pre-fetched name to avoid double call
        @return: True / False"""
        
        name = element_name if element_name is not None else self._getElementName(element).strip()
        if QETProject._RE_VALID_TERMINAL.search(name):
            if 'type' in element.attrib:  # elements must have a 'type'
                el_type = element.attrib['type']
                for el in self._terminalElementsSet:  # O(1) set lookup per element
                    if el_type.endswith(el):
                        return True
        
        return False



    @staticmethod
    def _buildConductorIndex(diagram):
        """Pre-build conductor lookup dicts for a diagram.
        Returns (by_element_uuid, by_terminal_id) dicts mapping to cable 'num'.
        Called once per diagram instead of once per terminal."""
        by_uuid = {}
        by_terminal_id = {}
        conductors_node = diagram.find('conductors')
        if conductors_node is None:
            return by_uuid, by_terminal_id
        for cable in conductors_node.findall('conductor'):
            cable_num = cable.attrib.get('num', '')
            for attr_name, attr_val in cable.attrib.items():
                if attr_name.startswith('element'):
                    if attr_val not in by_uuid:
                        by_uuid[attr_val] = cable_num
                elif attr_name.startswith('terminal'):
                    if attr_val not in by_terminal_id:
                        by_terminal_id[attr_val] = cable_num
        return by_uuid, by_terminal_id

    def _getCableNum(self, diagram, terminalId, terminalUUID, conductor_index=None):
        """Return the cable number connected at 'terminalId' in the page 'diagram'

        New in v1.2.6: To search for the cable num:
          - Start searching the Terminal's UUID in the 'element1' and 'element2' of conductors.
          - if not found, search for terminalId in the 'terminal1' and 'terminal2' of conductors

        @param terminalUUID: the UUID of the Terminal Element
        @param diagram: diagram(page) XML etree object
        @param terminalId: text with the terminal Id of the Terminal Element
        @param conductor_index: pre-built (by_uuid, by_terminal_id) tuple for O(1) lookup
        @return: string whith cable  number"""

        log.debug ("Getting cable number connected to terminal {} at page {} of element {}".format ( \
            terminalId, diagram.attrib['title'], terminalUUID))

        # Use pre-built index for O(1) lookup instead of O(n) scan
        if conductor_index:
            by_uuid, by_terminal_id = conductor_index
            result = by_uuid.get(terminalUUID, '')
            if result:
                return result
            return by_terminal_id.get(terminalId, '')

        # Fallback: original O(n) scan if no index provided
        for cable in diagram.find('conductors').findall('conductor'):
            for cable_element in [x for x in cable.attrib if x[:7] == 'element' ]:
                if cable.attrib[cable_element] == terminalUUID:
                    return cable.attrib['num']
        for cable in diagram.find('conductors').findall('conductor'):
            for cable_terminal in \
                    [x for x in cable.attrib if x[:8] == 'terminal' ]:
                if cable.attrib[cable_terminal] == terminalId:
                    return cable.attrib['num']
        return ''


    
    def _getXRef(self, diagram, element, offset_x = 0, offset_y = 0):
        """Return a string with the xreference.

        The element is specified by 'element' at page 'diagam'.
        The page number incremented in one if there are a "index" page

        @param diagram: diagram(page) XML etree object
        @param element: element XML etree object
        @param offset_x: correction of the coord x.
               Useful for Xref for the terminal of an element
        @param offset_y: correction of the coord y
        @return: string like "p-rc" (page - rowLetter colNumber)"""
        ret = self.folio_reference_type

        # get coord
        element_x = int(float(element.attrib['x'])) + int(float(offset_x))
        element_y = int(float(element.attrib['y'])) + int(float(offset_y))
        row, col = self._getXRefByCoord (diagram, element_x, element_y)
        diagram_page = str(int(diagram.attrib['order']) + self.pageOffset)

        # Change tags to real value
        if '%f' in ret:
            ret = ret.replace('%f', diagram_page)
        if '%F' in ret:
            # %F could include extra tags
            folio_label = diagram.attrib['folio']
            if '%id' in folio_label:
                folio_label = folio_label.replace('%id', diagram_page)
            if '%total' in folio_label:
                folio_label = folio_label.replace('%total', str(self._totalPages))
            if '%autonum' in folio_label:
                folio_label = folio_label.replace('%autonum', diagram_page)
            ret = ret.replace('%F', folio_label)
        if '%M' in ret:
            ret = ret.replace('%M', self._getDiagramAttribute(diagram,'machine'))
        if '%LM' in ret:
            ret = ret.replace('%LM', self._getDiagramAttribute(diagram, 'locmach'))
        if '%l' in ret:
            ret = ret.replace('%l', row)
        if '%c' in ret:
            ret = ret.replace('%c', col)

        return ret


    def _getDiagramAttribute(self, diagram, sAttrib):
        """Returns the value of an attribut of the diagram.
        If does not exist returns ''

        @param diagram: diagram(page) XML etree object
        @param sAttrib: attribute name
         """
        if sAttrib in diagram:
            return diagram.attrib[sAttrib]
        else:
            return ''


    def _getXRefByCoord(self, diagram, x, y):
        """Return a string with the xreference for the coordinates at page 'diagam'
        The page number incremented in one if there are a "index" page

        @param diagram: diagram(page) XML etree object
        @param x,y: coordinates
        @return: string like "p-rc" (page - rowLetter colNumber)"""

        # get requiered data
        cols = int(diagram.attrib['cols'])
        col_size = int(diagram.attrib['colsize'])
        rows = int(diagram.attrib['rows'])
        row_size = int(diagram.attrib['rowsize'])
        element_x = int(x)
        element_y = int(y)
        rows_letters = [chr(x + 65) for x in range(rows)]

        log.debug( 'Cols: {}\tCol size: {}\tRow size: {}\tX position: {}\tY Position: {}'. \
                format (cols, col_size, row_size, element_x, element_y))

        row_letter = rows_letters[ int(
                (element_y - QETProject.QET_COL_ROW_SIZE) / row_size) - 1 + 1]
                # +1: cal calc. -1 index of lists start 0.
        column = str(int((element_x - QETProject.QET_COL_ROW_SIZE) / col_size) + 1)
        return (row_letter, column)



    def _get_used_terminals(self):
        return self.__used_terminals



    def _set_used_terminals(self):
        """Creates a list of all terminal elements used in the qet project.
        List where every element is a dict. See class info.
        Sorted by Block_name and terminal_pos
        """

        ret = []

        # first search for elements of type 'terminal' and its conductors.
        for diagram in self.qet_project.findall('diagram'):  # all diagrams
            # Pre-build conductor index ONCE per diagram (O(conductors) instead of O(terminals × conductors))
            conductor_index = QETProject._buildConductorIndex(diagram)
            for element in diagram.findall('.//element'):  # all elements in diagram
                el = {}

                # Get name once and pass it to avoid double call
                elementName = self._getElementName(element).strip()
                if self._isValidTerminal(element, element_name=elementName):

                    terminalName = elementName
                    meta_data = self._getElementMetadata (element)
                    
                    terminals = element.find('terminals').findall( 'terminal' )
                    terminalId = terminals[0].attrib['id']
                    cableNum = self._getCableNum(diagram, terminalId, element.attrib['uuid'], conductor_index)
                    try:
                        terminalId2 = terminals[1].attrib['id']
                        cableNum2 = self._getCableNum(diagram, terminalId2, element.attrib['uuid'], conductor_index)
                        if cableNum == '': cableNum = cableNum2
                    except (IndexError, KeyError):
                        pass
                    el['uuid'] = element.attrib['uuid']
                    el['block_name'] = terminalName.split(':')[0]
                    el['terminal_name'] = terminalName.split(':')[1]
                    el['terminal_xref'] = self._getXRef(diagram, element)
                    el['cable'] = cableNum             
                    if meta_data['terminal_pos']=='':  #  convert to integer for more initial intelligent sorting
                        try:
                            el['terminal_pos'] = int(el['terminal_name'])
                        except (ValueError, TypeError):
                            el['terminal_pos'] = 1
                    else:
                        el['terminal_pos'] = int(meta_data['terminal_pos'])
                    el['terminal_type'] = meta_data['terminal_type']
                    el['hose'] = meta_data['hose']
                    el['conductor'] = meta_data['conductor']
                    el['bridge1'] = meta_data['bridge1']
                    el['bridge2'] = meta_data['bridge2']
                    el['bridge3'] = meta_data['bridge3']
                    el['bridge4'] = meta_data['bridge4']
                    el['etage'] = meta_data.get('etage', '1')
                    # Auto etage from ID suffix .1, .2, .3, .4
                    tn = el.get('terminal_name', '')
                    if tn.endswith('.1'): el['etage'] = '1'
                    elif tn.endswith('.2'): el['etage'] = '2'
                    elif tn.endswith('.3'): el['etage'] = '3'
                    elif tn.endswith('.4'): el['etage'] = '4'
                    
                    el['terminal_color'] = meta_data.get('terminal_color', '')
                    el['num_reserve'] = meta_data['num_reserve']
                    el['reserve_positions'] = meta_data['reserve_positions']
                    el['size'] = meta_data['size']
                if el: ret.append(el)
        
        # SQL = ORDER BY block_name DESC, terminal_pos ASC
        ret.sort(key=operator.itemgetter('terminal_pos'))
        ret.sort(key=operator.itemgetter('block_name'), reverse=True)

        #Renum. position field from 1 by one-to-one
        memo_tb = ''; i = 1
        for t in ret:
            if t['block_name'] != memo_tb:
                i=1
            t['terminal_pos'] = i
            memo_tb = t['block_name']
            i +=1

        self.__used_terminals = ret


    def get_max_tb_length(self):
        """
        Returns the lenth of terminal-block with more terminals
        """
        t = [ x['block_name'] for x in self.__used_terminals]
        ocurrences = [t.count(i) for i in t]
        return max(ocurrences)

    def update_terminals(self, data):
        """Changes the config of every terminal in the diagra. The changes made 
        in the plugin will be save in the 'elementInformation' of every
        terminal."""
        # Pre-index data by UUID for O(1) lookup instead of O(n) linear scan
        data_by_uuid = {d['uuid']: d for d in data}
        
        for diagram in self.qet_project.findall('diagram'):  # all diagrams(pages)
            for element in diagram.iter('element'):  # all elements in diagram
                dt_item = data_by_uuid.get(element.attrib.get('uuid'))
                if dt_item:
                    found = False
                    value = r'%p{}%t{}%h{}%n{}%b1{}%b2{}%b3{}%b4{}%v{}%c{}%'.format(
                            dt_item['terminal_pos'], \
                            dt_item['terminal_type'], \
                            dt_item['hose'], \
                            dt_item['conductor'], \
                            dt_item.get('bridge1', ''), \
                            dt_item.get('bridge2', ''), \
                            dt_item.get('bridge3', ''), \
                            dt_item.get('bridge4', ''), \
                            dt_item.get('etage', '1'), \
                            dt_item.get('terminal_color', '') )
                    for elinfo in element.iter('elementInformation'):
                        if elinfo.attrib['name'] == 'function':
                            elinfo.text = value
                            found = True
                    if not found:  # crete a new child
                        father = element.find('elementInformations')
                        new = etree.SubElement(father, \
                                'elementInformation',
                                name="function", \
                                show="0")
                        new.text = value


    def save_tb(self, filename):
        # Write to in-memory buffer first, then do logo replacement in one pass
        if self.original_logo_section:
            buf = BytesIO()
            self._qet_tree.write(buf, encoding='utf-8', xml_declaration=True)
            xml = buf.getvalue().decode('utf-8')
            # Replace temporal empty logo with the original in memory
            xml = re.sub(r'<logos\s*/>', self.original_logo_section[0], xml, 1)
            with open(filename, 'w', encoding='utf8') as f:
                f.write(xml)
        else:
            self._qet_tree.write(filename, encoding='utf-8', xml_declaration=True)



    def insert_tb(self, name, tb_node):
        """Inserts a xml node representing a terminal block,
        removing first the old element if exists
        @param name: name of the segment
        @param tb_node: xml tree of the terminal block.
        @return: none"""
        
        element_name_to_delete = 'TB_' + name + '.elmt'
        collection = self.qet_project.find('collection')
        if collection is None:
            collection = etree.SubElement(self.qet_project, 'collection')
        
        # Try to find an existing category for imports
        father = None
        for cat in collection.findall('category'):
            cat_name = cat.get('name', '').lower()
            if cat_name in ['import', 'importé', 'imported']:
                father = cat
                break
        
        if father is None:
            # If no designated import category, try the first category available
            father = collection.find('category')
            
        if father is None:
            # Still none? Create the 'import' category
            father = etree.SubElement(collection, 'category', name="import")
            names = etree.SubElement(father, 'names')
            etree.SubElement(names, 'name', lang='fr').text = 'Importé'
            etree.SubElement(names, 'name', lang='en').text = 'Imported'
        
        # remove the old element
        for element in list(father.findall('element')):
            if element.attrib.get('name') == element_name_to_delete:
                father.remove(element)

        # adding the element
        father.insert(0, tb_node)
    

    def _get_tb_names(self):
        """
        Get a list of the terminal-block names sorted
        """
        sort_key = [x['block_name'] for x in self.__used_terminals]
        return list(OrderedDict.fromkeys(sort_key)) 
  
    
    # properties
    terminals = property(_get_used_terminals)
    tb_names = property(_get_tb_names)
