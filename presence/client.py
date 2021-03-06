import socket, threading, cgi, logging, re, os

import xml.etree.ElementTree

from parser import Parser
from sock   import ClientSocket
from types  import *

class ClientThread(threading.Thread):
    @staticmethod
    def make_command(func=None, helptext='', greedy=False):
        if not func:
            func = lambda client, message: True
        d = { 'func': func, 'help': helptext, 'greedy': greedy }
        return type('Command', (object,), d)

    def __init__(self, sock, address, logger=logging.getLogger(), args={}):
        super(ClientThread,self).__init__()
        self.logger = logger
        self.cs     = ClientSocket(sock,address,logger=self.logger)
        self.args   = dict(args)
        
        self.identity    = self.args.get('name',  socket.gethostname()+'.local')
        self.other       = self.args.get('other', None)
        self.downloaddir = self.args.get('downloaddir', None)
        self.commands    = self.args.get('commands', {})
        self.commands.update(self._default_commands())
        
        self.parser  = Parser(logger=self.logger)
        self.stopped = threading.Event()
        self.cleanup_func   = None
        self.broadcast_func = None

        self.stream_is_open = False
        
    # public interface
    def send_ascii(self,ascii):
        asciitext = cgi.escape(ascii.strip()).encode('ascii', 'xmlcharrefreplace')
        htmltext = re.sub(r'\n', r'<br/>', asciitext)
        message = Message(html=htmltext, ascii=asciitext, identity=self.identity, other=self.other)
        self.send_message(message)

    def send_html(self,html):
        message = Message(html=html, ascii=None, identity=self.identity, other=self.other)
        self.send_message(message)

    def is_empty_message(self,message):
        ascii = message.ascii.strip()
        html  = ''.join(xml.etree.ElementTree.fromstring('<p>%s</p>' % message.html).itertext()).strip()
        if len(ascii) or len(html):
            return False
        return True

    def send_message(self,message):
        if message.identity != self.identity:
            self.logger.warning('Message identities do not match: message "%s", client "%s"' % (message.identity,self.identity))
        if message.other != self.other:
            self.logger.warning('Message recipients do not match: message "%s", client "%s"' % (message.other,self.other))
        if not message.ascii:
            message.ascii = re.sub(r'<br/?>', '\n', message.html)
            message.ascii = ''.join(xml.etree.ElementTree.fromstring('<p>%s</p>' % message.ascii).itertext())
        message.ascii = message.ascii.strip()
        if len(message.ascii):
            message.ascii = cgi.escape(message.ascii).encode('ascii', 'xmlcharrefreplace')
            message.ascii = '\n' + message.ascii
        msg = [
            "<message",
            "from='%s'" % self.identity,
            "to='%s'"   % self.other,
            "type='chat'><body>%s</body><html xmlns='http://www.w3.org/1999/xhtml'><body>%s</body></html></message>" % (message.ascii,message.html)
            ]
        line = ' '.join(msg)
        self.cs.send_line( line)

    def echo(self, message):
        identity = message.identity
        other    = message.other
        message.identity = other
        message.other    = identity
        self.send_message(message)
        
    def help(self):
        self.send_html('<br/>'.join([
                    self._command_text()
                    ]))

    def vars(self):
        self.send_html('<br/>'.join([
                    self._var_text()
                    ]))

    def hello(self):
        self.send_html('Welcome at <b>%s</b><br/>%s' % (self.identity,self._command_text()))

    def ls_downloaddir(self):
        d = self.downloaddir
        if not d:
            self.send_html('Downloads disabled')
            return
        if not os.path.exists(d):
            self.send_html('Download directory does not exist')
            return
        fill = ' '*4
        msg = 'Contents of <b>%s</b><br/>' % d 
        entries = os.listdir(d)
        for entry in entries:
            stat = os.stat(os.path.join(d,entry))
            printname = entry
            if os.path.isdir(entry):
                printname = '[%s]' % printname
            elif os.path.isfile(entry):
                printname = '%s' % printname
            msg += fill + ("%s\n" % printname)
        if not len(entries):
            msg += 'No files found'

        self.send_html(msg)


    # internal functions
    def _default_commands(self):
        return {
            'echo': self.make_command(
                func=staticmethod(lambda client, message: client.echo(message)),
                helptext="echo text",
                greedy=True),
            'help': self.make_command(
                func=staticmethod(lambda client, message: client.help()),
                helptext="print this help"),
            'hello': self.make_command(
                func=staticmethod(lambda client, message: client.hello()),
                helptext="print a hello message"),
            'vars': self.make_command(
                func=staticmethod(lambda client, message: client.vars()),
                helptext="print variables"),
            'ls': self.make_command(
                func=staticmethod(lambda client, message: client.ls_downloaddir()),
                helptext="list contents of download directory"),
            }
    
    def _command_text(self):
        ret = '<b>commands:</b><br/>'
        for k, v in sorted(self.commands.items()):
            ret += '  %s - %s<br/>'% (k, v.help)
        return ret

    def _var_text(self):
        ret = '<b>variables:</b><br/>'
        ret += '  identity - %s<br/>'   % str(self.identity)
        ret += '  other - %s<br/>'      % str(self.other)
        ret += '  downloaddir - %s<br/>'% str(self.downloaddir)
        return ret
        
    def _send_si_result(self, iq_id):
        line = ''.join([
                "<iq type='result' from='%s' to='%s' id='%s'>" %(self.identity,self.other,iq_id),
                "<si xmlns='http://jabber.org/protocol/si'>",
                "<feature xmlns='%s'>" % Protocol.FEATURE_NEG,
                "<x xmlns='jabber:x:data' type='submit'>",
                "<field var='stream-method'>",
                "<value>%s</value>" % Protocol.BYTESTREAMS,
                "</field>",
                "</x>",
                    "</feature>",
                "</si>",
                "</iq>",
                ])
        self.cs.send_line(line)

    # handlers for parser results
    def handle_message(self, message):
        if self.is_empty_message(message):
            return
        
        # check for command
        words = message.ascii.strip().split()
        command = None
        if len(words):
            if words[0].strip() in self.commands.keys():
                command = words[0].strip()
        if command:        
            if not self.commands[command].greedy and \
                    len(words) > 1:
                return
            self.commands[command].func(self,message)
        else:
            if self.broadcast_func:
                self.broadcast_func(self,message)

    def handle_transfer(self, transfer):
        if not self.downloaddir:
            self.logger.info("Rejecting file transfer, download directory not set")
            transfer.reject(self.cs)
            return
        status = transfer.retrieve(self.cs, self.downloaddir)

    def handle_stream_open(self,stream):
        if self.stream_is_open:
            self.logger.error('Stream already open')
            return
        if not self.identity:
            self.identity == stream.identity
        elif self.identity != stream.identity:
            self.logger.error('Identity different from received one: self "%s", remote "%s"' % (self.identity, stream.identity))

        if not self.other:
            self.other = stream.other
        elif self.other != stream.other:
            self.logger.error('Other different from received one: self "%s", remote "%s"' %(self.other,stream.other))
             
        line =' '.join([
                "<stream:stream xmlns='jabber:client'",
                "xmlns:stream='http://etherx.jabber.org/streams'",
                "from='%s'" % self.identity,
                "to='%s'"   % self.other,
                "version='1.0'>",
                ])
        
        self.cs.send_line(line)
        self.stream_is_open = True

    def handle_feature_neg(self, fn):
        for v in fn.option_values:
            if v == Protocol.BYTESTREAMS:
                self._send_si_result(fn.iq_id)
                break
            else:
                self.logger.warning('Unhandled option value "%s"' % v)

    def close_stream(self):
        if not self.stream_is_open:
            self.logger.error("Stream is not open, not closing")
            return
        self.cs.send_line("</stream:stream>")
        self.stream_is_open = False

    # Functions related to threading/event loop
    def process_result(self, result):
        if result.type   == ResultType.STREAM_OPEN:
            self.logger.debug("Handling stream open")
            self.handle_stream_open(result.data)
        elif result.type == ResultType.STREAM_CLOSE:
            self.logger.debug("Handling stream close")
            self.close_stream()
        elif result.type   == ResultType.MESSAGE:
            self.logger.debug("Handling message")
            self.handle_message(result.data)
        elif result.type == ResultType.FILE_TRANSFER:
            self.logger.debug("Handling transfer")
            self.handle_transfer(result.data)
        elif result.type == ResultType.FEATURE_NEG:
            self.logger.debug("Handling feature negotiation")
            self.handle_feature_neg(result.data)
        else:
            self.logger.warning("Unknown result type")

    def process(self):
        result = self.parser.next()
        while result:
            self.process_result(result)
            result = self.parser.next()
            
    def receive(self):
        chunk = ''
        try:
            while self.parser.process(chunk):
                chunk = self.cs.recv()
        except socket.timeout, e:
            #self.logger.debug('socket.timeout %s' % str(e))
            return False
        except socket.error, e:
            self.logger.debug('socket.error %s' % str(e))
            return False
        return True

    def run(self):
        try:
            while not self.stopped.is_set():
                self.receive()
                self.process()
        except RuntimeError:
            pass
        if self.stream_is_open:
            self.close_stream()
        self.cs.close()
        if self.cleanup_func:
            self.cleanup_func(self)

    def stop(self):
        self.stopped.set()

