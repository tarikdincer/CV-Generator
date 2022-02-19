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
from urllib.parse import urlparse
import urllib.request
from langdetect import detect
from deep_translator import GoogleTranslator
from fpdf import FPDF
import datetime;

scanned_links = []

def download_file(download_url, filename):
    print("pdf downloading: ", download_url)
    response = urllib.request.urlopen(download_url)
    file = open(filename, "wb")
    file.write(response.read())
    file.close()


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
        headers = node.findall('h1') + node.findall('h2') + node.findall('h3') + node.findall(
            'h4') + node.findall('h5') + node.findall('strong') + node.findall('b')
        is_slot_found = False
        if(len(headers) > 0):
            for header in headers:
                #print(header.tag,':', header.text)
                title = translate_to_english(header.text)
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
                            print(title, '-->', slot['slot'], '(', w, ')\n')
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
                                                listed_blocks[assigned_slot] = [
                                                ]
                                            if(text.replace('\n', ' ').strip() != ''):
                                                list_text += " " + \
                                                    text.replace(
                                                        '\n', ' ').strip()
                                        listed_blocks[assigned_slot].append(
                                            list_text)
                                else:
                                    for text in next_tag.itertext(with_tail=True):
                                        content += "\n" + \
                                            text.replace('\n', ' ').strip()
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
    for slot, line_str in blocks.items():
        lines_temp = split_newline(line_str)
        lines += [x.replace('\n', '').replace('\t', '') for x in lines_temp]
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
    # print("html",html_content)
    parser = etree.XMLParser(recover=True)
    tree = ET.fromstring(html_content, parser)
    #print_tree(tree, "")
    blocks, listed_blocks = get_blocks(tree)
    print("url", url)
    print("listed block", listed_blocks)
    return blocks, listed_blocks


def get_combined_people_list(persons):
    isShouldContinue = True
    while isShouldContinue:
        persons, isShouldContinue = compare_persons(persons)
    return persons


def compare_persons(persons):
    for i, p1 in enumerate(persons):
        for j, p2 in enumerate(persons):
            if (i != j and check_if_same(p1, p2)):
                persons.remove(p1)
                persons.remove(p2)
                persons.append(combine_persons(p1, p2))
                return persons, True
    return persons, False


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


def check_if_same(p1, p2):
    similarity_score = 100
    if (not (p1["personal"]["mail"] in p2["personal"]["mail"] or p2["personal"]["mail"] in p1["personal"]["mail"])):
        similarity_score -= 20
    if (not (p1["personal"]["phone"] in p2["personal"]["phone"] or p2["personal"]["phone"] in p1["personal"]["phone"])):
        similarity_score -= 20
    if (not (p1["personal"]["web_site"] in p2["personal"]["web_site"] or p2["personal"]["web_site"] in p1["personal"]["web_site"])):
        similarity_score -= 20

    for p1_education in p1["education"]:
        for p2_education in p2["education"]:
            if((p1_education["degree"] == p2_education["degree"] and not(p1_education["university"] == p2_education["university"]))):
                similarity_score -= 10
            if("end_year" in p1_education and "end_year" in p2_education and p1_education["end_year"] == p2_education["end_year"] and not(p1_education["university"] == p2_education["university"])):
                similarity_score -= 10

    for p1_work in p1["work"]:
        for p2_work in p2["work"]:
            if((p1_work["work_place"] == p2_work["work_place"] and not(p1_work["job_title"] == p2_work["job_title"]))):
                similarity_score -= 10
            if("end_year" in p1_work and "end_year" in p2_work and p1_education["end_year"] == p2_education["end_year"] and not(p1_education["work_place"] == p2_education["work_place"])):
                similarity_score -= 10

    return similarity_score > 50


def combine_persons(person_1, person_2):
    combined_person = dict()
    combined_person["personal"] = dict()
    combined_person["education"] = []
    combined_person["work"] = []
    combined_person["publications"] = []
    combined_person["skills"] = []
    combined_person["awards"] = []
    combined_person["services"] = []
    combined_person["courses"] = []
    combined_person["personal"]["name"] = person_1["personal"]["name"]
    combined_person["personal"]["mail"] = person_1["personal"]["mail"] + ("" if (
        person_1["personal"]["mail"] == "" or person_2["personal"]["mail"] == "") else ", ") + person_2["personal"]["mail"]
    combined_person["personal"]["phone"] = person_1["personal"]["phone"] + ("" if (
        person_1["personal"]["phone"] == "" or person_2["personal"]["phone"] == "") else ", ") + person_2["personal"]["phone"]
    combined_person["personal"]["web_site"] = person_1["personal"]["web_site"] + \
        ("" if person_1["personal"]["web_site"] == "" or person_2["personal"]
         ["web_site"] == "" else ", ") + person_2["personal"]["web_site"]
    combined_person["personal"]["address"] = person_1["personal"]["address"] + ("" if (
        person_1["personal"]["address"] == "" or person_2["personal"]["address"] == "") else ", ") + person_2["personal"]["address"]

    for education in (person_1["education"] + person_2["education"]):
        if(not(any(True for x in combined_person["education"] if x["degree"] == education["degree"]))):
            combined_person["education"].append(education)

    for work in (person_1["work"] + person_2["work"]):
        if(not(any(True for x in combined_person["work"] if x["work_place"] == work["work_place"] and x["job_title"] == work["job_title"]))):
            combined_person["work"].append(work)

    combined_person["skills"] = list(
        set(person_1["skills"] + person_2["skills"]))
    combined_person["awards"] = list(
        set(person_1["awards"] + person_2["awards"]))
    combined_person["services"] = list(
        set(person_1["services"] + person_2["services"]))
    combined_person["courses"] = list(
        set(person_1["courses"] + person_2["courses"]))

    combined_person["publications"] = person_1["publications"] if len(
        person_1["publications"]) != 0 else person_2["publications"]

    return combined_person


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
        scanned_block, scanned_listed_block, scanned_content, pdfs = scan_link(
            link, 1, rname)
        print("pdfs cumulative: ", pdfs)
        # print(scanned_block)
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
        person_1 = process_keyword_analysis(
            lines=lines, rname=rname, block_index=block_index, listed_block=scanned_listed_block)
        person_2 = process_keyword_analysis(
            lines=scanned_content.splitlines(), rname=rname)
        person_3 = process_keyword_analysis(
            lines=scanned_content.splitlines(), rname=rname, line_by_line=True)
        person_temp = combine_persons(
            combine_persons(person_1, person_2), person_3)
        for i, pdf in enumerate(pdfs):
            filename = "downloaded_documents/" + rname + "_" + str(i) + ".pdf"
            download_file(pdf, filename)
            content = parse_pdf_tika(filename).splitlines()
            pdf_person = process_keyword_analysis(content, rname=rname)
            person_temp = combine_persons(person_temp, pdf_person)

        persons.append(person_temp)

    # print(link_tree)
    # print("content: " + cv_content)
    # print(cv_content)
    return persons


def scan_link(link, counter=1, rname=""):
    if link in scanned_links:
        return dict(), dict(), "", []
    scanned_links.append(link)
    #print("cv_content", cv_content)
    block = dict()
    listed_blocks = dict()
    content = ""
    pdfs = []
    try:
        if(".pdf" in link):
            pdfs.append(link)
            print("pdf found: ", link)
        else:
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
        # f = open("href_keywords.txt", "r")
        # href_keys = f.readlines()
        # href_keys = [x.replace('\n','') for x in href_keys]
        root_url = urlparse(link).netloc
        index = 0
        for l in soup.find_all('a'):
            # print("href")
            new_link = urllib.parse.urljoin(link, l.get('href'))
            new_link_root = urlparse(new_link).netloc
            if(index > 10):
                break
            if(new_link_root != root_url):
                continue
            # print("href keys", href_keys)
            print("new link", new_link)
            # if(not(any(True for x in href_keys if x.lower() in new_link.lower())) or counter > 10):
            #     #print("not link",new_link)
            #     continue
            index += 1
            #print("yes link",new_link)
            b, lb, c, p = scan_link(new_link, counter - 1, rname)
            pdfs += p
            block = dict(list(block.items()) + list(b.items()))
            listed_blocks = dict(
                list(listed_blocks.items()) + list(lb.items()))
            content += "\n" + c
    #print("aaa", block, listed_blocks, content)
    return block, listed_blocks, content, pdfs


def translate_to_english(text):
    if(len(text) > 1):
        lang = detect(text)
        if(lang != "en"):
            text = GoogleTranslator(source='auto', target='en').translate(text)
            print("translated from " + lang)
    return text

def create_pdf_from_person(person):
    pdf = FPDF()
    pdf.add_font("Arial", "", "./fonts/arial.ttf", uni=True)
    pdf.add_page()

    pdf.set_font("Arial", size=18, style="B")
    pdf.cell(0, 8, txt="CV", ln=1, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, txt="Name: " + person["personal"]["name"], ln=1, align='L')
    pdf.cell(0, 8, txt="Mail: " + person["personal"]["mail"], ln=1, align='L')
    pdf.cell(0, 8, txt="Phone: " + person["personal"]["phone"], ln=1, align='L')
    pdf.cell(0, 8, txt="Web Site: " +
            person["personal"]["web_site"], ln=1, align='L')
    pdf.cell(0, 8, txt="Address: " +
            person["personal"]["address"], ln=1, align='L')

    if(len(person["education"]) > 0):
        pdf.set_font("Arial", size=18, style="B")
        pdf.cell(0, 8, txt="", ln=1, align='L')
        pdf.cell(0, 10, txt="Education", ln=1, align='L')
        pdf.set_font("Arial", size=12)
        for x in person["education"]:
            pdf.cell(0, 8, txt="•" + x["degree"] + ", " + x["department"] + ", " +
                    x["university"] + ", " + x["start_year"] + "-" + x["end_year"], ln=1, align='L')

    if(len(person["work"]) > 0):
        pdf.set_font("Arial", size=18, style="B")
        pdf.cell(0, 8, txt="", ln=1, align='L')
        pdf.cell(0, 10, txt="Work", ln=1, align='L')
        pdf.set_font("Arial", size=12)
        for x in person["work"]:
            pdf.cell(0, 8, txt="•" + x["job_title"] + ", " + x["department"] + ", " +
                    x["work_place"] + ", " + x["start_year"] + "-" + x["end_year"], ln=1, align='L')

    if(len(person["publications"]) > 0):
        pdf.set_font("Arial", size=18, style="B")
        pdf.cell(0, 8, txt="", ln=1, align='L')
        pdf.cell(0, 10, txt="Publications", ln=1, align='L')
        pdf.set_font("Arial", size=12)
        for x in person["publications"]:
            pdf.cell(0, 8, txt="•" + x["title"] + ", " + x["year"], ln=1, align='L')

    if(len(person["skills"]) > 0):
        pdf.set_font("Arial", size=18, style="B")
        pdf.cell(0, 8, txt="", ln=1, align='L')
        pdf.cell(0, 10, txt="Skills", ln=1, align='L')
        pdf.set_font("Arial", size=12)
        for x in person["skills"]:
            pdf.cell(0, 8, txt="•" + x, ln=1, align='L')

    if(len(person["courses"]) > 0):
        pdf.set_font("Arial", size=18, style="B")
        pdf.cell(0, 8, txt="", ln=1, align='L')
        pdf.cell(0, 10, txt="Courses", ln=1, align='L')
        pdf.set_font("Arial", size=12)
        for x in person["courses"]:
            pdf.cell(0, 8, txt="•" + x, ln=1, align='L')

    if(len(person["awards"]) > 0):
        pdf.set_font("Arial", size=18, style="B")
        pdf.cell(0, 8, txt="", ln=1, align='L')
        pdf.cell(0, 10, txt="Awards", ln=1, align='L')
        pdf.set_font("Arial", size=12)
        for x in person["awards"]:
            pdf.cell(0, 8, txt="•" + x, ln=1, align='L')

    if(len(person["services"]) > 0):
        pdf.set_font("Arial", size=18, style="B")
        pdf.cell(0, 8, txt="", ln=1, align='L')
        pdf.cell(0, 10, txt="Services", ln=1, align='L')
        pdf.set_font("Arial", size=12)
        for x in person["services"]:
            pdf.cell(0, 8, txt="•" + x, ln=1, align='L')

    file_path = person["personal"]["name"] + " " + datetime.datetime.now() + ".pdf"
    pdf.output(file_path)
    return file_path
