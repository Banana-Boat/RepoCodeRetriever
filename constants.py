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


RET_MAX_OUTPUT_LENGTH = 80

# prompt of different hierarchies during retrieval
# directory / file / class
RET_SCOPE_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a Java code repository, as well as a batch of summary of directories or files or classes in this code repository in JSON format, as in the following example:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
A directory contains files and subdirectories, a file contains Java classes, and a Java class contains methods.
You need to infer whether this method may exists in these directories or files or classes, indirect inclusion counts as existence as well. If it exists, answer the ID of the directory or file. Otherwise, the answer ID is -1. Regardless of whether it is found or not, give a reason of about 30 words. Answer in JSON format as following:
{"id": <PLACEHOLDER>, "reason": <PLACEHOLDER>}'''
# method
RET_METHOD_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a Java code repository, as well as a batch of summary of directories or files or classes in this code repository in JSON format, as in the following example:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
A directory contains files and subdirectories, a file contains Java classes, and a Java class contains methods.
You need to infer whether this method may exists in these directories or files or classes, indirect inclusion counts as existence as well. If it exists, answer the ID of the directory or file. Otherwise, the answer ID is -1. Regardless of whether it is found or not, give a reason of about 30 words. Answer in JSON format as following:
{"id": <PLACEHOLDER>, "reason": <PLACEHOLDER>}'''
