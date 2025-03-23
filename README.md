# TCLI – TextFSM Device CLI

This is not an officially supported Google product.

## Overview

TCLI is a client interface for issuing commands to arbitrarily large numbers of devices
(hundreds, thousands, even hundreds of thousands). TCLI is a frontend to TextFSM and adds a
rich set of interactive functions and collates responses into various tabular display formats.

An essential tool for scaling network administration when device access is required via CLI.
The cross section of devices to receive commands is controlled by matching on device names or
other attributes. The commands are sent and received asyncronously and the outputs are collated
into tables for a unified view.

Useful for real time analysis, interactive or exploratory troubleshooting, and creating holistic
views of device state or configuration for the cross section of the fleet you are interested in.

Can be used against a live network, for real-time data, or against a repository of stored command
outputs for offline use with near-realtime data.

See the [TCLI Power Users Guide](https://github.com/harro/tcli/wiki/TCLI-Power-Users-Guide) for how
to make use of the interactive CLI functionality.

Type ```/help``` to get started. TCLI commands are prefixed with a forward slash ```/```.
All other commands are forwarded to the target device/s for remote execution.

Pipes are supported locally in the client with double piping ```||``` . e.g.
```show inter terse | grep ge || wc -l```
Sends 'show inter terse | grep ge' to the target devices and pipes the result through ```wc -l```
locally in the TCLI host.

Inline commands are supported with double slash ```//```. e.g.
```show version //display csv //color on```

Returns the output of the 'show version' in csv format, with color still on,
regardless of what the global setting are. Global settings are not changed
by inline commands.

Commands can be passed to the host shell with ```/!``` or ```/exec```.

The file ```~/.tclirc``` is executed at startup.

Interactive TCLI starts in 'safe mode' - toggle off with ```/S``` or ```/safemode```.

## Cautions and Caveats

Empowers users to run commands across potentially large sets of devices with very few restrictions –
Exercise caution against 'overmatching' with your target and attribute filters and please use wisely and cautiously.

Does not support commands that are multi-part, or have non-discrete responses
e.g. the **ping** command.

<!-- markdownlint-disable MD033 -->
> **Note:** You can use commands like `ping count 5 127.0.0.1` or
`monitor traffic brief count 2` that do not require
<kbd>Ctrl</kbd> + <kbd>C</kbd> to terminate.
<!-- markdownlint-enable MD033 -->

## Architecture

TCLI is the front end of the software stack and there are several additional
components needed for a complete solution.

```mermaid
graph LR
    style TCLI fill:#eee,color:#333
    TCLI@{shape: rounded}
    A@{shape: manual-input, label: fa:fa-user User}
    B@{shape: cyl, label: "Device\nInventory"}
    C@{shape: proc, label: Authenticator}
    D@{shape: procs, label: Accessor}
    E@{label: TextFSM}
    F@{shape: docs, label: Templates}
    A <--> TCLI
    TCLI <--> B
    TCLI <--> C
    C <--> D
    TCLI <--> E
    E --- F
```

* [**TextFSM**](https://github.com/google/textfsm/wiki/Code-Lab) for formatting raw
CLI output into structured tables
* [**NTC Templates**](https://github.com/networktocode/ntc-templates) for TextFSM
to be able to structure output for specific commands and families of devices.
* **Accessor**: A service to send and receive commands to/from devices.
Examples include:
  * [Notch](https://pypi.org/project/notch.agent/)
  * [Rancid](https://pypi.org/project/rancidcmd/)
  * [Salt](https://docs.saltproject.io/en/latest/contents.html)
  * [Scrapli](https://carlmontanari.github.io/scrapli/)
  * [Netmiko](https://pypi.org/project/netmiko/)
* **Inventory**: A database, DNS or CVS file of device names and attributes, or the data file
from the accessor library above, such as router.db from RANCID.
* **Authenticator**: Authentication and authorisation policies for what commands can be sent
to devices.
  
  An AAA policy might allow NOC personnel to use the CLI but then only permit _'show'_
commands so that changes cannot be made to the devices.
  
  This policy and its implementation will vary greatly between organisations and unfortunately
you'll need to _'roll your own'_ here.

## Getting Started

Although TCLI requires significant setup and basic Python familiarity. It can be run straight out
of the box with fictitious devices and a limited set of commands with canned output:

* Devices:
  * device_a
  * device_b
  * device_c
* Commands:
  * show version
  * show vlan

To try TCLI, execute the **main.py** script in the parent directory.

```python
python3 main.py
```

Once setup for your environment, the Power Users guide will get you up and running fast! -
[TCLI Power Users Guide](https://github.com/harro/tcli/wiki/TCLI-Power-Users-Guide)

## Setup

To use in your environment TCLI needs to be configured to:

 1. Retrieve a list of devices from whatever system is used to manage site specific inventory.
 1. Call the site specific device accessor system (or to scrape the output files that it produces).

### Inventory

Inventory customisation is made to a new file that implements a child class of ``Inventory``.
This class is declared in ``inventory.py``. Import, inherit, and override the ``_FetchDevices``
method of the parent class.

An example implementation is provided, ``inventory_csv.py``, that reads devices from a CSV file.

Your new library can be substituted in at runtime with the _'--inventory_file'_ flag. The module is
expected to be located in the tcli directory.

### Accessor

A single function is customised to use your chosen device accessor.
Copy the ``accessor.py`` file and replace ``SendRequests`` in that file.

An example implementation is provided, ``accessor_canned.py``, that reads
example device outputs that are stored (canned) in static files.

Your new function can be substituted in at runtime with the _'--accessor_file'_ flag. The module is
expected to be located in the tcli directory.

Contributors are welcome to add various inventory or accessor library files for
popular inventory or device accessor solutions.

### Other Customisations

The structured format for device output is enabled via [TextFSM](https://github.com/google/textfsm).
You can create new templates to display output in CSV or other structured
formats per the [TextFSM Code Lab](https://github.com/google/textfsm/wiki/Code-Lab).
Or use the open source template repository
[ntc-templates](https://github.com/networktocode/ntc-templates)
that provides a library of templates for many device types and common commands.

Before contributing
-------------------
If you are not a Google employee, our lawyers insist that you sign a Contributor
Licence Agreement (CLA).

If you are an individual writing original source code and you're sure you own
the intellectual property, then you'll need to sign an
[individual CLA](https://cla.developers.google.com/about/google-individual).
Individual CLAs can be signed electronically. If you work for a company that
wants to allow you to contribute your work, then you'll need to sign a
[corporate CLA](https://cla.developers.google.com/clas).
The Google CLA is based on Apache's. Note that unlike some projects
(notably GNU projects), we do not require a transfer of copyright. You still own
the patch.

Unfortunately, even the smallest patch needs a CLA.
