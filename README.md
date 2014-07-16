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
is for. It reads in data from an SQLite3 database. The database should have
a table `cases`, with schema `cases (court TEXT, number INTEGER, name TEXT)`.

Example from [@pacerrssscraper](https://twitter.com/pacerrssscraper):
```
sqlite> SELECT * FROM cases ORDER BY name DESC;
court  number    name                                    
-----  --------  ----------------------------------------
cacd   543744    Ingenuity13 v. Doe #Prenda              
ilnd   280638    Duffy v. Godfread #Prenda               
ctd    98605     AFH v. Olivas #Prenda                   
ilnd   284511    #Prenda v. Internets                    
```
`name`, which is required, overrides the official name of the case.
(The hashtags are for tweeting.)

Another way would be keyword-matching on the case name
or document title. For a full list of fields which can
be matched on, see the documentation for the `RSSEntry`
class.

List of US District Courts with RSS feeds 
-----------------------------------------
Derived from http://www.pacer.gov/psco/cgi-bin/links.pl.

These are the only courts that this script can monitor.

```python
["almd", "alsd", "ared", "arwd", "cacd", "cand", "ctd",
 "dcd", "flmd", "flsd", "gamd", "gud", "idd", "ilcd",
 "ilnd", "innd", "iand", "iasd", "ksd", "kywd", "laed",
"lamd", "lawd", "mied", "miwd", "moed", "mowd", "mtd",
"ned", "nhd", "njd", "nyed", "nynd", "nced", "ncmd", 
"ncwd", "nmid", "ohnd", "ohsd", "okwd", "paed", "pawd", 
"prd", "rid", "sdd", "tned", "tnmd", "txed", "txsd", 
"utd", "vtd", "vid", "vawd", "wvnd", "wied", "wiwd"]
```
