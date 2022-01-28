from codecs import ignore_errors
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
import spacy
import xml.etree.ElementTree as ET
import xmltodict
from lxml import etree
import json

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


def print_tree(node, indent):

    try:
        for element in node.iterchildren():
            print(indent, element.tag, ',', element.text, ',', element.tail)
            print_tree(element, indent + " ")
    except:
        print('over')


def get_blocks(root):
    f = open("slot_keywords.json")
    slots = json.load(f)
    blocks = dict()
    listed_blocks = dict()

    get_blocks_helper(root, blocks, listed_blocks, slots)
    return blocks, listed_blocks


def get_blocks_helper(node, blocks, listed_blocks, slots):
    try:
        headers = node.findall('h1') + node.findall('h2') + node.findall('h3') + node.findall('h4') + node.findall('h5') + node.findall('strong') + node.findall('b')
        is_slot_found = False
        if(len(headers) > 0):
            for header in headers:
                #print(header.tag,':', header.text)
                title = header.text
                if title == None or title.strip() == '':
                  title = ''
                  for text in header.itertext(with_tail=True):
                    title += text
                  #print('hader content: ',title)
                if(header.tag == 'b' and len(title.split()) > 3):
                  continue
                assigned_slot = ''
                for slot in slots:
                    for w in slot['headers']:                       
                        if ' ' + w.lower() + ' ' in ' ' + re.sub(r'[^\w\s]', ' ', title.lower()) + ' ' and assigned_slot == '':
                            print(title, '-->',slot['slot'], '(', w, ')\n')
                            is_slot_found = True
                            assigned_slot = slot['slot']
                            content = ""
                            while (True):
                              childCount = 0
                              if(header.getparent() is not None):
                                for element in header.getparent().iterchildren():
                                  if(element.tag != 'hr'):
                                    childCount += 1
                                if(childCount > 1):
                                  break
                                else:
                                  header = header.getparent()
                              else:
                                break
                            current_tag = header.getnext().tag if header.getnext() is not None else ""
                            next_tag = header.getnext()
                            while next_tag is not None and (current_tag in "h1h2h3h4h5" or current_tag == next_tag.tag):
                              if current_tag == 'ul':
                                for list_item in next_tag.iterchildren():
                                  list_text = ''
                                  for text in list_item.itertext(with_tail=True):
                                    if assigned_slot not in listed_blocks:
                                      listed_blocks[assigned_slot] = []
                                    if(text.replace('\n', ' ').strip() != ''):
                                      list_text += " " + text.replace('\n', ' ').strip()
                                  listed_blocks[assigned_slot].append(list_text)
                              else:
                                  for text in next_tag.itertext(with_tail=True):
                                      content += "\n" + text.replace('\n', ' ').strip()
                                  if assigned_slot not in blocks:
                                      blocks[assigned_slot] = ""
                                  if content not in blocks[assigned_slot]:
                                    #print('content added: ', content, '\n')
                                    blocks[assigned_slot] += "\n" + content
                              current_tag = next_tag.tag
                              next_tag = next_tag.getnext()
                            break
        for element in node.iterchildren():
            get_blocks_helper(element, blocks, listed_blocks, slots)
    except Exception as e:
        print(e)

def block_to_index(blocks):
    lines = []
    block_index = dict()
    c = 0
    for slot,line_str in blocks.items():
        lines_temp = split_newline(line_str)
        lines += [x.replace('\n','').replace('\t','') for x in lines_temp]
        block_index[slot] = c
        c += len(lines_temp)
    
    return lines, block_index

def extract_from_url(url):
    html_content = requests.get(url).text
    try:
        body_start = html_content.index('<body')
        body_end = html_content.index('</body>') + 7
        html_content = html_content[body_start:body_end]
    except Exception as e:
        print("body not found")
        print(e)
    #print("html",html_content)
    parser = etree.XMLParser(recover=True)
    tree = ET.fromstring(html_content, parser)
    #print_tree(tree, "")
    blocks,listed_blocks = get_blocks(tree)
    print("url", url)
    print("listed block", listed_blocks)
    return blocks, listed_blocks
    


def elem2dict(node):
    """
    Convert an lxml.etree node tree into a dict.
    """
    result = {}

    for element in node.iterchildren():
        # Remove namespace prefix
        # print(element.tag)
        try:
            key = element.tag.split(
                '}')[1] if '}' in element.tag else element.tag

            # Process element as tree element if the inner XML contains non-whitespace content
            if element.text and element.text.strip():
                value = element.text
            else:
                value = elem2dict(element)
            if key in result:

                if type(result[key]) is list:
                    result[key].append(value)
                else:
                    tempvalue = result[key].copy()
                    result[key] = [tempvalue, value]
            else:
                result[key] = value
        except:
            continue
    return result

# Condenses all repeating newline characters into one single newline character


def condense_newline(text):
    return ' '.join([p for p in re.split('\n|\r', text) if len(p) > 0])


def split_newline(text):
    return [p for p in re.split('\n|\r', text) if len(p) > 0]

# def extract_from_url(url):
#     # Make a GET request to fetch the raw HTML content
#     html_content = requests.get(url).text
#     # body_start = html_content.index('<body>')
#     # body_end = html_content.index('</body>')
#     #parser = etree.XMLParser(recover=True)
#     #print(html_content)
#     #tree = ET.fromstring(" ".join(html_content.split()), parser)
#     # for child in tree:
#     #     print(child.tag)
#     #tree_dict = elem2dict(tree.getroottree().getroot())
#     #tree = xmltodict.parse('''<div class='logo'><a href='http://alhajj.cpsc.ucalgary.ca'><img src='img/logo.png' alt='' style='height:130px' title='' border='0' /></a></div><div id='menu'><ul><liclass='selected'><a href='index.php'>Home</a></li><li><a href='aboutme.php'>About me</a></li><li><a href='researchinterests.php'>Interests</a></li><li><a href='teaching.php'>Teaching</a></li><li><a href='publications.php'>Publications</a></li><li><a href='collaboration.php'>Collaboration</a></li><li><a href='personal.php'>Personal</a></li><li><a href='students.php'>Students</a></li></ul></div>''')
#     #print("html", tree_dict, "\n\n\n")
#     clean_text = '\n'.join(BeautifulSoup(html_content, "html.parser").stripped_strings)
#     return clean_text
# # Returns the text from a HTML file


def parse_html(html_path):
    # Text extraction with boilerpy3
    html_extractor = extractors.KeepEverythingExtractor()
    return split_newline(html_extractor.get_content_from_url(html_path))


def traverse_web_links(rname, url=None):
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

    query = rname + " university biography"

    for j in search(query, num=10, stop=3, pause=2):
        link_tree.append(j)

    persons = []

    for link in link_tree:
        scanned_block, scanned_listed_block, scanned_content = scan_link(link, 1, rname)
        #print(scanned_block)
        lines = []
        block_index = None
        if(len(scanned_block.keys())):
            lines, block_index = block_to_index(scanned_block)
            # nlp = spacy.load("en_core_web_sm")
            # print("content", scanned_content)
            # doc = nlp(scanned_content)
            # sent_temp = [" ".join(x.text.strip().replace("\t", " ").split()) for x in doc.sents if len(x.text) != 0]
            # sents = []
            # for sent in sent_temp:
            #     sents += split_newline(sent)
        persons.append(process_keyword_analysis(
            lines=lines, rname=rname, block_index=block_index, listed_block = scanned_listed_block))
        persons.append(process_keyword_analysis(lines=scanned_content.splitlines(), rname=rname))

    # print(link_tree)
    # print("content: " + cv_content)
    # print(cv_content)
    return persons

def scan_link(link, counter=1, rname=""):
    if link in scanned_links:
        return dict(), dict(), ""
    scanned_links.append(link)
    #print("cv_content", cv_content)
    block = dict()
    listed_blocks = dict()
    content = ""
    try:
        print(link)
        content = "\n".join(parse_html(link))
        block, listed_blocks = extract_from_url(link)

        # print(content)
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
        f = open("href_keywords.txt", "r")
        href_keys = f.readlines()
        for l in soup.find_all('a'):
            print("href")
            new_link = urllib.parse.urljoin(link, l.get('href'))
            if(not(any(True for x in href_keys if x in new_link))):
                continue
            print("new link", new_link)
            b, lb, c= scan_link(new_link, counter - 1, rname)
            block = dict(list(block.items()) + list(b.items()))
            listed_blocks = dict(list(listed_blocks.items()) + list(lb.items()))
            content += "\n" + c
    print("aaa", block, listed_blocks, content)  
    return block, listed_blocks, content

# def scan_link(link, counter=1, rname=""):
#     if link in scanned_links:
#         return ""
#     scanned_links.append(link)
#     #print("cv_content", cv_content)
#     content = ""
#     try:
#         print(link)
#         #content = parse_html(link)
#         content = extract_from_url(link)
#         # print(content)
#     except Exception as e:
#         print(e)
#         print(link + " is not accessible")
#         pass
#     #print("rname", rname)
#     #print("content", content)
#     if rname.lower() not in content.lower():
#         content = ""

#     if counter != 0:
#         page = requests.get(link)
#         data = page.text
#         soup = BeautifulSoup(data)

#         for l in soup.find_all('a'):
#             new_link = urllib.parse.urljoin(link, l.get('href'))
#             content = content + "\n" + scan_link(new_link, counter - 1, rname)

#     return content
