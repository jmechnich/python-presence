import logging
import socket
import threading

from .client import ClientThread
from .types  import Message

# main class
class PresenceServer(object):
    def __init__(self, address='', port=5298, logger=logging.getLogger()):
        super(PresenceServer,self).__init__()
        self.address = address
        self.port    = port
        self.logger  = logger
        
        self.serversocket  = None
        self.clientthreads = []
        self.lock = threading.Lock()
    
    # client callbacks
    def _client_stopped(self, client):
        with self.lock:
            self.clientthreads.remove(client)

    def _broadcast(self,client,message):
        self.logger.debug(f'Broadcasting message from "{message.identity}"')
        with self.lock:
            clientthreads = self.clientthreads[:]
        for ct in clientthreads:
            if ct == client:
                continue
            m = Message(identity=ct.identity,other=ct.other)
            if len(message.html):
                m.html  = f"<b>{message.other}:</b> {message.html}"
            if len(message.ascii):
                m.ascii = f"{message.other}: {message.ascii}"
            ct.send_message(m)

    # server commands
    def _users(self,client,message):
        with self.lock:
            clientthreads = self.clientthreads[:]
        users = []
        for ct in clientthreads:
            users.append(ct.other)
        client.send_html("<b>users:</b><br/>" + '<br/>'.join(users))

    def _server_commands(self):
        return {
            'users': ClientThread.make_command(
                func=self._users,
                helptext="print list of connected users"
                )
        }

    # public interface
    def listen(self):
        if self.serversocket:
            return
        address = self.address if len(self.address) else '*'
        self.logger.info(f'Listening on {address}:{self.port}')

        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.serversocket.bind((self.address, self.port))
        self.serversocket.listen(5)
    
    def wait_for_connect(self,client_args={}):
        (clientsocket, address) = self.serversocket.accept()
        self.logger.info(f"Starting client thread {address[0]}:{address[1]}")
        commands = self._server_commands()
        args = dict(client_args)
        if 'commands' in args:
            args['commands'].update(commands)
        else:
            args['commands'] = commands
        ct = ClientThread(
            sock=clientsocket, address=address, logger=self.logger, args=args
        )
        ct.cleanup_func   = self._client_stopped
        ct.broadcast_func = self._broadcast
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
            
