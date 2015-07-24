#! /usr/bin/env python3
"""
 PACER RSS feed scraper and reporter
 ========================================


 ----GENERIC VERSION----

 To use this program for your own purposes, fork this and write your own
 `make_notifier` (together with any custom notifiers) and `entry_filter`,
 modify the main loop as necessary, and supply a VERSION string.
 (Search for "****REPLACE THIS****".)

 A few notifiers are included. The default configuration checks only
 for cases that are specified on a list (see `read_cases`) and uses a
 dummy notifier.


 Author: Calvin Li
 License: MIT (see below)

 Testing
 ----------
 There should be test cases in ./tests. This module should also pass
 pylint with 10.00/10 with the provided disable pragmas.


 License
 ----------
 The MIT License (MIT)

 Copyright (c) 2013-2014 Calvin Li

 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:

 The above copyright notice and this permission notice shall be included in
 all copies or substantial portions of the Software.

 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 THE SOFTWARE.
"""
import feedparser
from time import gmtime, sleep
from datetime import datetime, timedelta, tzinfo
from calendar import timegm # inverse of gmtime
import sys
import traceback
import os
import signal
import smtplib
from email.mime.text import MIMEText
import re
from pprint import pformat
import argparse
import socket
from urllib.error import URLError
from xml.sax import SAXException
from collections import OrderedDict, defaultdict
import logging, logging.handlers
from html import unescape
# https://github.com/sixohsix/twitter/tree/master
from twitter import Twitter, OAuth, TwitterHTTPError
import json
import sqlite3
from bs4 import BeautifulSoup

# pylint: disable=C0103,R0902,W0142,W0232,W0621,W0703

VERSION = "generic-0.4"

# PACER servers frequently have problems.
# Ensure that connections don't hang.
socket.setdefaulttimeout(10)


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
    - time_filed:    This is an offset-aware datetime object.
                     I am not sure if the provided date/time is accurate
                     because there actually isn't any way to independently
                     verify this information (time of filing
                     does not appear anywhere in PACER).
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
    # Pre-compiled regular expressions used in every invocation of __init__()
    p_link = re.compile(r'href="(.*)\?(.*)"')
    p_number = re.compile(r'>([0-9]+)<')
    p_title = re.compile(r'\[(.+)\]')
    p_court = re.compile(r'ecf\.([a-z]+)\.')
    p_pacer_num = re.compile(r'DktRpt.pl\?([0-9]+)')


    def __init__(self, entry):
        """Construct an RSSEntry object out of the actual RSS entry."""

        # code adapted from the old parse_entry()

        # get the link itself (to the actual document)
        # (this also strips the query strings)
        match = self.p_link.search(entry['summary'])
        self._link = unescape(match.group(1)) if match else ""

        # extract the document number
        match = self.p_number.search(entry['summary'])
        self.number = int(match.group(1)) if match else 0

        # title
        match = self.p_title.search(entry['summary'])
        self.title = unescape(match.group(1)) if match else "?"
        # PACER likes to put HTML in the title. Take it out.
        if "<" in self.title:
            self.title = ''.join(BeautifulSoup(self.title).findAll(text=True))

        # court
        match = self.p_court.search(entry['link'])
        self.court = match.group(1) if match else "?"

        # PACER number
        match = self.p_pacer_num.search(entry['link'])
        self.pacer_num = match.group(1) if match else 0
        # 0 is potentially a valid PACER number though, so beware

        self.docket_link = unescape(entry['id'].split("&")[0])

        self.case_name = unescape(" ".join(entry['title'].split(" ")[1:]))
        if "<" in self.case_name:
            self.case_name = ''.join(BeautifulSoup(self.case_name).findAll(text=True))

        self.case = entry['title'].split(" ")[0].replace(":", "-")

        # strip off judge initials and criminal case sub-numbers
        self.case = self.case.split("-")[:4]
        # restore colon
        self.case = self.case[0] + ":" + "-".join(self.case[1:])

        self.time_filed = st2dt(entry['published_parsed'])

    @property
    def recap_links(self):
        """Get the RECAP links for this case and document.

        Because of RECAP's standardized URL system, we know
        what the URL of a document will be even before the
        document is posted there.

        This returns a 2-tuple of strings, the first of which
        is the URL of the case and the second, the URL
        of the document.

        Out of necessity, neither is verified.
        """
        recap_case = "gov.uscourts.{}.{}".format(self.court, self.pacer_num)
        recap_doc = recap_case + ".{}.0.pdf".format(self.number)

        return ("https://archive.org/details/"+recap_case,
                "https://archive.org/download/"+recap_case+"/"+recap_doc)

    @property
    def lref(self):
        """LREF as a str.
        If the number of the document is not known, this uses 0.
        """
        return "gov.uscourts.{}.{}.{}.0".format(
            self.court, self.case.replace(":", "-"), self.number)

    @property
    def link(self):
        """Override link attribute."""
        return self._link if self.number > 0 else self.docket_link

    def __repr__(self):
        return "RSSEntry "+pformat({
            "title": self.title,
            "time_filed": dtfmt(self.time_filed),
            "court": self.court,
            "case": self.case,
            "case_name": self.case_name,
            "pacer_num": self.pacer_num,
            "docket_link": self.docket_link,
            "link": self.link,
            "number": self.number,
            "lref": self.lref})


def scrape(court, entry_filter, last_checked, notifier):
    """Scrape for certain cases in the given court.

    Arguments:
    - court: the court to check
             The available courts are listed somewhere below, in the readme, and
             at http://www.pacer.gov/psco/cgi-bin/links.pl.
    - entry_filter: predicate returning whether an entry should be reported
                    The predicate should take a single argument, an RSSEntry
                    object, and return a boolean value.
    - last_checked: an offset-aware datetime object representing
                    the point at which we should stop scraping
                    Recommended value: the return value of the last
                    invocation of this function on this court.
    - notifier: result of calling make_notifier
                Or in general, any function which takes an RSSEntry object.

    Returns:
        when the scraped feed was generated as an offset-aware datetime object
    """
    feed = feedparser.parse(
        "https://ecf.{}.uscourts.gov/cgi-bin/rss_outside.pl".format(court))
    if feed.bozo and feed.bozo_exception:
        raise feed.bozo_exception

    # We key entries on their URLs so we can detect duplicates.
    # OrderedDict is used to keep them in chronological order.
    entries = OrderedDict()

    last_updated = st2dt(feed['feed']['updated_parsed'])

    # Ignore the feed if it has no entries. Yes, this really does happen:
    #
    # $ date
    # Fri Jul 11 22:27:31 EDT 2014
    # $ curl https://ecf.mtd.uscourts.gov/cgi-bin/rss_outside.pl
    # <?xml version="1.0" encoding="ISO-8859-1"?>
    # <rss version="2.0"
    #  xmlns:blogChannel="http://backend.userland.com/blogChannelModule"
    # >
    # <channel>
    # <title>District Of Montana - Recent Entries</title>
    # <link>https://ecf.mtd.uscourts.gov</link>
    # <description>Docket entries of type: All</description>
    # <lastBuildDate>Sat, 12 Jul 2014 01:59:54 GMT</lastBuildDate>
    # </channel>
    # </rss>

    if len(feed['entries']) == 0:
        return last_updated

    # Check to make sure that last_updated is at least as recent as the first
    # (most recent) entry. This constraint *should* always hold but has not
    # on occasion in the District for the Northern Mariana Islands.

    latest_entry_time = st2dt(feed['entries'][0]['published_parsed'])
    if latest_entry_time > last_updated:
        log.error("{} IS LYING ABOUT UPDATE TIME! ".format(court) +
                  "Claimed {} but latest entry is from {}. ".format(
                      dtfmt(last_updated), dtfmt(latest_entry_time))+
                  "Attempting to recover...")
        last_updated = latest_entry_time

    if last_updated <= last_checked:
        log.debug("{} has not been updated.".format(court))
        return last_updated

    log.debug("{} was updated at {}.".format(court, dtfmt(last_updated)))

    for entry in feed['entries']:
        if st2dt(entry['published_parsed']) <= last_checked:
            # We have checked all new entries.
            log.debug("Read all new entries for {}.".format(court))
            break

        info = RSSEntry(entry)

        if entry_filter(info):
            log.debug(info)

            # Deduplication
            if info.link in entries:
                # This deals with criminal cases which have sub-cases.
                # In this case many documents will appear with identical
                # URLs and titles.
                if entries[info.link].title == info.title:
                    continue

                # Instead of reporting as another RSSEntry,
                # append this title to the previously seen one(s).
                entries[info.link].title += " // "+info.title
            else:
                entries[info.link] = info

    # report entries in what *should* be chronological order
    for entry in reversed(list(entries.values())):
        log.info("reporting the following:")
        log.info(entry)

        try:
            notifier(entry)
        except Exception:
            # Catch exceptions here in attempt to prevent
            # throwing an exception without returning the
            # correct last_updated.
            # `Exception` is necessary otherwise
            # sys.exit() is also caught.
            log.exception(entry)

    log.debug("Scrape of {} completed.".format(court))
    return last_updated

# Convenience functions for dealing with times
class UTC(tzinfo):
    """UTC time zone. The default timezone.utc object is both
    too overpowered and prints the timezone name as "UTC+00:00",
    which is annoying and not changeable."""
    def utcoffset(self, dt):
        return timedelta(0)
    def tzname(self, dt):
        return "UTC"
    def dst(self, dt):
        return timedelta(0)
UTC = UTC()
def st2dt(struct_time):
    """Convert a UTC struct_time (as returned by, e.g., time.gmtime() and
    feedparser) to an offset-aware datetime object in UTC."""
    return datetime.fromtimestamp(timegm(struct_time), UTC)
def dtnow():
    """Offset-aware datetime object representing the
    current time (time of calling this function)."""
    return datetime.now(UTC)
def dtfmt(dt):
    """Date formatting to `Thu Jan 01 00:00:00 1970 UTC`"""
    return dt.strftime("%a %b %d %X %Y %Z")

###################

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
        # ****REPLACE THIS****
        (" v. ", " v "),
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

    message += link

    try:
        twitter.statuses.update(status=message)
        log.info("Successfully tweeted: \"{}\"".format(message))
    except TwitterHTTPError:
        log.exception("Tweet failed. Probably a duplicate.")

def sql_notifier(entry, db):
    """Log reported entries to an SQLite3 database."""
    if entry.number == 0:
        # Abort --- it won't have a sensible LREF
        return

    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.execute("""INSERT INTO filings
                 (time, lref, case_name, number, title, pacer, court)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (timegm(entry.time_filed), entry.LREF, entry.case_name,
               entry.number, entry.title, entry.link, entry.court))

    conn.commit()
    c.close()

    log.debug("sql-logged {}".format(entry.lref))

def send_email(entry, email_account, email_pass, email_to):
    """Send an email containing `entry`.
    Note: currently only works on Gmail.

    **Not tested**
    """

    s = smtplib.SMTP()
    s.connect("smtp.gmail.com", 587)
    s.starttls()
    s.login(email_account, email_pass)

    message = MIMEText(str(entry))
    message['Subject'] = "New PACER entry in {}".format(entry.case_name)
    message['From'] = "pacerrssscraper"
    s.send_message(message, from_addr=email_account, to_addrs=email_to)
    s.quit()

def make_notifier(*args, **kwargs):
    """Make a notifier function with access to credentials, etc.

    Modify this to add/remove custom notifiers."""
    # pylint: disable=W0613

    def notify(entry):
        """Generate a notification about `entry`, which is an
        RSSEntry object.
        This function has access to `args` and `kwargs`
        from `make_notifer`.
        """
        pass # ****REPLACE THIS****

    return notify

def read_cases(filename):
    """Read in a list of cases (PACER numbers) and aliases for them.

    This takes a basic unstructured JSON list of cases to follow, like

    [
      {"name": "Ingenuity13 v. Doe #Prenda", "number": 543744, "court": "cacd"},
      {"name": "Duffy v. Godfread #Prenda", "number": 280638, "court": "ilnd"},
      {"name": "#Prenda v. Internets", "number": 284511, "court": "ilnd"},
    ]

    and compiles it to two python dictionaries:
        cases   : court name --> set of PACER numbers
        aliases : tuple (court, number) --> short name

    See: list_filter
    """
    cases = {}
    aliases = {}

    c = json.load(open(filename, 'r'))

    for entry in c:
        court = entry['court']
        number = entry['number']
        name = entry['name']

        if court in cases:
            cases[court].add(number)
        else:
            cases[court] = {number}
        aliases[(court, number)] = name

    return cases, aliases

def list_filter(cases, aliases):
    """The scrape filter corresponding to read_cases.
    """
    def entry_filter(entry):
        """
        Return True for entries matching a case in `cases`,
        and modify their titles according to `aliases`.
        """
        court = entry.court
        num = int(entry.pacer_num)
        if court in cases and num in cases[court]:
            alias = aliases[(court, num)]
            if alias:
                entry.case_name = alias
            return True
        else:
            return False

    return entry_filter


if __name__ == '__main__':
    # get command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-list", action='store')
    parser.add_argument("--log", action='store')
    parser.add_argument("--verbose", "-v", action='count', default=0)
    parser.add_argument("--email", action='store_true')
    parser.add_argument("--twitter", action='store_true')
    for arg in ["--e-from", "--e-pass", "--e-to",
                "--t-oauth-token", "--t-oauth-secret",
                "--t-consumer-key", "--t-consumer-secret"]:
        parser.add_argument(arg, action='store', default="")
    args = parser.parse_args()

    case_list = args.case_list
    log_location = args.log
    verbosity = min(3, args.verbose) # verbosity breaks after -vvv

    notifier = make_notifier(
        twitter={
            'oauth_token': args.t_oauth_token,
            'oauth_secret': args.t_oauth_secret,
            'consumer_key': args.t_consumer_key,
            'consumer_secret': args.t_consumer_secret
        },
        email={
            'from': args.e_from,
            'to': args.e_to,
            'pass': args.e_pass}
    )

    # set up a logger (separate from notifier)
    log = logging.getLogger("pacerrssscraper-"+VERSION)
    log.setLevel(logging.DEBUG)

    log_format = logging.Formatter(
        fmt="[{asctime}] *"+VERSION+"* {levelname}: {message}",
        datefmt="%a %b %d %X %Y UTC", style="{")
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


    # set up a SIGTERM/SIGINT handler so that this process
    # can be killed with Ctrl+C or kill(1).
    def cb_quit(signal, frame):
        """Quit with a message and exit code 0."""
        log.critical("Received SIGTERM. Quitting.\n--------------------\n")
        sys.exit(0)
    signal.signal(signal.SIGTERM, cb_quit)
    signal.signal(signal.SIGINT, cb_quit)

    # Override sys.excepthook
    def exception_handler(exc_type, value, tb):
        log.error(*traceback.format_exception(exc_type, value, tb))
    sys.excepthook = exception_handler

    # ------------------------------

    log.critical("Starting...")
    log.critical("We are process {}".format(os.getpid()))

    RSS_COURTS = ["almd", "alsd", "akd", "ared", "arwd", "cacd",
                  "cand", "casd", "ctd", "ded", "dcd", "flmd",
                  "flsd", "gamd", "gud", "idd", "ilcd", "ilnd",
                  "innd", "insd", "iand", "iasd", "ksd", "kywd", "laed",
                  "lamd", "lawd", "mad", "mied", "miwd", "moed",
                  "mowd", "mtd", "ned", "nhd", "njd", "nyed",
                  "nynd", "nysd", "nced", "ncmd", "ncwd", "nmid",
                  "ohnd", "ohsd", "okwd", "ord", "paed", "pamd", "pawd",
                  "prd", "rid", "sdd", "tned", "tnmd", "txed",
                  "txsd", "txwd", "utd", "vtd", "vid", "vawd",
                  "waed", "wawd", "wied", "wiwd", "wvnd", "wvsd", "wyd"]

    # Time to wait between checks of a given court.
    # This could probably be tuned somewhat.
    SCRAPE_INTERVAL = timedelta(minutes=35)

    # Time to wait between checks.
    # Setting this too low may make the PACER people mad.
    # Setting this too high makes reporting bursty.
    CHECK_INTERVAL = timedelta(minutes=5)

    # Table for exponential backoff in case of timeouts
    #
    # Sometimes courts go down for extended periods of time
    # (up to several days). We don't want to clobber them
    # every CHECK_INTERVAL in such cases.
    backoff = defaultdict(lambda: 1)


    # court -> datetime
    last_updated = {}
    next_check = {}

    #
    # Main loop
    #
    while True:
        # Load case and court information from database
        if case_list:
            try:
                cases, aliases = read_cases(case_list)
            except ValueError:
                log.exception("")
                cases, aliases = {}, {}
        else:
            cases, aliases = {}, {}

        # The default filter uses the provided case list,
        # unless one wasn't provided, in which case it
        # uses an empty case list.
        default_filter = list_filter(cases, aliases)

        # This adds *all* RSS-enabled courts to the list of courts
        # to watch. You should ****REPLACE THIS****
        #for court in RSS_COURTS:
        #    if court not in cases:
        #        cases[court] = set()

        # Add courts to last_updated and next_check if necessary.
        for court in cases.keys() - next_check.keys():
            log.info("Adding {}.".format(court))

            # suppress most logging in this next part
            # (scrape does a bunch of logging that we're
            #  not interested in right now)
            logging.disable(logging.ERROR)
            try:
                # we're not really trying to scrape, we're just getting
                # when it was last updated (which scrape() returns)
                last_updated[court] = scrape(court, lambda x: False,
                                             dtnow(), lambda x: None)
            except Exception:
                # in the case of errors, just set last_updated
                # to... something...
                #
                # (last_updated will end up syncing to the court's
                #  actual update schedule later, so we'll be fine)
                last_updated[court] = dtnow()

            # re-enable logging
            logging.disable(logging.NOTSET)

            next_check[court] = last_updated[court] + SCRAPE_INTERVAL


        #
        # Do the actual checking.
        #
        now = dtnow()

        courts_to_check = [c for c in next_check if next_check[c] < now]

        log.info("Checking {}...".format(", ".join(courts_to_check)))

        for court in courts_to_check:
            try:
                log.debug("Checking {} for entries since {}:".format(
                    court, dtfmt(last_updated[court])))

                last_updated[court] = scrape(
                    court,
                    default_filter, # You may want to ****REPLACE THIS****
                    last_updated[court],
                    notifier)
                next_check[court] = last_updated[court] + SCRAPE_INTERVAL

                backoff[court] = 1
            except socket.timeout:
                # treat timeouts specially because they seem to happen a lot
                log.warning(
                    "Timed out while getting feed for {}.".format(court))

                next_check[court] += backoff[court]*CHECK_INTERVAL
                backoff[court] *= 2
                continue
            except URLError as e:
                log.warning("Failed to get feed for {}:".format(court))
                log.warning(e.__class__.__name__+": "+str(e))

                next_check[court] += backoff[court]*CHECK_INTERVAL
                backoff[court] *= 2
                continue
            except SAXException as e:
                # Means we got invalid XML.
                log.warning(
                    "Invalid XML in feed for {} (not reading):".format(court))
                log.warning(e.__class__.__name__+": "+str(e))
            except Exception as e:
                # traceback is printed automatically by logger
                log.exception(court)
                continue

            # NB: the continue statements in the above except blocks
            # prevent the check below from running.


            # Don't let next_check[court] be in the past.
            # Without this, certain courts get clobbered.
            #
            # (Note: Another way of handling this is to keep incrementing
            #  by SCRAPE_INTERVAL until next_check > now. Not sure which
            #  method is better, or even if there's a difference.)
            now = dtnow()
            if next_check[court] < now:
                next_check[court] = now + SCRAPE_INTERVAL

            log.debug("{} will be next checked at {}.".format(
                court, dtfmt(next_check[court])))

        log.info("Checks complete.")

        sleep(CHECK_INTERVAL.total_seconds())
