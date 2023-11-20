

import json
import os
import sys
from dotenv import load_dotenv
from ie_client import IEClient
from run_sum import create_loggers, parse_repo
from summarizer import Summarizer


if __name__ == "__main__":
    start_idx = sys.argv[1] if len(sys.argv) > 1 else 0

    repo_root_path = "./eval_data/repo"
    repo_list_file_path = "./eval_data/filtered/repo2.jsonl"
    result_root_path = "./eval_data/result"

    load_dotenv()  # load environment variables from .env file

    # create client for Inference Endpoints
    try:
        ie_client = IEClient()
    except Exception as e:
        print(e)
        exit(1)
    if not ie_client.check_health():
        print("Inference Endpoints is not available.")
        exit(1)

    with open(repo_list_file_path, "r") as f:
        repo_objs = [json.loads(line) for line in f.readlines()]

        for idx, repo_obj in enumerate(repo_objs[start_idx:]):
            try:
                repo_name = repo_obj['name'].split('/')[-1]
                repo_path = os.path.join(
                    repo_root_path, f"{repo_name}-{repo_obj['sha']}")

                result_dir_path = os.path.join(result_root_path, repo_name)

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

                # create logger
                _, sum_logger = create_loggers(sum_log_path)

                # check if existence of path
                if not os.path.exists(repo_path):
                    raise Exception("Repo's path does not exist.")

                # parse entire repo using java-repo-parser tool
                if (0 != parse_repo(repo_path, parse_out_path, parse_log_path)):
                    raise Exception("Failed to parse repo.")

                # build summary tree for entire repo
                print(f"Summarizing {idx + start_idx}th repo: {repo_name}...")

                summarizer = Summarizer(sum_logger, ie_client)
                with open(parse_out_path, "r") as f_parse_out:
                    repo_obj = json.loads(f_parse_out.read())
                    result = summarizer.summarize_repo(repo_obj)

                    # write result to file
                    with open(sum_out_path, "w") as f_sum_out:
                        f_sum_out.write(json.dumps(result))

                print(f"Summarized {idx + start_idx}th repo: {repo_name}")

            except Exception as e:
                print(e)
                print(f'Stop at {idx + start_idx}')
                break
