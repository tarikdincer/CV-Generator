from flask import Flask, jsonify, request, render_template, url_for, redirect, session
from flask_session import Session
from server.utils import preprocess_data, predict, idx2tag
from werkzeug.utils import secure_filename
from werkzeug.datastructures import  FileStorage
from preprocess import parse_html,condense_newline,traverse_web_links,parse_pdf_tika,split_newline
import textract
from pdfminer.high_level import extract_text
from scholarly import scholarly
import traceback
from process import *
import ast

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

app.config['JSON_SORT_KEYS'] = False
UPLOAD_FOLDER = '/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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
        rname = name + " " + surname
        website_url = result["Url"]
        #rid = insertResearcher(name, surname)
        #get_pubs(rid)
        url = None
        persons = []

        if website_url:
            url = website_url

        try:
            #web_content = parse_html(website_url)
            web_persons = traverse_web_links(rname=rname, url=url)
            persons += web_persons
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
                    content = ftxt.readlines()
                    txt_person = process_keyword_analysis(lines=content, rname=rname)
                    persons.append(txt_person)
                    #process_ner(content)
                    #predict_entities(resume_text=content, researcherid = rid, rname=name+" "+surname)
                except Exception as e:
                    print(e)
                    print("txt not found")
            elif '.doc' in filename:
                try:
                    content = split_newline(textract.process(filename).decode('utf-8'))
                    doc_person = process_keyword_analysis(lines=content, rname=rname)
                    persons.append(doc_person)
                    #predict_entities(resume_text=content, researcherid = rid, rname=name+" "+surname)
                except Exception as e:
                    print(filename, "doc not found", e)
            elif '.pdf' in filename:
                try:
                    content = parse_pdf_tika(filename).splitlines()
                    pdf_person = process_keyword_analysis(content, rname=name+" "+surname)
                    persons.append(pdf_person)
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
        print(persons)
        session["persons"] = persons
        #return redirect(url_for('cv_create', researcherid = rid))
        return redirect(url_for('select_people'))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/select_people", methods=['POST', 'GET'])
def select_people():
    #rid = request.args.get('researcherid')
    people = session["persons"]
    print("session", session)
    if people is None:
        return "Please add people parameter"
    # if rid is None:
    #     return "Please add researcherid parameter"
    
    people_tabs = ""
    people_contents = ""
    for i, person in enumerate(people):
        #person = json.loads(person_str)
        isActive = ""
        if(i == 0):
            isActive = "active"
        people_tabs += f'''
        <li class="nav-item" role="presentation">
            <button class="nav-link {isActive}" id="p{i}-tab" data-bs-toggle="tab" href="#p{i}" data-bs-target="#p{i}" type="button" role="tab" aria-controls="home" aria-selected="true">{i}</button>
        </li>
        '''
    for i, person in enumerate(people):
        isActive = ""
        if(i == 0):
            isActive = "show active"
        #person = json.loads(person_str)
        education_html = "<h3> Education </h3>"
        for education in person["education"]:
            education_html += f'''<div>
            <h5> {education["degree"] if "degree" in education else ""} </h5>
            <p> {education["university"] if "university" in education else ""} </p>
            <p> {education["department"] if "department" in education else ""} </p>
            <p> {education["start_year"] if "start_year" in education else ""} </p>
            <p> {education["end_year"] if "end_year" in education else ""} </p>
            </div>'''
        work_html = "<h3> Work Experience </h3>"
        for work in person["work"]:
            work_html += f'''<div>
            <h5> {work["job_title"] if "job_title" in work else ""} </h5>
            <p> {work["work_place"] if "work_place" in work else ""} </p>
            <p> {work["department"] if "department" in work else ""} </p>
            <p> {work["start_year"] if "start_year" in work else ""} </p>
            <p> {work["end_year"] if "end_year" in work else ""} </p>
            </div>'''
        skill_html = "<h3> Skills </h3>"
        for skill in person["skills"]:
            skill_html += f'''<div>
            <p> {skill} </p>
            </div>'''
        # pub_html = "<h3> Publications </h3>"
        # for pub in pubs:
        #     pub_html += f'''<div>
        #     <h5> {pub[0]} ({pub[1]}) </h5>
        #     </div>'''

        people_contents += f'''<div class="tab-pane fade {isActive}" id="p{i}" role="tabpanel" aria-labelledby="p{i}-tab">
            {education_html}
            {work_html}
            {skill_html}
        </div>
        '''
    return f"""
    <!DOCTYPE html>
    <head>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.2/dist/js/bootstrap.bundle.min.js"></script>
        <title>Cv Generator</title>
    </head>
    <body>
        <div class="container-fluid p-5 bg-primary text-white text-center">
            <h2> Who are you looking for? </h2>
            <ul class="nav nav-tabs" id="myTab" role="tablist">
            {people_tabs}
            </ul>
            <div class="tab-content" id="myTabContent">
            {people_contents}
            </div>
        </div>
    </body>
    """

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


# @app.route('/predict', methods=['POST'])
# def predict_api():
#     if request.method == 'POST':
#         data = io.BytesIO(request.files.get('resume').read())
#         resume_text = preprocess_data(data)
#         entities = predict(model, TOKENIZER, idx2tag,
#                            DEVICE, resume_text, MAX_LEN)
#         return jsonify({'entities': entities})  

if __name__ == '__main__':
    app.run(debug=True)