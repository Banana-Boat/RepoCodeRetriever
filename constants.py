INPUT_SEPARATOR = "##################################################################"
LOG_SEPARATOR = "============================================================================================================"

NO_SUMMARY = "*** No summary ***"

# prompt and max output length of different hierarchies during summarization
SUM_DIR = {
    "system_prompt": '''You will be provided with a directory name and a information list of subdirectories and Java class files in this directory in JSON format as follows:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
You need to summarize the directory in about 100 words.''',
    "max_output_length": 200,
}
SUM_FILE = {
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
RET_DIR_OR_FILE_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a Java code repository, and a information list of directories or Java class files in this repository in JSON format as follows:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
A directory contains Java class files and subdirectories, a Java class file contains a class with the same name and methods in the class.
You need to follow the steps below:
- Step 1: Calculate the probability that these directories or Java class files contain this method directly or indirectly.
- Step 2: Sort these directories or Java class files according to probability from high to low, and return ids of the top 3 (if the length of information list is less than 3, return all ids in order).
- Step 3: Give a reason of about 50 words.
You need to give a JSON object that can be parsed directly as follows:
{"ids": [<PLACEHOLDER>...], "reason": <PLACEHOLDER>}'''
RET_METHOD_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a Java code repository, as well as a information list of methods in this code repository in JSON format as follows:
{"id": <PLACEHOLDER>, "signature": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
You need to infer whether the method provided with the description is one of these methods. If so, answer the id of the method. Otherwise, the answer id is -1. Regardless of whether it is found or not, give a reason of about 30 words.
You need to give a JSON object that can be parsed directly as follows:
{"id": <PLACEHOLDER>, "reason": <PLACEHOLDER>}'''
