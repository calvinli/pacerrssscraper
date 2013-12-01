pacer-rss
=========

Script that reads PACER RSS feeds and looks for updates in selected cases.

It can then (optionally) send an email or post on twitter (designed
for unattended operation using cron, etc). This requires certain
command-line options to be set (use `-h` to see them).

This is in active development and should not be considered usable.
(Just look at the commit log...)

*Update*: Cases to check are no longer hard-coded! In fact
the only reference to Prenda is now in the tweet message.
It now takes in the name of an SQLite3 database. The DB should
have two tables,
`cases (court TEXT, number TEXT, name TEXT)` and
`updated (court TEXT UNIQUE, time INTEGER)`.

(For reference, my current setup is this:
```
sqlite> SELECT * FROM cases;
court       number      name
----------  ----------  ------------------
cacd        543744      Ingenuity13 v. Doe
cand        254869      AFH v. Navasca
ctd         98605       AFH v. Olivas
ilnd        280638      Duffy v. Godfread
ilnd        284511      Prenda v. Internet
sqlite> SELECT * FROM updated;
court       time
----------  ----------
cacd        1385897219
cand        1385900386
ctd         1385900368
ilnd        1385899020
```
`name` overrides the official name of the case, which
is often overly verbose.)

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
