pacer-rss
=========

Script that reads PACER RSS feeds and looks for updates in selected cases.
(Currently these are hardcoded into the script as `cases`.)

It can then (optionally) send an email or post on twitter (designed
for unattended operation using cron, etc). This requires certain
command-line options to be set (use `-h` to see them).

This is in active development and should not be considered usable.
(Just look at the commit log...)


List of US District Courts with RSS feeds 
-----------------------------------------
As given at http://www.pacer.gov/psco/cgi-bin/links.pl.

These are the only courts that this script can monitor.

```python
["almd", "alsd", "ared", "arwd", "cacd", "cand", "ctd",
 "dcd", "flmd", "flsd", "gamd", "gud", "idd", "ilcd",
 "ilnd", "iand", "iasd", "ksd", "kywd", "laed", "lamd",
 "lawd", "mied", "miwd", "moed", "mowd", "mtd", "ned",
 "nhd", "njd", "nyed", "nynd", "nced", "ncmd", "ncwd",
 "nmid", "ohnd", "ohsd", "okwd", "paed", "pawd", "prd",
 "rid", "sdd", "tned", "tnmd", "txed", "txsd", "utd",
 "vtd", "vid", "vawd", "wvnd", "wied", "wiwd"]
```
