import os
import re
from boilerpy3 import extractors

# Condenses all repeating newline characters into one single newline character
def condense_newline(text):
    return ' '.join([p for p in re.split('\n|\r', text) if len(p) > 0])

# Returns the text from a HTML file
def parse_html(html_path):
    # Text extraction with boilerpy3
    html_extractor = extractors.KeepEverythingExtractor()
    return condense_newline(html_extractor.get_content_from_url(html_path))