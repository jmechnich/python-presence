import socket, threading, time, cgi, sys, os, subprocess

import xml.parsers.expat

class Presence(threading.Thread):
    @staticmethod
    def make_command(func=None, helptext='', greedy=False):
        if not func:
            func = lambda x: True
        d = { 'func': func, 'help': helptext, 'greedy': greedy }
        return type('Command', (object,), d)

    def default_commands(self):
        return {
            'echo': Presence.make_command(
                func=staticmethod(lambda x: self.echo()),
                helptext="echo text",
                greedy=True),
            'help': Presence.make_command(
                func=staticmethod(lambda x: self.help()),
                helptext="print this help"),
            }
    
    def __init__(self, sock, client_args):
        super(Presence,self).__init__()
        self.stopped = threading.Event()
        self.sock = sock
        self.sock.settimeout(1)
        self.client_args = dict(client_args)
        self.name     = self.client_args.get('name', 'Default')
        self.commands = self.client_args.get('commands', {})
        self.commands.update(self.default_commands())
        
        self.ignore = ['font', 'composing']
        self.text_elems = { 'BODY': 0x1, 'HTML': 0x2 }
        self.__dict__.update(self.text_elems)
        self.modes = { 'IDLE': 0, 'MESSAGE': 1, 'EVENT': 2 }
        self.__dict__.update(self.modes)
        self.mode = self.IDLE
        
        self.parser = xml.parsers.expat.ParserCreate()
        self.parser.StartElementHandler  = self.start_element
        self.parser.EndElementHandler    = self.end_element
        self.parser.CharacterDataHandler = self.char_data

    def start_element(self, name, attrs):
        if name == 'stream:stream':
            self.other = attrs['from']
            self.send_response_stream_header()
            self.send_features()
            self.hello()
        elif name == 'x' and attrs['xmlns'] == 'jabber:x:event':
            self.mode = self.EVENT
        elif name == 'message':
            self.mode = self.MESSAGE
            self.message = ""
            self.flags   = 0
        elif name == 'html':
            self.flags |= self.HTML
        elif name == 'body':
            self.flags |= self.BODY
        elif name in self.ignore:
            pass
        else:
            print 'Start element:', name, attrs
            
    def end_element(self, name):
        if name == 'stream:stream':
            self.send_line('</stream:stream>')
        elif name == 'message':
            self.mode = self.IDLE
            self.handle_message()
        elif name == 'html':
            self.flags &= ~self.HTML
        elif name == 'body':
            self.flags &= ~self.BODY
        elif name == 'x' and self.mode == self.EVENT:
            self.mode = self.IDLE
        elif name in self.ignore:
            pass
        else:
            print 'End element:', name
        
    def char_data(self, data):
        if self.mode == self.MESSAGE:
            if not (self.flags & (self.BODY) and
                    self.flags & (self.HTML)):
                self.message += data
        else:
            print 'Data:', data

    def reset(self):
        self.data = []
        self.timeoutcounter = 0
        
    def process(self,text):
        if len(text) == 0:
            return True
        self.parser.Parse(text,False)
        return False
    
    def send_message(self,text,tags=['body']):
        #print "SENDING", text
        text = cgi.escape(text).encode('ascii', 'xmlcharrefreplace')
        openingtags = ''.join(['<%s>' % t for t in tags ])
        closingtags = ''.join(['</%s>'% t for t in reversed(tags) ])
        message = [
            "<message",
            "from='%s'" % self.name,
            "to='%s'"   % self.other,
            "type='chat'>%s%s%s</message>" % (openingtags,text,closingtags)
            ]
        line = ' '.join(message)
        self.send_line( line)

    def send_message_html(self,text):
        self.send_message(text,tags=['body', 'html', 'body'])

    def send_response_stream_header(self):
        self.send_line(' '.join([
                    "<stream:stream xmlns='jabber:client'",
                    "xmlns:stream='http://etherx.jabber.org/streams'",
                    "from='%s'" % self.name,
                    "to='%s'"   % self.other,
                    "version='1.0'>",
                    ]))

    def send_features(self):
        self.send_line('\n'.join([
                    "<stream:features>",
                    "<starttls xmlns='urn:ietf:params:xml:ns:xmpp-tls'>",
                    "<optional/>",
                    "</starttls>",
                    "</stream:features>",
                    ]))

    def echo(self):
        self.send_message(self.message[5:].strip())
        
    def help(self):
        self.send_message('\n'.join([
                    '',
                    self.command_text()
                    ]))

    def command_text(self):
        ret = '<b>commands:</b>\n'
        for k, v in self.commands.items():
            ret += '  %s - %s\n'% (k, v.help)
        return ret

    def hello(self):
        self.send_message('\n'.join([
                    '',
                    'Hello at <b>%s</b>' % self.name,
                    self.command_text()]))
        self.send_message

    def handle_message(self):
        words = self.message.split()
        if len(words):
            command = words[0]
            if command in self.commands.keys():
                if not self.commands[command].greedy and \
                        len(words) > 1:
                    return
                self.commands[command].func(self)
            else:
                self.print_message()

    def print_message(self):
        print "RECEIVED", self.message
            
    def run(self):
        try:
            print "Entering loop"
            while not self.stopped.is_set():
                self.receive()
        except RuntimeError:
            pass
        print "Closing socket"
        self.sock.close()

    def stop(self):
        self.stopped.set()
    
    def send_line(self, msg):
        msg += '\n'
        self.send(msg)

    def send(self, msg):
        totalsent = 0
        while totalsent < len(msg):
            sent = self.sock.send(msg[totalsent:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            totalsent = totalsent + sent

    def receive(self):
        self.reset()
        chunk = ''
        try:
            while self.process(chunk):
                chunk = self.sock.recv(2048)
                if chunk == '':
                    raise RuntimeError("socket connection broken")
        except socket.timeout, e:
            self.timeoutcounter += 1
            if self.timeoutcounter == 10:
                #self.sock.close()
                self.timeoutcounter = 0
            return False
        except socket.error, e:
            print 'error', e
            return False
        return True
