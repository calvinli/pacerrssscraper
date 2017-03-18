Note to readers
-----------------
*The code here is presented for informational purposes only, and is by no means
the ideal way to do what it does. (This program was written in 2013 for a
very limited purpose, and will probably not be helpful to you.)*

*It is not recommended that you attempt to run this code yourself if you need
to monitor PACER feeds: for that, I recommend an RSS feed reader service
with keyword alert capability.*


pacerrssscraper
=================

Customizable and extensible daemon that reads the court filing RSS feeds
of the [Public Access to Court Electronic Records](http://www.pacer.gov/)
(PACER) system and permits the reporting of metadata on federal court filings
in near real-time to arbitrary locations.

For documentation beyond what is provided below,
see the comments in the source code.

A version of this program runs on twitter as [@pacerrssscraper](https://twitter.com/pacerrssscraper).

### License ###
The source code of this program is licensed under the MIT License,
the terms of which are in the source and at http://opensource.org/licenses/MIT.

Dependencies
--------------
**Python 3.4.0 or newer**.

The following Python packages. Install by downloading them and running
`python3 setup.py install`. Use the `--user` flag if you do not have root.

* **feedparser**: Available at https://pypi.python.org/pypi/feedparser.
* **BeautifulSoup**: Available at http://www.crummy.com/software/BeautifulSoup/.
* **Twitter** (optional): *Python Twitter Tools*, https://github.com/sixohsix/twitter.
    You will also need API keys (see below).

The recommended **MySQL** wrapper library, should you need one, is the official Oracle
`mysql.connector` package, "platform-independent" version. Install as above.

Use
------
To use this program for your own purposes, fork this and write your own
`make_notifier` (together with any custom notifiers) and `entry_filter`,
modify the main loop as necessary, and supply a `VERSION` string.
(Search for `****REPLACE THIS****`.)

A few notifiers are included. The default configuration (which you will need
to change) checks all RSS-enabled district courts and reports no entries.

### Twitter use ###
Using this on twitter requires the creation of an application with write
access; see [apps.twitter.com](https://apps.twitter.com/). Then give
this program the provided four API keys. *Never put API keys in public
source code.*

Inputs
---------
Which courts this script checks, and which cases it will report, are up to you;
this is decided in the `entry_filter` function.

One way is reporting all cases on a particular list; this is what `read_cases`
is for. It takes in a JSON list like

```json
[
  {"name": "Ingenuity13 v. Doe #Prenda", "number": 543744, "court": "cacd"},
  {"name": "Duffy v. Godfread #Prenda", "number": 280638, "court": "ilnd"},
  {"name": "#Prenda v. Internets", "number": 284511, "court": "ilnd"},
]
```

The list can be changed while the program is running.

Another way would be keyword-matching on the case name
or document title. For a full list of fields which can
be matched on, see the documentation for the `RSSEntry`
class.

List of US District Courts with RSS feeds 
-----------------------------------------
Derived from http://www.pacer.gov/psco/cgi-bin/links.pl.

These are the only courts that this script can monitor.

```python
["almd", "alsd", "akd", "ared", "arwd",
 "cacd", "cand", "casd", "ctd", "ded", "dcd",
 "flmd", "flsd", "gamd", "gud", "idd", "ilcd",
 "ilnd", "innd", "iand", "iasd", "ksd", "kywd",
 "laed", "lamd", "lawd", "mad", "mied", "miwd",
 "moed", "mowd", "mtd", "ned", "nhd", "njd",
 "nyed", "nynd", "nysd", "nced", "ncmd", "ncwd",
 "nmid", "ohnd", "ohsd", "okwd", "paed", "pawd",
 "prd", "rid", "sdd", "tned", "tnmd", "txed",
 "txsd", "txwd", "utd", "vtd", "vid", "waed",
 "wvnd", "wvsd", "wied", "wiwd", "wyd"]
```
