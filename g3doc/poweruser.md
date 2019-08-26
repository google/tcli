# TCLI Power Users Guide

## Contents

[TOC]

TCLI can be run in either batch or interactive mode.

## Batch Mode

In batch mode, commands and settings are provided as flags and the output is
printed on stdout.

### Multiple Commands for Single Device.

Multiple commands are newline separated.

<code class="lang-shell"><pre>
  # Collect some diagnostic from *device_a*.
  tcli -C <kbd>'show version
  show chassis
  sh ip ospf neighbor' -T device_a'</kbd>
</pre></code>

### Multiple Devices

Scope of target devices to send commands to is controlled by expressions for
what to include (targets) and to exclude (xtargets).

The target can be a literal *`device_a`*, or several literals comma separated
(note that there are no spaces) like: *`device_a,device_b`* or instead of a
literal, a regular expression is indicated by prefixing a *`^`* to the entry
i.e. *`^device_(a|b)`* which would match both **`device_a`** and **`device_b`**.

### Output in Structured Format

Output Display engines post process data. The dispaly formats of **`csv`**,
**`tbl`** and **`nvp`** are supported (covered below). Commands that cannot be
handled by the display engine are returned in **`raw`** format (unformatted).

<code class="lang-shell"><pre>
  # Show version of all devices in single table.
  tcli -C <kbd>'show version'</kbd> -T <kbd>^device_.</kbd> -D <kbd>csv</kbd>
</pre></code>

## Interactive Mode

Most of the power of TCLI is in the interactive mode. Easiest way to reach this
mode is supply no arguments at the commandline or by requesting it explicitly
with the **`-I`** flag. e.g.

<code class="lang-shell"><pre>
  tcli
</pre></code>

This mode will also be reached if the flags passed to TCLI are somehow
incomplete for batch mode i.e. specifying targets and no corresponding commands
in this case the environment of interactive mode will be pre populated by
whatever flags were specified.

Interactive mode has two types of commands:

1.  **Escape Commands**: <br/> Commands destined for **TCLI** itself, used to
    modify the operating environment of **TCLI**. Escape commands are proceeded
    by a '/'.

1.  **Target Commands**: <br/> Commands destined for the target devices. The
    commands are forwarded to the target list and then the resultant output is
    collated and displayed. Target commands are **not** proceeded by a **`/`**.

There is also an *escape command* ( **`/command`** ) that takes all its
arguments and forwards it as a *target command*. This may seem pointless but
makes sense when used in conjunction with *safemode* which is discussed later.

### Interactive Mode Environment

Changes to the environment made to **TCLI** are persistent across commands.

To inspect the current environment.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /env
  <kbd>Targets: , XTargets:
  Display: raw, Filter: default
  Record: None, Recordall: None
  Log: None, Logall: logall
  Color: True, Scheme: light
  Timeout: 30, Verbose: False
  Safemode: True</kbd>
</pre></code>

In interactive mode a prompt is supplied that indicates some key environment
variable (targets, target count, safemode). The running environment can be
tailored with *escape commands*.

### Interactive Mode Prompt

<code class="lang-shell"><pre>
  <kbd>#!&lt;device_a[1]&gt; !#</kbd>
</pre></code>

The above prompt indicates that the **`target`** string is **device_a** which
matches a single target **`[1]`**. Whereas in the case of **`#!
<^device_.*[96]*> !#`** the target list includes all devices prefixed with
**device_** (96 in this case). The list can be seen by issuing
**`/expandtargets`**.

With so many devices matched by the target list particular care should be taken
not to issue spurious commands to **TCLI** (see safemode below).

### Safe Mode

TCLI starts up with *safemode* as the default operation environment. In this
mode commands are not sent to the target list until either the safemode is
disabled off or the commands are issued as a escape command .i.e. prefixed with
**`/command`**.

**Note:** **`Ctrl-C`** will interrupt a running command and return to the
prompt. It does not however stop the commands from being sent to the devices.
Once a commands request is submitted to the backend it will be processed. The
**`Ctrl-C`** will merely stop **TCLI** waiting for the command responses to
return.

#### To disable safe mode.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /safemode off
</pre></code>

### Getting Help

A limited set of tab completion is available in interactive mode. This works for
escape commands, so by typing **`/`** followed by tabbing, the possible
completions will be displayed.

It also works to a limited extent for router commands, this support is dependant
on the existence of TextFSM templates for the commands.

Online help is available with:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /help
</pre></code>

### Managing the Target List

In interactive mode it is possible to append to the existing *target* and
*xtarget* entries.

**Example:**

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /targets ^device_(a|b)
</pre></code>

To confirm that we have matched correctly:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /expandtargets
     <kbd>device_a,device_b</kbd>
</pre></code>

To then add **`device_c`** to the targets

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /targets+ device_c
  <kbd>#! &lt;^device_(a|b),device_c[3]*&gt; !#</kbd>
  <kbd>#!</kbd> /expandtargets
     <kbd>device_a,device_b,device_c</kbd>
</pre></code>

To remove device_a from this list we could build a new target list or
alternatively extend the **`xtargets`** .

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /xtargets+ device_a
  <kbd>#! &lt;^device_(a|b),device_c[2]*&gt; !#</kbd>
  <kbd>#!</kbd> /expandtargets
     <kbd>device_b,device_c</kbd>
</pre></code>

Resetting the targets back to null:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /targets ^
</pre></code>

**Note:** Care should be taken to preserve the existing *xtargets* string as
this typically includes devices you would note normally want to send commands
to. A default *xtargets* can be created by editing the **`.tclirc`** file
(discussed below).

## General Functionality

### Short Command Syntax

Many commands also have a shorthand equivalent which a single capitalised
character. These are listed at the end of the description for each command in
the online help and include:

<a name="table0"></a>
<table border="1" cellspacing="0" cellpadding="1">
  <tr>
    <th bgcolor="#99CCCC"> Command </th>
    <th bgcolor="#99CCCC" align="center"> Shorthand </th>
  </tr>
  <tr>
    <td> targets </td>
    <td> T </td>
  </tr>
  <tr>
    <td> xtargets </td>
    <td> X </td>
  </tr>
  <tr>
    <td> display </td>
    <td> D </td>
  </tr>
  <tr>
    <td> safemode </td>
    <td> S </td>
  </tr>
  <tr>
    <td> exec </td>
    <td> ! </td>
  </tr>
  <tr>
    <td> command </td>
    <td> C </td>
  </tr>
  <tr>
    <td> play </td>
    <td> P </td>
  </tr>
  <tr>
    <td> filter </td>
    <td> F </td>
  </tr>
</table>

So the following two lines are equivalent:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /targets+ <kbd>targetlist</kbd>
  <kbd>#!</kbd> /T+ <kbd>targetlist</kbd>
</pre></code>

### Colour

By default **TCLI** starts up with colour enabled and assumes that the terminal
is dark - hence the colour scheme chosen is **`light`** to gain maximum
contrast.

Colour can be toggled on/off with the command:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /color
</pre></code>

If your terminal has a light background then alternatively change the colour
scheme to be dark for better contrast:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /color_scheme dark
</pre></code>

### Customising Start Environment

If the file **`.tclirc`** exists in the users home directory then it will be
read into the buffer 'startup' and 'played' to **TCLI** as if it was a regular
buffer 'play' command. The contents of this file are then accessible from
'startup' buffer thereafter.

This allows users to customise the 'at start' environment of **TCLI**.

**Example:** if you prefer the 'dark' colour scheme and are comfortable without
safemode enabled then add the following to your **`.tclirc`** :

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /color_scheme dark
  <kbd>#!</kbd> /safemode off
</pre></code>

### Timeouts

The timeout value determines how long to wait for the device accessor to return
a result from any of the pending devices. This may need changing in unusual
situations where the command output is large. The value is specified in seconds.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /timeout 120
</pre></code>

## Display Formats and Filters

Command output can be formatted by several display filters.

Change the display format with **`/display`** (or **`-D`**).

In the cases other than *raw* a filter engine extracts the significant fields
and returns only this data in one of several formats.

### Raw

Unprocessed device output. Command return data is displayed 'as is'.

### Comma Separated Values (CSV):

Comma separated values suitable for importing into spreadsheets.

Command output is processed by the engine specified by **`filter`** and the data
returned is in a CSV table. If there are multiple targets then they are included
in the same table and the first column will be the target device name.

If data fields in the returned data are different between devices then they will
be split into separate tables.

If no template exists for a command, hence it cannot be formatted, then it is
returned in raw mode.

```
Host, ColAa, ColAb
device_a, hello, world
device_b, HELLO, WORLD
```

### Table (TBL):

Output is formatted into a user friendly tabular data. Includes padded columns
and row separators that are not as machine friendly as the *CSV* format but is
clearer for humans to read.

```
 Host      ColAa  ColAb
========================
 device_a  hello  world
 device_b  HELLO  WORLD
```

### Name Value Pairs (NVP):

Display name value pairs. One per row, suitable for row based parsing. If
multiple targets then the target name is embedded in the name field. Producing a
lined based format suitable for grep or parsing with scripts.

```
# LABEL Value
device_a.ColAa hello
device_a.ColAb world
device_b.ColAa HELLO
device_b.ColAb WORL
```

The filter engine is the
[CLI Table](https://github.com/google/textfsm/wiki/Cli- Table) textual output
parser. **TCLI** extends the functionality to support suppressing unwanted data
for more concise display. Values in the TextFSM template can be suppressed in
the default response by adding the label **`Verbose`** to the **`Value`**
entries in the template.

The set of fields returned by the engine is controlled by toggling the
**`verbose`** command in **TCLI**. This is off by default and only the most
significant fields are returned (intended to help data fit in a display). If
**`verbose`** is true then the full set of fields are returned.

## Text Buffers

### Logging and Recording

Commands and command output can be logged to a buffer with:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /log <kbd>buffername</kbd>
</pre></code>

To log both router commands and system output such as escape commands and
errors.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /logall <kbd>buffername</kbd>
</pre></code>

Alternatively to record the commands issued but skip logging the data returned
then use the **`record`** and **`recordall`** commands.

To record router commands issued:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /record <kbd>buffername</kbd>
</pre></code>

Or to record both **TCLI** escape commands and commands sent to the targets:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /recordall <kbd>buffername</kbd>
</pre></code>

**Note:** It is not possible to specify the same buffer as a destination for
multiple log/record commands.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /log abuffer
  <kbd>#!</kbd> /logall abuffer
     <kbd>Buffer: 'abuffer', already open for writing.</kbd>
</pre></code>

To see which buffers are currently in use then use the **`env`** command.

To stop writing to a log or record then either issue a **`logstop`** or
**`recordstop`** command.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /logstop <kbd>buffername</kbd>
</pre></code>

The commands **`logstop`** and **`recordstop`** are interchangeable.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /log abuffer
  <kbd>#!</kbd> /recordstop abuffer
  <kbd>#!</kbd> /logstop abuffer
     <kbd>Buffer not in use for logging or recording.</kbd>
</pre></code>

Buffers and buffer content persists after we are no longer writing to it. A
buffer can be reused for logging/recording. It will be deleted and overwritten
with the new data unless we specify a '+' as a command suffix.

To append log data:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /log+ <kbd>buffername</kbd>
</pre></code>

### Reading, Writing and Editing

To see the list of buffers active or previously used to date:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /bufferlist
</pre></code>

If a **`.tclirc`** exists (discussed below) then there will be an initial buffer
**`startup`** present.

Buffers can be edited with **`vi`** , even while being edited.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /vi <kbd>buffername</kbd>
</pre></code>

Buffers can be read and written from the local host.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /read <kbd>buffername filename</kbd>
</pre></code>

**Example:**<br/>To read the file **postmortem** into buffer **abuffer**.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /read abuffer ~/postmortem
     <kbd>122 lines read.</kbd>
</pre></code>

The command **`write`** takes a buffer and writes it to a file.

For both **`read`** and **`write`** the filename supports tilde **`~`** and
shell variable substitution.

So **`'~/$USER/file.txt`** is a valid destination and for the user **`harro`** ,
it will write to **`/home/harro/harro/file.txt`** .

### Buffer Playback

A buffer can be 'played' to **TCLI** as if it was user input. The buffer could
contain both TCLI commands and router commands.

To play the contents of a buffer:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> /play <kbd>buffername</kbd>
</pre></code>

Particular care should be taken so that you understand the contents of the
buffer and the current running environment before playing out its contents.
Attempting to playback a buffer that is currently in use for logging or
recording will result in an error message.

### Inline Escape Commands

Escape commands persist in interactive mode. Inline escape commands are a
convenient way to supply overrides on a per command basis. Inline escape
commands do not modify the persistent environment.

Inline escape commands follow the targeted command with a '//' rather than the
usual '/'. There can be any number of them (the leftmost have precedence).

e.g. The following command sequence attempts to send a command to a single
target and then repeats this with safemode disabled.

<code class="lang-shell"><pre>
  <kbd>#! &lt;[0]*&gt; !#</kbd>
  <kbd>#!</kbd> /targets device_a
  <kbd>#! &lt;device_a[1]*&gt; !#</kbd>
  <kbd>#!</kbd> show version | grep boot
  <kbd>Safe mode on, command ignored.</kbd>
  <kbd>#! &lt;device_a[1]*&gt; !#</kbd>
  <kbd>#!</kbd> show version | grep boot //safemode off
  <kbd>#!# device_a:show version | grep boot #!#</kbd>
  JUNOS Base OS boot [#####]
  <kbd>#! &lt;device_a[1]*&gt; !#</kbd>
  <kbd>#!</kbd> show version | grep boot
  <kbd>Safe mode on, command ignored.</kbd>
</pre></code>

Not all commands are supported in inline mode, some of them simply don't make
sense in this context.

The following commands can be used inline:

```
* color
* color_scheme
* display
* exit
* filter
* log
* logall
* logstop
* record
* recordall
* recordstop
* safemode
* targets
* timeout
* verbose
* xtargets
```

The behaviour is identical to its regular usage with one exception of **`exit`**
. The Exit command ceases inline command parsing at that point. Inline command
parsing occurs from right to left. This might be necessary if the data portion
of the command contains '//' strings. Inline command parsing will also cease on
the first inline command that fails to parse.

So a command:

<code class="lang-shell"><pre> <kbd>#!</kbd> file list "a file name containing a
seemingly valid //targets inlinecommand" //exit </pre></code>

Will successfully list the file with the (somewhat contrived) name "a file name
containing a seemingly valid //targets inlinecommand". Rather than sending 'file
list "a file name containing a seemingly valid' to target list 'inlinecommand'.

Further:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> show version //display raw //bogus
</pre></code>

Will fail to parse '//bogus' and send this entire string to the targets with
none of the inline commands removed.

Tab completion unfortunately doesn't work on inline commands so take care to
format them correctly to avoid them being sent to the target as targeted command
data.

## Command Modes and Pipes

Many targets support multiple command lines (or 'modes'). Such as the shell on a
Juniper or Netscaler. The shell, cli and cligated on a unix device acting as a
router.

The default mode is 'cli'. In the case of a box with no 'cli' (such as a unix
box) then cli is mapped to the primary cli equivalent such as shell. The target
mode can be changed with **`mode`**. For devices that don't support the
specified mode then it will fall back to 'cli'.

<code class="lang-shell"><pre>
  <kbd>#!</kbd> show version
  <kbd>#!</kbd> /mode shell
  <kbd>#!</kbd> ls
</pre></code>

### Executing Unix Commands

Commands can be passed to the local host for execution with **`exec`** or
**`!`** . the resultant unix output will be captured by any active **`logall`**
buffering.

### Local and Remote Pipes

Many target devices support target side filtering/formatting of command data.

**Example:** 'show version | grep Boot' is meaningful to a Juniper router.

**TCLI** supports target side pipes and also supports client side pipes with the
'||' syntax. Multiple client pipes ('||') are permitted but must be to the
'right' of any target pipes ('|') and before (to the left) of any inline
commands.

**Example:** The following will count how many tacacs servers are configured on
the targets.

<code class="lang-shell"><pre>
  <kbd>#! </kbd>sh run | grep "tacacs-server host" || wc -l //safemode off
</pre></code>

To avoid problems with '||' appearing in command data, quote the string
containing the '||'. The parser will also stop splitting output for client pipes
on encountering the first '|', so if '||' needs to appear in the command data
unquoted then add a superfulous '|' to the right hand side.

So the following commands are OK:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> sh run | grep "a || string"
  <kbd>#!</kbd> sh run | grep || | grep .
</pre></code>

But this will be incomplete:

<code class="lang-shell"><pre>
  <kbd>#!</kbd> sh run | grep ||
</pre></code>

**Note:** The display formats other than 'raw' use filter engines to parse and
extract data fields from the semi-structured device output. Using target side
filters such as grep may defeat these parsing efforts and return incomplete
data.
