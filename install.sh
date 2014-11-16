#!/bin/sh

PREFIX=/usr/local
#PREFIX=/usr
FILES=files.txt

echo "Installing to $PREFIX, keeping list of files in $FILES"
echo

(python setup.py build && \
    sudo python setup.py install --prefix "$PREFIX" --record "$FILES")
