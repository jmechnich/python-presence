import html
import logging
import re
import os
import socket
import threading

import xml.etree.ElementTree

from .parser import Parser
from .sock   import ClientSocket
from .types  import *

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
        asciitext = html.escape(ascii.strip())
        htmltext = re.sub(r'\n', r'<br/>', asciitext)
        message = Message(
            html=htmltext,
            ascii=asciitext,
            identity=self.identity,
            other=self.other
        )
        self.send_message(message)

    def send_html(self,html):
        message = Message(
            html=html,
            ascii=None,
            identity=self.identity,
            other=self.other
        )
        self.send_message(message)

    def is_empty_message(self,message):
        ascii = message.ascii.strip()
        html  = ''.join(
            xml.etree.ElementTree.fromstring(
                f'<p>{message.html}</p>'
            ).itertext()
        ).strip()
        if len(ascii) or len(html):
            return False
        return True

    def send_message(self,message):
        if message.identity != self.identity:
            self.logger.warning(
                f'Message identities do not match:'
                f' message "{message.identity}", client "{self.identity}"'
            )
        if message.other != self.other:
            self.logger.warning(
                f'Message recipients do not match:'
                f' message "{message.other}", client "{self.other}"'
            )
        if not message.ascii:
            message.ascii = re.sub(r'<br/?>', '\n', message.html)
            message.ascii = ''.join(
                xml.etree.ElementTree.fromstring(
                    f'<p>{message.ascii}</p>'
                ).itertext()
            ).strip()
        if len(message.ascii):
            message.ascii = html.escape(message.ascii)
            message.ascii = '\n' + message.ascii
        self.cs.send_line(
            f"<message from='{self.identity}' to='{self.other}' type='chat'>"
            f"<body>{message.ascii}</body>"
            f"<html xmlns='http://www.w3.org/1999/xhtml'>"
            f"<body>{message.html}</body>"
            f"</html></message>"
        )

    def echo(self, message):
        identity = message.identity
        other    = message.other
        message.identity = other
        message.other    = identity
        self.send_message(message)
        
    def help(self):
        self.send_html('<br/>'.join([self._command_text()]))

    def vars(self):
        self.send_html('<br/>'.join([self._var_text()]))

    def hello(self):
        self.send_html(
            f'Welcome at <b>{self.identity}</b><br/>{self._command_text()}'
        )

    def ls_downloaddir(self):
        d = self.downloaddir
        if not d:
            self.send_html('Downloads disabled')
            return
        if not os.path.exists(d):
            self.send_html('Download directory does not exist')
            return
        fill = ' '*4
        msg = f'Contents of <b>{d}</b><br/>'
        entries = os.listdir(d)
        for entry in entries:
            stat = os.stat(os.path.join(d,entry))
            printname = entry
            if os.path.isdir(entry):
                printname = f'[{printname}]'
            elif os.path.isfile(entry):
                printname = str(printname)
            msg += fill + (f"{printname}\n")
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
                func=staticmethod(lambda client, message:
                                  client.ls_downloaddir()),
                helptext="list contents of download directory"),
            }
    
    def _command_text(self):
        ret = '<b>commands:</b><br/>'
        for k, v in sorted(self.commands.items()):
            ret += f'  {k} - {v.help}<br/>'
        return ret

    def _var_text(self):
        return ('<b>variables:</b><br/>'
                f'  identity - {self.identity}<br/>'
                f'  other - {self.other}<br/>'
                f'  downloaddir - {self.downloaddir}<br/>')
        return ret
        
    def _send_si_result(self, iq_id):
        self.cs.send_line(
            f"<iq type='result' from='{self.identity}' to='{self.other}'"
            f" id='{ip_id}'>"
            f"<si xmlns='http://jabber.org/protocol/si'>"
            f"<feature xmlns='{Protocol.FEATURE_NEG}'>"
            f"<x xmlns='jabber:x:data' type='submit'>"
            f"<field var='stream-method'>"
            f"<value>{Protocol.BYTESTREAMS}</value>"
            f"</field></x></feature></si></iq>"
        )

    # handlers for parser results
    def handle_message(self, message):
        self.logger.debug("Entering client.handle_message")
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
        self.logger.debug("Entering client.handle_transfer")
        if not self.downloaddir:
            self.logger.info(
                "Rejecting file transfer, download directory not set"
            )
            transfer.reject(self.cs)
            return
        status = transfer.retrieve(self.cs, self.downloaddir)

    def handle_stream_open(self,stream):
        self.logger.debug("Entering client.handle_stream_open")
        if self.stream_is_open:
            self.logger.error('Stream already open')
            return
        if not self.identity:
            self.identity == stream.identity
        elif self.identity != stream.identity:
            self.logger.error(
                f'Identity different from received one: self "{self.identity}",'
                f' remote "{stream.identity}"'
            )

        if not self.other:
            self.other = stream.other
        elif self.other != stream.other:
            self.logger.error(
                f'Other different from received one: self "{self.other}",'
                f' remote "{stream.other}"'
            )
             
        self.cs.send_line(
            f"<stream:stream xmlns='jabber:client'"
            f" xmlns:stream='http://etherx.jabber.org/streams'"
            f" from='{self.identity}' to='{self.other}' version='1.0'>"
        )
        self.stream_is_open = True

    def handle_feature_neg(self, fn):
        self.logger.debug("Entering client.handle_feature_neg")
        for v in fn.option_values:
            if v == Protocol.BYTESTREAMS:
                self._send_si_result(fn.iq_id)
                break
            else:
                self.logger.warning(f'Unhandled option value "{v}"')

    def close_stream(self):
        self.logger.debug("Entering client.close_stream")
        if not self.stream_is_open:
            self.logger.error("Stream is not open, not closing")
            return
        self.cs.send_line("</stream:stream>")
        self.stream_is_open = False

    # Functions related to threading/event loop
    def process_result(self, result):
        self.logger.debug("Entering client.process_result")
        if result.type   == ResultType.STREAM_OPEN:
            self.logger.debug("Handling stream open")
            self.handle_stream_open(result.data)
        elif result.type == ResultType.STREAM_CLOSE:
            self.logger.debug("Handling stream close")
            self.stop()
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
        except socket.timeout as e:
            return False
        except socket.error as e:
            self.logger.debug(f'socket.error {str(e)}')
            return False
        return True

    def run(self):
        self.logger.debug("Entering client.run")
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
        self.logger.debug("Entering client.stop")
        self.stopped.set()

