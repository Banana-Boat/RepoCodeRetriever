import json
import logging
import re
import time
from enum import Enum

import tiktoken
from constants import INPUT_SEPARATOR, LOG_SEPARATOR, RET_DIR_SYSTEM_PROMPT, RET_DIR_MAX_INFO_LENGTH, RET_FILE_MAX_INFO_LENGTH, RET_MAX_OUTPUT_LENGTH, RET_FILE_SYSTEM_PROMPT, RET_MAX_BACKTRACK_COUNT

from openai_client import OpenAIClient
from sim_caculator import SimCaculator


class InferType(Enum):
    FILE = 0  # retrieve in file
    DIR = 1  # retrieve in directory


class Retriever:
    def __init__(self, logger: logging.Logger, openai_client: OpenAIClient, sim_caculator: SimCaculator):
        self.logger = logger

        self.openai_tokenizer = tiktoken.encoding_for_model(
            openai_client.model_name)
        self.openai_client = openai_client
        self.token_used_count = 0

        self.sim_caculator = sim_caculator

        self.result_path = []  # result path, reset every retrieval
        self.most_probable_path = []  # most probable path, reset every retrieval
        self.is_first_try = True  # reset every retrieval
        self.ret_times = 0  # retrieval times, reset every retrieval

    def _is_legal_input(self, system_input_text: str, user_input_text: str) -> bool:
        '''Check if the input text length exceeds the model limit.'''
        encoded_text = self.openai_tokenizer.encode(
            system_input_text + user_input_text)

        return len(encoded_text) <= self.openai_client.max_number_of_tokens - RET_MAX_OUTPUT_LENGTH

    def _infer(self, node_id: int, type: InferType, user_input_text: str) -> dict:
        '''
            Generate inference through API calls.
            return: {id: int | None, ids: List[int] | None} | None
            If an error occurred during generation, return None.
        '''
        self.ret_times += 1

        # set system input text
        if type == InferType.FILE:
            system_input_text = RET_FILE_SYSTEM_PROMPT
        else:
            system_input_text = RET_DIR_SYSTEM_PROMPT

        try:
            # generate inference
            total_tokens, output_text = self.openai_client.generate(
                system_input_text, user_input_text, RET_MAX_OUTPUT_LENGTH)
            self.token_used_count += total_tokens
        except Exception as e:
            self.logger.error(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nSystem Input:\n{system_input_text}\nUser Input:\n{user_input_text}\n{e}")
            return None

        try:
            # get json object in output_text
            match = re.search(r'\{.*\}', output_text, re.DOTALL)
            if not match:
                raise Exception()
            json_text = match.group(0)

            # check if the result is formatted
            infer_obj = json.loads(json_text)
            if type == InferType.FILE:
                if 'id' not in infer_obj or \
                        not isinstance(infer_obj['id'], int):
                    raise Exception()
            elif type == InferType.DIR:
                if 'ids' not in infer_obj or \
                        not isinstance(infer_obj['ids'], list) or \
                        not all(isinstance(x, int) for x in infer_obj['ids']):
                    raise Exception()

            self.logger.info(
                f"INFERENCE{LOG_SEPARATOR}\nNode ID: {node_id}\nSystem Input:\n{system_input_text}\nUser Input:\n{user_input_text}\nOutput:\n{infer_obj}")

            return infer_obj
        except Exception as e:
            self.logger.error(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nSystem Input:\n{system_input_text}\nUser Input:\n{user_input_text}\nOutput:\n{output_text}\nThe inference result is not formatted")
            return None

    def _retrieve_in_file(self, des: str, file_sum_obj: dict) -> dict:
        '''
            Retrieve the method according to its description and the summary of the file.
            return {is_found: bool, is_error: bool}.
        '''
        user_input_text = f"Method Description: {des}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(file_sum_obj['methods']) == 0:
            self.logger.info(
                f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nNo method in this file.")
            return {
                'is_found': False,
                'is_error': True,
            }

        # get information list of method
        infos = []
        for method_sum_obj in file_sum_obj['methods']:
            infos.append({
                'id': method_sum_obj['id'],
                'name': method_sum_obj['name'],
                'summary': method_sum_obj['summary'],
            })

        # calculate similarity
        summaries = [info['summary'] for info in infos]
        similarities = self.sim_caculator.calc_similarities(des, summaries)

        for i, info in enumerate(infos):
            info['similarity'] = similarities[i]
        infos.sort(key=lambda x: x['similarity'], reverse=True)

        # concat info list to context.
        for info in infos[:RET_FILE_MAX_INFO_LENGTH]:
            temp_obj = {
                'id': info['id'],
                'name': info['name'],
                'similarity': info['similarity'],
                'summary': info['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if not self._is_legal_input(RET_FILE_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'is_error': True,
                }

            user_input_text += temp_str

        # infer the method
        infer_obj = self._infer(
            file_sum_obj['id'], InferType.FILE, user_input_text)

        # error occurred during generation
        if infer_obj == None:
            return {
                'is_found': False,
                'is_error': True,
            }

        # no method was selected in this class
        if infer_obj['id'] == -1:
            self.is_first_try = False
            return {
                'is_found': False,
                'is_error': False,
            }

        # get method_sum_obj according to infer_obj['id']
        method_sum_obj = next(
            filter(lambda x: x['id'] == infer_obj['id'], file_sum_obj['methods']), None)
        if method_sum_obj is None:
            self.logger.info(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nThe method is not found in this class.")
            return {
                'is_found': False,
                'is_error': True,
            }

        # return the result of retrieval
        self.result_path.append(method_sum_obj['name'])
        return {
            'is_found': True,
            'is_error': False,
        }

    def _retrieve_in_dir(self, des: str, dir_sum_obj: dict) -> dict:
        '''
            Retrieve the method according to its description and the summary of the directory.
            return {is_found: bool, is_error: bool}.
        '''
        user_input_text = f"Method Description: {des}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(dir_sum_obj['subdirectories']) == 0 and len(dir_sum_obj['files']) == 0:
            self.logger.info(
                f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nNo file or subdirectory in this directory.")
            return {
                'is_found': False,
                'is_error': True,
            }

        # get information list of subdirectory and file
        infos = []
        for sub_dir_sum_obj in dir_sum_obj['subdirectories']:
            infos.append({
                'id': sub_dir_sum_obj['id'],
                'name': sub_dir_sum_obj['name'],
                'summary': sub_dir_sum_obj['summary'],
            })
        for file_sum_obj in dir_sum_obj['files']:
            infos.append({
                'id': file_sum_obj['id'],
                'name': file_sum_obj['name'],
                'summary': file_sum_obj['summary'],
            })

        # calculate similarity
        summaries = [info['summary'] for info in infos]
        similarities = self.sim_caculator.calc_similarities(des, summaries)

        for i, info in enumerate(infos):
            info['similarity'] = similarities[i]
        infos.sort(key=lambda x: x['similarity'], reverse=True)

        # concat info list to context.
        for info in infos[:RET_DIR_MAX_INFO_LENGTH]:
            temp_obj = {
                'id': info['id'],
                'name': info['name'],
                'similarity': info['similarity'],
                'summary': info['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if not self._is_legal_input(RET_DIR_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'is_error': True,
                }

            user_input_text += temp_str

        # infer the subdirectiry or file
        infer_obj = self._infer(
            dir_sum_obj['id'], InferType.DIR, user_input_text)

        # error occurred during generation
        if infer_obj == None:
            return {
                'is_found': False,
                'is_error': True,
            }

        # try ids in turn
        for infer_id in infer_obj['ids'][:RET_MAX_BACKTRACK_COUNT]:
            file_sum_obj = None
            sub_dir_sum_obj = None
            next_sum_obj = None
            res = None

            # find next_sum_obj according to infer_id
            file_sum_obj = next(
                filter(lambda x: x['id'] == infer_id, dir_sum_obj['files']), None)
            sub_dir_sum_obj = next(
                filter(lambda x: x['id'] == infer_id, dir_sum_obj['subdirectories']), None)

            if file_sum_obj is None and sub_dir_sum_obj is None:
                # can't find next_sum_obj
                self.logger.info(
                    f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nThe file or subdirectory is not found in this directory.")
                return {
                    'is_found': False,
                    'is_error': True,
                }

            if file_sum_obj is not None:
                next_sum_obj = file_sum_obj
                if self.is_first_try:
                    # add to most probable path if it is the first try
                    self.most_probable_path.append(next_sum_obj['name'])

                res = self._retrieve_in_file(des, file_sum_obj)
            elif sub_dir_sum_obj is not None:
                next_sum_obj = sub_dir_sum_obj
                if self.is_first_try:
                    # add to most probable path if it is the first try
                    self.most_probable_path.append(next_sum_obj['name'])

                res = self._retrieve_in_dir(des, sub_dir_sum_obj)

            if res['is_found'] or res['is_error']:
                self.result_path.append(next_sum_obj['name'])
                return res

        return {
            'is_found': False,
            'is_error': False,
        }

    def retrieve_in_repo(self, des: str, repo_sum_obj: dict) -> dict:
        '''
            Retrieve the method according to its description and the summary of the entire repo.
            return {is_found: bool, is_error: bool, path: List[str], ret_times: int}.
            If is_found is False, path is the search path of the most probability.
        '''
        start_time = time.time()

        self.result_path = []
        self.is_first_try = True
        self.most_probable_path = []
        self.ret_times = 0

        res = self._retrieve_in_dir(des, repo_sum_obj)

        self.logger.info(f"COMPLETION{LOG_SEPARATOR}")
        self.logger.info(f"Token Used: {self.token_used_count}")
        self.logger.info(
            f"Retrieval time cost: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")

        if res['is_found']:
            self.result_path.reverse()
            res['path'] = self.result_path
        else:
            res['path'] = self.most_probable_path

        res['ret_times'] = self.ret_times

        return res
