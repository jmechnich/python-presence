import socket, os, hashlib, tempfile, shutil, urllib2

# parser result type
ResultTypeStr = ['STREAM_OPEN', 'STREAM_CLOSE', 'MESSAGE', 'FILE_TRANSFER', 'FEATURE_NEG']
ResultType    = type('ResultType', (object,), { t: i for i,t in enumerate(ResultTypeStr)})

class Result(object):
    def __init__(self, type, data=None):
        super(Result,self).__init__()
        self.type = type
        self.data = data

# protocols
class Protocol:
    BYTESTREAMS = 'http://jabber.org/protocol/bytestreams'
    FEATURE_NEG = 'http://jabber.org/protocol/feature-neg'
    SI          = 'http://jabber.org/protocol/si' 
    SI_TRANSFER = os.path.join(SI, 'profile/file-transfer')

# IQ stanza properties
class IQ(object):
    def __init__(self, identity, other, id, type):
        super(IQ,self).__init__()
        self.identity = identity
        self.other    = other
        self.id       = id
        self.type     = type
        
# Stream stanza properties
class Stream(object):
    def __init__(self, identity, other):
        super(Stream,self).__init__()
        self.identity = identity
        self.other    = other
        
# text/html message
class Message(object):
    def __init__(self, html='', ascii='', identity=None, other=None):
        super(Message,self).__init__()
        self.html     = html
        self.ascii    = ascii
        self.identity = identity
        self.other    = other

# feature negotiation
class FeatureNeg(object):
    def __init__(self, iq_id):
        super(FeatureNeg,self).__init__()
        self.iq_id = iq_id
        self.option_values = []

# file transfer
class Transfer(object):
    def __init__(self, parent, **kwargs):
        super(Transfer,self).__init__()
        self.__dict__['logger'] = parent.logger
        self._add_vars(['filename','filesize', 'identity', 'other'])
        for k,v in kwargs.items():
            self.__setattr__(k,v)

    def __setattr__(self,key, val):
        if key not in self.__dict__.keys():
            self.logger.warning("Not setting transfer attribute '%s' to '%s'" %(key,str(val)))
            return
        super(Transfer,self).__setattr__(key,val)

    def _add_vars(self,varlist):
        for var in varlist:
            self.__dict__[var] = None
        
    def _is_valid(self):
        status = True
        for k,v in self.__dict__.items():
            if k.startswith("_"):
                continue
            if v == None:
                self.logger.error("%s not set" % k)
                status = False
        return status

# SOCKS5 transfer
class Transfer_SOCKS5(Transfer):
    def __init__(self, parent, **kwargs):
        self._add_vars(['iq_id', 'sid', 'streamhosts' ])
        super(Transfer_SOCKS5,self).__init__(parent, **kwargs)
        
    def retrieve(self, clientsocket, downloaddir):
        if not self._is_valid():
            return False
        
        status = False
        for host in self.streamhosts:
            status = self._get_file_socks5(host, downloaddir)
            if status:
                break
        return status

    def reject(self, cs):
        line = ' '.join([
            "<iq from='%s'" % self.identity,
            "id='%s'" % self.iq_id,
            "to='%s'" % self.other,
            "type='error'>",
            "<error type='modify'>",
            "<not-acceptable",
            "xmlns='urn:ietf:params:xml:ns:xmpp-stanzas'/>",
            "</error>",
            "</iq>",
        ])
        cs.send_line(line)

    def _get_file_socks5(self, streamhost, downloaddir):
        self.logger.debug('Connecting to "%s"' % str(streamhost))
        target_jid = streamhost[2]
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
            
            # SHA1 Hash of: (SID + Requester JID + Target JID)
            idhash = hashlib.sha1("%s%s%s" % (self.sid,self.iq_id, target_jid))
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
            destfile = os.path.join(downloaddir,os.path.basename(self.filename))
            self.logger.info("Download complete: %s", destfile)
            shutil.copyfile(fpath,destfile)
            os.remove(fpath)
            return True
        except socket.error, e:
            self.logger.debug("%s" % str(e))
        return False

# out-of-band data transfer
class Transfer_OOB(Transfer):
    def __init__(self,parent, **kwargs):
        super(Transfer_OOB,self).__init__(parent, **kwargs)
        # optional variable iq_id to differentiate between iq and x OOB
        self.__dict__['iq_id'] = ''
        
    def retrieve(self, clientsocket, downloaddir):
        if not self._is_valid():
            return False
        status = self._get_file_oob(downloaddir)
        if len(self.iq_id):
            if status:
                self._send_iq_oob_success(clientsocket)
            else:
                self._send_iq_oob_failure(clientsocket,404)
        return status
    
    def reject(self,clientsocket):
        # can't reject x OOB?
        if len(self.iq_id):
            self._send_iq_oob_failure(clientsocket,406)
        
    def _get_file_oob(self, downloaddir):
        self.logger.debug('retrieving file %s, size %s bytes' %(self.filename, self.filesize))
        fd, fpath = tempfile.mkstemp()
        f = os.fdopen(fd, "w")
        self.logger.debug('Writing to "%s"'% fpath)
        bytesread = 0
        filesize = int(self.filesize)
        try:
            infile = urllib2.urlopen(self.filename)
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
        destfile = os.path.join(downloaddir,os.path.basename(self.filename))
        shutil.copyfile(fpath,destfile)
        os.remove(fpath)
        return True

    def _send_iq_oob_success(self, cs):
        msg = ' '.join([
                "<iq type='result'",
                "from='%s'" % self.identity,
                "to='%s'"   % self.other,
                "id='%s'/>" % self.iq_id
                ])
        cs.send(msg)
    
    def _send_iq_oob_failure(self,cs,errorcode):
        msg = ' '.join([
                "<iq type='error'",
                "from='%s'" % self.identity,
                "to='%s'"   % self.other,
                "id='%s'/>" % self.iq_id
                ])
        msg += "<query xmlns='jabber:iq:oob'>"
        msg += "<url>%s</url>" % self.filename
        msg += "</query>"
        if errorcode == 404:
            msg += "<error code='404' type='cancel'>"
            msg += "<item-not-found xmlns='urn:ietf:params:xml:ns:xmpp-stanzas'/>"
            msg += "</error>"
        elif errorcode == 406:
            msg += "<error code='406' type='modify'>"
            msg += "<not-acceptable xmlns='urn:ietf:params:xml:ns:xmpp-stanzas'/>"
            msg += "</error>"
        else:
            msg += "<error code='404' type='cancel'>"
            msg += "<item-not-found xmlns='urn:ietf:params:xml:ns:xmpp-stanzas'/>"
            msg += "</error>"
        msg += "</iq>"
        cs.send(msg)
