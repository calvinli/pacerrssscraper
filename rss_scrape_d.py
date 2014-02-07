#! /usr/bin/env python3
#
#    _____               ______   __  __    ____    _   _ 
#   |  __ \      /\     |  ____| |  \/  |  / __ \  | \ | |
#   | |  | |    /  \    | |__    | \  / | | |  | | |  \| |
#   | |  | |   / /\ \   |  __|   | |\/| | | |  | | | . ` |
#   | |__| |  / ____ \  | |____  | |  | | | |__| | | |\  |
#   |_____/  /_/    \_\ |______| |_|  |_|  \____/  |_| \_|
#               for scraping PACER RSS feeds
#
# Author: Calvin Li
#
# +-------------------------------------------------------------------------------+
# |                                                                               |  
# | The MIT License (MIT)                                                         |
# |                                                                               |
# | Copyright (c) 2013 Calvin Li                                                  |
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
from time import asctime, gmtime, strftime, sleep
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

# PACER servers frequently have problems.
# Ensure that connections don't hang.
socket.setdefaulttimeout(10) 

LOG_LEVEL = 0
def log(level, *args, **kwargs):
    """Logging with log levels and timestamps.

Lower log levels = more important. All log messages with log level <=
the global variable LOG_LEVEL are timestamped and printed to stdout."""
    if level <= LOG_LEVEL:
        args = list(args)
        args.insert(0, "[{} UTC] ".format(asctime(gmtime())))
        return print(*args, **kwargs)

def get_feed(url):
    feed = feedparser.parse(url)
    
    # I'm not sure if these are actually necessary, as I believe
    # feedparser returns an empty feed (i.e. feed['entries'] == [])
    # in the case of errors.
    if 'status' not in feed:
        raise Exception("Getting feed {} failed.".format(url))
    if feed['status'] != 200:
        raise Exception("Getting feed {} failed with code {}.".format(
                            feed['href'], feed['status']))
    return feed

def send_email(info, email_account, email_pass, email_to):
    """info should be the result of calling parse_entry()."""

    s = smtplib.SMTP()
    s.connect("smtp.gmail.com", 587)
    s.starttls()
    s.login(email_account, email_pass)

    message = MIMEText("""
Case: {} ({})
Document #: {}
Description: {}
Link: {}
Time: {}
""".format(info['case'], info['court'],
           info['num'],
           info['description'],
           info['link'],
           strftime("%a %b %d %H:%M:%S %Y", info['time'])))

    message['Subject'] = "New PACER entry found by RSS Scraper"
    message['From'] = "PACER RSS Scraper"
    s.send_message(message, from_addr=email_account, to_addrs=email_to)
    s.quit()

def send_tweet(info, oauth_token, oauth_secret, consumer_key, consumer_secret):
    twitter = Twitter(auth=OAuth(oauth_token, oauth_secret,
                                 consumer_key, consumer_secret))
    """info should be the result of calling parse_entry()."""

    # truncate the description to fit
    if len(info['case']) + len(info['description']) > 90:
        space = 90 - len(info['case'])
        info['description'] = info['description'][:space-3] + "..."

    message = "New doc in {} ({}): #{} {}. {}".format(
              info['case'], info['court'],
              info['num'], info['description'],
              info['link'])

    try:
        twitter.statuses.update(status=message)
        log(1, "Successfully sent the following tweet: \"{}\"".format(message))
    except TwitterHTTPError:
        # TODO: Ensure that this TwitterHTTPError really is a 403 due to duplicate tweet.
        #       If it isn't, we should re-raise the exception.
        log(1, "Tweet failed. Probably a duplicate.")

def parse_entry(entry):
    """Extract the info out of an entry.

Returns a dictionary containing the following keys: num, link, case, court,
time, description.
"""
    info = {}

    # p.search() returns None if the search fails.
    # (Entries routinely lack several of these fields.)

    # extract the document number out of the link
    p = re.compile(">([0-9]+)<") 
    info['num'] = p.search(entry['description'])
    info['num'] = (info['num'].group(1) if info['num'] else "?")

    # get the link itself (to the actual document)
    p = re.compile("href=\"(.*)\"") 
    info['link'] = p.search(entry['description'])
    info['link'] = (info['link'].group(1) if info['link'] else "?")

    # if this doesn't exist I don't even...
    info['case'] = " ".join(entry['title'].split(" ")[1:]) # strip the case # out

    p = re.compile("ecf\.([a-z]+)\.") # find the court
    info['court'] = p.search(entry['link'])
    # this definitely should exist though
    info['court'] = (info['court'].group(1) if info['court'] else "?") 

    info['time'] = entry['published_parsed'] # this is a time.struct_time

    # The description of the entry
    p = re.compile("^\[(.+)\]")
    info['description'] = p.search(entry['summary'])
    info['description'] = (info['description'].group(1) if info['description'] else "?") 

    return info


def make_notifier(creds, email=False, twitter=False):
    """Make a notifier function with access to credentials, etc.
"""
    def notify(entry):
        if email:
            send_email(entry, creds['email_account'], creds['email_pass'],
                              creds['email_to'])
        if twitter:
            send_tweet(entry, creds['oauth_token'], creds['oauth_secret'],
                       creds['consumer_key'], creds['consumer_secret'] )
    return notify

def scrape(court, cases, alias, last_checked, notifier):
    """Scrape for the given cases in the given court.

    Arguments:
    - court: the court to check
    - cases: list of PACER numbers
    - alias: dict from PACER numbers to case names
    - last_checked: struct_time of when this court was last checked (UTC!)
    - notifier: result of calling make_notifier

    Every PACER number in cases must have an alias, even if it's just "".

    Returns when the scraped feed was generated as a datetime object.
    """
    log(2, "checking {} for entries in ".format(court) +
           ", ".join(["{} ({})".format(num, alias[num]) for num in cases]) + 
           " since {} UTC".format(asctime(last_checked)))

    feed = get_feed(
            "https://ecf.{}.uscourts.gov/cgi-bin/rss_outside.pl".format(court))
    log(2, "Feed downloaded.")

    # Build up a dict of entries keyed by the document URL.
    # This handles when there are multiple RSS entries for
    # the same document.
    entries = {}
    # these have no document URLs and so get special treatment
    no_doc_entries = []

    last_updated = feed['feed']['updated_parsed']
    if last_updated <= last_checked:
        # Feed has not been updated since last time.
        # Exit without scraping.
        log(2, "Feed has not been updated.")
        return datetime.utcfromtimestamp(timegm(last_updated))

    for entry in feed['entries']:
        if entry['published_parsed'] < last_checked:
            # We have checked all new entries.
            break
 
        # see if any cases of interest show up
        case_num = entry['link'].split("?")[-1]
        if case_num in cases:
            # print raw dict to stdout for debugging/testing purposes
            log(0, entry)

            info = parse_entry(entry)

            # override the case name if we have a manually-set one
            case_name = alias[case_num]
            if len(case_name) > 1:
                info['case'] = case_name

            if info['link'] == '?':
                no_doc_entries.append(info)
            elif info['link'] in entries:
                entries[info['link']]['description'] += " // "+info['description']
            else:
                entries[info['link']] = info

    for e in (list(entries.values())+no_doc_entries)[::-1]:
        log(1, "reporting the following:")
        log(1, e)
        notifier(e)

    log(2, "Scrape of {} completed.".format(court))
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

    # conn.commit() # this is unnecessary as we do no writes
    c.close()

    return cases, aliases

if __name__ == '__main__':
    log(0, "Starting...")
    log(0, "We are process {}".format(os.getpid()))

    # set up a SIGTERM handler
    def quit(signal, frame):
        log(0, "Received SIGTERM. Quitting.\n--------------------\n")
        sys.exit(0)
    signal.signal(signal.SIGTERM, quit)

    # get command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", action='store')
    parser.add_argument("--verbose", "-v", action='count')
    parser.add_argument("--email", action='store_true')
    parser.add_argument("--twitter", action='store_true')
    for arg in ["--e-from", "--e-pass", "--e-to",
                "--t-oauth-token", "--t-oauth-secret",
                "--t-consumer-key", "--t-consumer-secret"]:
        parser.add_argument(arg, action='store', default="")
    args = parser.parse_args()

    DB = args.db
    LOG_LEVEL = args.verbose
 
    notifier = make_notifier(email=args.email, twitter=args.twitter, creds = {
        'email_account': args.e_from,
        'email_pass': args.e_pass,
        'email_to': args.e_to,
        'oauth_token': args.t_oauth_token,
        'oauth_secret': args.t_oauth_secret,
        'consumer_key': args.t_consumer_key,
        'consumer_secret': args.t_consumer_secret
    })    

    # ------------------------------

    # Number of minutes to wait between checks of a given court.
    CHECK_INTERVAL = timedelta(minutes=35)

    last_updated = {}
    next_check = {}

    # Main loop
    while True:
        # Load case and court information from database
        cases, aliases = read_cases(os.path.dirname(os.path.realpath(__file__))+"/"+DB)

        # initialize any new courts
        old_log_level, LOG_LEVEL = LOG_LEVEL, 0
        for court in (cases.keys() - next_check.keys()):
            log(0, "Adding {}.".format(court))
            last_updated[court] = scrape(court, cases[court], aliases, gmtime(), notifier)
            next_check[court] = last_updated[court] + CHECK_INTERVAL
        # delete any removed courts
        for court in (next_check.keys() - cases.keys()):
            log(0, "Removing {}.".format(court))
            del next_check[court]
            del last_updated[court]
        LOG_LEVEL = old_log_level


        now = datetime.utcnow()

        courts_to_check = list(filter(lambda c: next_check[c] < now, next_check));
        log(1, "Checking {}...".format(", ".join(courts_to_check)))

        for court in courts_to_check:
            try:
                last_updated[court] = scrape(court, cases[court], aliases,
                                             last_updated[court].timetuple(),
                                             notifier) 
                next_check[court] = last_updated[court] + CHECK_INTERVAL
            except:
                # Never allow an exception during scraping to kill the program
                traceback.print_exc()
                continue
            
            # Never let next_check[court] be in the past.
            # (That would otherwise happen in the case of, e.g., CACD,
            #  which updates hourly rather than half-hourly.)
            if next_check[court] < now:
                next_check[court] = now + CHECK_INTERVAL

            log(2, "{} will be next checked at {} UTC.".format(court,
                                    asctime(next_check[court].timetuple())))
        log(1, "Checks complete.")
        # keep at least a modicum of sanity
        sleep(300)
