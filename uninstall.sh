#!/bin/sh

FILES=files.txt

if ! [ -e $FILES ]; then exit 0; fi

echo "Deleting"
cat $FILES | sed 's,^,  ,g'
cat $FILES | sudo xargs rm -rf

echo "Deleting $FILES"
sudo rm -f $FILES
