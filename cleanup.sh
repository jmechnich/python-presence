#!/bin/sh

find . -name '*.pyc' | xargs rm -f
find . -name '*~' | xargs rm -f

rm -f MANIFEST
rm -rf build dist
