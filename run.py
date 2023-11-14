import json
import logging
import os
from dotenv import load_dotenv
from ie_client import IEClient

from summarizer import Summarizer


def parse_repo(repo_path, output_path, log_path) -> int:
    return os.system(
        "java -jar ./java-repo-parser.jar -r={} -o={} -l={}".format(
            repo_path, output_path, log_path)
    )


# check if the directory path of each path in the path list exists, if not, create it
def exam_dir_paths(paths):
    for path in paths:
        dir_path = os.path.dirname(path)
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)


def create_logger():
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    return logger


if __name__ == "__main__":
    load_dotenv()
    logger = create_logger()

    # handle paths
    repo_name = "pgjdbc"
    repo_path = "./repo/{}".format(repo_name)
    parse_log_path = "./result/parse_log_{}.txt".format(repo_name)
    parse_output_path = "./result/parse_out_{}.json".format(repo_name)
    summarize_log_path = "./result/sum_log_{}.txt".format(repo_name)
    summarize_output_path = "./result/sum_out_{}.json".format(repo_name)

    if not os.path.exists(repo_path):
        logger.error("Repo's path does not exist")
        exit(1)

    exam_dir_paths([
        parse_log_path, parse_output_path, summarize_log_path, summarize_output_path
    ])

    # parse entire repo using java-repo-parser tool
    if (0 != parse_repo(repo_path, parse_output_path, parse_log_path)):
        logging.error("Failed to parse repo")
        exit(1)
    logger.info("Repo parsed successfully, log file was written to {}, result file was written to {} ".format(
        parse_log_path, parse_output_path))

    # build summary tree for entire repo
    token = os.getenv('IE_TOKEN')
    url = os.getenv('IE_URL')
    max_input_length = os.getenv('IE_MODEL_INPUT_LENGTH')
    model_name = os.getenv('IE_MODEL_NAME')
    if token == None or url == None or model_name == None or max_input_length == None:
        logging.error("Cannot get value in .env file")
        exit(1)
    ie_client = IEClient(url, token, model_name, int(max_input_length))

    summarizer = Summarizer(logger, ie_client)
    result = {}
    sum_logs = []

    with open(parse_output_path, "r") as f:
        parsed_json = json.loads(f.read())
        sum_logs, result = summarizer.summarize_repo(parsed_json)

    # write result and log to files
    with open(summarize_output_path, "w") as f_out, open(summarize_log_path, "w") as f_log:
        for log in sum_logs:
            f_log.write(log + "\n")
        logger.info("Log file of summarization was written to {}".format(
            summarize_log_path))

        f_out.write(json.dumps(result))
        logger.info("Result file of summarization was written to {}".format(
            summarize_output_path))

    logger.info("RepoSummarizer: Done!")
