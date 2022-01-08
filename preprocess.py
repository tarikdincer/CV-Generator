import os
import re
from boilerpy3 import extractors
from bs4 import BeautifulSoup, SoupStrainer
from flask import app
import requests
import urllib
from googlesearch import search
import requests
from urllib.request import urlopen
import PyPDF4
import re
import io
from tika import parser
from process import process_keyword_analysis


scanned_links = []

def parse_pdf_tika(filename):
    file_data = parser.from_file(filename)
    text = file_data['content']
    return text

def parse_pdf(file_path):
    lines = []
    pdfFileObj = open(file_path, 'rb')
    pdfReader = PyPDF4.PdfFileReader(pdfFileObj)
    for i in range(pdfReader.numPages):
        pageObj = pdfReader.getPage(i)
        pages_text = pageObj.extractText()

        for line in io.StringIO(pages_text):
            if(len(line) != 0):
                lines.append(line)
    
    return lines

# Condenses all repeating newline characters into one single newline character
def condense_newline(text):
    return ' '.join([p for p in re.split('\n|\r', text) if len(p) > 0])

def split_newline(text):
    return [p for p in re.split('\n|\r', text) if len(p) > 0]

def extract_from_url(url):
    # Make a GET request to fetch the raw HTML content
    html_content = requests.get(url).text
    clean_text = '\n'.join(BeautifulSoup(html_content, "html.parser").stripped_strings)
    return clean_text
# Returns the text from a HTML file
def parse_html(html_path):
    # Text extraction with boilerpy3
    html_extractor = extractors.KeepEverythingExtractor()
    return split_newline(html_extractor.get_content_from_url(html_path))

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
    
    persons = []
    
    for link in link_tree:
        scanned_content = scan_link(link, 0, rname)
        if(scanned_content):
            persons.append(process_keyword_analysis(lines=split_newline(scanned_content), rname=rname))
            # cv_content = cv_content + "\n" + scanned_content
    
    # print(link_tree)
    # print("content: " + cv_content)
    # print(cv_content)
    return persons


def scan_link(link, counter = 1, rname = ""):
    if link in scanned_links:
        return ""
    scanned_links.append(link)
    #print("cv_content", cv_content)
    content = ""
    try:
        print(link)
        #content = parse_html(link)
        content = extract_from_url(link)
        #print(content)
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