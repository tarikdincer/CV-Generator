from re import template
from flask import Flask, jsonify, request, render_template
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
    print(res)
    rname = res[1] + " " + res[2]
    search_query = scholarly.search_keyword(rname)
    print("query", search_query)
    author = scholarly.fill(next(search_query))
    print(author)

    # Print the titles of the author's publications
    print([pub['bib']['title'] for pub in author['publications']])

    # Take a closer look at the first publication
    pub = scholarly.fill(author['publications'][0])
    print(pub)
        


@app.route("/cv_sent", methods=['POST', 'GET'])
def cv_sent():
    if request.method == 'POST':
        result = request.form
        name = result["Name"]
        surname = result["Surname"]
        website_url = result["Url"]
        print(name, surname)
        rid = insertResearcher(name, surname)
        #get_pubs(rid)

        if website_url:
            try:
                print(website_url)
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
                    print("content", content)
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
            print(filename)
        return render_template("index.html")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/cv_create", methods=['POST', 'GET'])
def cv_create():
    rid = request.args.get('researcherid')
    researcher = selectResearcher(researcherid=rid)
    skills = selectSkill(researcherid=rid)
    skill_html = ""
    for skill in skills:
        skill_html += f'''<div>
        <p> {skill[1]} </p>
        </div>'''
    return f"""<div>
    <h3>{researcher[0][1]} {researcher[0][2]}</h3>
    {skill_html}
    </div>"""

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
    print("asdasdasd ", rows)
    return rows

def selectSkill(researcherid):
    cur.execute(f"SELECT * FROM skill WHERE researcherid = {researcherid};")
    rows = cur.fetchall()
    print("asdasdasd ", rows)
    return rows

if __name__ == '__main__':
    app.run()