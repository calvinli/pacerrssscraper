#! /usr/bin/env python3

#
# Script to scrape PACER RSS feeds to look for cases of interest.
#
# Calvin Li, 2013-10-07
# Licensed under the WTFPLv2
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
import traceback

def get_feed(url):
    feed = feedparser.parse(url)
    
    if feed['status'] != 200:
        raise Exception("Getting PACER RSS feed {} failed with code {}.".format(
                            feed['href'], feed['status']))
    return feed



def send_email(entry, email_account, email_pass, email_to):
    s = smtplib.SMTP()
    s.connect("smtp.gmail.com", 587)
    s.starttls()
    s.login(email_account, email_pass)

    info = parse_entry(entry)

    message = MIMEText("""
Case: {} ({})
Document #: {}
Description:
Link: {}
Time: {}
""".format(info['case'], info['court'],
           info['num'],
           info['description'],
           info['link'],
           time.strftime("%a %b %d %H:%M:%S %Y", info['time'])))

    message['Subject'] = "New PACER entry found by RSS Scraper"
    message['From'] = "PACER RSS Scraper"
    s.send_message(email_account, email_to, message)
    s.quit()

def send_tweet(entry, oauth_token, oauth_secret, consumer_key, consumer_secret):
    twitter = Twitter(auth=OAuth(oauth_token, oauth_secret,
                                 consumer_key, consumer_secret))

    info = parse_entry(entry)

    message = "New doc in {} ({}): #{} {}. #PACER {}".format(
              info['case'][:30], info['court'],
              info['num'], info['description'][:50],
              info['link'])

    twitter.statuses.update(status=message)


def parse_entry(entry):
    """Extract the info out of an entry.

Returns a dictionary containing the following keys: num, link, case, court,
time, description.
"""
    info = {}

    # TODO: confirm that this works on all courts.

    # p.search() returns None if the search fails.
    # Annoyingly, I have already seen one instance
    # in which the RSS feed lacks certain fields.
    #

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
    p = re.compile("\[(.+)\] \(<a")
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
            try:
                send_email(entry, creds['email_account'], creds['email_pass'],
                                  creds['email_to'])
            except Exception:
                traceback.print_exc()

        if twitter:
            try:
                send_tweet(entry, creds['oauth_token'], creds['oauth_secret'],
                                  creds['consumer_key'], creds['consumer_secret'] )
            except Exception:
                traceback.print_exc()

    return notify

def scrape(courts, cases, notifier):
    pacer_feeds = {court: get_feed(url) for court, url in courts.items()}

    last_seen = get_last_time()

    # Go through each court
    for court, feed in pacer_feeds.items():
        # Go through each element
        for entry in feed['entries']:
            # check to see if we've already seen this
            if time.mktime(entry['published_parsed']) <= last_seen:
                break 

            # see if any cases of interest show up
            if entry['link'].split("?")[-1] in cases[court]:
                print(entry)
                notifier(entry)

                # Next time, ignore all entries at or before this time.
                #   this system could fail if courts are on a significant lag
                #   relative to each other
                set_last_time(time.mktime( entry['published_parsed']) )

    print("Scrape completed.")

#
# Ancillary files
#
KILL_SWITCH = os.path.dirname( os.path.realpath(__file__) )+"/killswitch"
def set_kill_switch():
    with open(KILL_SWITCH, 'w') as f:
        f.write("script disabled\n")

def kill_switch_set():
    with open(KILL_SWITCH, 'r') as f:
        return len(f.readline()) > 2

LAST_TIME = os.path.dirname( os.path.realpath(__file__) )+"/lasttime"
def set_last_time(time):
    """Time should be a numerical type corresponding to Unix timestamp."""
    with open(LAST_TIME, 'w') as f:
        f.write(str(int(time)) + "\n")
def get_last_time():
    with open(LAST_TIME, 'r') as f:
        return int(f.readline())

#
#
#
if __name__ == '__main__':
    if kill_switch_set():
        print("killswitch set. not scraping.")
        sys.exit()


    courts = {
              "cacd": "https://ecf.cacd.uscourts.gov/cgi-bin/rss_outside.pl",
              "cand": "https://ecf.cand.uscourts.gov/cgi-bin/rss_outside.pl",
              "ilnd": "https://ecf.ilnd.uscourts.gov/cgi-bin/rss_outside.pl",
             }
    
    cases = {
              "cacd": ["543744", # Ingenuity 13 v. Doe (Wright)
                      ],
              "cand": ["254869", # AF Holdings v. Navasca (Chen/Vadas)
                       "254879", # AF Holdings v. Trinh
                      ],
              "ilnd": ["280638", # Duffy v. Godfread et. al
                       "284511", # Prenda v. Internets
                       "287443", # new Malibu Media v. Doe case, 13-cv-50286
                      ],
            }

    #
    # Get command-line arguments.
    # 
    parser = argparse.ArgumentParser()
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
    
    notifier = make_notifier(email=args.email, twitter=args.twitter, creds = {
'email_account': args.e_from,
'email_pass': args.e_pass,
'email_to': args.e_to,
'oauth_token': args.t_oauth_token,
'oauth_secret': args.t_oauth_secret,
'consumer_key': args.t_consumer_key,
'consumer_secret': args.t_consumer_secret
})

    scrape(courts, cases, notifier)
