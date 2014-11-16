import presence, socket, threading, logging

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
        self.serversocket.bind((self.address, self.port))
        self.serversocket.listen(5)
    
    def client_stopped(self, client):
        with self.lock:
            self.clientthreads.remove(client)

    def broadcast(self,client):
        with self.lock:
            clientthreads = self.clientthreads[:]
        for ct in clientthreads:
            if ct == client:
                continue
            ct.send_message("%s: %s" % (client.other,client.message))

    def users(self,client):
        with self.lock:
            clientthreads = self.clientthreads[:]
        users = []
        for ct in clientthreads:
            users.append(ct.other)
        client.send_message("\nusers:\n" + '\n'.join(users))

    def server_args(self):
        return { 'commands': {
                'users': presence.Presence.make_command(
                    func=self.users,
                    helptext="print list of connected users"
                    )}
                 }

    def wait_for_connect(self,client_args={}):
        (clientsocket, address) = self.serversocket.accept()
        self.logger.info("Starting client thread %s:%d" % address)
        args = self.server_args()
        args.update(client_args)
        ct = presence.Presence(sock=clientsocket, address=address, logger=self.logger, args=args)
        ct.register_cleanup_func(self.client_stopped)
        ct.register_broadcast_func(self.broadcast)
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
