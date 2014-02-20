pacerrssscraper
=================

Daemon that reads PACER RSS feeds and looks for updates in selected cases.

If `--twitter` is set it will tweet about entries it finds; if `--email` is
set it will email new entries.
(NB: Both require certain command-line arguments to be set.)

The program now takes in the name of an SQLite3 database.
The database should have a table `cases`,
`cases (court TEXT, number INTEGER, name TEXT)`.

(For reference, my current setup is this:
```
sqlite> SELECT * FROM cases ORDER BY name DESC;
court  number    name                                    
-----  --------  ----------------------------------------
cacd   543744    Ingenuity13 v. Doe #Prenda              
ilnd   280638    Duffy v. Godfread #Prenda               
ctd    98605     AFH v. Olivas #Prenda                   
cand   259654    (not © related) Stewart et al v. Gogo  
ilnd   284511    #Prenda v. Internets                    
miwd   70867     #MalibuMedia v. Roy 12-617              
flsd   404544    #MalibuMedia v. Pelizzo 12-22768        
innd   73135     #MalibuMedia v. Nguyen 13-163           
mied   281102    #MalibuMedia v. House 13-12218          
flsd   434643    #MalibuMedia v. Doe 14-20216            
ilnd   287384    #MalibuMedia v. Doe 13-6372             
ilnd   287310    #MalibuMedia v. Doe 13-6312             
wied   63285     #MalibuMedia v. Doe 13-536              
ilnd   287444    #MalibuMedia v. Doe 13-50287            
ilnd   287443    #MalibuMedia v. Doe 13-50286            
ilnd   285400    #MalibuMedia v. Doe 13-4968             
ilnd   283630    #MalibuMedia v. Doe 13-3707             
ilnd   283541    #MalibuMedia v. Doe 13-3648             
ilnd   282178    #MalibuMedia v. Doe 13-2710             
ilnd   282170    #MalibuMedia v. Doe 13-2702
```
`name`, which is required, overrides the official name of the case. I use hashtags because `name` is included in tweets.)

*New in the latest version*: Cases can be added or removed while the daemon is running; there is no need to restart the daemon.

List of US District Courts with RSS feeds 
-----------------------------------------
As given at http://www.pacer.gov/psco/cgi-bin/links.pl.

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
