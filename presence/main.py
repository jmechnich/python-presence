import argparse
import logging
import logging.handlers
import os
import signal
import sys
import psutil
import time

from pidfile import PidFile

from daemon import DaemonContext

from .server import PresenceServer

def _main(name, daemon, loglevel, client_args):
    logger = logging.getLogger(name)
    logger.setLevel(loglevel)
    
    if not daemon:
        # logging to console
        handler = logging.StreamHandler()
        logFormatter = logging.Formatter(
            "[%(threadName)s] %(message)s",
            #"%(asctime)s [%(levelname)-5.5s] [%(threadName)s] %(message)s",
        )
        handler.setFormatter(logFormatter)
        logger.addHandler(handler)
    else:
        handler = logging.handlers.SysLogHandler(address='/dev/log')
        logFormatter = logging.Formatter(
            "%(name)s[%(process)s]: [%(threadName)s] %(message)s",
            #"%(asctime)s [%(levelname)-5.5s] [%(threadName)s] %(message)s",
        )
        handler.setFormatter(logFormatter)
        logger.addHandler(handler)
    
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
    parser.add_argument('-d', '--daemon',  action="store_true",
                         help='run as daemon')
    parser.add_argument('-k', '--kill',  action="store_true",
                         help='kill running instance if any before start')
    parser.add_argument('-f', '--force', action="store_true",
                         help='force start on bogus lockfile')
    parser.add_argument('-v', '--verbose', action="store_true",
                         help='')
    args = parser.parse_args()
    
    if args.verbose:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    if os.geteuid() == 0:
        lock = f'/var/run/{name}.lock'
    else:
        lock = os.path.join(os.environ['HOME'],f'.{name}.lock')

    pid = -1
    if os.path.exists(lock):
        with open(lock,'r') as pidfile:
            pid = int(pidfile.readline().strip())
    if pid != -1 and not psutil.pid_exists(pid):
        os.remove(lock)
        pid = -1

    if pid != -1:
        if args.kill:
            try:
                print("Sending SIGTERM to", pid)
                os.kill(pid,signal.SIGTERM)
                retries = 5
                while psutil.pid_exists(pid) and retries:
                    retries -= 1
                    time.sleep(1)
                if psutil.pid_exists(pid):
                    print("Sending SIGKILL to", pid)
                    os.kill(pid,signal.SIGKILL)
                    time.sleep(1)
                if psutil.pid_exists(pid):
                    print("Could not kill", pid)
                    print("Kill manually")
                    sys.exit(1)
            except OSError as e:
                if args.force:
                    print("Error stopping running instance, forcing start")
                    os.remove(lock)
                else:
                    print(e)
                    sys.exit(1)
        else:
            if os.path.exists(lock):
                print("Process already running (lockfile exists), exiting")
                sys.exit(1)

    if args.daemon:
        with DaemonContext(umask=0o002, pidfile=PidFile(lock)):
            _main(name, args.daemon, loglevel, client_args)
    else:
        _main(name, args.daemon, loglevel, client_args)
