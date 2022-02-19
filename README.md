---CV Generator---
------------------

To install and run,
1. $cd <project_path>
2. $python3 -m venv venv (For Windows: $py -3 -m venv venv)
3. $. venv/bin/activate (For Windows: $venv\Scripts\activate)
4. $pip install Flask
5. $pip freeze > requirements. txt
6. $pip install -r requirements.txt
7. $flask run
8. Go to http://127.0.0.1:5000/ on your browser

Also, you should create database using PostgreSQL with these informations: 
database="postgres", user="postgres", password="admin", host="127.0.0.1", port="5432" (You can edit them in "preprocess.py")
To create tables, you can use "create_tables.sql".

Algorithm:
----------
1. Get researcher name, url (optional), file (optional) from the form (index.html) -> app.py/cv_sent()
2. Get list of links from google search, add given url if exists -> preprocess.py/traverse_web_links()
	2.1. For each link, 
		2.1.1. Get content of both it and its reference links _> preprocess.py/scan_link()
			2.1.1.1. Extract content blocks and assign to the slots which are given in "slot_keywords.json" -> preprocess.py/extract_from_url() (Note: This function calls get_blocks() and returns two dictionaries (block, listed_block). If content is in list tags, it returns a list for the slot. Each item in list is considered as a potential element for the slot, for example, {skills:["x","y","z"]}. Otherwise, it returns content string, {skills:"x, y and z"})
		2.1.2. Analyze the content blocks created above and extract informations of the person. -> process.py/process_keyword_analysis() (called with predetermined block_index parameter)
		2.1.3. Get whole content as a string, analyze it and extract informations of the person. -> process.py/process_keyword_analysis()
		2.1.4. Assign slot to each line of content, analyze it and extract informations of the person. -> process.py/process_keyword_analysis() (called with line_by_line parameter)
		2.1.5. If there is any pdf file in the links, analyze it and extract informations of the person. -> process.py/process_keyword_analysis()
		2.1.6. Combine these informations and create a person object as a dictionary.  -> process.py/combine_persons()
3. If there is a file given by user, analyze it and extract informations of the person. -> process.py/process_keyword_analysis()
4. Get the person objects created above and combine them if they are the same person -> process.py/check_if_same(), process.py/combine_persons()
5. Display the final people list -> app.py/select_people()


process.py/process_keyword_analysis():
--------------------------------------
1. Only for cases (2.1.3 and 2.1.4) where blocks are not predetermined: For given content, extract the blocks and assign a slot to them. To do this, compare each line of the content with the slot keywords, assign the most similar one as its slot. Then, if there are 3 line in a row with the same slot, define the first line as block start and reassign the lines between two block starts as the slot of the upper one (variable block_index is used for this).
2. If block_index is still empty, assign slot to the lines independently.
3. By iterating the lines, extract slot values according to current_slot and add them to the person dictionary.
4. If listed_block is not empty, extract slot values from the list elements and add them to the person dictionary.
5. For publication slot, if content is compatible with the crossref query, add publication list of crossref to the person dictionary.
6. Extract address by getting first index as the index of street information and last index as the index of country, or city if country does not exists.
7. Prune person dictionary by eliminating meaningless information.
8. Return person.


preprocess.py/get_blocks():
---------------------------
1. Get a node of DOM tree (Starting from the root).
2. Get the child elements with header, strong and bold tags.
3. For each of these child elements,
	3.1. If the text of the element is compatible with one of the slots and not covered before,
		3.1.1. While the element is single child of its parent, get parent element.
		3.1.2. Get the content of the next sibling element and repeat it while the tag of the element is same with that of the previous one.
		3.1.3. Add each content as a block with the compatible slot.
4. Repeat the function for child elements.
5. Return blocks and listed_blocks.