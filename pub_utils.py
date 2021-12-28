import subprocess


def get_pubs_from_author(author_name):
    process = subprocess.Popen(['pop8query', '--crossref','--author="'+ author_name +'"', '--format=json', '--max=10'], 
                            stdout=subprocess.PIPE,
                            universal_newlines=True, encoding='utf-8')
    #outf = open("outf.txt", "w", encoding="utf-8")
    out_str = ""
    while True:
        output = process.stdout.readline()
        out_str += output.strip()
        #print(output.strip())
        #utf.write(output.strip())
        # Do something else
        return_code = process.poll()
        if return_code is not None:
            print('RETURN CODE', return_code)
            # Process has finished, read rest of the output 
            for output in process.stdout.readlines():
                print(output.strip())
            break
    return out_str

#get_pubs_from_author("Tansel Ozyer")