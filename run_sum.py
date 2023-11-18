import json
import logging
import os
import sys
from typing import Tuple
from dotenv import load_dotenv
from ie_client import IEClient

from summarizer import Summarizer


def parse_repo(repo_path, output_path, log_path) -> int:
    return os.system(
        f"java -jar ./java-repo-parser.jar -r={repo_path} -o={output_path} -l={log_path}")


def create_loggers(sum_log_path: str) -> Tuple[logging.Logger, logging.Logger]:
    '''
        create loggers for summarization and pipeline.
    '''
    logging.basicConfig(level=logging.INFO,
                        format='%(name)s - %(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%m/%d/%Y %H:%M:%S')

    sum_logger = logging.getLogger("summarizer")
    sum_logger.addHandler(
        logging.FileHandler(sum_log_path, "w", "utf-8")
    )
    sum_logger.propagate = False  # prevent printing to console

    pipeline_logger = logging.getLogger("pipeline")

    return pipeline_logger, sum_logger


if __name__ == "__main__":
    load_dotenv()  # load environment variables from .env file

    # handle paths
    repo_path = sys.argv[1]  # get repo_path from cli args
    repo_name = repo_path.split("/")[-1]

    result_dir_path = "./result"
    if not os.path.exists(result_dir_path):
        os.mkdir(result_dir_path)

    parse_log_path = os.path.join(
        result_dir_path, f"parse_log_{repo_name}.txt")
    parse_out_path = os.path.join(
        result_dir_path, f"parse_out_{repo_name}.json")
    sum_log_path = os.path.join(
        result_dir_path, f"sum_log_{repo_name}.txt")
    sum_out_path = os.path.join(
        result_dir_path, f"sum_out_{repo_name}.json")

    # create loggers
    pipeline_logger, sum_logger = create_loggers(sum_log_path)

    # check if existence of path
    if not os.path.exists(repo_path):
        pipeline_logger.error("Repo's path does not exist.")
        exit(1)

    # parse entire repo using java-repo-parser tool
    if (0 != parse_repo(repo_path, parse_out_path, parse_log_path)):
        pipeline_logger.error("Failed to parse repo.")
        exit(1)
    pipeline_logger.info(
        f"Repo parsed successfully, log file was written to {parse_log_path}, result file was written to {parse_out_path}.")

    # create client for Inference Endpoints
    try:
        ie_client = IEClient()
    except Exception as e:
        pipeline_logger.error(e)
        exit(1)
    if not ie_client.check_health():
        pipeline_logger.error("Inference Endpoints is not available.")
        exit(1)
    pipeline_logger.info(
        "Client for Inference Endpoints was created successfully.")

    # build summary tree for entire repo
    summarizer = Summarizer(sum_logger, ie_client)
    with open(parse_out_path, "r") as f_parse_out:
        repo_obj = json.loads(f_parse_out.read())
        result = summarizer.summarize_repo(repo_obj)

        # write result to file
        with open(sum_out_path, "w") as f_sum_out:
            f_sum_out.write(json.dumps(result))
            pipeline_logger.info(
                f"Result file of summarization was written to {sum_out_path}.")

    pipeline_logger.info("Done!")
