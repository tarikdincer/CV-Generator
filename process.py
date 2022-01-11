from server.utils import preprocess_data, predict, idx2tag
from transformers import BertTokenizerFast, BertForTokenClassification
import torch
import spacy
from spacy.matcher import Matcher
from difflib import SequenceMatcher
import json
import re
import pub_utils
import psycopg2
import pyap
import traceback

conn = psycopg2.connect(database="postgres", user = "postgres", password = "admin", host = "127.0.0.1", port = "5432")
cur = conn.cursor()

MAX_LEN = 500
NUM_LABELS = 12
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODEL_PATH = 'bert-base-uncased'
STATE_DICT = torch.load("model-state.bin", map_location=DEVICE)
TOKENIZER = BertTokenizerFast("./vocab/vocab.txt", lowercase=True)

model = BertForTokenClassification.from_pretrained(
    'bert-base-uncased', state_dict=STATE_DICT['model_state_dict'], num_labels=NUM_LABELS)
model.to(DEVICE)


def find_universities_by_pattern(text, university_keywords = ["university", "college", "institute", "school"]):
    universities = []
    # load english language model
    nlp = spacy.load('en_core_web_sm',disable=['ner','textcat'])
    patterns = [[{'POS': {"IN" : ['PROPN']}, 'OP': '?'}, {'LOWER': {"IN": university_keywords}}, {'POS':'ADP'}, {'POS': {"IN" : ['PROPN', 'NOUN']}}, {'POS': {"IN" : ['PROPN', 'NOUN']}, 'OP': '?'}],
    [{'POS': {"IN" : ['PROPN', 'NOUN']}}, {'POS': {"IN" : ['PROPN', 'NOUN']}, 'OP': '?'}, {'LOWER': {"IN": university_keywords}}]]
    matcher = Matcher(nlp.vocab)
    matcher.add("process_1", None, *patterns)
    doc = nlp(text)
    matches = matcher(doc)
    for _, start, end in matches:
        universities.append(doc[start:end].text)

def find_departments_by_pattern(text, department_keywords = ["department"], degree_keywords = ["ba","bsc","bachelor","llb","ms","msc","meng","ma","mba","llm","phd","masters"]):
    departments = []
    # load english language model
    nlp = spacy.load('en_core_web_sm',disable=['ner','textcat'])
    patterns = [[{'LOWER': {"IN": department_keywords}}, {'LOWER': 'of'}, {'POS': {"IN" : ['PROPN', 'NOUN']}}, {'POS': {"IN" : ['PROPN', 'NOUN']}, 'OP': '?'}, {'POS': {"IN" : ['PROPN', 'NOUN']}, 'OP': '?'}],
    [{'LOWER': {"IN": department_keywords}}, {'LOWER': 'of'},{'POS': {"IN" : ['PROPN', 'NOUN']}},{'POS': {"IN" : ['PROPN', 'NOUN']}, 'OP': '?'}, {'POS': 'CCONJ'}, {'POS': {"IN" : ['PROPN', 'NOUN']}},{'POS': {"IN" : ['PROPN', 'NOUN']}, 'OP': '?'}]]
    matcher = Matcher(nlp.vocab)
    matcher.add("process_1", None, *patterns)
    doc = nlp(text)
    matches = matcher(doc)
    for _, start, end in matches:
        departments.append(" ".join(doc[start:end].text.split()[2:]))

def predict_skills(resume_text, rname):
    entities = predict(model, TOKENIZER, idx2tag,
                           DEVICE, resume_text, MAX_LEN)
    found_skills = []
    addresses = []
    #print("entities",entities)
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
                    for skill_sep_2 in skill_sep.split('&'):
                        if(skill_sep_2 not in found_skills):
                            found_skills.append(skill_sep_2.strip())
                    #insertSkill(sname = skill_sep, researcherid = researcherid)  
        if entity['entity'] == 'Location':
            addresses.append(entity["text"])
        

    return found_skills, addresses


def contains_word(s, w):
    return f' {w} ' in f' {s} '

def process_keyword_analysis(lines, tolerance = 0.2, starvation = 2, rname = "", block_threshold = 3):
    lines = [line for line in lines if len(line.strip()) != 0]
    print("lines", lines)
    resume_text = " ".join(lines)

    #re.compile('\d{1,4} [\w\s]{1,20}(?:street|st|avenue|ave|road|rd|highway|hwy|square|sq|trail|trl|drive|dr|court|ct|park|parkway|pkwy|circle|cir|boulevard|blvd)\W?(?=\s|$)', re.IGNORECASE)
    #addresses = pyap.parse("6 King’s College Rd., Toronto, Ontario, Canada M5S 3G4", country='US')
    skills, addresses = predict_skills(resume_text=re.sub(r'[^\w\s]', ' ', resume_text), rname=rname)
    # print("skills",skills)
    # print("addresses",addresses)
    #print("lines",lines)
    f = open("slot_keywords.json")
    data = json.load(f)
    current_slot = "personal"
    person = dict()
    person["personal"] = dict()
    person["personal"]["name"] = rname
    person["personal"]["address"] = addresses[0] if len(addresses) != 0 else ""
    person["education"] = []
    person["work"] = []
    person["publications"] = []
    person["skills"] = skills
    publications = get_pubs(rname)
    education_starvation = 0
    work_starvation = 0
    #c = 0
    slot_lines = []
    personal_lines = ""
    publication_lines = ""
    for line in lines:
        lookup_line = line
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
        slot_lines.append({"slot": current_slot, "line": line})
    c = 0
    previous_slot = ""
    block_index = dict()
    for index, slot_line in enumerate(slot_lines):
        if(slot_line["slot"] == previous_slot):
            c += 1
        else:
            c = 0
        if(c == block_threshold):
            if previous_slot not in block_index:
                block_index[previous_slot] = index - block_threshold
        previous_slot = slot_line["slot"]


    print(block_index)
    for index, line in enumerate(lines):
        #find the slot of line
        
        current_slot = ""
        try:
            for slot, i in block_index.items():
                if i <= index:
                    current_slot = slot
                #print(slot, i)
        except Exception as e:
                    print(traceback.format_exc())
                    print(e)
                    
        
        lookup_line = line
        line = re.sub(r'[^\w\s]', '', line).lower()
        #print(current_slot, line)
        
        # max_slot_conf = 0.0
        # for slot in data:
        #     current_conf = 0.0
        #     for w in slot["high_conf_keywords"]:
        #         if(contains_word(line,w)):
        #             current_conf += 0.3
        #     for w in slot["low_conf_keywords"]:
        #         if(contains_word(line,w)):
        #             current_conf += 0.1
        #     if(current_conf > max_slot_conf + tolerance):
        #         current_slot = slot["slot"]
        #         #print(slot["slot"], line)
        #         max_slot_conf = current_conf
        
        #keyword corpuses
        f_1 = open("university_corpus.txt", "r", encoding="utf-8")
        universities = [x.replace("\n", "").lower() for x in f_1.readlines() if len(x) != 0]
        f_2 = open("department_corpus.txt", "r", encoding="utf-8")
        departments = [x.replace("\n", "").lower() for x in f_2.readlines() if len(x) != 0]
        f_3 = open("degree_corpus.txt", "r", encoding="utf-8")
        degrees = [x.replace("\n", "").lower() for x in f_3.readlines() if len(x) != 0]
        f_4 = open("job_corpus.txt", "r", encoding="utf-8")
        jobs = [x.replace("\n", "").lower() for x in f_4.readlines() if len(x) != 0]
        #find the attributes of line regarding to slot
        
        if(current_slot == "personal"):
            #print("personal",line)
            personal_lines += " " + line
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
                if(len(person["education"]) == 0):
                    person["education"].append(dict())
                person["education"][-1]["end_year"] = years[-1]
                person["education"][-1]["start_year"] = years[0] if len(years) == 2 else ""

            if(len(unis) == 0 and len(deps) == 0 and len(degs) == 0 and len(years) == 0):
                education_starvation += 1


            
            
        elif(current_slot == "work"):
            #print("work",line)
            work_companies = re.findall(r"\b[A-Z]\w+(?:\.com?)?(?:[ -]+(?:&[ -]+)?[A-Z]\w+(?:\.com?)?){0,2}[,\s]+(?i:ltd|llc|inc|plc|co(?:rp)?|group|holding|gmbh)\b", line)
            work_unis =  [re.sub(r'[^\w\s]', '', x) for x in universities if re.sub(r'[^\w\s]', '', x) in line if contains_word(line,re.sub(r'[^\w\s]', '', x))]
            deps = [re.sub(r'[^\w\s]', '', x) for x in departments if x in line if contains_word(line,x)]
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
            
            if(len(deps) != 0):
                if(len(person["work"]) == 0):
                    person["work"].append(dict())
                if("department" in person["work"][-1]):
                    person["work"].append(dict())
                    person["work"][-1]["department"] = deps[0]
                else:
                    person["work"][-1]["department"] = deps[0]
            
            if(len(years) != 0 and len(person["work"]) != 0):
                if(len(person["work"]) == 0):
                    person["work"].append(dict())
                person["work"][-1]["end_year"] = years[-1]
                person["work"][-1]["start_year"] = years[0] if len(years) == 2 else ""
            
            if(len(works) == 0 and len(jbs) == 0 and len(years) == 0):
                work_starvation += 1
        
        elif(current_slot == "publication"):
            publication_lines += " " + line.lower()

    #print("pub lines", publication_lines)
    #print(publications)
    for pub in publications:
        if("title" not in pub):
            continue
        title = re.sub(r'[^\w\s]', '', pub['title']).lower().strip()
        #print("title", title)
        if(len(title) != 0 and title in publication_lines):
            person["publications"] = [x for x in publications if "title" in x and "year" in x]
            break
    
    address = ""
    #print("personal lines", personal_lines)
    streets = re.findall('\d{1,4} [\w\s]{1,20}(?:street|st|avenue|ave|road|rd|highway|hwy|square|sq|trail|trl|drive|dr|court|ct|park|parkway|pkwy|circle|cir|boulevard|blvd)\W?(?=\s|$)', personal_lines, re.IGNORECASE)
    #print("streets", streets)
    if(len(streets) != 0):
        print("street",streets)
        street_index = personal_lines.index(streets[0])
        f_5 = open("country_corpus.txt", "r", encoding="utf-8")
        countries = [x.replace("\n", "").lower() for x in f_5.readlines() if len(x) != 0]
        #print(countries)
        found_countries = [x for x in countries if x.lower() in personal_lines[street_index:].lower() if contains_word(personal_lines[street_index:].lower(),x.lower())]
        print(found_countries)
        if(len(found_countries) != 0):
            country_index = personal_lines[street_index:].lower().index(found_countries[0].lower())
            if(country_index - street_index < 60):
                address = personal_lines[street_index:street_index + country_index + len(found_countries[0])]
                print("personal address", address)
                person["personal"]["address"] = address
            else:
                f_6 = open("city_corpus.txt", "r", encoding="utf-8")
                cities = [x.replace("\n", "").lower() for x in f_6.readlines() if len(x) != 0]
                found_cities = [x for x in cities if x.lower() in personal_lines[street_index:].lower() if contains_word(personal_lines[street_index:].lower(),x.lower())]
                if(len(found_cities) != 0):
                    city_index = personal_lines[street_index:].lower().index(found_cities[0].lower())
                    if(city_index - street_index < 60):
                        address = personal_lines[street_index:street_index + city_index + len(found_cities[0])]
                        print("personal address", address)
                        person["personal"]["address"] = address
                    else:
                        person["personal"]["address"] = streets[0]
        else:
            f_6 = open("city_corpus.txt", "r", encoding="utf-8")
            cities = [x.replace("\n", "").lower() for x in f_6.readlines() if len(x) != 0]
            found_cities = [x for x in cities if x.lower() in personal_lines.lower() if contains_word(personal_lines.lower(),x.lower())]
            if(len(found_cities) != 0):
                city_index = personal_lines[street_index:].lower().index(found_cities[0].lower())
                if(city_index - street_index < 60):
                    address = personal_lines[street_index:street_index + city_index + len(found_cities[0])]
                    print("personal address", address)
                    person["personal"]["address"] = address
                else:
                    person["personal"]["address"] = streets[0]

            
    
    pruned_person = dict()
    pruned_person["personal"] = person["personal"]
    pruned_person["education"] = []
    pruned_person["work"] = []
    pruned_person["publications"] = person["publications"]
    pruned_person["skills"] = skills

    for education in person["education"]:
        if("degree" in education and ("university" in education or "department" in education)):
            if(education not in pruned_person["education"]):
                pruned_person["education"].append(education)
    
    for work in person["work"]:
        if("work_place" in work and "job_title" in work):
            if(work not in pruned_person["work"]):
                pruned_person["work"].append(work)
            

    #print(pruned_person)
    return pruned_person

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

# def get_pubs(rid):
#     # Retrieve the author's data, fill-in, and print
#     res = selectResearcher(researcherid=rid)[0]
#     rname = res[1] + " " + res[2]
#     try:
#         pubs = pub_utils.get_pubs_from_author(rname)
#         if(len(pubs) > 0):
#             publications = json.loads(pubs)
#             for publication in publications:
#                 pid = insertPublication(ptitle = publication["title"], pyear = publication["year"], venue = publication["source"], scholarurl = publication["article_url"])
#                 insertCoauthor(pid, rid)
#     except:
#         print("Publications can not be accessed")

def get_pubs(rname):
    # Retrieve the author's data, fill-in, and print
    publications = []
    try:
        pubs = pub_utils.get_pubs_from_author(rname)
        if(len(pubs) > 0):
            publications = json.loads(pubs)
    except:
        print("Publications can not be accessed")
    
    return publications

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


def check_if_same(p1,p2):
    similarity_score = 100
    if ("mail" in p1["personal"] and "mail" in p2["personal"] and p1["personal"]["mail"] == p2["personal"]["mail"]):
        similarity_score -= 20
    if ("phone" in p1["personal"] and "phone" in p2["personal"] and p1["personal"]["phone"] == p2["personal"]["phone"]):
        similarity_score -= 20
    if ("web_site" in p1["personal"] and "web_site" in p2["personal"] and p1["personal"]["web_site"] == p2["personal"]["web_site"]):
        similarity_score -= 20

    if ("education" in p1 and "education" in p2):
        if (len(p1["education"]) < len(p2["education"])):
            for education1 in p1["education"]:
                if(education1["university"] not in [education2["university"] for education2 in p2["education"]]):
                    similarity_score -= 10
        else:
            for education2 in p2["education"]:
                if(education2["university"] not in [education1["university"] for education1 in p1["education"]]):
                    similarity_score -= 10

    if ("work" in p1 and "work" in p2):
        if (len(p1["work"]) < len(p2["work"])):
            for work1 in p1["work"]:
                if(work1["work_place"] not in [work2["work_place"] for work2 in p2["work"]]):
                    similarity_score -= 10
        else:
            for work2 in p2["work"]:
                if(work2["work_place"] not in [work1["work_place"] for work1 in p1["work"]]):
                    similarity_score -= 10

    if ("skills" in p1 and "skills" in p2):
        if (len(p1["skills"]) < len(p2["skills"])):
            for skill1 in p1["skills"]:
                if(skill1 not in p2["skills"]):
                    similarity_score -= 10
        else:
            for skill2 in p2["skills"]:
                if(skill2 not in p1["skills"]):
                    similarity_score -= 10

    if (similarity_score > 50):
        return True
    return False


def get_different_people(people):
    isExitTime = False
    people_dict = dict()

    while isExitTime == False:
        isExitTime, people_dict = combine_people(people)

    return people_dict

def combine_people(people):
    isCompleted = True
    for i, p1 in enumerate(people):
        for j, p2 in enumerate(people):
            if (i != j and check_if_same(p1,p2)):
                if ("mail" in p2["personal"]):
                    p1["personal"]["mail"] = p2["personal"]["mail"]
                if ("phone" in p2["personal"]):
                    p1["personal"]["phone"] = p2["personal"]["phone"]
                if ("web_site" in p2["personal"]):
                    p1["personal"]["web_site"] = p2["personal"]["web_site"]

                if ("education" in p1 and "education" in p2):
                        for education2 in p2["education"]:
                            isExist = False
                            for i, education1 in enumerate(p1["education"]):
                                if(education2["university"] == education1["university"] and education2["degree"] == education1["degree"]):
                                    if("start_year" in education2):
                                        p1["education"][i]["start_year"] = education2["start_year"]
                                    if("end_year" in education2):
                                        p1["education"][i]["end_year"] = education2["end_year"]
                                    isExist = True
                                    break
                            if(not isExist):
                                p1["education"].append(education2)
                                
                if ("work" in p1 and "work" in p2):
                        for work2 in p2["work"]:
                            isExist = False
                            for i, work1 in enumerate(p1["work"]):
                                if(work2["work_place"] == work1["work_place"] and work2["degree"] == work1["degree"]):
                                    if("start_year" in work2):
                                        p1["work"][i]["start_year"] = work2["start_year"]
                                    if("end_year" in work2):
                                        p1["work"][i]["end_year"] = work2["end_year"]
                                    isExist = True
                                    break
                            if(not isExist):
                                p1["work"].append(work2)

                if ("skill" in p1 and "skill" in p2):
                        for skill2 in p2["skill"]:
                            isExist = False
                            if (skill2 not in p1["skills"]):
                                p1["skills"].append(skill2)

            people.remove(j)
            isCompleted = False
    return isCompleted, people