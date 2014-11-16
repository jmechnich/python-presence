import socket, threading, cgi, logging, re, os, tempfile, hashlib, shutil, urllib2

import xml.parsers.expat
import xml.etree.ElementTree

class Presence(threading.Thread):
    protocol_bytestreams = "http://jabber.org/protocol/bytestreams"
    
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
    
    def __init__(self, sock, address, logger=None, args={}):
        super(Presence,self).__init__()
        self.stopped = threading.Event()
        self.sock = sock
        self.sock.settimeout(1)
        self.address = address[0]
        self.port    = address[1]
        if not logger:
            logger = logging.getLogger()
        self.logger = logger
        self.args = dict(args)
        self.name        = self.args.get('name', 'Default')
        self.downloaddir = self.args.get('downloaddir', None)
        self.commands    = self.args.get('commands', {})
        self.commands.update(self.default_commands())
        
        flags = ['BODY','HTML', 'HTMLBODY', 'OPTION', 'VALUE']
        self.text_elems = { f: 1 << i for i,f in enumerate(flags) }
        self.__dict__.update(self.text_elems)
        modes = [ 'IDLE', 'MESSAGE', 'FILE_OOB', 'FILE_SOCKS5', 'FEATURE_NEG' ]
        self.modes = { m: i for i,m in enumerate(modes) }
        self.__dict__.update(self.modes)
        self.mode = self.IDLE
        self.ignore = ['font', 'composing']
        
        self.parser = xml.parsers.expat.ParserCreate()
        self.parser.StartElementHandler  = self.start_element
        self.parser.EndElementHandler    = self.end_element
        self.parser.CharacterDataHandler = self.char_data
        
        self.cleanup_func = None
        self.broadcast_func = None
        self.flags   = 0

    def send_si_result(self):
        self.send_line(''.join([
                    "<iq type='result' to='%s' id='%s'>" %(self.other,self.iq_id),
                    "<si xmlns='http://jabber.org/protocol/si'>",
                    "<feature xmlns='http://jabber.org/protocol/feature-neg'>",
                    "<x xmlns='jabber:x:data' type='submit'>",
                    "<field var='stream-method'>",
                    "<value>%s</value>" % Presence.protocol_bytestreams,
                    "</field>",
                    "</x>",
                    "</feature>",
                    "</si>",
                    "</iq>",
                    ]))

    def get_file_oob(self):
        print 'retrieving file %s, size %s bytes' %(self.url, self.filesize)
        fd, fpath = tempfile.mkstemp()
        f = os.fdopen(fd, "w")
        self.logger.debug('Writing to "%s"'% fpath)
        bytesread = 0
        filesize = int(self.filesize)
        try:
            infile = urllib2.urlopen(self.url)
            while bytesread < filesize:
                chunk = infile.read(2048)
                if not len(chunk):
                    break
                f.write(chunk)
                bytesread += len(chunk)
                #self.logger.debug('read %d/%d bytes' % (bytesread,filesize))
        except:
            raise
        self.logger.debug( "read %d/%d bytes" % (bytesread,filesize))
        f.close()
        if self.downloaddir:
            downloaddir = self.downloaddir
        else:
            downloaddir = os.environ['HOME']
        destfile = os.path.join(downloaddir,os.path.basename(self.url))
        shutil.copyfile(fpath,destfile)
        os.remove(fpath)
        return True

    def send_oob_success(self):
        msg = ' '.join([
                "<iq type='result'",
                "from='%s'" % self.name,
                "to='%s'" % self.other,
                "id='%s'/>" % self.iq_id
                ])
        self.send_line(msg)
    
    def send_oob_failure(self,errorcode):
        msg = ' '.join([
                "<iq type='error'",
                "from='%s'" % self.name,
                "to='%s'" % self.other,
                "id='%s'/>" % self.iq_id
                ])
        msg += "<query xmlns='jabber:iq:oob'>"
        msg += "<url>%s</url>" % self.url
        msg += "</query>"
        if errorcode == 404:
            msg += "<error code='404' type='cancel'>"
            msg += "<item-not-found xmlns='urn:ietf:params:xml:ns:xmpp-stanzas'/>"
            msg += "</error>"
        elif errorcode == 404:
            msg += "<error code='406' type='modify'>"
            msg += "<not-acceptable xmlns='urn:ietf:params:xml:ns:xmpp-stanzas'/>"
            msg += "</error>"
        else:
            msg += "<error code='404' type='cancel'>"
            msg += "<item-not-found xmlns='urn:ietf:params:xml:ns:xmpp-stanzas'/>"
            msg += "</error>"
        msg += "</iq>"
        self.send_line(msg)
    
    def start_element(self, name, attrs):
        if name in ['id']:
            pass
        elif name == 'stream:stream':
            self.other = attrs['from']
            self.send_response_stream_header()
            #self.send_features()
            self.hello()
        elif name == 'x':
            xmlns = attrs['xmlns']
            if xmlns == 'jabber:x:event':
                pass
            elif xmlns == 'jabber:x:data':
                type = attrs['type']
            elif xmlns == 'jabber:x:oob':
                self.mode = self.FILE_OOB
                self.url  = ''
        elif name == 'url':
            mimeType=attrs['mimeType']
            posixflags=attrs['posixflags']
            if attrs['type'] == 'file':
                self.filesize = attrs['size']
        elif name == 'message':
            self.mode = self.MESSAGE
            self.message = ""
            self.message_html = ""
        elif name == 'html':
            self.flags |= self.HTML
        elif name == 'body':
            if self.flags & self.HTML:
                self.flags |= self.HTMLBODY
            else:
                self.flags |= self.BODY
        elif name == 'iq':
            self.iq_id   = attrs['id']
            self.iq_type = attrs['type']
        elif name == 'si':
            xmlns = attrs['xmlns']
            self.si_id      = attrs['id']
            self.si_profile = attrs['profile']
        elif name == 'file':
            xmlns = attrs['xmlns']
            self.filename = attrs['name']
            self.filesize = attrs['size']
        elif name == 'feature':
            xmlns = attrs['xmlns']
            if xmlns == 'http://jabber.org/protocol/feature-neg':
                self.mode = self.FEATURE_NEG
                self.option_values = []
        elif name == 'field':
            var = attrs['var']
            type = attrs['type']
        elif name == 'option':
            self.flags |= self.OPTION
        elif name == 'value':
            self.flags |= self.VALUE
        elif name == 'query':
            xmlns = attrs['xmlns']
            mode = attrs['mode']
            self.sid = attrs['sid']
            if xmlns == Presence.protocol_bytestreams:
                self.streamhosts = []
                self.mode = self.FILE_SOCKS5
        elif name == 'streamhost':
            jid = attrs['jid']
            host = attrs['host']
            port = attrs['port']
            self.streamhosts.append((host, port, jid))
        elif name in self.ignore:
            pass
        else:
            if not self.flags & self.HTMLBODY:
                self.logger.debug('Start element: %s %s' % (name, str(attrs)))
            
    def end_element(self, name):
        if name in ['id','field', 'url', 'streamhost', 'file']:
            pass
        elif name == 'stream:stream':
            self.send_line('</stream:stream>')
        elif name == 'message':
            self.mode = self.IDLE
            self.handle_message()
        elif name == 'html':
            self.flags &= ~self.HTML
        elif name == 'body':
            if self.flags & self.HTML:
                self.flags &= ~self.HTMLBODY
            else:
                self.flags &= ~self.BODY
        elif name == 'x':
            if self.mode == self.FILE_OOB:
                status = self.get_file_oob()
                if status:
                    self.send_oob_success()
                else:
                    self.send_oob_failure(404)
                self.mode == self.IDLE
        elif name == 'iq':
            self.iq_id   = None
            self.iq_type = None
        elif name == 'si':
            self.si_profile = None
            self.si_id      = None
        elif name == 'feature':
            if self.mode == self.FEATURE_NEG:
                for v in self.option_values:
                    if v == Presence.protocol_bytestreams:
                        self.send_si_result()
                    else:
                        self.logger.warning('Unhandled option value "%s"' % v)
                self.option_values = None
                self.mode = self.IDLE
        elif name == 'option':
            self.flags &= ~self.OPTION
        elif name == 'value':
            self.flags &= ~self.VALUE
        elif name == 'query':
            if self.mode == self.FILE_SOCKS5:
                for host in self.streamhosts:
                    if self.get_file_socks5(host):
                        break
                self.mode = self.IDLE
        elif name in self.ignore:
            pass
        else:
            if not self.flags & self.HTMLBODY:
                self.logger.debug('End element: %s' % name)
        
    def char_data(self, data):
        if self.mode == self.MESSAGE:
            if not (self.flags & (self.HTMLBODY)):
                self.message += data
            if self.flags & (self.HTMLBODY):
                self.message_html += data
        elif self.mode == self.FEATURE_NEG:
            if self.flags & self.OPTION and self.flags & self.VALUE:
                self.option_values.append(data)
        elif self.mode == self.FILE_OOB:
            self.url += data
        else:
            self.logger.debug('Data: %s' % data)
    
    def get_file_socks5(self, streamhost):
        self.logger.debug('Connecting to "%s"' % str(streamhost))
        hostjid = streamhost[2]
        try:
            sock = socket.create_connection((streamhost[0],int(streamhost[1])))
            # start SOCKS5 handshake, send version identifier/method selection message
            msg = bytearray([0x5, 0x0])
            sock.send(msg)
            # receive METHOD selection message from server
            servermethods = sock.recv(2)
            if len(servermethods) == 2 and ord(servermethods[0]) == 0x5 and ord(servermethods[1]) == 0x0:
                # success
                pass
            else:
                self.logger.error('SOCKS5 handshake failed')
                return False
            
            idhash = hashlib.sha1("%s%s%s" % (self.sid,self.iq_id,hostjid))
            # SOCKS5 request: VER, CMD, RSV, ATYP, DST.ADDR, DST.PORT
            # VER = 0x05, CMD = [ CONNECT 0x01, BIND 0x02, UDP ASSOCIATE 0x03 ], RSV = 0x0
            # ATYP = [ IPv4 address: 0x01, DOMAINNAME: 0x03, IPv6 address: 0x04 ]
            # DST.ADDR = Variable, DST.PORT = 0x0000 (2 bytes)
            dst_addr = bytearray(idhash.digest())
            msg = bytearray([0x05, 0x01, 0x00, 0x03, len(dst_addr)]) + dst_addr + bytearray([0x0,0x0])
            sock.send(msg)
            fd, fpath = tempfile.mkstemp()
            f = os.fdopen(fd, "w")
            self.logger.debug('Writing to "%s"'% fpath)
            bytesread = 0
            filesize = int(self.filesize)
            read_reply = True
            reply = ''
            # SOCKS5 reply: VER, REP, RSV, ATYP, BND.ADDR, BND.PORT
            # VER = 0x05, REP = [ 0x0 succeeded, 0x1 general SOCKS server failure, 0x2 connection not allowed by ruleset,
            #   0x3 Network unreachable, 0x4 Host unreachable, 0x5 Connection refused, 0x6 TTL expired, 0x7 Command not supported
            #   0x8 Address type not supported, 0x9 to X'FF' unassigned ], RSV = 0x0,
            # ATYP = [ IPv4 address: 0x01, DOMAINNAME: 0x03, IPv6 address: 0x04 ],
            # BND.ADDR = Variable, BND.PORT = 2 bytes
            while bytesread < filesize:
                chunk = sock.recv(2048)
                if not len(chunk):
                    break
                if read_reply:
                    if len(chunk) < 7:
                        self.logger.error("Could not parse SOCKS5 message, chunk too short")
                        return False
                    pos = 0
                    if ord(chunk[pos]) != 0x5 or ord(chunk[pos+1]) != 0x0 or ord(chunk[pos+2]) != 0x0:
                        self.logger.error("Connection with SOCKS5 server failed")
                        return False
                    pos+=3
                    addr_type = ord(chunk[pos])
                    pos+=1
                    if addr_type == 1 or addr_type == 4:
                        # IPv4 or IPv6
                        pos += 4*addr_type
                    elif addr_type == 3:
                        # domainname
                        length = ord(chunk[pos])
                        pos += 1 + length
                    else:
                        self.logger.error("Error parsing SOCKS5 bind address")
                        return False
                    # no clue which order but does not matter anyways
                    port = ord(chunk[pos]) << 8 & ord(chunk[pos+1])
                    pos += 2
                    
                    reply = chunk[:pos]
                    chunk = chunk[pos:]
                    read_reply = False
                f.write(chunk)
                bytesread += len(chunk)
                #self.logger.debug('read %d/%d bytes' % (bytesread,filesize))
            self.logger.debug( "Reply: read %d/%d bytes" % (bytesread,filesize))
            self.logger.debug( "SOCKS5 reply: %s" %repr(reply))
            f.close()
            if self.downloaddir:
                downloaddir = self.downloaddir
            else:
                downloaddir = os.environ['HOME']
            destfile = os.path.join(downloaddir,os.path.basename(self.filename))
            self.logger.info("Download complete: %s", destfile)
            shutil.copyfile(fpath,destfile)
            os.remove(fpath)
            return True
        except socket.error, e:
            print e
        return False
        
    def reset(self):
        self.data = []
        self.timeoutcounter = 0
        
    def process(self,text):
        if len(text) == 0:
            return True

        self.parser.Parse(text,False)
        return False
    
    def send_message(self,text):
        text = cgi.escape(text).encode('ascii', 'xmlcharrefreplace')
        message = [
            "<message",
            "from='%s'" % self.name,
            "to='%s'"   % self.other,
            "type='chat'><body>%s</body></message>" % text
            ]
        line = ' '.join(message)
        self.send_line( line)

    def send_message_html(self,text):
        asciitext = '\n' + re.sub(r'<br/?>', '\n', text)
        asciitext = ''.join(xml.etree.ElementTree.fromstring('<p>%s</p>' % asciitext).itertext())
        asciitext = cgi.escape(asciitext).encode('ascii', 'xmlcharrefreplace')
        message = [
            "<message",
            "from='%s'" % self.name,
            "to='%s'"   % self.other,
            "type='chat'><body>%s</body><html xmlns='http://www.w3.org/1999/xhtml'><body>%s</body></html></message>" % (asciitext,text)
            ]
        line = ' '.join(message)
        self.send_line( line)

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
        self.send_message_html('\n'.join([
                    self.command_text()
                    ]))

    def command_text(self):
        ret = '<b>commands:</b><br/>'
        for k, v in self.commands.items():
            ret += '  %s - %s<br/>'% (k, v.help)
        return ret

    def hello(self):
        self.send_message_html(
            ('Welcome at <b>%s</b><br/>' % self.name) +
            self.command_text())
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
        if self.logger.getEffectiveLevel() == logging.DEBUG:
            self.logger.debug('Received from %s:%d' %(self.address,self.port))
            for line in self.message.split('\n'):
                self.logger.debug("R: %s" % line)
            self.logger.debug('Receive end')
        if self.broadcast_func:
            self.broadcast_func(self)
    
    def run(self):
        try:
            while not self.stopped.is_set():
                self.receive()
        except RuntimeError:
            pass
        self.logger.info('Closing connection to %s:%d' % (self.address,self.port))
        self.sock.close()
        if self.cleanup_func:
            self.cleanup_func(self)

    def register_cleanup_func(self, func):
        self.cleanup_func = func
    
    def register_broadcast_func(self, func):
        self.broadcast_func = func
    
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
            self.logger.debug('WRITE %s' % repr(msg[totalsent:totalsent+sent]))
            totalsent = totalsent + sent

    def receive(self):
        self.reset()
        chunk = ''
        try:
            while self.process(chunk):
                chunk = self.sock.recv(2048)
                self.logger.debug('READ  %s' % repr(chunk))
                if chunk == '':
                    raise RuntimeError("socket connection broken")
        except socket.timeout, e:
            self.timeoutcounter += 1
            if self.timeoutcounter == 10:
                self.timeoutcounter = 0
            return False
        except socket.error, e:
            self.logger.debug('socket.error %s' % str(e))
            return False
        return True
