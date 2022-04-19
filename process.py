from turtle import pu
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
from langdetect import detect
from deep_translator import GoogleTranslator

conn = psycopg2.connect(database="postgres", user="postgres",
                        password="admin", host="127.0.0.1", port="5432")
cur = conn.cursor()

nlp = spacy.load('en_core_web_sm', disable=['ner', 'textcat'])

MAX_LEN = 500
NUM_LABELS = 12
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODEL_PATH = 'bert-base-uncased'
STATE_DICT = torch.load("model-state.bin", map_location=DEVICE)
TOKENIZER = BertTokenizerFast("./vocab/vocab.txt", lowercase=True)

model = BertForTokenClassification.from_pretrained(
    'bert-base-uncased', state_dict=STATE_DICT['model_state_dict'], num_labels=NUM_LABELS)
model.to(DEVICE)


def find_companies_by_pattern(text, work_keywords=["group", "ltd", "llc", "inc", "plc", "holding", "gmbh", "corp", "corporation"]):
    companies = []
    patterns = [[{'POS': {"IN": ['PROPN']}, 'OP': '?'}, {'LOWER': {"IN": work_keywords}}, {'POS': 'ADP'}, {'POS': {"IN": ['PROPN', 'NOUN']}}, {'POS': {"IN": ['PROPN', 'NOUN']}, 'OP': '?'}],
                [{'POS': {"IN": ['PROPN', 'NOUN']}}, {'POS': {"IN": ['PROPN', 'NOUN']}, 'OP': '?'}, {'LOWER': {"IN": work_keywords}}]]
    matcher = Matcher(nlp.vocab)
    matcher.add("process_1", patterns)
    doc = nlp(text)
    matches = matcher(doc)
    for _, start, end in matches:
        companies.append(doc[start:end].text)
    return companies


def find_universities_by_pattern(text, university_keywords=["university", "college", "institute", "school"]):
    universities = []

    patterns = [[{'POS': {"IN": ['PROPN']}, 'OP': '?'}, {'LOWER': {"IN": university_keywords}}, {'POS': 'ADP'}, {'POS': {"IN": ['PROPN', 'NOUN']}}, {'POS': {"IN": ['PROPN', 'NOUN']}, 'OP': '?'}],
                [{'POS': {"IN": ['PROPN', 'NOUN']}}, {'POS': {"IN": ['PROPN', 'NOUN']}, 'OP': '?'}, {'LOWER': {"IN": university_keywords}}]]
    matcher = Matcher(nlp.vocab)
    matcher.add("process_1", patterns)
    doc = nlp(text)
    matches = matcher(doc)
    for _, start, end in matches:
        universities.append(doc[start:end].text)
    return universities


def find_departments_by_pattern(text, department_keywords=["department"], degree_keywords=["ba", "bsc", "bachelor", "llb", "ms", "msc", "meng", "ma", "mba", "llm", "phd", "masters"]):
    departments = []
    # load english language model
    # nlp = spacy.load('en_core_web_sm', disable=['ner', 'textcat'])
    # patterns = [[{'LOWER': {"IN": department_keywords}}, {'LOWER': 'of'}, {'POS': {"IN": ['PROPN', 'NOUN']}}, {'POS': {"IN": ['PROPN', 'NOUN']}, 'OP': '?'}, {'POS': {"IN": ['PROPN', 'NOUN']}, 'OP': '?'}],
    #             [{'LOWER': {"IN": department_keywords}}, {'LOWER': 'of'}, {'POS': {"IN": ['PROPN', 'NOUN']}}, {'POS': {"IN": ['PROPN', 'NOUN']}, 'OP': '?'}, {'POS': 'CCONJ'}, {'POS': {"IN": ['PROPN', 'NOUN']}}, {'POS': {"IN": ['PROPN', 'NOUN']}, 'OP': '?'}]]
    # matcher = Matcher(nlp.vocab)
    # matcher.add("process_1", patterns)
    # doc = nlp(text)
    # matches = matcher(doc)
    # for _, start, end in matches:
    #     departments.append(" ".join(doc[start:end].text.split()[2:]))
    return departments


def predict_skills(resume_text, rname):
    entities = predict(model, TOKENIZER, idx2tag,
                       DEVICE, resume_text, MAX_LEN)
    found_skills = []
    addresses = []
    # print("entities",entities)
    is_relevant = True
    for entity in entities:
        if entity['entity'] == 'Name':
            if SequenceMatcher(None, entity["text"], rname).ratio() > 0.7:
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


def translate_to_english(text):
    try:
        if(len(text) > 1):
            lang = detect(text)
            if(lang != "en"):
                text = GoogleTranslator(
                    source='auto', target='en').translate(text)
                #print("translated from " + lang)
    except:
        pass
        #print("translate error")
    return text


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
            if("university" in p1_education and "university" in p2_education):
                if((p1_education["degree"] == p2_education["degree"] and not(p1_education["university"] == p2_education["university"]))):
                    similarity_score -= 10
                if("end_year" in p1_education and "end_year" in p2_education and p1_education["end_year"] == p2_education["end_year"] and not(p1_education["university"] == p2_education["university"])):
                    similarity_score -= 10

    for p1_work in p1["work"]:
        for p2_work in p2["work"]:
            if((p1_work["work_place"] == p2_work["work_place"] and not(p1_work["job_title"] == p2_work["job_title"]))):
                similarity_score -= 10
            if("end_year" in p1_work and "end_year" in p2_work and p1_work["end_year"] == p2_work["end_year"] and not(p1_work["work_place"] == p2_work["work_place"])):
                similarity_score -= 10

    return similarity_score > 50


def process_keyword_analysis(lines, tolerance=0.2, starvation=2, rname="", block_threshold=3, block_index=None, listed_block=None, line_by_line=False):
    # lines = [translate_to_english(x) for x in lines]

    print("lines", lines)
    print("scanned_listed_block", listed_block)
    #print("lines", lines)
    resume_text = " ".join(lines)

    #re.compile('\d{1,4} [\w\s]{1,20}(?:street|st|avenue|ave|road|rd|highway|hwy|square|sq|trail|trl|drive|dr|court|ct|park|parkway|pkwy|circle|cir|boulevard|blvd)\W?(?=\s|$)', re.IGNORECASE)
    #addresses = pyap.parse("6 King’s College Rd., Toronto, Ontario, Canada M5S 3G4", country='US')
    skills, addresses = predict_skills(resume_text=re.sub(
        r'[^\w\s]', ' ', resume_text), rname=rname)
    # print("skills",skills)
    # print("addresses",addresses)
    # print("lines",lines)
    f = open("slot_keywords.json")
    data = json.load(f)
    current_slot = "personal"
    person = dict()
    person["personal"] = dict()
    person["personal"]["name"] = rname
    person["personal"]["phone"] = ""
    person["personal"]["mail"] = ""
    person["personal"]["address"] = ""
    person["personal"]["web_site"] = ""
    person["personal"]["address"] = addresses[0] if len(addresses) != 0 else ""
    person["education"] = []
    person["work"] = []
    person["publications"] = []
    person["skills"] = skills
    person["awards"] = []
    person["services"] = []
    person["courses"] = []
    publications = get_pubs(rname)
    education_starvation = 0
    work_starvation = 0
    f_1 = open("university_corpus.txt", "r", encoding="utf-8")
    universities = [x.replace("\n", "").lower()
                    for x in f_1.readlines() if len(x) != 0]
    f_2 = open("department_corpus.txt", "r", encoding="utf-8")
    departments = [x.replace("\n", "").lower()
                   for x in f_2.readlines() if len(x) != 0]
    f_3 = open("degree_corpus.txt", "r", encoding="utf-8")
    degrees = [x.replace("\n", "").lower()
               for x in f_3.readlines() if len(x) != 0]
    f_4 = open("job_corpus.txt", "r", encoding="utf-8")
    jobs = [x.replace("\n", "").lower()
            for x in f_4.readlines() if len(x) != 0]
    #c = 0
    slot_lines = []
    personal_lines = ""
    publication_lines = ""

    if(block_index is None):
        block_index = dict()
        for line in lines:
            lookup_line = line
            line = re.sub(r'[^\w\s]', '', line).lower()
            max_slot_conf = 0.0
            for slot in data:
                current_conf = 0.0
                for w in slot["high_conf_keywords"]:
                    if(contains_word(line, w)):
                        current_conf += 0.3
                for w in slot["low_conf_keywords"]:
                    if(contains_word(line, w)):
                        current_conf += 0.1
                if(current_conf > max_slot_conf + tolerance):
                    current_slot = slot["slot"]
            slot_lines.append({"slot": current_slot, "line": line})
        c = 0
        previous_slot = ""

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
        line = line.strip()
        if len(line) == 0:
            continue
        # find the slot of line

        current_slot = ""
        if(len(block_index) > 0 and line_by_line == False):
            try:
                for slot, i in block_index.items():
                    if i <= index:
                        current_slot = slot
                    #print(slot, i)
            except Exception as e:
                print(traceback.format_exc())
                print(e)
        else:
            max_slot_conf = 0.0
            for slot in data:
                current_conf = 0.0
                for w in slot["high_conf_keywords"]:
                    if(contains_word(line, w)):
                        current_conf += 0.3
                for w in slot["low_conf_keywords"]:
                    if(contains_word(line, w)):
                        current_conf += 0.1
                if(current_conf > max_slot_conf + tolerance):
                    current_slot = slot["slot"]
                    max_slot_conf = current_conf

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

        # keyword corpuses

        # find the attributes of line regarding to slot

        if(current_slot == "personal"):
            # print("personal",line)
            personal_lines += " " + line
            phone_numbers = re.findall(
                r"(\d{3}[-\.\s]??\d{3}[-\.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-\.\s]??\d{4}|\d{3}[-\.\s]??\d{4})", lookup_line)
            if len(phone_numbers) != 0:
                person["personal"]["phone"] = phone_numbers[0]
            mail_addresses = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", lookup_line)
            if len(mail_addresses) != 0:
                person["personal"]["mail"] = mail_addresses[0]
            web_sites = re.findall(r'''(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))''', lookup_line)
            if len(web_sites) != 0:
                person["personal"]["web_site"] = web_sites[0]

        elif(current_slot == "education"):
            # print("education",line)
            unis = [re.sub(r'[^\w\s]', '', x) for x in universities if re.sub(
                r'[^\w\s]', '', x) in line if contains_word(line, re.sub(r'[^\w\s]', '', x))] + find_universities_by_pattern(line)
            deps = [re.sub(r'[^\w\s]', '', x)
                    for x in departments if x in line if contains_word(line, x)]
            degs = [re.sub(r'[^\w\s]', '', x)
                    for x in degrees if x in line if contains_word(line, x)]
            years = re.findall(
                r'\b(?:2050|20[0-4][0-9]|19[56789][0-9])\b', line)

            if(len(unis) != 0):
                if(len(person["education"]) == 0 or education_starvation == starvation):
                    person["education"].append(dict())
                    education_starvation = 0
                if("university" in person["education"][-1]):
                    person["education"].append(dict())
                    person["education"][-1]["university"] = unis[0]
                    education_starvation = 0
                else:
                    person["education"][-1]["university"] = unis[0]

            if(len(degs) != 0):
                if(len(person["education"]) == 0 or education_starvation == starvation):
                    person["education"].append(dict())
                    education_starvation = 0
                if("degree" in person["education"][-1]):
                    person["education"].append(dict())
                    person["education"][-1]["degree"] = degs[0]
                    education_starvation = 0
                else:
                    person["education"][-1]["degree"] = degs[0]

            if(len(deps) != 0):
                if(len(person["education"]) == 0 or education_starvation == starvation):
                    person["education"].append(dict())
                    education_starvation = 0
                if("department" in person["education"][-1]):
                    person["education"].append(dict())
                    person["education"][-1]["department"] = deps[0]
                    education_starvation = 0
                else:
                    person["education"][-1]["department"] = deps[0]

            if(len(years) != 0):
                if(len(person["education"]) == 0):
                    person["education"].append(dict())
                    education_starvation = 0
                person["education"][-1]["end_year"] = years[-1]
                person["education"][-1]["start_year"] = years[0] if len(
                    years) == 2 else ""
                if(person["education"][-1]["end_year"] < person["education"][-1]["start_year"]):
                    start_year = person["education"][-1]["end_year"]
                    end_year = person["education"][-1]["start_year"]
                    person["education"][-1]["start_year"] = start_year
                    person["education"][-1]["end_year"] = end_year

            if(len(unis) == 0 and len(deps) == 0 and len(degs) == 0 and len(years) == 0):
                education_starvation += 1

        elif(current_slot == "work"):
            # print("work",line)
            work_companies = re.findall(
                r"\b[A-Z]\w+(?:\.com?)?(?:[ -]+(?:&[ -]+)?[A-Z]\w+(?:\.com?)?){0,2}[,\s]+(?i:ltd|llc|inc|plc|co(?:rp)?|group|holding|gmbh)\b", line) + find_companies_by_pattern(line)
            work_unis = [re.sub(r'[^\w\s]', '', x) for x in universities if re.sub(r'[^\w\s]', '', x) in line if contains_word(
                line, re.sub(r'[^\w\s]', '', x))] + find_universities_by_pattern(line)

            deps = [re.sub(r'[^\w\s]', '', x)
                    for x in departments if x in line if contains_word(line, x)]
            jbs = [re.sub(r'[^\w\s]', '', x) for x in sorted(
                jobs, key=len, reverse=True) if x in line if contains_word(line, x)]
            years = re.findall(
                r'\b(?:2050|20[0-4][0-9]|19[56789][0-9])\b', line)
            works = work_companies + work_unis

            if(len(works) != 0):
                if(len(person["work"]) == 0 or work_starvation == starvation):
                    person["work"].append(dict())
                    work_starvation = 0
                if("work_place" in person["work"][-1]):
                    person["work"].append(dict())
                    person["work"][-1]["work_place"] = works[0]
                    work_starvation = 0
                else:
                    person["work"][-1]["work_place"] = works[0]

            if(len(jbs) != 0):
                if(len(person["work"]) == 0 or work_starvation == starvation):
                    person["work"].append(dict())
                    work_starvation = 0
                if("job_title" in person["work"][-1]):
                    person["work"].append(dict())
                    person["work"][-1]["job_title"] = jbs[0]
                    work_starvation = 0
                else:
                    person["work"][-1]["job_title"] = jbs[0]

            if(len(deps) != 0):
                if(len(person["work"]) == 0 or work_starvation == starvation):
                    person["work"].append(dict())
                    work_starvation = 0
                if("department" in person["work"][-1]):
                    person["work"].append(dict())
                    person["work"][-1]["department"] = deps[0]
                    work_starvation = 0
                else:
                    person["work"][-1]["department"] = deps[0]

            if(len(years) != 0 and len(person["work"]) != 0):
                if(len(person["work"]) == 0):
                    person["work"].append(dict())
                    work_starvation = 0
                person["work"][-1]["end_year"] = years[-1]
                person["work"][-1]["start_year"] = years[0] if len(
                    years) == 2 else ""
                if(person["work"][-1]["end_year"] < person["work"][-1]["start_year"]):
                    start_year = person["work"][-1]["end_year"]
                    end_year = person["work"][-1]["start_year"]
                    person["work"][-1]["start_year"] = start_year
                    person["work"][-1]["end_year"] = end_year

            if(len(works) == 0 and len(jbs) == 0 and len(years) == 0):
                work_starvation += 1

        elif(current_slot == "publication"):
            publication_lines += " " + line.lower()

    if(listed_block is not None):
        for slot, lines in listed_block.items():
            for line in lines:
                line = translate_to_english(
                    re.sub(r'[^\w\s]', '', line)).lower().strip()
                if(slot == "research_interests"):
                    person["skills"].append(line)
                elif(slot == "personal"):
                    # print("personal",line)
                    personal_lines += " " + line
                    phone_numbers = re.findall(
                        r"(\d{3}[-\.\s]??\d{3}[-\.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-\.\s]??\d{4}|\d{3}[-\.\s]??\d{4})", lookup_line)
                    if len(phone_numbers) != 0:
                        person["personal"]["phone"] = phone_numbers[0]
                    mail_addresses = re.findall(
                        r"[\w\.-]+@[\w\.-]+\.\w+", lookup_line)
                    if len(mail_addresses) != 0:
                        person["personal"]["mail"] = mail_addresses[0]
                    web_sites = re.findall(r'''(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))''', lookup_line)
                    if len(web_sites) != 0:
                        person["personal"]["web_site"] = web_sites[0]
                elif(slot == "education"):
                    # print("education",line)
                    unis = [re.sub(r'[^\w\s]', '', x) for x in universities if re.sub(r'[^\w\s]', '', x) in line if contains_word(
                        line, re.sub(r'[^\w\s]', '', x))] + find_universities_by_pattern(line)
                    deps = [re.sub(r'[^\w\s]', '', x)
                            for x in departments if x in line if contains_word(line, x)]
                    degs = [re.sub(r'[^\w\s]', '', x)
                            for x in degrees if x in line if contains_word(line, x)]
                    years = re.findall(
                        r'\b(?:2050|20[0-4][0-9]|19[56789][0-9])\b', line)

                    if(len(unis) != 0):
                        if(len(person["education"]) == 0 or education_starvation == starvation):
                            person["education"].append(dict())
                            education_starvation = 0
                        if("university" in person["education"][-1]):
                            person["education"].append(dict())
                            person["education"][-1]["university"] = unis[0]
                            education_starvation = 0
                        else:
                            person["education"][-1]["university"] = unis[0]

                    if(len(degs) != 0):
                        if(len(person["education"]) == 0 or education_starvation == starvation):
                            person["education"].append(dict())
                            education_starvation = 0
                        if("degree" in person["education"][-1]):
                            person["education"].append(dict())
                            person["education"][-1]["degree"] = degs[0]
                            education_starvation = 0
                        else:
                            person["education"][-1]["degree"] = degs[0]

                    if(len(deps) != 0):
                        if(len(person["education"]) == 0 or education_starvation == starvation):
                            person["education"].append(dict())
                            education_starvation = 0
                        if("department" in person["education"][-1]):
                            person["education"].append(dict())
                            person["education"][-1]["department"] = deps[0]
                            education_starvation = 0
                        else:
                            person["education"][-1]["department"] = deps[0]

                    if(len(years) != 0):
                        if(len(person["education"]) == 0):
                            person["education"].append(dict())
                            education_starvation = 0
                        person["education"][-1]["end_year"] = years[-1]
                        person["education"][-1]["start_year"] = years[0] if len(
                            years) == 2 else ""
                        if(person["education"][-1]["end_year"] < person["education"][-1]["start_year"]):
                            start_year = person["education"][-1]["end_year"]
                            end_year = person["education"][-1]["start_year"]
                            person["education"][-1]["start_year"] = start_year
                            person["education"][-1]["end_year"] = end_year

                    if(len(unis) == 0 and len(deps) == 0 and len(degs) == 0 and len(years) == 0):
                        education_starvation += 1
                elif(slot == "work"):
                    # print("work",line)
                    work_companies = re.findall(
                        r"\b[A-Z]\w+(?:\.com?)?(?:[ -]+(?:&[ -]+)?[A-Z]\w+(?:\.com?)?){0,2}[,\s]+(?i:ltd|llc|inc|plc|co(?:rp)?|group|holding|gmbh)\b", line) + find_companies_by_pattern(line)
                    work_unis = [re.sub(r'[^\w\s]', '', x) for x in universities if re.sub(r'[^\w\s]', '', x) in line if contains_word(
                        line, re.sub(r'[^\w\s]', '', x))] + find_universities_by_pattern(line)
                    deps = [re.sub(r'[^\w\s]', '', x)
                            for x in departments if x in line if contains_word(line, x)]
                    jbs = [re.sub(r'[^\w\s]', '', x) for x in sorted(
                        jobs, key=len, reverse=True) if x in line if contains_word(line, x)]
                    years = re.findall(
                        r'\b(?:2050|20[0-4][0-9]|19[56789][0-9])\b', line)
                    works = work_companies + work_unis

                    if(len(works) != 0):
                        if(len(person["work"]) == 0 or work_starvation == starvation):
                            person["work"].append(dict())
                            work_starvation = 0
                        if("work_place" in person["work"][-1]):
                            person["work"].append(dict())
                            person["work"][-1]["work_place"] = works[0]
                            work_starvation = 0
                        else:
                            person["work"][-1]["work_place"] = works[0]

                    if(len(jbs) != 0):
                        if(len(person["work"]) == 0 or work_starvation == starvation):
                            person["work"].append(dict())
                            work_starvation = 0
                        if("job_title" in person["work"][-1]):
                            person["work"].append(dict())
                            person["work"][-1]["job_title"] = jbs[0]
                            work_starvation = 0
                        else:
                            person["work"][-1]["job_title"] = jbs[0]

                    if(len(deps) != 0):
                        if(len(person["work"]) == 0 or work_starvation == starvation):
                            person["work"].append(dict())
                            work_starvation = 0
                        if("department" in person["work"][-1]):
                            person["work"].append(dict())
                            person["work"][-1]["department"] = deps[0]
                            work_starvation = 0
                        else:
                            person["work"][-1]["department"] = deps[0]

                    if(len(years) != 0 and len(person["work"]) != 0):
                        if(len(person["work"]) == 0):
                            person["work"].append(dict())
                            work_starvation = 0
                        person["work"][-1]["end_year"] = years[-1]
                        person["work"][-1]["start_year"] = years[0] if len(
                            years) == 2 else ""
                        if(person["work"][-1]["end_year"] < person["work"][-1]["start_year"]):
                            start_year = person["work"][-1]["end_year"]
                            end_year = person["work"][-1]["start_year"]
                            person["work"][-1]["start_year"] = start_year
                            person["work"][-1]["end_year"] = end_year

                    if(len(works) == 0 and len(jbs) == 0 and len(years) == 0):
                        work_starvation += 1
                elif(slot == "award"):
                    person["awards"].append(line)

                elif(slot == "service"):
                    person["services"].append(line)

                elif(slot == "courses"):
                    person["courses"].append(line)

                elif(slot == "publication"):
                    publication_lines += " " + line.lower()

    #print("pub lines", publication_lines)
    # print(publications)
    for pub in publications:
        if("title" not in pub):
            continue
        title = re.sub(r'[^\w\s]', '', pub['title']).lower().strip()
        #print("title", title)
        if(len(title) != 0 and title in publication_lines):
            person["publications"] = [
                x for x in publications if "title" in x and "year" in x]
            break

    address = ""
    #print("personal lines", personal_lines)
    streets = re.findall(
        r'\d{1,4} [\w\s]{1,20}(?:street|st|avenue|ave|road|rd|highway|hwy|square|sq|trail|trl|drive|dr|court|ct|park|parkway|pkwy|circle|cir|boulevard|blvd)\W?(?=\s|$)', personal_lines, re.IGNORECASE)
    #print("streets", streets)
    if(len(streets) != 0):
        print("street", streets)
        street_index = personal_lines.index(streets[0])
        f_5 = open("country_corpus.txt", "r", encoding="utf-8")
        countries = [x.replace("\n", "").lower()
                     for x in f_5.readlines() if len(x) != 0]
        # print(countries)
        found_countries = [x for x in countries if x.lower() in personal_lines[street_index:].lower(
        ) if contains_word(personal_lines[street_index:].lower(), x.lower())]
        print(found_countries)
        if(len(found_countries) != 0):
            country_index = personal_lines[street_index:].lower().index(
                found_countries[0].lower())
            if(country_index - street_index < 60):
                address = personal_lines[street_index:street_index +
                                         country_index + len(found_countries[0])]
                print("personal address", address)
                person["personal"]["address"] = address
            else:
                f_6 = open("city_corpus.txt", "r", encoding="utf-8")
                cities = [x.replace("\n", "").lower()
                          for x in f_6.readlines() if len(x) != 0]
                found_cities = [x for x in cities if x.lower() in personal_lines[street_index:].lower(
                ) if contains_word(personal_lines[street_index:].lower(), x.lower())]
                if(len(found_cities) != 0):
                    city_index = personal_lines[street_index:].lower().index(
                        found_cities[0].lower())
                    if(city_index - street_index < 60):
                        address = personal_lines[street_index:street_index +
                                                 city_index + len(found_cities[0])]
                        print("personal address", address)
                        person["personal"]["address"] = address
                    else:
                        person["personal"]["address"] = streets[0]
        else:
            f_6 = open("city_corpus.txt", "r", encoding="utf-8")
            cities = [x.replace("\n", "").lower()
                      for x in f_6.readlines() if len(x) != 0]
            found_cities = [x for x in cities if x.lower() in personal_lines.lower(
            ) if contains_word(personal_lines.lower(), x.lower())]
            if(len(found_cities) != 0):
                city_index = personal_lines[street_index:].lower().index(
                    found_cities[0].lower())
                if(city_index - street_index < 60):
                    address = personal_lines[street_index:street_index +
                                             city_index + len(found_cities[0])]
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
    pruned_person["awards"] = person["awards"]
    pruned_person["services"] = person["services"]
    pruned_person["courses"] = person["courses"]

    for education in person["education"]:
        if("degree" in education and ("university" in education or "department" in education)):
            if(education not in pruned_person["education"]):
                pruned_person["education"].append(education)

    for work in person["work"]:
        if("work_place" in work and "job_title" in work):
            if(work not in pruned_person["work"]):
                pruned_person["work"].append(work)

    # print(pruned_person)
    return pruned_person


def predict_entities(resume_text, researcherid, rname):
    entities = predict(model, TOKENIZER, idx2tag,
                       DEVICE, resume_text, MAX_LEN)
    print(entities)
    is_relevant = True
    for entity in entities:
        if entity['entity'] == 'Name':
            if SequenceMatcher(None, entity["text"], rname).ratio() > 0.7:
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
                    insertSkill(sname=skill_sep, researcherid=researcherid)

        degree_index = 0
        designation_index = 0
        if entity['entity'] == 'Skills':
            r = re.compile(r'(?:[^,(]|\([^)]*\))+')
            skills = r.findall(entity["text"])
            for skill in skills:
                for skill_sep in skill.split(' and'):
                    insertSkill(sname=skill_sep, researcherid=researcherid)
        if entity['entity'] == 'Degree':
            oid = -1
            for entity_temp in entities:
                temp_index = 0
                if entity_temp['entity'] == 'College Name':
                    if temp_index == degree_index:
                        oid = insertOrganization(oname=entity_temp['text'])
                    temp_index += 1
            degree_index += 1
            if oid == -1:
                oid = insertOrganization()
            insertEducation(organizationid=oid,
                            researcherid=researcherid, edegree=entity['text'])
        if entity['entity'] == 'Designation':
            oid = -1
            for entity_temp in entities:
                temp_index = 0
                if entity_temp['entity'] == 'Companies worked at':
                    if temp_index == designation_index:
                        oid = insertOrganization(oname=entity_temp['text'])
                    temp_index += 1
            designation_index += 1
            if oid == -1:
                oid = insertOrganization()
            insertWork(organizationid=oid, researcherid=researcherid,
                       wtitle=entity['text'])

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


#######################################################################
def insertResearcher(rname="", rlastname="", orchid=0, rmail="", rphone="", rwebsite="", raddress=""):
    # todo: ayni kisi varsa onu don
    if len(raddress) > 190:
        raddress = raddress[0:190]
    cur.execute(f"INSERT INTO researcher (rname, rlastname, orchid, rmail, rphone, rwebsite, raddress) \
      VALUES ('{rname}', '{rlastname}', '{orchid}', '{rmail}', '{rphone}', '{rwebsite}', '{raddress}') RETURNING researcherid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


def insertSkill(sname="", proficiencylevel=0, researcherid=0):
    cur.execute(
        f"SELECT skillid FROM skill WHERE researcherid= {researcherid} AND sname = '{sname}'  AND proficiencylevel = '{proficiencylevel}';")
    awards = cur.fetchall()
    if(len(awards) > 0):
        return awards[0][0]
    cur.execute(f"INSERT INTO skill (sname, proficiencylevel, researcherid) \
      VALUES ('{sname}', '{proficiencylevel}', {researcherid}) RETURNING skillid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


def insertAward(aname="", ayear=0, researcherid=0):
    if(ayear == ""):
        ayear = 0
    cur.execute(
        f"SELECT awardid FROM award WHERE researcherid= {researcherid} AND aname = '{aname}'  AND ayear = '{ayear}';")
    awards = cur.fetchall()
    if(len(awards) > 0):
        return awards[0][0]
    cur.execute(f"INSERT INTO award (aname, ayear, researcherid) \
      VALUES ('{aname}', '{ayear}', {researcherid}) RETURNING awardid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


def insertService(srole="", swhere="", syear=0, researcherid=0):
    if(syear == ""):
        syear = 0
    cur.execute(
        f"SELECT serviceid FROM service WHERE researcherid= {researcherid} AND srole = '{srole}'  AND swhere = '{swhere}' AND syear = '{syear}';")
    services = cur.fetchall()
    if(len(services) > 0):
        return services[0][0]
    cur.execute(f"INSERT INTO service (srole, swhere, syear, researcherid) \
      VALUES ('{srole}', '{swhere}', '{syear}', {researcherid}) RETURNING serviceid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


def insertGivenCourse(cname="", code="", cyear=0, csemester="", researcherid=0):
    if(cyear == ""):
        cyear = 0
    cur.execute(
        f"SELECT courseid FROM given_course WHERE researcherid= {researcherid} AND cname = '{cname}' AND code = '{code}'  AND cyear = '{cyear}' AND csemester = '{csemester}';")
    awards = cur.fetchall()
    if(len(awards) > 0):
        return awards[0][0]
    cur.execute(f"INSERT INTO given_course (cname, code, cyear, csemester, researcherid) \
      VALUES ('{cname}', '{code}', '{cyear}', '{csemester}', {researcherid}) RETURNING courseid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


def insertWork(researcherid=0, organizationid=0, wtitle="", wdepartment="", startyear=0, endyear=0):
    if(startyear == ""):
        startyear = 0
    if(endyear == ""):
        endyear = 0
    cur.execute(
        f"SELECT organizationid FROM work WHERE researcherid= {researcherid} AND organizationid = {organizationid} AND wtitle = '{wtitle}' AND wdepartment = '{wdepartment}';")
    work = cur.fetchall()
    if(len(work) > 0):
        return work[0][0]
    cur.execute(f"INSERT INTO work (researcherid, organizationid, wtitle, wdepartment, startyear, endyear) \
      VALUES ({researcherid}, {organizationid}, '{wtitle}', '{wdepartment}', '{startyear}', '{endyear}') RETURNING organizationid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


def insertEducation(researcherid=0, organizationid=0, edegree="", edepartment="", startyear=0, endyear=0):
    if(startyear == ""):
        startyear = 0
    if(endyear == ""):
        endyear = 0
    cur.execute(
        f"SELECT organizationid FROM education WHERE researcherid= {researcherid} AND organizationid = {organizationid} AND edegree = '{edegree}' AND edepartment = '{edepartment}';")
    educations = cur.fetchall()
    if(len(educations) > 0):
        return educations[0][0]
    cur.execute(f"INSERT INTO education (researcherid, organizationid, edegree, edepartment, startyear, endyear) \
      VALUES ({researcherid}, {organizationid}, '{edegree}', '{edepartment}', '{startyear}', '{endyear}') RETURNING organizationid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


def insertOrganization(oname="", ocity="", ostate="", ocountry=""):
    cur.execute(
        f"SELECT organizationid FROM organization WHERE oname = '{oname}';")
    orgs = cur.fetchall()
    if(len(orgs) > 0):
        return orgs[0][0]
    cur.execute(f"INSERT INTO organization (oname, ocity, ostate, ocountry) \
      VALUES ('{oname}', '{ocity}', '{ostate}', '{ocountry}') RETURNING organizationid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


def insertPublication(ptitle="", pyear=0, ptype="", venue="", doi=0, scholarurl="", bibtex=""):
    if(pyear == ""):
        pyear = 0
    cur.execute(
        f"SELECT publicationid FROM publication WHERE ptitle = '{ptitle}';")
    pubs = cur.fetchall()
    if(len(pubs) > 0):
        return pubs[0][0]
    cur.execute(f"INSERT INTO publication (ptitle, pyear, ptype, venue, doi, scholarurl, bibtex) \
      VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING publicationid;", (ptitle, pyear, ptype, venue, doi, scholarurl, bibtex))
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


def insertCoauthor(publicationid=0, researcherid=0):
    cur.execute(
        f"SELECT publicationid FROM co_author WHERE researcherid= {researcherid} AND publicationid = {publicationid};")
    co_authors = cur.fetchall()
    if(len(co_authors) > 0):
        return co_authors[0][0]
    cur.execute(f"INSERT INTO co_author (publicationid, researcherid) \
      VALUES ({publicationid}, {researcherid}) RETURNING publicationid;")
    rows = cur.fetchall()
    conn.commit()
    return rows[0][0]


#########################################################
def selectResearcher(researcherid):
    cur.execute(
        f"SELECT rname,rlastname,orchid,rmail,rphone,rwebsite,raddress FROM researcher WHERE researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows


def selectSkill(researcherid):
    cur.execute(
        f"SELECT sname,proficiencylevel FROM skill WHERE researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows


def selectAward(researcherid):
    cur.execute(
        f"SELECT aname,ayear FROM award WHERE researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows


def selectService(researcherid):
    cur.execute(
        f"SELECT swhere,srole,syear FROM service WHERE researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows


def selectGivenCourse(researcherid):
    cur.execute(
        f"SELECT cname,code,cyear,csemester FROM given_course WHERE researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows


def selectPublication(researcherid):
    cur.execute(
        f"SELECT ptitle, pyear, venue FROM co_author, publication WHERE co_author.publicationid = publication.publicationid AND co_author.researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows


def selectEducation(researcherid):
    cur.execute(
        f"SELECT edepartment, edegree, startyear, endyear, oname FROM education, organization WHERE education.organizationid = organization.organizationid AND education.researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows


def selectWork(researcherid):
    cur.execute(
        f"SELECT wdepartment, wtitle, startyear, endyear, oname FROM work, organization WHERE work.organizationid = organization.organizationid AND work.researcherid = {researcherid};")
    rows = cur.fetchall()
    return rows


def selectOrganization(oname=""):
    cur.execute(
        f"SELECT oname,ocity,ostate,ocountry FROM organization WHERE oname = '{oname}';")
    rows = cur.fetchall()
    return rows

############################################################################


def updateResearcher(researcherid=0, orchid=0, rmail="", rphone="", rwebsite="", raddress=""):
    # todo: ayni kisi varsa onu don
    if len(raddress) > 190:
        raddress = raddress[0:190]
    cur.execute(f"UPDATE researcher SET orchid = '{orchid}', rmail = '{rmail}', rphone = '{rphone}', rwebsite = '{rwebsite}', raddress = '{raddress}' \
      WHERE researcherid = {researcherid} RETURNING researcherid;")
    cur.fetchall()
    conn.commit()

############################################################################


def insert_person(person):
    r_name = person["personal"]["name"]
    rid = 0
    similar_person = search_researcher(person)
    if(similar_person == {}):
        rid = insertResearcher(rname=r_name[0:r_name.rfind(
            ' ')], rlastname=r_name[r_name.rfind(' ') + 1], rmail=person["personal"]["mail"],
            rphone=person["personal"]["phone"], rwebsite=person["personal"]["web_site"], raddress=person["personal"]["address"])
    else:
        rid = similar_person["researcher_id"]
        rmail = person["personal"]["mail"] if similar_person["personal"][
            "mail"] in person["personal"]["mail"] else similar_person["personal"]["mail"]
        rphone = person["personal"]["phone"] if similar_person["personal"][
            "phone"] in person["personal"]["phone"] else similar_person["personal"]["phone"]
        rwebsite = person["personal"]["web_site"] if similar_person["personal"][
            "web_site"] in person["personal"]["web_site"] else similar_person["personal"]["web_site"]
        raddress = person["personal"]["address"] if similar_person["personal"][
            "address"] in person["personal"]["address"] else similar_person["personal"]["address"]
        updateResearcher(researcherid=rid, rmail=rmail,
                         rphone=rphone, rwebsite=rwebsite, raddress=raddress)

    for education in person["education"]:
        oid = insertOrganization(oname=education["university"])
        insertEducation(researcherid=rid, organizationid=oid,
                        edegree=education["degree"], edepartment=education["department"], startyear=education["start_year"], endyear=education["end_year"])

    for work in person["work"]:
        oid = insertOrganization(oname=work["work_place"])
        insertWork(researcherid=rid, organizationid=oid,
                   wtitle=work["job_title"], wdepartment=work["department"], startyear=work["start_year"], endyear=work["end_year"])

    for pub in person["publications"]:
        pid = insertPublication(ptitle=pub["title"], pyear=pub["year"])
        insertCoauthor(researcherid=rid, publicationid=pid)

    for skill in person["skills"]:
        insertSkill(sname=skill, researcherid=rid)

    for award in person["awards"]:
        insertAward(aname=award, researcherid=rid)

    for service in person["services"]:
        insertService(srole=service, researcherid=rid)

    for course in person["courses"]:
        insertGivenCourse(cname=course, researcherid=rid)


def select_person(rid):
    person = dict()

    # rname,rlastname,orchid,rmail,rphone,rwebsite,raddress
    researcher_q = selectResearcher(researcherid=rid)[0]
    # edepartment,edegree,startyear,endyear,oname
    education_q = selectEducation(researcherid=rid)
    # wdepartment,wtitle,startyear,endyear,oname
    work_q = selectWork(researcherid=rid)
    publication_q = selectPublication(researcherid=rid)  # ptitle,pyear,venue
    skill_q = selectSkill(researcherid=rid)  # sname,proficiencylevel
    award_q = selectAward(researcherid=rid)  # aname,ayear
    service_q = selectService(researcherid=rid)  # swhere,srole,syear
    # cname,code,cyear,csemester
    course_q = selectGivenCourse(researcherid=rid)

    person["personal"] = {"name": researcher_q[0] + " " + researcher_q[1], "mail": researcher_q[3],
                          "phone": researcher_q[4], "web_site": researcher_q[5], "address": researcher_q[6]}
    person["education"] = [{"department": x[0], "degree":x[1], "university":x[4],
                            "start_year": x[2], "end_year": x[3]} for x in education_q]
    person["work"] = [{"department": x[0], "job_title":x[1],
                       "work_place":x[4], "start_year": x[2], "end_year": x[3]} for x in work_q]
    person["publications"] = [{"title": x[0], "year":x[1]}
                              for x in publication_q]
    person["skills"] = [x[0] for x in skill_q]
    person["awards"] = [x[0] for x in award_q]
    person["services"] = [x[0] for x in service_q]
    person["courses"] = [x[0] for x in course_q]

    return person


def search_researcher(person):
    r_name = person["personal"]["name"]
    cur.execute(
        f"SELECT researcherid FROM researcher WHERE rname = '{r_name[0:r_name.rfind(' ')]}' AND rlastname = '{r_name[r_name.rfind(' ') + 1]}';")
    researcher_ids = cur.fetchall()

    if(len(researcher_ids) == 0):
        return {}
    else:
        for researcher_id in researcher_ids:
            person_temp = select_person(rid=researcher_id[0])
            if(check_if_same(person, person_temp)):
                person_temp["researcher_id"] = researcher_id[0]
                return person_temp
        return {}
