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

        recall_arr = []
        precision_arr = []
        iou_arr = []
        efficiency_arr = []

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

                # print(f"true path: {true_path_arr}")
                # print(f"result path: {result_obj['path']}")

                # calculate recall & efficiency & iou
                correct_count = 0
                for i in range(len(true_path_arr)):
                    if i < len(result_obj['path']) and result_obj['path'][i] == true_path_arr[i]:
                        correct_count += 1
                    else:
                        break
                if correct_count == len(true_path_arr):
                    recall_arr.append(1)
                    precision_arr.append(1)

                    efficiency_arr.append(
                        result_obj['ret_times'] / len(true_path_arr))
                else:
                    if result_obj['is_found']:
                        precision_arr.append(0)

                    recall_arr.append(0)
                    # print(f"Wrong: {result_obj['id']}")

                    iou_arr.append(
                        correct_count / len(true_path_arr))

        recall = round(np.mean(recall_arr), 3)
        precision = round(np.mean(precision_arr), 3)
        iou = round(np.mean(iou_arr), 3)
        efficiency = round(np.mean(efficiency_arr), 3)

        print(
            f"Recall: {recall} -- Number of samples: {len(recall_arr)}")
        print(
            f"Precision: {precision} -- Number of samples: {len(precision_arr)}")
        print(
            f"IoU: {iou} -- Number of samples: {len(iou_arr)}")
        print(
            f"Efficiency: {efficiency} -- Number of samples: {len(efficiency_arr)}")

    logging.shutdown()
