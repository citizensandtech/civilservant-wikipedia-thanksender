#! /usr/bin/env bash
echo "THANKSENDER WRAPPER SCRIPT RUNNING"
ENVDIR=/usr/local/civilservant/thanker
THANKSENDERDIR=/usr/local/civilservant/thanksender/thank

cd $ENVDIR
PATH=/usr/local/bin:$PATH
echo "$ENVDIR $THANKSENDER DIR"
pipenv run cs api.sendthanks --lang=en
