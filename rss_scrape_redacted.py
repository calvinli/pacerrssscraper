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

def get_feed(url):
    feed = feedparser.parse(url)
    
    if feed['status'] != 200:
        raise Exception("Getting PACER RSS feed {} failed with code {}.".format(
                            feed['href'], feed['status']))
    return feed



def send_email(entry):
    s = smtplib.SMTP()
    s.connect("smtp.gmail.com", 587)
    s.starttls()
    s.login(SUBSTITUTE_YOUR_OWN, SUBSTITUTE_YOUR_OWN)

    message = MIMEText(str(entry)) # not sure if that str() call is necessary
    message['Subject'] = "New PACER entry found by RSS Scraper"
    message['From'] = "PACER RSS Scraper"
    s.sendmail(SUBSTITUTE_YOUR_OWN, SUBSTITUTE)YOUR_OWN, message)
    s.quit()

def scrape(courts, cases):
    pacer_feeds = {court: get_feed(url) for court, url in courts.items()}

    #

    last_seen = get_last_time()

    # Go through each court
    for court, feed in pacer_feeds.items():
        # Go through each element
        for entry in feed['entries']:
            # check to see if we've already seen this
            if time.mktime(entry['published_parsed']) <= last_seen:
                break # this SHOULD break out of this for loop

            # see if any cases of interest show up
            if entry['link'].split("?")[-1] in cases[court]:
                print(entry)
                send_email("""
Case: {} ({})
Summary: {}
Time: {}

""".format(entry['title'], court.upper(),
           entry['summary'],
           time.strftime("%a %b %d %H:%M:%S %Y", entry['published_parsed']))
)
                
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
                      ],
            }

    scrape(courts, cases)
