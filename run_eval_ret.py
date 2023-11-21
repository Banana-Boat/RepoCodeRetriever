import json
import logging
import os
import sys
from typing import Tuple
from dotenv import load_dotenv

from openai_client import OpenAIClient
from retriever import Retriever
from run_ret import create_loggers


if __name__ == "__main__":
    start_idx = sys.argv[1] if len(sys.argv) > 1 else 0

    data_file_path = "./eval_data/filtered/data2.jsonl"
    result_root_path = "./eval_data/result"
    result_file_path = "./eval_data/result/result.jsonl"

    load_dotenv()  # load environment variables from .env file

    # create client for OpenAI
    try:
        openai_client = OpenAIClient()
    except Exception as e:
        print(e)
        exit(1)
    # check if enough credits
    # if openai_client.get_credit_grants() < 2.0:
    #     print("Not enough credits to retrieval.")
    #     exit(1)

    with open(data_file_path, "r") as f_data, open(result_file_path, "a") as f_result:
        data_objs = [json.loads(line) for line in f_data.readlines()]

        for idx, data_obj in enumerate(data_objs[start_idx:]):

            try:
                query = data_obj['query']
                repo_name = data_obj['name'].split('/')[-1]
                result_dir_path = os.path.join(result_root_path, repo_name)

                sum_out_path = os.path.join(
                    result_dir_path, f"sum_out_{repo_name}.json")
                ret_log_path = os.path.join(
                    result_dir_path, f"ret_log_{repo_name}.txt")

                # create loggers
                _, ret_logger = create_loggers(ret_log_path)

                # check if existence of path
                if not os.path.exists(sum_out_path):
                    raise Exception("Summary output path does not exist.")

                # retrieve method according to the description
                print(f"Retrieving {idx + start_idx}th data...")

                retriever = Retriever(ret_logger, openai_client)
                with open(sum_out_path, "r") as f_sum_out:
                    repo_sum_obj = json.loads(f_sum_out.read())
                    result = retriever.retrieve_in_repo(query, repo_sum_obj)

                # TODO: write result to file

                print(f"Retrieved {idx + start_idx}th data")

            except Exception as e:
                print(e)
                print(f'Stop at {idx + start_idx}')
                break
