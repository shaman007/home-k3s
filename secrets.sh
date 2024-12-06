#!/bin/bash

dirs=( $(ls -la|grep drw|grep -v "\."| awk '{ print $9 }') )

for dirs in "${dirs[@]}"
do
    echo $dirs
    cd $dirs
    rm ./secret.yaml.asc -f
    gpg -a -r 'Andrey Bondarenko <me@andreybondarenko.com>' --encrypt secret.yaml
    cd ..
done
