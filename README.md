# TCLI - TextFSM Device CLI

This is not an officially supported Google product

## Overview

TCLI - client interface for issuing commands to any number of devices. Supports
batch and interactive modes and multiple display formats.

Handy for trouble shooting, reporting etc from live devices.

## Cautions and Caveats

Empowers users to run commands across potentially large sets of devices with
very few restrictions - please use wisely and cautiously. Does not support
commands that are multi-part, or have non-descreet responses e.g. ping (note:
you can still use commands like "ping count 5 127.0.0.1" or "monitor traffic
brief count 2" which do not require a ctrl-c to terminate).

## Documentation

Setup - TCLI runs straight out of the box but only supports a very limited set
of commands, producing canned output for fictictous devices.

To use it in your environment it needs an additional library configured to call
your device accessor system/tool and needs to know where/what you are using to
inventory those devices.

A 'canned' example has been included as the default (inventory_csv.py) to
illustrate how to do this. Please refer to the comments at the start of that
file for instructions on custimising for your environment.

All setup, then the Power Users guide will get you up and running fast!

[TCLI Power Users Guide](g3doc/poweruser.md)

See the following Wiki for how to create new templates for displaying output in
CSV and other structured formats.

[TextTableFSM](https://github.com/google/textfsm/wiki/Code-Lab)
