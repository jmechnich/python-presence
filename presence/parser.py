import html
import logging

import xml.parsers.expat

from .types import *

# xml parser
class Parser(object):
    def __init__(self,logger=logging.getLogger()):
        super(Parser,self).__init__()
        self.logger = logger
        
        # create parser and set handlers
        self.parser = xml.parsers.expat.ParserCreate()
        self.parser.StartElementHandler  = self._start_element
        self.parser.EndElementHandler    = self._end_element
        self.parser.CharacterDataHandler = self._char_data
       
        # state variables
        flagsstr = ['BODY','HTML', 'HTMLBODY', 'OPTION', 'VALUE']
        flags = { f: 1 << i for i,f in enumerate(flagsstr) }
        self.__dict__.update(flags)
        self.flags = 0
        
        self.modestr = [ 'IDLE', 'MESSAGE', 'FILE_OOB', 'FILE_SOCKS5', 'FEATURE_NEG' ]
        modes   = { m: i for i,m in enumerate(self.modestr) }
        self.__dict__.update(modes)
        self.mode  = self.IDLE
        
        # xml start and end elements to ignore
        self.ignore = ['font', 'composing', 'id', 'si', 'field']
        
        self.results = []
        self.current = None
        
    # public interface
    def process(self,text):
        if len(text) == 0:
            return True
        self.parser.Parse(text,False)
        return False
    
    def next(self):
        if not len(self.results):
            return None
        return self.results.pop(0)

    # internal helper functions
    def _set_mode(self,mode):
        self.logger.debug('Setting mode to "%s"' % self.modestr[mode])
        self.mode = mode
        
    def _check_mode(self,mode):
        if self.mode != mode:
            self.logger.error("Wrong mode")
        
    def _add_html_start_element(self, name, attrs):
        self.current.html += '<%s' % name
        for a in attrs.items():
            self.current.html += ' %s="%s"' % a
        self.current.html += '>'
    
    def _add_result(self,result):
        self.logger.debug("Adding parser result %s" % ResultTypeStr[result.type])
        self.results.append(result)
        
    # expat parser callback functions
    def _start_element(self, name, attrs):
        ignore = []
        # check first if we are inside a HTML body tag
        if self.flags & self.HTMLBODY:
            self._check_mode(self.MESSAGE)
            self._add_html_start_element(name,attrs)
        elif name in (ignore + self.ignore):
            return
        elif name == 'stream:stream':
            stream = Stream(identity=attrs['to'],other=attrs['from'])
            result = Result(type=ResultType.STREAM_OPEN,data=stream)
            self._add_result(result)
        elif name == 'message':
            self._check_mode(self.IDLE)
            self._set_mode(self.MESSAGE)
            self.current = Message(identity=attrs['to'],other=attrs['from'])
        elif name == 'iq':
            self.iq = IQ(identity=attrs['to'],other=attrs['from'],
                         id=attrs['id'],type=attrs['type'])
        elif name == 'x':
            xmlns = attrs['xmlns']
            if xmlns == 'jabber:x:oob':
                self._check_mode(self.MESSAGE)
                self._set_mode(self.FILE_OOB)
                self.current = Transfer_OOB(
                    self,identity=self.current.identity,other=self.current.identity)
        elif name == 'url':
            if self.mode == self.FILE_OOB and attrs['type'] == 'file':
                self.current.filename = ""
                self.current.filesize = attrs['size']
        elif name == 'html':
            self.flags |= self.HTML
        elif name == 'body':
            if self.flags & self.HTML:
                self.flags |= self.HTMLBODY
            else:
                self.flags |= self.BODY
        elif name == 'file':
            xmlns = attrs['xmlns']
            if xmlns == Protocol.SI_TRANSFER:
                self.filename = attrs['name']
                self.filesize = attrs['size']
        elif name == 'feature':
            xmlns = attrs['xmlns']
            if xmlns == Protocol.FEATURE_NEG:
                self._set_mode(self.FEATURE_NEG)
                self.current = FeatureNeg(iq_id=self.iq.id)
        elif name == 'option':
            self.flags |= self.OPTION
        elif name == 'value':
            self.flags |= self.VALUE
        elif name == 'query':
            xmlns = attrs['xmlns']
            mode = attrs['mode']
            if xmlns == Protocol.BYTESTREAMS:
                self._check_mode(self.IDLE)
                self._set_mode(self.FILE_SOCKS5)
                self.current = Transfer_SOCKS5(
                    self, identity=self.iq.identity, other=self.iq.other,
                    sid=attrs['sid'], iq_id=self.iq.id, streamhosts=[])
                if self.filename:
                    self.current.filename = self.filename
                    self.filename = None
                if self.filesize:
                    self.current.filesize = self.filesize
                    self.filesize = None
        elif name == 'streamhost':
            jid = attrs['jid']
            host = attrs['host']
            port = attrs['port']
            self.current.streamhosts.append((host, port, jid))
        else:
            self.logger.debug('Start element: %s %s' % (name, str(attrs)))
            
    def _end_element(self, name):
        ignore = ['url', 'streamhost', 'file']
        if name == 'html':
            self.flags &= ~self.HTML
        elif name == 'body':
            if self.flags  &  self.HTML:
                self.flags &= ~self.HTMLBODY
            else:
                self.flags &= ~self.BODY
        elif self.flags & self.HTMLBODY:
            self._check_mode(self.MESSAGE)
            self.current.html += '</%s>' % name
        elif name in (ignore + self.ignore):
            pass
        elif name == 'stream:stream':
            result = Result(type=ResultType.STREAM_CLOSE,data=None)
            self._add_result(result)
        elif name == 'message':
            if self.mode == self.MESSAGE:
                result = Result(type=ResultType.MESSAGE,data=self.current)
                self._add_result(result)
                self.current = None
                self._set_mode(self.IDLE)
        elif name == 'html':
            self.flags &= ~self.HTML
        elif name == 'body':
            if self.flags & self.HTML:
                self.flags &= ~self.HTMLBODY
            else:
                self.flags &= ~self.BODY
        elif name == 'x':
            if self.mode == self.FILE_OOB:
                result = Result(type=ResultType.FILE_TRANSFER,data=self.current)
                self._add_result(result)
                self.current = None
                self._set_mode(self.IDLE)
        elif name == 'iq':
            self.iq = None
        elif name == 'feature':
            self._check_mode(self.FEATURE_NEG)
            result = Result(type=ResultType.FEATURE_NEG,data=self.current)
            self._add_result(result)
            self.current = None
            self._set_mode(self.IDLE)
        elif name == 'option':
            self.flags &= ~self.OPTION
        elif name == 'value':
            self.flags &= ~self.VALUE
        elif name == 'query':
            if self.mode == self.FILE_SOCKS5:
                result = Result(type=ResultType.FILE_TRANSFER,data=self.current)
                self._add_result(result)
                self.current = None
                self._set_mode(self.IDLE)
        else:
            self.logger.debug('End element: %s' % name)
        
    def _char_data(self, data):
        if self.mode == self.MESSAGE:
            if self.flags & (self.HTMLBODY):
                self.current.html += html.escape(data, quote=False)
            else:
                self.current.ascii += data
        elif self.mode == self.FEATURE_NEG:
            if self.flags & self.OPTION and self.flags & self.VALUE:
                self.current.option_values.append(data)
        elif self.mode == self.FILE_OOB:
            self.current.filename += data
        else:
            self.logger.debug('Data: %s' % data)
