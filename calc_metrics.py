import json
import logging
import os
from typing import List

import numpy as np


def get_true_path_arr(sum_obj, true_path_str) -> List[str]:
    def get_method_path(file_obj, path_str):
        if path_str[0] == '/':
            path_str = path_str[1:]

        for method_obj in file_obj['methods']:
            if path_str == method_obj['name']:
                true_path_arr.append(method_obj['name'])
                return
        raise Exception("Can't find method path")

    def get_file_path(dir_obj, path_str):
        if path_str[0] == '/':
            path_str = path_str[1:]

        for sub_dir_obj in dir_obj['subdirectories']:
            if path_str.startswith(sub_dir_obj['name']):
                true_path_arr.append(sub_dir_obj['name'])
                get_file_path(sub_dir_obj, path_str[len(sub_dir_obj['name']):])
                return

        for file_obj in dir_obj['files']:
            if path_str.startswith(file_obj['name']):
                true_path_arr.append(file_obj['name'])
                get_method_path(file_obj, path_str[len(file_obj['name']):])
                return

        raise Exception("Can't find file path")

    true_path_arr = []
    try:
        # if not only repo name in root node
        if len(sum_obj['name'].split('/')) > 1:
            path_exclude_repo_name = "/".join(
                sum_obj['name'].split('/')[1:])
            if true_path_str.startswith(path_exclude_repo_name):
                true_path_str = true_path_str[len(path_exclude_repo_name):]
                get_file_path(sum_obj, true_path_str)
            else:
                raise Exception(
                    "An error occured when truncating path in first node")
        else:
            get_file_path(sum_obj, true_path_str)
    except Exception as e:
        print(e)
        return None

    return true_path_arr


if __name__ == "__main__":
    data_file_path = "./eval_data/filtered/data_final.jsonl"
    ret_result_file_path = "./eval_data/ret_result.jsonl"
    sum_result_root_path = "./eval_data/sum_result"
    with open(data_file_path, "r") as f_data, open(ret_result_file_path, "r") as f_ret_result:
        data_objs = [json.loads(line) for line in f_data.readlines()]
        result_objs = [json.loads(line) for line in f_ret_result.readlines()]

        # Initialize a dictionary to store the statistics for each repo_name
        repo_stats = {}

        # Initialize global statistics arrays
        global_recall_arr = []
        global_precision_arr = []
        global_iou_arr = []
        global_efficiency_arr = []

        for result_obj in result_objs:
            # get corresponding data object
            data_obj = next(
                filter(lambda x: x["id"] == result_obj["id"], data_objs), None)
            if data_obj is None:
                print(
                    f"Data object not found for id {result_obj['id']}, skip it.")
                continue

            # get true path arr
            repo_name = data_obj['repo'].split('/')[-1]
            sum_out_path = os.path.join(
                sum_result_root_path, repo_name, f"sum_out_{repo_name}.json")
            if not os.path.exists(sum_out_path):
                print(
                    f"Summary output path does not exist for id {result_obj['id']}")
                continue

            with open(sum_out_path, "r") as sum_f:
                sum_obj = json.load(sum_f)
                true_path_arr = get_true_path_arr(sum_obj, data_obj['path'])
                if true_path_arr is None or len(true_path_arr) == 0:
                    print(
                        f"Can't get true path array for id {result_obj['id']}")
                    continue

                # Initialize the statistics for the repo_name if not already done
                if repo_name not in repo_stats:
                    repo_stats[repo_name] = {
                        'recall_arr': [],
                        'precision_arr': [],
                        'iou_arr': [],
                        'efficiency_arr': []
                    }

                # calculate recall & efficiency & iou
                correct_count = 0
                for i in range(len(true_path_arr)):
                    if i < len(result_obj['path']) and result_obj['path'][i] == true_path_arr[i]:
                        correct_count += 1
                    else:
                        break
                if correct_count == len(true_path_arr):
                    repo_stats[repo_name]['recall_arr'].append(1)
                    repo_stats[repo_name]['precision_arr'].append(1)
                    repo_stats[repo_name]['efficiency_arr'].append(
                        result_obj['ret_times'] / len(true_path_arr))

                    # Update global statistics arrays
                    global_recall_arr.append(1)
                    global_precision_arr.append(1)
                    global_efficiency_arr.append(
                        result_obj['ret_times'] / len(true_path_arr))
                else:
                    if result_obj['is_found']:
                        repo_stats[repo_name]['precision_arr'].append(0)
                        # Update global statistics arrays
                        global_precision_arr.append(0)

                    repo_stats[repo_name]['recall_arr'].append(0)
                    # Update global statistics arrays
                    global_recall_arr.append(0)

                    repo_stats[repo_name]['iou_arr'].append(
                        correct_count / len(true_path_arr))
                    # Update global statistics arrays
                    global_iou_arr.append(correct_count / len(true_path_arr))

        # Print the statistics for each repo_name
        for repo_name, stats in repo_stats.items():
            recall = round(np.mean(stats['recall_arr']) * 100.0, 2)
            precision = round(np.mean(stats['precision_arr']) * 100.0, 2)
            iou = round(np.mean(stats['iou_arr']), 2)
            efficiency = round(np.mean(stats['efficiency_arr']), 2)

            print(f"Repo: {repo_name}")
            print(f"Recall: {recall}")
            print(f"Precision: {precision}")
            print(f"IoU: {iou}")
            print(f"Efficiency: {efficiency}")
            print('-' * 20)

        # Print the global statistics
        global_recall = round(np.mean(global_recall_arr) * 100.0, 2)
        global_precision = round(np.mean(global_precision_arr) * 100.0, 2)
        global_iou = round(np.mean(global_iou_arr), 2)
        global_efficiency = round(np.mean(global_efficiency_arr), 2)

        print("Global Statistics:")
        print(f"Recall: {global_recall}")
        print(f"Precision: {global_precision}")
        print(f"IoU: {global_iou}")
        print(f"Efficiency: {global_efficiency}")

    logging.shutdown()
