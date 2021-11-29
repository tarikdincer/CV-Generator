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
from preprocess import parse_html,condense_newline
import textract
from pdfminer.high_level import extract_text
import psycopg2
import re
from scholarly import scholarly

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



def predict_entities(resume_text, researcherid):
    entities = predict(model, TOKENIZER, idx2tag,
                           DEVICE, resume_text, MAX_LEN)
    print(entities)
    for entity in entities:
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
    search_query = scholarly.search_pubs(rname)
    publication = next(search_query, None)
    counter = 0

    while publication is not None and counter < 10:
        publication = next(search_query, None)
        #print(publication)
        pid = insertPublication(ptitle = publication["bib"]["title"], pyear = publication["bib"]["pub_year"], venue = publication["bib"]["venue"], scholarurl = publication["pub_url"], bibtex = scholarly.bibtex(publication))
        insertCoauthor(pid, rid)
        counter += 1    


@app.route("/cv_sent", methods=['POST', 'GET'])
def cv_sent():
    if request.method == 'POST':
        result = request.form
        name = result["Name"]
        surname = result["Surname"]
        website_url = result["Url"]
        rid = insertResearcher(name, surname)
        get_pubs(rid)

        if website_url:
            try:
                web_content = parse_html(website_url)
                predict_entities(resume_text=web_content, researcherid = rid)
            except:
                print("url is not accessible")

        if request.files.get('file', None):
            f = request.files['file']
            f.save(secure_filename(f.filename))
            filename = secure_filename(f.filename)
            if '.txt' in filename:
                try:
                    ftxt = open(filename, 'r')
                    content = condense_newline(ftxt.read())
                    predict_entities(resume_text=content, researcherid = rid)
                except:
                    print("txt not found")
            elif '.doc' in filename:
                try:
                    content = condense_newline(textract.process(filename).decode('utf-8'))
                    predict_entities(resume_text=content)
                except:
                    print(filename, "doc not found")
            elif '.pdf' in filename:
                try:
                    content = condense_newline(extract_text(filename))
                    predict_entities(resume_text=content, researcherid = rid)
                except:
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