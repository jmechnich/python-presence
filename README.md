[![PyPI versio](https://img.shields.io/pypi/v/python-presence)](https://pypi.org/project/python-presence/)
[![PyPi format](https://img.shields.io/pypi/format/python-presence)](https://pypi.org/project/python-presence/)
[![PyPI license](https://img.shields.io/pypi/l/python-presence)](https://pypi.org/project/python-presence/)
[![PyPi weekly downloads](https://img.shields.io/pypi/dw/python-presence)](https://pypi.org/project/python-presence/)

## python-presence

A minimal implementation of a serverless XMPP client.

### Installation

  * Clone this repository and run `pip install .` OR
  * Install from PyPi: `pip install python-presence`

### Usage (example client)

There is a minimal python script called `python-presence` for running
a service:

```
usage: python-presence [-h] [-d] [-k] [-f] [-v]

python-presence

optional arguments:
  -h, --help     show this help message and exit
  -d, --daemon   run as daemon
  -k, --kill     kill running instance if any before start
  -f, --force    force start on bogus lockfile
  -v, --verbose
```

### Default client commands

The client currently supports the following built-in trigger
commands/keywords:

| Commmand | Description                         |
|----------|-------------------------------------|
| `echo`   | echo message text                   |
| `help`   | print a list of commands            |
| `hello`  | print a hello message               |
| `vars`   | print variables                     |
| `ls`     | list contents of download directory |

### Extending the client with custom commands

A simple application of client commands is remote query of system
information.

```python
    import subprocess
    commands = {
        'df': ClientThread.make_command(
            func=staticmethod(
                lambda client, _: client.send_ascii(
                    subprocess.check_output("df -h", shell=True).decode('utf-8'))
            ),
            helptext='show list of processes',
        ),
        'ps': ClientThread.make_command(
            func=staticmethod(
                lambda client, _: client.send_ascii(
                    subprocess.check_output("ps aux", shell=True).decode('utf-8'))
            ),
            helptext='show list of processes',
        ),
    }
```

### System integration

`misc/presence.service` is a template file for configuring an Avahi
service. After copying to `/etc/avahi/services` the service
advertisement should immediately show up in clients on the same subnet.

`misc/python-presence.service` is a systemd service than can be used
as-is after copying to `/etc/systemd/system`.

The files are also available in the data folder of the PyPi package.
