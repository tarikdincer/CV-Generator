import os
import re
from boilerpy3 import extractors
from bs4 import BeautifulSoup, SoupStrainer
import requests
import urllib
from googlesearch import search
import requests
from urllib.request import urlopen

scanned_links = []

# Condenses all repeating newline characters into one single newline character
def condense_newline(text):
    return ' '.join([p for p in re.split('\n|\r', text) if len(p) > 0])

# Returns the text from a HTML file
def parse_html(html_path):
    # Text extraction with boilerpy3
    html_extractor = extractors.KeepEverythingExtractor()
    return condense_newline(html_extractor.get_content_from_url(html_path))

def traverse_web_links(rname, url = None):
    cv_content = ""
    link_tree = list()
    if url != None:
        link_tree.append(url)
    # goog_search = 'https://google.com/search?q=' + rname + " biography"
    # goog_search = goog_search.replace(" ", "%20")
    # print(goog_search)
    # r = requests.get(goog_search)
    # search_soup = BeautifulSoup(r.text, "html.parser")
    # results = search_soup.find_all('cite', limit=3)
    # print("results", results)
    # for result in results:
    #     link_tree.append(result.text)

    query = rname + " biography"

    for j in search(query, num=10, stop=3, pause=2): 
        link_tree.append(j)
    
    for link in link_tree:
        scanned_content = scan_link(link, 0, rname)
        if(scanned_content):
            cv_content = cv_content + "\n" + scanned_content
    print(link_tree)
    print("content: " + cv_content)
    print(cv_content)
    return cv_content


def scan_link(link, counter = 1, rname = ""):
    if link in scanned_links:
        return ""
    scanned_links.append(link)
    #print("cv_content", cv_content)
    content = ""
    try:
        print(link)
        content = parse_html(link)
    except Exception as e:
            print(e)
            print(link + " is not accessible")
            pass
    #print("rname", rname)
    #print("content", content)
    if rname.lower() not in content.lower():
        content = ""
        
    if counter != 0:    
        page = requests.get(link)    
        data = page.text
        soup = BeautifulSoup(data)

        for l in soup.find_all('a'):
            new_link = urllib.parse.urljoin(link,l.get('href'))
            content = content + "\n" + scan_link(new_link, counter - 1, rname)

    return content