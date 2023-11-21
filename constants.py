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
    "prompt": "Summarize the Java {} below in about 50 words, don't include examples and details.",
    "max_output_length": 100,
}
SUM_METHOD = {
    "prompt": "Summarize the Java method below in about 30 words.",
    "max_output_length": 60,
}


RET_MAX_OUTPUT_LENGTH = 200

# prompt of different hierarchies during retrieval
# directory / file / class
RET_SCOPE_MAX_BACKTRACK_COUNT = 2
RET_SCOPE_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a Java code repository, as well as a information list of directories or files or Java classes/interfaces/enums in this repository in JSON format as follows:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
A directory contains files and subdirectories, a file contains Java classes/interfaces/enums, and a Java class/interface/enum contains methods.
You need to follow the steps below:
- Step 1: Calculate the probability that these directories or files or Java classes/interfaces/enums contain this method directly or indirectly.
NOTICE: If a directory or file contains interfaces or enums but no class, the probability should be the lowest.
- Step 2: Sort them from high to low according to the probability, return the option ID list.
- Step 3: Give a reason of about 50 words.
You need to give a JSON object that can be parsed directly as follows:
{"ids": [<PLACEHOLDER>...], "reason": <PLACEHOLDER>}'''
# method
RET_METHOD_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a Java code repository, as well as a information list of methods in this code repository in JSON format as follows:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "signature": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
You need to infer whether the method provided with the description is one of these methods. If so, answer the ID of the method. Otherwise, the answer ID is -1. Regardless of whether it is found or not, give a reason of about 30 words.
You need to give a JSON object that can be parsed directly as follows:
{"id": <PLACEHOLDER>, "reason": <PLACEHOLDER>}'''
