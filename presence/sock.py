import logging
import socket

# client socket wrapper
class ClientSocket(object):
    def __init__(self, sock, address, logger=logging.getLogger()):
        super(ClientSocket,self).__init__()
        self.sock = sock
        self.sock.settimeout(1)
        self.address = address[0]
        self.port    = address[1]
        self.logger = logger
        
    def close(self):
        self.logger.info(f'Closing connection to {self.address}:{self.port}')
        self.sock.close()
        
    def send_line(self, msg):
        msg += '\n'
        self.send(msg)

    def send(self, msg):
        totalsent = 0
        bmsg = msg.encode()
        while totalsent < len(bmsg):
            sent = self.sock.send(bmsg[totalsent:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            self.logger.debug(f'WRITE {repr(bmsg[totalsent:totalsent+sent])}')
            totalsent = totalsent + sent

    def recv(self):
        chunk = self.sock.recv(2048)
        self.logger.debug(f'READ  {repr(chunk)}')
        if chunk == '':
            raise RuntimeError("socket connection broken")
        return chunk
