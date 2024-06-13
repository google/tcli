# TCLI – TextFSM Device CLI

## Overview

TCLI is a client interface for issuing commands to any number of devices which
supports batch and interactive modes and multiple display formats.

Handy for performing, troubleshooting, and generating reports from arbitrarily
large numbers of live devices.

## Cautions and Caveats

Empowers users to run commands across potentially large sets of devices with
very few restrictions – please use wisely and cautiously.

Does not support commands that are multi-part, or have non-discrete responses
(e.g. the **ping** command).

> **Note**<br> You can still use commands like `ping count 5 127.0.0.1` or
`monitor traffic brief count 2` that do not require a <kbd>Ctrl</kbd> +
<kbd>C</kbd> to terminate.

## Documentation

### Setup

TCLI requires some setup but can be run straight out of the box using some
fictitious devices and a limited set of commands that produce canned output:

Devices

* device_a
* device_b
* device_c

Commands

* show version
* show vlan

To try TCLI, execute the **main.py** script in the parent directory.

    python3 main.py

To use in your environment it will need to be integrated to call your device
accessor system and also retrieve a device list from whatever system you are
using to inventory those devices.

The "canned" example has been included as the default
[**inventory_csv.py**](https://github.com/google/tcli/blob/master/tcli/inventory_csv.py)
to illustrate how to do this. Please refer to the comments at the start of that
file for instructions on customizing your environment.

Contributors are welcome to add libraries for popular open source device
accessor methods – notch, rancid and inventory systems – DNS, SQL.

Once setup for your environment, then the Power Users guide will get you up and
running fast!<br>
[TCLI Power Users Guide](https://github.com/google/tcli/wiki/TCLI-Power-Users-Guide)

The structured format for device output is enable via
[TextFSM](https://github.com/google/tcli). Follow the instructions below to
create new templates to display output in CSV or other structured formats.<br>
[TextTableFSM](https://github.com/google/textfsm/wiki/Code-Lab)

There are open source template repositories such as
[ntc-templates](https://github.com/networktocode/ntc-templates) that provide
structured output for many common commands.
