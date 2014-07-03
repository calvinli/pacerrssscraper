#! /usr/bin/env python3
#
# PACER RSS feed scraper and reporter.
#
#
# Author: Calvin Li
#
# +-------------------------------------------------------------------------------+
# |                                                                               |  
# | The MIT License (MIT)                                                         |
# |                                                                               |
# | Copyright (c) 2013-2014 Calvin Li                                             |
# |                                                                               |
# | Permission is hereby granted, free of charge, to any person obtaining a copy  |
# | of this software and associated documentation files (the "Software"), to deal |
# | in the Software without restriction, including without limitation the rights  |
# | to use, copy, modify, merge, publish, distribute, sublicense, and/or sell     |
# | copies of the Software, and to permit persons to whom the Software is         |
# | furnished to do so, subject to the following conditions:                      |
# |                                                                               |
# | The above copyright notice and this permission notice shall be included in    |
# | all copies or substantial portions of the Software.                           |
# |                                                                               |
# | THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR    |
# | IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,      |
# | FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE   |
# | AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER        |
# | LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, |
# | OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN     |
# | THE SOFTWARE.                                                                 |
# |                                                                               |
# +-------------------------------------------------------------------------------+
#
import feedparser
from time import asctime, gmtime, sleep
from datetime import datetime, timedelta
from calendar import timegm
import sys
import os
import signal
from twitter import * # https://github.com/sixohsix/twitter/tree/master
import smtplib
from email.mime.text import MIMEText
import re
import argparse
import sqlite3
import traceback
import socket
from urllib.error import URLError
from xml.sax import SAXException
from collections import OrderedDict
import logging, logging.handlers
import html.parser
# from html import unescape   # for python3.4.0+

# PACER servers frequently have problems.
# Ensure that connections don't hang.
socket.setdefaulttimeout(10) 

#### REMOVE FOR PYTHON 3.4.0+ ###
_h = html.parser.HTMLParser()
unescape = _h.unescape

def get_feed(url):
    feed = feedparser.parse(url)

    if feed.bozo and feed.bozo_exception:
        raise feed.bozo_exception

    return feed

def send_tweet(entry, oauth_token, oauth_secret, consumer_key, consumer_secret):
    """entry should be an RSSEntry object."""

    twitter = Twitter(auth=OAuth(oauth_token, oauth_secret,
                                 consumer_key, consumer_secret))

    case = entry.case_name
    title = entry.title
    link = entry.link
    number = entry.number if entry.number > 0 else "?"

    # Shorten the case name
    rules = [
     ("Malibu Media", "#MalibuMedia"),
     ("MALIBU MEDIA", "#MalibuMedia"),
     (", LLC", ""),
     (" LLC", ""),
     (" v. ", " v "),
     ("JOHN DOE SUBSCRIBER ASSIGNED IP ADDRESS ", ""),
     ("John Doe Subscriber Assigned IP Address ", ""),
     (" subscriber assigned IP address", ""),
     ("JOHN DOE", "Doe"),
     ("John Doe", "Doe")
    ]

    for r in rules:
        case = case.replace(*r)

    # truncate the description to fit
    if len(case) + len(title) > 100:
        if len(case) > 60:
            case = case[:57]+"..."
        space = 100 - len(case)
        title = title[:space-3] + "..."

    message = "{} ({}): #{} {}. ".format(
              case, entry.court, number, title)

    if len(message) > 120:
        log.critical("Bad tweet truncation!")
        return

    message += entry.link

    try:
        twitter.statuses.update(status=message)
        log.info("Successfully sent the following tweet: \"{}\"".format(message))
    except TwitterHTTPError:
        log.exception("Tweet failed. Probably a duplicate.")

class RSSEntry:
    """
    This class encapsulates everything we know about
    a new document from the RSS feed.

    Fields
    ----------
    - title:         As given by the RSS feed, so this doesn't always
                     match the actual title in the PDF / docket.
                     From experience, this appears to be more of
                     a categorization of the filing than its title.
    - time_filed:    I am not sure if the provided date/time is accurate
                     because there actually isn't any way to independently
                     verify this information (time of filing
                     does not appear anywhere in PACER).
                     This is a time.struct_time.
    - court:         The court in which the document was filed;
                     equivalent to the 3rd LREF element.
    - case:          The "caption", i.e. 4th element in the LREF
    - case_name:     In human-readable form.
    - pacer_num:     The internal "PACER" number of the case. This allows
                     references to RECAP.
    - docket_link:   The url of the PACER docket for this case.
    - link*:         A link at which the document itself may be viewed.
    - number*:       The number of the document within the docket.

    * Some entries are not numbered. In this case link will equal
      docket_link and number will be 0. This will break LREF
      and the second RECAP link.

    Other attributes on-the-fly as defined below.

    Re: LREF, see http://www.plainsite.org/articles/article.html?id=7
    """
    def __init__(self, entry):
        """Construct an RSSEntry object out of the actual RSS entry."""

        # code adapted from the old parse_entry()

        # p.search() returns None if the search fails.
        # (Entries routinely lack several of these fields.)

        # get the link itself (to the actual document)
        p = re.compile("href=\"(.*)\"") 
        r = p.search(entry['description'])
        self._link = r.group(1) if r else ""

        # extract the document number
        p = re.compile(">([0-9]+)<") 
        r = p.search(entry['description'])
        self.number = int(r.group(1)) if r else 0

        # title
        p = re.compile("^\[(.+)\]")
        r = p.search(entry['summary'])
        self.title = unescape(r.group(1)) if r else "?"

        # court
        p = re.compile("ecf\.([a-z]+)\.")
        r = p.search(entry['link'])
        self.court = r.group(1) if r else "?"

        # PACER number
        p = re.compile("DktRpt.pl\?([0-9]+)")
        r = p.search(entry['link'])
        self.pacer_num = r.group(1) if r else 0
        # 0 is potentially a valid PACER number though, so beware

        self.docket_link = entry['id']

        self.case_name = unescape(" ".join(entry['title'].split(" ")[1:]))

        self.case = entry['title'].split(" ")[0].replace(":", "-")
        # strip judge initials out
        self.case = self.case.split("-")
        for part in self.case[3:]:
            if part.isalpha():
                self.case.remove(part)
        self.case = "-".join(self.case)

        self.time_filed = entry['published_parsed']

    @property
    def RECAP_links(self):
        """Get the RECAP links for this case and document.
        
        Because of RECAP's standardized URL system, we know
        what the URL of a document will be even before the
        document is posted there.
        
        This returns a 2-tuple of strings, the first of which
        is the URL of the case and the second, the URL
        of the document.
        
        Out of necessity, neither is verified.
        """
        RECAP_case = "gov.uscourts.{}.{}".format(self.court, self.pacer_num)
        RECAP_doc = RECAP_case + ".{}.0.pdf".format(self.number)

        return ("https://archive.org/details/"+RECAP_case,
               "https://archive.org/download/"+RECAP_case+"/"+RECAP_doc)
    
    @property
    def LREF(self):
        return "gov.uscourts.{}.{}.{}.0".format(self.court, self.case, self.number)

    @property
    def link(self):
        """Override link attribute."""
        return self._link if self.number > 0 else self.docket_link

    def __repr__(self):
        return "RSSEntry "+str({
            "title": self.title,
            "time_filed": self.time_filed,
            "court": self.court,
            "case": self.case,
            "case_name": self.case_name,
            "pacer_num": self.pacer_num,
            "docket_link": self.docket_link,
            "link": self.link,
            "number": self.number,
            "LREF": self.LREF})


def scrape(court, filter, last_checked, notifier):
    """Scrape for certain cases in the given court.

    Arguments:
    - court: the court to check
    - filter: predicate returning whether a case should be reported
    - last_checked: struct_time of when this court was last checked (UTC!)
    - notifier: result of calling make_notifier

    Returns when the scraped feed was generated as a datetime object.
    """
    feed = get_feed(
            "https://ecf.{}.uscourts.gov/cgi-bin/rss_outside.pl".format(court))
    entries = OrderedDict()

    last_updated = feed['feed']['updated_parsed']
    if last_updated <= last_checked:
        log.debug("Feed has not been updated.")
        return datetime.utcfromtimestamp(timegm(last_updated))

    for entry in feed['entries']:
        if entry['published_parsed'] < last_checked:
            # We have checked all new entries.
            log.debug("Read all new entries.")
            break
 
        if filter(entry):
            log.info(entry)

            info = RSSEntry(entry) 

            if info.link in entries:
                entries[info.link].title += " // "+info.title
            else:
                entries[info.link] = info

    for e in reversed(list(entries.values())):
        log.info("reporting the following:")
        log.info(e)
        notifier(e)

    log.debug("Scrape of {} completed.".format(court))
    return datetime.utcfromtimestamp(timegm(last_updated))

###################

def read_cases(filename):
    cases = {}
    aliases = {}

    conn = sqlite3.connect(filename)
    c = conn.cursor()
    c.execute("SELECT * FROM cases;")

    for court, case, name in c:
        case = str(case)
        if court in cases:
            cases[court].append( case )
        else:
            cases[court] = [case]
        aliases[case] = name

    c.close()

    return cases, aliases

def sql_notifier(entry, db):
    """Log reported entries to an SQLite3 database."""
    if entry.number == 0:
        # Abort --- it won't have a sensible LREF
        return

    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.execute("""INSERT INTO filings
                 (time, lref, case_name, number, title, pacer)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (timegm(entry.time_filed), entry.LREF, entry.case_name,
                  entry.number, entry.title, entry.link))

    conn.commit()
    c.close()

    log.debug("sql-logged {}".format(entry.LREF))

def make_notifier(creds, sql_db):
    """Make a notifier function with access to credentials, etc.
    
    Modify this to add/remove custom notifiers."""
    def notify(entry):
        send_tweet(entry, creds['oauth_token'], creds['oauth_secret'],
                   creds['consumer_key'], creds['consumer_secret'] )
        sql_notifier(entry, sql_db)

    return notify

if __name__ == '__main__':
    # get command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", action='store')
    parser.add_argument("--log", action='store')
    parser.add_argument("--verbose", "-v", action='count', default=0)
    parser.add_argument("--email", action='store_true')
    parser.add_argument("--twitter", action='store_true')
    for arg in ["--e-from", "--e-pass", "--e-to",
                "--t-oauth-token", "--t-oauth-secret",
                "--t-consumer-key", "--t-consumer-secret"]:
        parser.add_argument(arg, action='store', default="")
    args = parser.parse_args()

    DB = args.db
    log_location = args.log
    verbosity = min(3, args.verbose) # verbosity breaks after -vvv
 
    notifier = make_notifier(creds = {
        'oauth_token': args.t_oauth_token,
        'oauth_secret': args.t_oauth_secret,
        'consumer_key': args.t_consumer_key,
        'consumer_secret': args.t_consumer_secret
    },
    sql_db="malibu-filings.db")    

    # set up a logger (separate from notifier)
    log = logging.getLogger("pacerrssscraper-malibu")
    log.setLevel(logging.DEBUG)

    log_format = logging.Formatter(fmt="[{asctime}] * {levelname}: {message}",
            datefmt="%a %b %d %X %Y %Z", style="{")
    # use UTC time instead of local time since
    # the RSS feeds' times are given in UTC
    log_format.converter = gmtime

    log_stdout = logging.StreamHandler()
    log_stdout.setLevel(logging.ERROR - 10*verbosity)
    log_stdout.setFormatter(log_format)
    log.addHandler(log_stdout)

    if log_location:
        # WatchedFileHandler allows for the log file
        # to be modified or even moved underneath us.
        log_file = logging.handlers.WatchedFileHandler(log_location)
        log_file.setLevel(logging.ERROR - 10*verbosity)
        log_file.setFormatter(log_format)
        log.addHandler(log_file)

    # ------------------------------

    log.critical("Starting...")
    log.info("We are process {}".format(os.getpid()))

    # set up a SIGTERM handler
    def quit(signal, frame):
        log.critical("Received SIGTERM. Quitting.\n--------------------\n")
        sys.exit(0)
    signal.signal(signal.SIGTERM, quit)
    signal.signal(signal.SIGINT, quit)

    # ------------------------------

    RSS_COURTS = ["almd", "alsd", "ared", "arwd", "cacd", "cand", "ctd",
              "dcd", "flmd", "flsd", "gamd", "gud", "idd", "ilcd",
              "ilnd", "innd", "iand", "iasd", "ksd", "kywd", "laed",
              "lamd", "lawd", "mied", "miwd", "moed", "mowd", "mtd",
              "ned", "nhd", "njd", "nyed", "nynd", "nced", "ncmd",
              "ncwd", "nmid", "ohnd", "ohsd", "okwd", "paed", "pawd",
              "prd", "rid", "sdd", "tned", "tnmd", "txed", "txsd",
              "utd", "vtd", "vid", "vawd", "wvnd", "wied", "wiwd"]

    MALIBU_COURTS = ["cacd", "caed", "casd", "cod", "dcd", "flmd",
        "flnd", "fsd", "ilcd", "ilnd", "innd", "insd", "mdd", "mied",
        "miwd", "njd", "nyed", "nysd", "ohsd", "paed", "pamd", "txnd",
        "vaed", "wied", "wiwd"]

    # RSS_COURTS & MALIBU_COURTS
    MALIBU_RSS_COURTS = ['njd', 'innd', 'mied', 'cacd', 'wiwd', 'nyed', 'wied', 'ohsd', 'ilnd', 'miwd', 'ilcd', 'flmd', 'dcd', 'paed']

    # Number of minutes to wait between checks of a given court.
    # This could probably be tuned somewhat.
    CHECK_INTERVAL = timedelta(minutes=35)

    last_updated = {}
    next_check = {}

    # Main loop
    while True:
        # Load case and court information from database
        if DB:
            cases, aliases = read_cases(os.path.dirname(os.path.realpath(__file__))+"/"+DB)
        else:
            # In the absence of a provided database file, we assume that there isn't
            # a pre-generated list of cases to look at.
            cases, aliases = {}, {}
        
        for court in RSS_COURTS:
            if court not in cases:
                cases[court] = []

        for court in (cases.keys() - next_check.keys()):
            log.info("Adding {}.".format(court))

            # suppress most logging in this next part
            # (scrape does a bunch of logging that we're
            #  not interested in right now)
            logging.disable(logging.ERROR)
            try:
                # we're not really trying to scrape, we're just getting
                # when it was last updated (which scrape() returns)
                last_updated[court] = scrape(court, lambda x: False, gmtime(), lambda x: None)
            except Exception:
                # in the case of errors, just set last_updated
                # to... something...
                #
                # (last_updated will end up syncing to the court's
                #  actual update schedule later, so we'll be fine)
                last_updated[court] = datetime.utcnow()

            # re-enable logging
            logging.disable(logging.NOTSET)

            next_check[court] = last_updated[court] + CHECK_INTERVAL

        # error check
        for court in MALIBU_RSS_COURTS:
            assert court in cases.keys(), court+" "+str(cases)

        now = datetime.utcnow()

        courts_to_check = list(filter(lambda c: next_check[c] < now, next_check));

        log.info("Checking {}...".format(", ".join(courts_to_check)))

        for court in courts_to_check:
            try:
                last_updated[court] = scrape(court,
                                             lambda entry: "malibu media" in entry['title'].lower(),
                                             last_updated[court].timetuple(),
                                             notifier) 
                next_check[court] = last_updated[court] + CHECK_INTERVAL
            except socket.timeout:
                # treat timeouts specially because they seem to happen a lot
                log.warning("Timed out while getting feed for {}.".format(court))
                continue
            except URLError as e:
                if len(e.args) > 0 and type(e.args[0]) == socket.timeout:
                    log.warning("Timed out while getting feed for {}.".format(court))
                else:
                    # treat like generic Exception, see below
                    log.exception(court)
                continue
            except SAXException as e:
                # Means we got invalid XML.
                log.warning("Invalid XML in feed for {}.".format(court))

                # We could use log.exception(), but I don't really
                # care for the whole stack trace (it isn't even
                # a problem in this code, after all :P).
                # Just print out the exception, which will contain
                # a line and column number.
                log.info(e)
            except Exception as e:
                # traceback is printed automatically by logger
                log.exception(court)
                continue

            # A note on error handling here:
            #
            # With continue statements above, courts that hit errors
            # will be queried again in five minutes, rather than in
            # CHECK_INTERVAL. If the continue statements were to
            # be removed, then the code below would ensure that they
            # get checked no sooner than CHECK_INTERVAL.


            # Don't let next_check[court] be in the past.
            #
            # Without this, certain courts get clobbered
            while next_check[court] < now:
                next_check[court] += CHECK_INTERVAL

            log.debug("{} will be next checked at {} UTC.".format(court,
                                    asctime(next_check[court].timetuple())))
        log.info("Checks complete.")

        # keep at least a modicum of sanity
        sleep(300)
