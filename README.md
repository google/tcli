# TCLI - TextFSM Device CLI

This is not an officially supported Google product

## Overview

TCLI - client interface for issuing commands to any number of devices.

Supports batch and interactive modes and multiple display formats.

Handy for performing trouble shooting and geerating reports etc from
arbitrarily large numbers of live devices.

## Cautions and Caveats

Empowers users to run commands across potentially large sets of devices with
very few restrictions - please use wisely and cautiously.

Does not support commands that are multi-part, or have non-descreet responses
e.g. the **ping** command.
**Note:** You can still use commands like
**ping count 5 127.0.0.1** or **monitor traffic brief count 2**
that do not require a ctrl-c to terminate.

## Documentation

### Setup
TCLI requires some setup bit can be run straight out of the box using some
fictictous devices and a limited set of commands that produce canned output:

Devices

   * device_a
   * device_b
   * device_c

Commands

   * show version
   * show vlan

To try TCLI, execute the **main.py** script in the parent directory.

    python3 main.py

To use it for your environment it will need an additional library to call
your device accessor system and also needs to retrieve a device list from
what system you are using to inventory those devices.

The 'canned' example has been included as the default [inventory_csv.py](https://github.com/google/tcli/blob/master/tcli/inventory_csv.py) to
illustrate how to do this. Please refer to the comments at the start of that
file for instructions on custimising for your environment.

It is hoped that contributors will submit libraries for some of the more
popular opensources device accessor methods - notch, rancid and inventory systems - DNS, SQL.

Once setup for your environment, then the Power Users guide will get you up and running fast!

[TCLI Power Users Guide](https://github.com/google/tcli/wiki/TCLI-Power-Users-Guide)

The structured format for device output is enable via [TextFSM](https://github.com/google/tcli).
Follow the instructions below for how to create new templates to display output in CSV or other structured formats.

[TextTableFSM](https://github.com/google/textfsm/wiki/Code-Lab)

There are opensource template repositories such as [ntc-templates](https://github.com/networktocode/ntc-templates)
that provide structured output for many common commands.
