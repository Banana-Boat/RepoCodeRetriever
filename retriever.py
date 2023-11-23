import json
import logging
import re
import time
from typing import List
from enum import Enum

import tiktoken
from constants import INPUT_SEPARATOR, LOG_SEPARATOR, RET_CLS_SYSTEM_PROMPT, RET_DIR_OR_FILE_SYSTEM_PROMPT, RET_MAX_OUTPUT_LENGTH, RET_METHOD_SYSTEM_PROMPT, RET_MAX_BACKTRACK_COUNT

from openai_client import OpenAIClient


class InferType(Enum):
    METHOD = 0
    CLS = 1
    DIR_OR_FILE = 2


class Retriever:
    def __init__(self, logger: logging.Logger, openai_client: OpenAIClient):
        self.logger = logger
        self.tokenizer = tiktoken.encoding_for_model(openai_client.model_name)

        self.openai_client = openai_client

        self.token_used_count = 0

        self.result_path = []  # result path, reset every retrieval
        self.most_probable_path = []  # most probable path, reset every retrieval
        self.is_first_try = True  # reset every retrieval
        self.ret_times = 0  # retrieval times, reset every retrieval

    def _is_legal_input_text(self, system_input_text: str, user_input_text: str) -> bool:
        '''
            Check if the input text length exceeds the model limit.
        '''
        encoded_text = self.tokenizer.encode(
            system_input_text + user_input_text)

        return len(encoded_text) <= self.openai_client.max_number_of_tokens - RET_MAX_OUTPUT_LENGTH

    def _infer(self, node_id: int, type: InferType, user_input_text: str) -> dict:
        '''
            Generate inference through API calls.
            return: {id: int | None, ids: List[int] | None, reason: str} | None
            If an error occurred during generation, return None.
        '''
        self.ret_times += 1

        # set system input text
        if type == InferType.METHOD:
            system_input_text = RET_METHOD_SYSTEM_PROMPT
        elif type == InferType.CLS:
            system_input_text = RET_CLS_SYSTEM_PROMPT
        else:
            system_input_text = RET_DIR_OR_FILE_SYSTEM_PROMPT

        try:
            total_tokens, output_text = self.openai_client.generate(
                system_input_text, user_input_text, RET_MAX_OUTPUT_LENGTH)
            self.token_used_count += total_tokens

            try:
                # get json object in output_text
                match = re.search(r'\{.*\}', output_text, re.DOTALL)
                if not match:
                    raise Exception()
                json_text = match.group(0)

                # check if the inference result is formatted
                infer_obj = json.loads(json_text)
                if type == InferType.METHOD:
                    if 'id' not in infer_obj or 'reason' not in infer_obj or \
                            not isinstance(infer_obj['id'], int):
                        raise Exception()
                else:
                    if 'ids' not in infer_obj or 'reason' not in infer_obj or \
                            not isinstance(infer_obj['ids'], list) or \
                            not all(isinstance(x, int) for x in infer_obj['ids']):
                        raise Exception()

                self.logger.info(
                    f"INFERENCE{LOG_SEPARATOR}\nNode ID: {node_id}\nSystem Input:\n{system_input_text}\nUser Input:\n{user_input_text}\nOutput:\n{infer_obj}")

                return infer_obj
            except Exception as e:
                self.logger.error(
                    f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nThe inference result is not formatted, output text:\n{output_text}\n{e}")
                return None
        except Exception as e:
            self.logger.error(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nAn Error occurred during generation API call:\n{e}")
            return None

    def _retrieve_in_cls(self, des: str, cls_sum_obj: dict) -> dict:
        '''
            Retrieve the method according to the description and the summary of the class.
            return {is_found: bool, is_error: bool}.
        '''
        user_input_text = f"Method Description: {des}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(cls_sum_obj['methods']) == 0:
            self.logger.info(
                f"INSUFFICIENT CONTEXT{LOG_SEPARATOR}\nNode ID: {cls_sum_obj['id']}\nNo method in this class.")
            return {
                'is_found': False,
                'is_error': False,
            }

        # concat summary of methods to context
        for method_sum_obj in cls_sum_obj['methods']:
            temp_obj = {
                'id': method_sum_obj['id'],
                'name': method_sum_obj['name'],
                'signature': method_sum_obj['signature'],
                'summary': method_sum_obj['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if not self._is_legal_input_text(RET_METHOD_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {cls_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'is_error': True,
                }

            user_input_text += temp_str

        # infer the method
        infer_obj = self._infer(
            cls_sum_obj['id'], InferType.METHOD, user_input_text)

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
            filter(lambda x: x['id'] == infer_obj['id'], cls_sum_obj['methods']), None)
        if method_sum_obj is None:
            self.logger.info(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {cls_sum_obj['id']}\nThe method is not found in this class.")
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

    def _retrieve_in_file(self, des: str, file_sum_obj: dict) -> dict:
        '''
            Retrieve the method according to the description and the summary of the file.
            return {is_found: bool, is_error: bool}.
        '''
        user_input_text = f"Method Description: {des}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(file_sum_obj['classes']) == 0:
            self.logger.info(
                f"INSUFFICIENT CONTEXT{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nNo class in this file.")
            return {
                'is_found': False,
                'is_error': False,
            }

        # concat summary of classes to context
        for cls_sum_obj in file_sum_obj['classes']:
            temp_obj = {
                'id': cls_sum_obj['id'],
                'name': cls_sum_obj['name'],
                'summary': cls_sum_obj['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if not self._is_legal_input_text(RET_CLS_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'is_error': True,
                }

            user_input_text += temp_str

        # infer the class
        infer_obj = self._infer(
            file_sum_obj['id'], InferType.CLS, user_input_text)

        # error occurred during generation
        if infer_obj == None:
            return {
                'is_found': False,
                'is_error': True,
            }

        # try ids in turn
        for infer_id in infer_obj['ids'][:RET_MAX_BACKTRACK_COUNT]:
            cls_sum_obj = next(
                filter(lambda x: x['id'] == infer_id, file_sum_obj['classes']), None)
            if cls_sum_obj is None:

                self.logger.info(
                    f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nThe class is not found in this file.")
                return {
                    'is_found': False,
                    'is_error': True,
                }

            if self.is_first_try:
                # add to most probable path if it is the first try
                self.most_probable_path.append(cls_sum_obj['name'])

            res = self._retrieve_in_cls(des, cls_sum_obj)

            if res['is_found'] or res['is_error']:
                self.result_path.append(cls_sum_obj['name'])
                return res

        return {
            'is_found': False,
            'is_error': False,
        }

    def _retrieve_in_dir(self, des: str, dir_sum_obj: dict) -> dict:
        '''
            Retrieve the method according to the description and the summary of the directory.
            return {is_found: bool, is_error: bool}.
        '''
        user_input_text = f"Method Description: {des}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(dir_sum_obj['subdirectories']) == 0 and len(dir_sum_obj['files']) == 0:

            self.logger.info(
                f"INSUFFICIENT CONTEXT{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nNo file and subdirectory in this directory.")
            return {
                'is_found': False,
                'is_error': False,
            }

        # concat summary of subdirectories to context
        for sub_dir_sum_obj in dir_sum_obj['subdirectories']:
            temp_obj = {
                'id': sub_dir_sum_obj['id'],
                'name': sub_dir_sum_obj['name'],
                'summary': sub_dir_sum_obj['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if not self._is_legal_input_text(RET_DIR_OR_FILE_SYSTEM_PROMPT, user_input_text + temp_str):

                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'is_error': True,
                }

            user_input_text += temp_str

        # concat summary of files to context
        for file_sum_obj in dir_sum_obj['files']:
            temp_obj = {
                'id': file_sum_obj['id'],
                'name': file_sum_obj['name'],
                'summary': file_sum_obj['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if not self._is_legal_input_text(RET_DIR_OR_FILE_SYSTEM_PROMPT, user_input_text + temp_str):

                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'is_error': True,
                }

            user_input_text += temp_str

        # infer the subdirectiry or file
        infer_obj = self._infer(
            dir_sum_obj['id'], InferType.DIR_OR_FILE, user_input_text)

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
            Retrieve the method according to the description and the summary of the entire repo.
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
