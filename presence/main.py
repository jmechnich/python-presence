from server import PresenceServer

import argparse, lockfile, logging, os, signal, sys, psutil, time

from daemon import DaemonContext

def _main(name, daemon, loglevel, client_args):
    logger = logging.getLogger(name)
    logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s] [%(threadName)s] %(message)s")
    logger.setLevel( loglevel)
    
    if not daemon:
        # logging to console
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logFormatter)
        logger.addHandler(consoleHandler)
    
    # create server and listen on default socket 5298
    p = PresenceServer(logger=logger)
    p.listen()
    
    # wait for client to connect
    try:
        while True:
            p.wait_for_connect(client_args)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    
    # close client connections and server socket
    p.cleanup()

def main(name, client_args={}):
    parser = argparse.ArgumentParser(description=name)
    parser.add_argument( '-d', '--daemon',  action="store_true",
                         help='run as daemon')
    parser.add_argument( '-k', '--kill',  action="store_true",
                         help='kill running instance if any before start')
    parser.add_argument( '-v', '--verbose', action="store_true",
                         help='')
    args = parser.parse_args()
    
    if args.verbose:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    if os.geteuid() == 0:
        lock = '/var/run/%s' % name
    else:
        lock = os.path.join(os.environ['HOME'],'.%s' % name)
        
    if os.path.exists(lock+'.lock'):
        if args.kill:
            pidfile = open(lock+'.lock','r')
            pid = int(pidfile.readline().strip())
            pidfile.close()
            print "Sending SIGTERM to", pid
            os.kill(pid,signal.SIGTERM)
            retries = 5
            while psutil.pid_exists(pid) and retries:
                retries -= 1
                time.sleep(1)
            if psutil.pid_exists(pid):
                print "Sending SIGKILL to", pid
                os.kill(pid,signal.SIGKILL)
                time.sleep(1)
            if psutil.pid_exists(pid):
                print "Could not kill", pid
                print "Kill manually"
                sys.exit(1)
        else:
            print "Process already running (lockfile exists), exiting"
            sys.exit(1)
        
    if args.daemon:
        with DaemonContext(umask=0o002, pidfile=lockfile.FileLock(lock)):
            pidfile = open(lock+'.lock', 'w')
            print>>pidfile, os.getpid()
            pidfile.close()
            _main(name, args.daemon, loglevel, client_args)
    else:
            _main(name, args.daemon, loglevel, client_args)
