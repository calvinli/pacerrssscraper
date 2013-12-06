pacer-rss
=========

Daemon that reads PACER RSS feeds and looks for updates in selected cases.

If `--twitter` is set it will tweet about entries it finds.

This is in active development and should not be considered usable.
(Just look at the commit log...)

*Update*: Cases to check are no longer hard-coded! In fact
the only reference to Prenda is now in the tweet message.
It now takes in the name of an SQLite3 database. The DB should
have a table `cases`,
`cases (court TEXT, number TEXT, name TEXT)`

(For reference, my current setup is this:
```
sqlite> SELECT * FROM cases;
court       number      name
----------  ----------  ------------------
cacd        543744      Ingenuity13 v. Doe
ctd         98605       AFH v. Olivas
ilnd        280638      Duffy v. Godfread
ilnd        284511      Prenda v. Internet
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
 "ilnd", "iand", "iasd", "innd", "ksd", "kywd", "laed",
"lamd", "lawd", "mied", "miwd", "moed", "mowd", "mtd",
"ned", "nhd", "njd", "nyed", "nynd", "nced", "ncmd", 
"ncwd", "nmid", "ohnd", "ohsd", "okwd", "paed", "pawd", 
"prd", "rid", "sdd", "tned", "tnmd", "txed", "txsd", 
"utd", "vtd", "vid", "vawd", "wvnd", "wied", "wiwd"]
```
