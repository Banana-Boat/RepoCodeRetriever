INPUT_SEPARATOR = "##################################################################"
LOG_SEPARATOR = "============================================================================================================"

NO_SUMMARY = "*** No summary ***"

# prompt and max output length of different hierarchies during summarization
SUM_DIR = {
    "prompt": "Summarize the directory below in about 100 words, don't include examples and details.",
    "max_output_length": 200,
}
SUM_FILE = {
    "prompt": "Summarize the file below in about 50 words, don't include examples and details.",
    "max_output_length": 100,
}
SUM_CLS = {
    "prompt": "Summarize the Java class below in about 50 words, don't include examples and details.",
    "max_output_length": 100,
}
SUM_METHOD = {
    "prompt": "Summarize the Java method below in about 30 words.",
    "max_output_length": 60,
}


RET_MAX_OUTPUT_LENGTH = 300

# prompt of different hierarchies during retrieval
RET_MAX_BACKTRACK_COUNT = 2
RET_DIR_OR_FILE_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a Java code repository, and a information list of directories or files in this repository in JSON format as follows:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
A directory contains files and subdirectories, a file contains classes, and a class contains methods.
You need to follow the steps below:
- Step 1: Calculate the probability that these directories or files contain this method indirectly.
- Step 2: Sort these directories or files according to probability from high to low, and return ids of the top 3 (if the length of information list is less than 3, return all ids in order).
- Step 3: Give a reason of about 50 words.
You need to give a JSON object that can be parsed directly as follows:
{"ids": [<PLACEHOLDER>...], "reason": <PLACEHOLDER>}'''
RET_CLS_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a Java code repository, and a information list of Java classes in this repository in JSON format as follows:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
You need to follow the steps below:
- Step 1: Calculate the probability that these classes contain this method.
- Step 2: Sort these classes according to probability from high to low, and return ids of the top 3 (if the number of classes is less than 3, return all class's ids in order).
- Step 3: Give a reason of about 50 words.
You need to give a JSON object that can be parsed directly as follows:
{"ids": [<PLACEHOLDER>...], "reason": <PLACEHOLDER>}'''
RET_METHOD_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a Java code repository, as well as a information list of methods in this code repository in JSON format as follows:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "signature": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
You need to infer whether the method provided with the description is one of these methods. If so, answer the id of the method. Otherwise, the answer id is -1. Regardless of whether it is found or not, give a reason of about 30 words.
You need to give a JSON object that can be parsed directly as follows:
{"id": <PLACEHOLDER>, "reason": <PLACEHOLDER>}'''
