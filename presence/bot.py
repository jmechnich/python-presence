from presence import Presence

import socket

class PresenceBot(object):
    def __init__(self):
        super(PresenceBot,self).__init__()
        self.serversocket = None
        self.clientthreads = []
        
    def listen(self):
        if self.serversocket:
            return
        
        self.serversocket = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.bind(('', 5298))
        #become a server socket
        self.serversocket.listen(5)

    def wait_for_connect(self,client_args={}):
        (clientsocket, address) = self.serversocket.accept()
        print "Starting client thread", clientsocket
        ct = Presence(clientsocket, client_args)
        self.clientthreads.append(ct)
        ct.start()
        
    def cleanup(self):
        for ct in self.clientthreads:
            ct.stop()
            ct.join()
        self.clientthreads = []
        if self.serversocket:
            self.serversocket.close()
