**python-presence** is a minimal implementation of a serverless XMPP client.

###Components

- **PresenceBot**: holds a server socket on port 5298, listening for incoming message streams
- **Presence**:    client thread started by **PresenceBot** after a new connection was made

###Examples

See  https://github.com/jmechnich/python-presence/tree/master/examples
