INPUT_SEPARATOR = "##################################################################"
LOG_SEPARATOR = "============================================================================================================"

NO_SUMMARY = "*** No summary ***"

# variables for summarization
# prompt and max output length of different hierarchies during summarization
SUM_DIR = {
    "system_prompt": '''You will be provided with a directory name and an information list of subdirectories and Java class files in this directory in JSON format as follows:
{"id": <PLACEHOLDER>, "type": <PLACEHOLDER>, "name": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
You need to summarize the directory in about 150 words.''',
    "max_output_length": 300,
}
SUM_FILE = {
    "system_prompt": "Summarize the Java class provided to you in about 60 words.",
    "max_output_length": 120,
}
SUM_METHOD = {
    "system_prompt": "Summarize the Java method provided to you in about 40 words.",
    "max_output_length": 80,
}

# variables for query expansion
EXP_MAX_REF_COUNT = 3  # max reference summary count per node
EXP_QUERY = {
    "system_prompt": '''Users use a query expressed in natural language to search for a corresponding Java method. To make the results more precise, you need to expand this query to be more detailed.
You will be provided with a query and a document, please refer to this document to expand the given query to about 30 words.
You need to return a JSON object as follows:
{"expanded_query": <PLACEHOLDER>}''',
    "max_output_length": 80,
}

# variables for retrieval
RET_MAX_OUTPUT_LENGTH = 50
RET_MAX_BACKTRACK_COUNT = 2
RET_DIR_MAX_INFO_LENGTH = 8
RET_FILE_MAX_INFO_LENGTH = 12

# prompt of different hierarchies during retrieval
RET_DIR_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a code repository, and an information list of directories or Java class files in this repository in JSON format as follows:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "similarity": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
NOTE: The `similarity` field represents the text similarity between the summary and the method description.
A directory contains Java class files and subdirectories, a Java class contains methods.
You need to follow the steps below:
- Step 1: Calculate the probability that these directories or Java class files contain this method directly or indirectly.
- Step 2: Sort these items according to probability from high to low, and return ids of the top 3 (if the number of items is less than 3, return all ids in order).
You need to return a JSON object as follows:
{"ids": [<PLACEHOLDER>...]}'''
RET_FILE_SYSTEM_PROMPT = '''You will be provided with a description of a Java method in a code repository, and an information list of methods in this code repository in JSON format as follows:
{"id": <PLACEHOLDER>, "signature": <PLACEHOLDER>, "similarity": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
NOTE: The `similarity` field represents the text similarity between the summary and the method description.
You need to infer whether the provided description points to one of these methods. If so, answer the id of the method. Otherwise, the answer id is -1.
You need to return a JSON object as follows:
{"id": <PLACEHOLDER>}'''
