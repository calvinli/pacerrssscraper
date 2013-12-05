#! /usr/bin/env python3
#
# Script to scrape PACER RSS feeds to look for cases of interest.
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
import time
import sys
import os
import smtplib
from email.mime.text import MIMEText
from twitter import * # https://github.com/sixohsix/twitter/tree/master
import re
import argparse
import sqlite3

def get_feed(url):
    feed = feedparser.parse(url)
    
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
           time.strftime("%a %b %d %H:%M:%S %Y", info['time'])))

    message['Subject'] = "New PACER entry found by RSS Scraper"
    message['From'] = "PACER RSS Scraper"
    s.send_message(message, from_addr=email_account, to_addrs=email_to)
    s.quit()

def send_tweet(info, oauth_token, oauth_secret, consumer_key, consumer_secret):
    twitter = Twitter(auth=OAuth(oauth_token, oauth_secret,
                                 consumer_key, consumer_secret))
    """info should be the result of calling parse_entry()."""

    def truncate(string, num):
        if len(string) > num:
            return string[:num-3] + "..."
        else:
            return string

    message = "New doc in {} ({}): #{} {}. #Prenda {}".format(
              truncate(info['case'], 30), info['court'],
              info['num'], truncate(info['description'], 50),
              info['link'])

    twitter.statuses.update(status=message)
    print("Successfully sent the following tweet: \"{}\"".format(message))

def parse_entry(entry):
    """Extract the info out of an entry.

Returns a dictionary containing the following keys: num, link, case, court,
time, description.
"""
    info = {}

    # p.search() returns None if the search fails.
    # Annoyingly, I have already seen one instance
    # in which the RSS feed lacks certain fields.

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

If email==True, creds must contain email credentials, and if twitter==True
it must contain twitter credentials.
"""
    def notify(entry):
        if email:
            send_email(entry, creds['email_account'], creds['email_pass'],
                              creds['email_to'])
        if twitter:
            send_tweet(entry, creds['oauth_token'], creds['oauth_secret'],
                       creds['consumer_key'], creds['consumer_secret'] )
    return notify

def scrape(cases, alias, courts_checked, notifier):
    """Scrape the given cases.

    Arguments:
    - cases: dictionary from courts to PACER numbers
    - alias: dictionary from PACER numbers to custom case names
    - courts_checked: dictionary from courts to when they were last checked
    - notifier: object (made using make_notifier) to call with new stuff

    Every PACER number in cases must have an alias, even if it's just "".

    Returns a dictionary from court names to when they were last updated.
    """
    print("Loading feeds...")
    pacer_feeds = {court: get_feed(
        "https://ecf.{}.uscourts.gov/cgi-bin/rss_outside.pl".format(court) )
                   for court in cases}
    print("All feeds loaded.")

    courts_updated = courts_checked.copy()

    # Build up a dict of entries keyed by the document URL.
    # This prevents the issue of multiple RSS entries for
    # the same document.
    entries = {}

    # Go through each court
    for court, feed in pacer_feeds.items():
        if time.mktime(feed['feed']['updated_parsed']) <= courts_checked[court]:
            print("{} has not been updated since last time.".format(
                  court.upper() ) 
                 )
            continue
        else:
            courts_updated[court] = time.mktime(feed['feed']['updated_parsed'])

        print("Checking {} for {}.".format(
            court.upper(),
            ", ".join( ["{} ({})".format(num, alias[num]) for num in cases[court]] )))

        for entry in feed['entries']:
            if time.mktime(entry['published_parsed']) < courts_checked[court]:
                break 

            # see if any cases of interest show up
            case_num = entry['link'].split("?")[-1]
            if case_num in cases[court]:
                # print raw dict to stdout for debugging/testing purposes
                print(entry)

                info = parse_entry(entry)

                # override the case name if we have a manually-set one
                case_name = alias[case_num]
                if len(case_name) > 1:
                    info['case'] = case_name

                if info['link'] in entries:
                    ### WARNING: to my knowledge this has never been tested IRL
                    entries[info['link']]['description'] += "/"+info['description']
                else:
                    entries[info['link']] = info

    for e in entries.values():
        notifier(e)

    print("Scrape completed.")

    return courts_updated

###################


if __name__ == '__main__':
    #
    # Get command-line arguments.
    # 
    parser = argparse.ArgumentParser()
    
    # database of cases
    parser.add_argument("--db", action='store')

    # notification stuff
    parser.add_argument("--email", action='store_true')
    parser.add_argument("--twitter", action='store_true')
    
    parser.add_argument("--e-from", action='store')
    parser.add_argument("--e-pass", action='store')
    parser.add_argument("--e-to", action='store')

    parser.add_argument("--t-oauth-token", action='store')
    parser.add_argument("--t-oauth-secret", action='store')
    parser.add_argument("--t-consumer-key", action='store')
    parser.add_argument("--t-consumer-secret", action='store')

    args = parser.parse_args()

    # ------------------------------

    cases = {}
    courts_checked = {}
    aliases = {}

    CWD = os.path.dirname( os.path.realpath(__file__) )
    conn = sqlite3.connect(CWD+"/"+args.db)
    c = conn.cursor()
    c.execute("SELECT * FROM cases;")

    for court, case, name in c:
        if court in cases:
            cases[court].append( case )
        else:
            cases[court] = [case]
        aliases[case] = name

    c.execute("SELECT * FROM updated;")

    for court, checked in c:
        courts_checked[court] = int(checked)

    notifier = make_notifier(email=args.email, twitter=args.twitter, creds = {
        'email_account': args.e_from,
        'email_pass': args.e_pass,
        'email_to': args.e_to,
        'oauth_token': args.t_oauth_token,
        'oauth_secret': args.t_oauth_secret,
        'consumer_key': args.t_consumer_key,
        'consumer_secret': args.t_consumer_secret
    })
    
    courts_updated = scrape(cases, aliases, courts_checked, notifier)

    for court, updated in courts_updated.items():
        c.execute("REPLACE INTO updated (court, time) VALUES (?, ?)",
                  (court, updated))

    conn.commit()
    c.close()
