import socket, threading, logging

from presence.client import ClientThread
from presence.types  import Message

class PresenceBot(object):
    def __init__(self, address='', port=5298, logger=None):
        super(PresenceBot,self).__init__()
        self.address = address
        self.port    = port
        if not logger:
            logger   = logging.getLogger()
        self.logger  = logger
        
        self.serversocket  = None
        self.clientthreads = []
        self.lock = threading.Lock()
        
    def listen(self):
        if self.serversocket:
            return
        
        self.logger.info('Listening on %s:%d' % (self.address if len(self.address) else '*',self.port))
        self.serversocket = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serversocket.bind((self.address, self.port))
        self.serversocket.listen(5)
    
    def client_stopped(self, client):
        with self.lock:
            self.clientthreads.remove(client)

    def broadcast(self,client,message):
        self.logger.debug('Broadcasting message from "%s"' % message.identity)
        with self.lock:
            clientthreads = self.clientthreads[:]
        for ct in clientthreads:
            if ct == client:
                continue
            m = Message(identity=ct.identity,other=ct.other)
            if len(message.html):
                m.html  = "<b>%s:</b> %s" % (message.other,message.html)
            if len(message.ascii):
                m.ascii = "%s: %s"% (message.other,message.ascii)
            ct.send_message(m)

    def users(self,client,message):
        with self.lock:
            clientthreads = self.clientthreads[:]
        users = []
        for ct in clientthreads:
            users.append(ct.other)
        client.send_html("<b>users:</b><br/>" + '<br/>'.join(users))

    def server_commands(self):
        return {
            'users': ClientThread.make_command(
                func=self.users,
                helptext="print list of connected users"
                )}

    def wait_for_connect(self,client_args={}):
        (clientsocket, address) = self.serversocket.accept()
        self.logger.info("Starting client thread %s:%d" % address)
        commands = self.server_commands()
        args = dict(client_args)
        if args.has_key('commands'):
            args['commands'].update(commands)
        else:
            args['commands'] = commands
        ct = ClientThread(sock=clientsocket, address=address, logger=self.logger, args=args)
        ct.cleanup_func   = self.client_stopped
        ct.broadcast_func = self.broadcast
        with self.lock:
            self.clientthreads.append(ct)
        ct.start()
        
    def cleanup(self):
        with self.lock:
            clientthreads = self.clientthreads[:]
        for ct in clientthreads:
            ct.stop()
            ct.join()
        if self.serversocket:
            self.logger.info('Closing server socket')
            self.serversocket.close()
            
