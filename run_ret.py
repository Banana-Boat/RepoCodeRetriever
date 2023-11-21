import json
import logging
import os
from typing import Tuple
from dotenv import load_dotenv

from openai_client import OpenAIClient
from retriever import Retriever


def create_loggers(ret_log_path: str) -> Tuple[logging.Logger, logging.Logger]:
    '''
        create loggers for retrieval and pipeline.
    '''
    logging.basicConfig(level=logging.INFO,
                        format='%(name)s - %(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%m/%d/%Y %H:%M:%S')

    ret_logger = logging.getLogger("retriever")
    ret_logger.addHandler(
        logging.FileHandler(ret_log_path, "w", "utf-8")
    )
    ret_logger.propagate = False  # prevent printing to console

    pipeline_logger = logging.getLogger("pipeline")

    return pipeline_logger, ret_logger


if __name__ == "__main__":
    load_dotenv()  # load environment variables from .env file

    """
    {"repo": "zeromq/jeromq", "query": "bind, is available and compatible with the socket type.", "func_name": "SocketBase.checkProtocol", "path": "src/main/java/zmq/SocketBase.java"}
    {"repo": "zeromq/jeromq", "query": "Creates a Selector that will be closed when the context is destroyed.", "func_name": "Ctx.createSelector", "path": "src/main/java/zmq/Ctx.java"}
    {"repo": "zeromq/jeromq", "query": "Polling on items with given selector CAUTION: This could be affected by jdk epoll bug", "func_name": "ZMQ.poll", "path": "src/main/java/zmq/ZMQ.java"}
    {"repo": "zeromq/jeromq", "query": "Returns true if there is at least one message to read in the pipe.", "func_name": "Pipe.checkRead", "path": "src/main/java/zmq/pipe/Pipe.java"}
    {"repo": "zeromq/jeromq", "query": "Cancel the timer created by sink_ object with ID equal to id_.", "func_name": "PollerBase.cancelTimer", "path": "src/main/java/zmq/poll/PollerBase.java"}
    {"repo": "zeromq/jeromq", "query": "Removes an element from the front end of the queue.", "func_name": "YQueue.pop", "path": "src/main/java/zmq/pipe/YQueue.java"}
    """

    repo_name = "jeromq"
    query = "Returns true if there is at least one message to read in the pipe."

    # handle paths
    result_dir_path = "./result"
    sum_out_path = os.path.join(
        result_dir_path, f"sum_out_{repo_name}.json")
    ret_log_path = os.path.join(
        result_dir_path, f"ret_log_{repo_name}.txt")

    # create loggers
    pipeline_logger, ret_logger = create_loggers(ret_log_path)

    # check if existence of path
    if not os.path.exists(sum_out_path):
        pipeline_logger.error("Summary output path does not exist.")
        exit(1)

    # create client for OpenAI
    try:
        openai_client = OpenAIClient()
    except Exception as e:
        pipeline_logger.error(e)
        exit(1)

    # check if enough credits
    # credit = openai_client.get_credit_grants()
    # if credit < 2.0:
    #     pipeline_logger.error(
    #         f"Not enough credits to retrieval. Credit: {credit}")
    #     exit(1)
    pipeline_logger.info(
        "Client for OpenAI was created successfully.")

    # retrieve method according to the description
    pipeline_logger.info("Start retrieval...")
    retriever = Retriever(ret_logger, openai_client)
    with open(sum_out_path, "r") as f_sum_out:
        repo_sum_obj = json.loads(f_sum_out.read())
        result = retriever.retrieve_in_repo(query, repo_sum_obj)

        pipeline_logger.info(f"The result of retrieval:\n{result}")

    pipeline_logger.info("Done!")
