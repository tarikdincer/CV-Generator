from re import template
from flask import Flask, jsonify, request, render_template, url_for, redirect
import io
import os
import argparse
import torch
from transformers import BertTokenizerFast, BertForTokenClassification
from server.utils import preprocess_data, predict, idx2tag
from werkzeug.utils import secure_filename
from werkzeug.datastructures import  FileStorage
from preprocess import parse_html,condense_newline,traverse_web_links,parse_pdf,parse_pdf_tika
import textract
from pdfminer.high_level import extract_text
import psycopg2
import re
from scholarly import scholarly
import pub_utils
import json
from difflib import SequenceMatcher
import spacy
import pandas as pd
import re
import traceback

app = Flask(__name__)
conn = psycopg2.connect(database="postgres", user = "postgres", password = "admin", host = "127.0.0.1", port = "5432")
cur = conn.cursor()

app.config['JSON_SORT_KEYS'] = False
UPLOAD_FOLDER = '/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER 

MAX_LEN = 500
NUM_LABELS = 12
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODEL_PATH = 'bert-base-uncased'
STATE_DICT = torch.load("model-state.bin", map_location=DEVICE)
TOKENIZER = BertTokenizerFast("./vocab/vocab.txt", lowercase=True)

model = BertForTokenClassification.from_pretrained(
    'bert-base-uncased', state_dict=STATE_DICT['model_state_dict'], num_labels=NUM_LABELS)
model.to(DEVICE)


@app.route('/predict', methods=['POST'])
def predict_api():
    if request.method == 'POST':
        data = io.BytesIO(request.files.get('resume').read())
        resume_text = preprocess_data(data)
        entities = predict(model, TOKENIZER, idx2tag,
                           DEVICE, resume_text, MAX_LEN)
        return jsonify({'entities': entities})

def process_ner(raw_text):
    NER = spacy.load("en_core_web_lg")
    print(NER.get_pipe('ner').labels)
    text1= NER(raw_text)
    for word in text1.ents:
        print(word.text,word.label_)

def contains_word(s, w):
    return f' {w} ' in f' {s} '

def process_keyword_analysis(lines, tolerance = 0.2, starvation = 2, rname = ""):
    resume_text = " ".join(lines)
    skills = predict_skills(resume_text=resume_text, rname=rname)
    print("skills",skills)
    #print(lines)
    lines = [line for line in lines if len(line.strip()) != 0]
    f = open("slot_keywords.json")
    data = json.load(f)
    current_slot = "personal"
    person = dict()
    person["personal"] = dict()
    person["education"] = []
    person["work"] = []
    person["skills"] = skills
    education_starvation = 0
    work_starvation = 0
    c = 0

    for line in lines:
        #find the slot of line
        lookup_line = line.lower()
        line = re.sub(r'[^\w\s]', '', line).lower()
        max_slot_conf = 0.0
        for slot in data:
            current_conf = 0.0
            for w in slot["high_conf_keywords"]:
                if(contains_word(line,w)):
                    current_conf += 0.3
            for w in slot["low_conf_keywords"]:
                if(contains_word(line,w)):
                    current_conf += 0.1
            if(current_conf > max_slot_conf + tolerance):
                current_slot = slot["slot"]
                #print(slot["slot"], line)
                max_slot_conf = current_conf
        
        #keyword corpuses
        f_1 = open("university_corpus.txt", "r", encoding="utf-8")
        universities = [x.replace("\n", "").lower() for x in f_1.readlines() if len(x) != 0]
        f_2 = open("department_corpus.txt", "r", encoding="utf-8")
        departments = [x.replace("\n", "").lower() for x in f_2.readlines() if len(x) != 0]
        f_3 = open("degree_corpus.txt", "r", encoding="utf-8")
        degrees = [x.replace("\n", "").lower() for x in f_3.readlines() if len(x) != 0]
        f_4 = open("job_corpus.txt", "r", encoding="utf-8")
        jobs = [x.replace("\n", "").lower() for x in f_4.readlines() if len(x) != 0]
        if(c < 20):
            print(current_slot,line, len(line))
            c+=1
        #find the attributes of line regarding to slot
        if(current_slot == "personal"):
            #print("personal",line)
            phone_numbers = re.findall(r"(\d{3}[-\.\s]??\d{3}[-\.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-\.\s]??\d{4}|\d{3}[-\.\s]??\d{4})", lookup_line)
            if len(phone_numbers) != 0:
                person["personal"]["phone"] = phone_numbers[0]
            mail_addresses = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", lookup_line)
            if len(mail_addresses) != 0:
                person["personal"]["mail"] = mail_addresses[0]
            web_sites = re.findall(r'''(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))''',lookup_line)
            if len(web_sites) != 0:
                person["personal"]["web_site"] = web_sites[0]
            
        elif(current_slot == "education"):
            #print("education",line)
            unis =  [re.sub(r'[^\w\s]', '', x) for x in universities if re.sub(r'[^\w\s]', '', x) in line if contains_word(line,re.sub(r'[^\w\s]', '', x))]
            deps = [re.sub(r'[^\w\s]', '', x) for x in departments if x in line if contains_word(line,x)]
            degs = [re.sub(r'[^\w\s]', '', x) for x in degrees if x in line if contains_word(line,x)]
            years = re.findall(r'\b(?:2050|20[0-4][0-9]|19[56789][0-9])\b', line)

            if(len(unis) != 0):
                if(len(person["education"]) == 0 or education_starvation == starvation):
                    person["education"].append(dict())
                    education_starvation = 0
                if("university" in person["education"][-1]):
                    person["education"].append(dict())
                    person["education"][-1]["university"] = unis[0]
                else:
                    person["education"][-1]["university"] = unis[0]
            
            if(len(degs) != 0):
                if(len(person["education"]) == 0):
                    person["education"].append(dict())
                if("degree" in person["education"][-1]):
                    person["education"].append(dict())
                    person["education"][-1]["degree"] = degs[0]
                else:
                    person["education"][-1]["degree"] = degs[0]
            
            if(len(deps) != 0):
                if(len(person["education"]) == 0):
                    person["education"].append(dict())
                if("department" in person["education"][-1]):
                    person["education"].append(dict())
                    person["education"][-1]["department"] = deps[0]
                else:
                    person["education"][-1]["department"] = deps[0]
            
            if(len(years) != 0):
                person["education"][-1]["end_year"] = years[-1]
                person["education"][-1]["start_year"] = years[0] if len(years) == 2 else ""

            if(len(unis) == 0 and len(deps) == 0 and len(degs) == 0 and len(years) == 0):
                education_starvation += 1


            
            
        elif(current_slot == "work"):
            #print("work",line)
            work_companies = re.findall(r"\b[A-Z]\w+(?:\.com?)?(?:[ -]+(?:&[ -]+)?[A-Z]\w+(?:\.com?)?){0,2}[,\s]+(?i:ltd|llc|inc|plc|co(?:rp)?|group|holding|gmbh)\b", line)
            work_unis =  [re.sub(r'[^\w\s]', '', x) for x in universities if re.sub(r'[^\w\s]', '', x) in line if contains_word(line,re.sub(r'[^\w\s]', '', x))]
            jbs =  [re.sub(r'[^\w\s]', '', x) for x in sorted(jobs, key=len, reverse=True) if x in line if contains_word(line,x)]
            years = re.findall(r'\b(?:2050|20[0-4][0-9]|19[56789][0-9])\b', line)
            works = work_companies + work_unis

            if(len(works) != 0):
                if(len(person["work"]) == 0 or work_starvation == starvation):
                    person["work"].append(dict())
                    work_starvation = 0
                if("work_place" in person["work"][-1]):
                    person["work"].append(dict())
                    person["work"][-1]["work_place"] = works[0]
                else:
                    person["work"][-1]["work_place"] = works[0]
            
            if(len(jbs) != 0):
                if(len(person["work"]) == 0):
                    person["work"].append(dict())
                if("job_title" in person["work"][-1]):
                    person["work"].append(dict())
                    person["work"][-1]["job_title"] = jbs[0]
                else:
                    person["work"][-1]["job_title"] = jbs[0]
            
            if(len(years) != 0 and len(person["work"]) != 0):
                person["work"][-1]["end_year"] = years[-1]
                person["work"][-1]["start_year"] = years[0] if len(years) == 2 else ""
            
            if(len(works) == 0 and len(jbs) == 0 and len(years) == 0):
                work_starvation += 1
        
    print(person)
    return person



def predict_skills(resume_text, rname):
    entities = predict(model, TOKENIZER, idx2tag,
                           DEVICE, resume_text, MAX_LEN)
    skills = []
    print("entities",entities)
    is_relevant = True
    for entity in entities:
        if entity['entity'] == 'Name':
            if  SequenceMatcher(None, entity["text"], rname).ratio() > 0.7:
                is_relevant = True
            else:
                is_relevant = False
        
        # if not is_relevant:
        #     continue

        if entity['entity'] == 'Skills':
            r = re.compile(r'(?:[^,(]|\([^)]*\))+')
            skills = r.findall(entity["text"])
            for skill in skills:
                for skill_sep in skill.split(' and'):
                    if(skill_sep not in skills):
                        skills.append(skill_sep)
                    #insertSkill(sname = skill_sep, researcherid = researcherid)   

    return skills    

            

def predict_entities(resume_text, researcherid, rname):
    entities = predict(model, TOKENIZER, idx2tag,
                           DEVICE, resume_text, MAX_LEN)
    print(entities)
    is_relevant = True
    for entity in entities:
        if entity['entity'] == 'Name':
            if  SequenceMatcher(None, entity["text"], rname).ratio() > 0.7:
                is_relevant = True
            else:
                is_relevant = False
        
        if not is_relevant:
            continue

        if entity['entity'] == 'Skills':
            r = re.compile(r'(?:[^,(]|\([^)]*\))+')
            skills = r.findall(entity["text"])
            for skill in skills:
                for skill_sep in skill.split(' and'):
                    insertSkill(sname = skill_sep, researcherid = researcherid)
        
        degree_index = 0
        designation_index = 0
        if entity['entity'] == 'Skills':
            r = re.compile(r'(?:[^,(]|\([^)]*\))+')
            skills = r.findall(entity["text"])
            for skill in skills:
                for skill_sep in skill.split(' and'):
                    insertSkill(sname = skill_sep, researcherid = researcherid)
        if entity['entity'] == 'Degree':
            oid = -1
            for entity_temp in entities:
                temp_index = 0
                if entity_temp['entity'] == 'College Name':
                    if temp_index == degree_index:
                        oid = insertOrganization(oname = entity_temp['text'])
                    temp_index += 1
            degree_index += 1
            if oid == -1:
                oid = insertOrganization()
            insertEducation(organizationid = oid, researcherid = researcherid, edegree = entity['text'])
        if entity['entity'] == 'Designation':
            oid = -1
            for entity_temp in entities:
                temp_index = 0
                if entity_temp['entity'] == 'Companies worked at':
                    if temp_index == designation_index:
                        oid = insertOrganization(oname = entity_temp['text'])
                    temp_index += 1
            designation_index += 1
            if oid == -1:
                oid = insertOrganization()
            insertWork(organizationid = oid, researcherid = researcherid, wtitle = entity['text'])
    
    

def get_pubs(rid):
    # Retrieve the author's data, fill-in, and print
    res = selectResearcher(researcherid=rid)[0]
    rname = res[1] + " " + res[2]
    try:
        pubs = pub_utils.get_pubs_from_author(rname)
        if(len(pubs) > 0):
            publications = json.loads(pubs)
            for publication in publications:
                pid = insertPublication(ptitle = publication["title"], pyear = publication["year"], venue = publication["source"], scholarurl = publication["article_url"])
                insertCoauthor(pid, rid)
    except:
        print("Publications can not be accessed")
        

    # search_query = scholarly.search_pubs(rname)
    # publication = next(search_query, None)
    # counter = 0

    # while publication is not None and counter < 5:
    #     publication = next(search_query, None)
    #     #print(publication)
    #     pid = insertPublication(ptitle = publication["bib"]["title"], pyear = publication["bib"]["pub_year"], venue = publication["bib"]["venue"], scholarurl = publication["pub_url"], bibtex = scholarly.bibtex(publication))
    #     insertCoauthor(pid, rid)
    #     counter += 1    


@app.route("/cv_sent", methods=['POST', 'GET'])
def cv_sent():
    if request.method == 'POST':
        result = request.form
        name = result["Name"]
        surname = result["Surname"]
        website_url = result["Url"]
        rid = insertResearcher(name, surname)
        get_pubs(rid)
        url = None

        if website_url:
            url = website_url

        try:
            # web_content = parse_html(website_url)
            #web_content = traverse_web_links(name + " " + surname, url)
            #predict_entities(resume_text=web_content, researcherid = rid, rname=name+" "+surname)
            print("traversed web contents")
        except Exception as e:
            print(e)
            print("web scan is not accessible")

        if request.files.get('file', None):
            f = request.files['file']
            f.save(secure_filename(f.filename))
            filename = secure_filename(f.filename)
            if '.txt' in filename:
                try:
                    ftxt = open(filename, 'r')
                    content = condense_newline(ftxt.read())
                    process_ner(content)
                    #predict_entities(resume_text=content, researcherid = rid, rname=name+" "+surname)
                except Exception as e:
                    print(e)
                    print("txt not found")
            elif '.doc' in filename:
                try:
                    content = condense_newline(textract.process(filename).decode('utf-8'))
                    predict_entities(resume_text=content, researcherid = rid, rname=name+" "+surname)
                except Exception as e:
                    print(filename, "doc not found", e)
            elif '.pdf' in filename:
                try:
                    content = parse_pdf_tika(filename).splitlines()
                    process_keyword_analysis(content, rname=name+" "+surname)
                    #process_keyword_analysis(extract_text(filename).splitlines())
                    #content = condense_newline(extract_text(filename))
                    #predict_entities(resume_text=content, researcherid = rid, rname=name+" "+surname)
                except Exception as e:
                    print(traceback.format_exc())
                    print(e)
                    print("pdf not found")
            # f.save(os.path.join(app.config['UPLOAD_FOLDER'],\
            #          filename))
            #doc_pdf = weasyprint.HTML(url_for('cv_create', researcherid = rid)).write_pdf(name + '_' + surname + '_cv.pdf')
        return redirect(url_for('cv_create', researcherid = rid))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/cv_create", methods=['POST', 'GET'])
def cv_create():
    rid = request.args.get('researcherid')
    if rid is None:
        return "Please add researcherid parameter"
    researcher = selectResearcher(researcherid=rid)
    educations = selectEducation(researcherid=rid)
    works = selectWork(researcherid=rid)
    skills = selectSkill(researcherid=rid)
    pubs = selectPublication(researcherid=rid)
    education_html = "<h3> Education </h3>"
    for education in educations:
        education_html += f'''<div>
        <h5> {education[0]} </h5>
        <p> {education[1]} </p>
        </div>'''
    work_html = "<h3> Work Experience </h3>"
    for work in works:
        work_html += f'''<div>
        <h5> {work[0]} </h5>
        <p> {work[1]} </p>
        </div>'''
    skill_html = "<h3> Skills </h3>"
    for skill in skills:
        skill_html += f'''<div>
        <p> {skill[1]} </p>
        </div>'''
    pub_html = "<h3> Publications </h3>"
    for pub in pubs:
        pub_html += f'''<div>
        <h5> {pub[0]} ({pub[1]}) </h5>
        </div>'''

    return f"""
    <!DOCTYPE html>
    <head>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.2/dist/js/bootstrap.bundle.min.js"></script>
        <title>Cv Generator</title>
    </head>
    <body>
        <div class="container-fluid p-5 bg-primary text-white text-center">
            <h2>{researcher[0][1]} {researcher[0][2]}</h2>
            {education_html}
            {work_html}
            {skill_html}
            {pub_html}
        </div>
    </body>
    """

def insertResearcher(rname = "", rlastname = "", orchid=0):
    cur.execute(f"INSERT INTO researcher (rname, rlastname, orchid) \
      VALUES ('{rname}', '{rlastname}', {orchid}) RETURNING researcherid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]

def insertSkill(sname = "", proficiencylevel = 0, researcherid=0):
    cur.execute(f"INSERT INTO skill (sname, proficiencylevel, researcherid) \
      VALUES ('{sname}', '{proficiencylevel}', {researcherid}) RETURNING skillid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]

def insertOrganization(oname = "", ocity = "", ostate = "", ocountry = ""):
    cur.execute(f"INSERT INTO organization (oname, ocity, ostate, ocountry) \
      VALUES ('{oname}', '{ocity}', '{ostate}', '{ocountry}') RETURNING organizationid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]

def insertWork(researcherid = 0, organizationid = 0, wtitle = "", wdepartment = ""):
    cur.execute(f"INSERT INTO work (researcherid, organizationid, wtitle, wdepartment) \
      VALUES ({researcherid}, {organizationid}, '{wtitle}', '{wdepartment}') RETURNING organizationid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]

def insertEducation(researcherid = 0, organizationid = 0, edegree = "", edepartment = ""):
    cur.execute(f"INSERT INTO education (researcherid, organizationid, edegree, edepartment) \
      VALUES ({researcherid}, {organizationid}, '{edegree}', '{edepartment}') RETURNING organizationid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]

def selectResearcher(researcherid):
    cur.execute(f"SELECT * FROM researcher WHERE researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows

def selectSkill(researcherid):
    cur.execute(f"SELECT * FROM skill WHERE researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows

def insertPublication(ptitle = "", pyear = 0, ptype = "", venue = "", doi = 0, scholarurl = "", bibtex = ""):
    cur.execute(f"INSERT INTO publication (ptitle, pyear, ptype, venue, doi, scholarurl, bibtex) \
      VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING publicationid;", (ptitle, pyear, ptype, venue, doi, scholarurl, bibtex))
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]

def insertCoauthor(publicationid = 0, researcherid = 0):
    cur.execute(f"INSERT INTO co_author (publicationid, researcherid) \
      VALUES ({publicationid}, {researcherid}) RETURNING publicationid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]

def selectPublication(researcherid):
    cur.execute(f"SELECT ptitle, pyear, venue FROM co_author, publication WHERE co_author.publicationid = publication.publicationid AND co_author.researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows

def selectEducation(researcherid):
    cur.execute(f"SELECT edegree,oname FROM education, organization WHERE education.organizationid = organization.organizationid AND education.researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows

def selectWork(researcherid):
    cur.execute(f"SELECT wtitle,oname FROM work, organization WHERE work.organizationid = organization.organizationid AND work.researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows

if __name__ == '__main__':
    app.run(debug=True)