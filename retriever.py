import json
import logging
import re
import time
from typing import List

import tiktoken
from constants import INPUT_SEPARATOR, LOG_SEPARATOR, RET_MAX_OUTPUT_LENGTH, RET_METHOD_SYSTEM_PROMPT, RET_SCOPE_MAX_TRY_NUM, RET_SCOPE_SYSTEM_PROMPT

from openai_client import OpenAIClient


class Retriever:
    def __init__(self, logger: logging.Logger, openai_client: OpenAIClient):
        self.logger = logger
        self.tokenizer = tiktoken.encoding_for_model(openai_client.model_name)

        self.openai_client = openai_client

        self.token_used_count = 0

    def _is_legal_input_text(self, system_input_text: str, user_input_text: str) -> bool:
        '''
            Check if the input text length exceeds the model limit.
        '''
        encoded_text = self.tokenizer.encode(
            system_input_text + user_input_text)

        return len(encoded_text) <= self.openai_client.max_number_of_tokens - RET_MAX_OUTPUT_LENGTH

    def _infer_method(self, node_id: int, user_input_text: str) -> dict:
        '''
            Generate inference about method through API calls.
            return: {id: int, reason: str} | None, id=-1 means model can't find the method.
            If an error occurred during generation, return None.
        '''
        try:
            total_tokens, output_text = self.openai_client.generate(
                RET_METHOD_SYSTEM_PROMPT, user_input_text, RET_MAX_OUTPUT_LENGTH)
            self.token_used_count += total_tokens

            try:
                # get json object in output_text
                match = re.search(r'\{.*\}', output_text, re.DOTALL)
                if not match:
                    raise Exception()
                json_text = match.group(0)

                # check if the inference result is formatted
                infer_obj = json.loads(json_text)
                if 'id' not in infer_obj or 'reason' not in infer_obj or \
                        not isinstance(infer_obj['id'], int):
                    raise Exception()

                self.logger.info(
                    f"INFERENCE{LOG_SEPARATOR}\nNode ID: {node_id}\nUser Input:\n{user_input_text}\nOutput:\n{infer_obj}")

                return infer_obj
            except Exception as e:
                self.logger.error(
                    f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nThe inference result is not formatted, output text:\n{output_text}\n{e}")
                return None
        except Exception as e:
            self.logger.error(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nAn Error occurred during generation API call:\n{e}")
            return None

    def _infer_scope(self, node_id: int, user_input_text: str) -> dict:
        '''
            Generate inference about scope(directory/file/class) through API calls.
            return: {ids: List[int], reason: str} | None.
            If an error occurred during generation, return None.
        '''
        try:
            total_tokens, output_text = self.openai_client.generate(
                RET_SCOPE_SYSTEM_PROMPT, user_input_text, RET_MAX_OUTPUT_LENGTH)
            self.token_used_count += total_tokens

            try:
                # get json object in output_text
                match = re.search(r'\{.*\}', output_text, re.DOTALL)
                if not match:
                    raise Exception()
                json_text = match.group(0)

                # check if the inference result is formatted
                infer_obj = json.loads(json_text)
                if 'ids' not in infer_obj or 'reason' not in infer_obj or \
                        not isinstance(infer_obj['ids'], list) or \
                        not all(isinstance(x, int) for x in infer_obj['ids']):
                    raise Exception()

                self.logger.info(
                    f"INFERENCE{LOG_SEPARATOR}\nNode ID: {node_id}\nSystem Input:\n{RET_SCOPE_SYSTEM_PROMPT}\nUser Input:\n{user_input_text}\nOutput:\n{infer_obj}")

                return infer_obj
            except Exception as e:
                self.logger.error(
                    f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nThe inference result is not formatted, output text:\n{output_text}\n{e}")
                return None
        except Exception as e:
            self.logger.error(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nAn Error occurred during generation API call:\n{e}")
            return None

    def _retrieve_in_cls(self, des: str, cls_sum_obj: dict, path: str) -> dict:
        '''
            Retrieve the method according to the description and the summary of the class.
            return {is_found: bool, need_backtrack: bool, path: str | None}, path is str only when is_found is True.
        '''
        user_input_text = f"Method Description: {des}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(cls_sum_obj['methods']) == 0:
            self.logger.info(
                f"INSUFFICIENT CONTEXT{LOG_SEPARATOR}\nNode ID: {cls_sum_obj['id']}\nNo method in this class.")
            return {
                'is_found': False,
                'need_backtrack': True,
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
                    'need_backtrack': False,
                }

            user_input_text += temp_str

        # infer the method
        infer_obj = self._infer_method(cls_sum_obj['id'], user_input_text)

        # error occurred during generation
        if infer_obj == None:
            return {
                'is_found': False,
                'need_backtrack': False,
            }

        # no method was selected in this class
        if infer_obj['id'] == -1:
            return {
                'is_found': False,
                'need_backtrack': True,
            }

        # get method_sum_obj according to infer_obj['id']
        method_sum_obj = next(
            filter(lambda x: x['id'] == infer_obj['id'], cls_sum_obj['methods']), None)
        if method_sum_obj is None:
            self.logger.info(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {cls_sum_obj['id']}\nThe method is not found in this class.")
            return {
                'is_found': False,
                'need_backtrack': False,
            }

        # return the result of retrieval
        return {
            'is_found': True,
            'need_backtrack': False,
            'path': f"{path}.{method_sum_obj['name']}",
        }

    def _retrieve_in_file(self, des: str, file_sum_obj: dict, path: str) -> dict:
        '''
            Retrieve the method according to the description and the summary of the file.
            return {is_found: bool, need_backtrack: bool, path: str | None}, path is str only when is_found is True.
        '''
        user_input_text = f"Method Description: {des}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(file_sum_obj['classes']) == 0:
            self.logger.info(
                f"INSUFFICIENT CONTEXT{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nNo class in this file.")
            return {
                'is_found': False,
                'need_backtrack': True,
            }

        # concat summary of classes to context
        for cls_sum_obj in file_sum_obj['classes']:
            temp_obj = {
                'id': cls_sum_obj['id'],
                'name': cls_sum_obj['name'],
                'type': cls_sum_obj['type'],
                'summary': cls_sum_obj['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if not self._is_legal_input_text(RET_SCOPE_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'need_backtrack': False,
                }

            user_input_text += temp_str

        # infer the class
        infer_obj = self._infer_scope(file_sum_obj['id'], user_input_text)

        # error occurred during generation
        if infer_obj == None:
            return {
                'is_found': False,
                'need_backtrack': False,
            }

        # try ids in turn
        for infer_id in infer_obj['ids'][:RET_SCOPE_MAX_TRY_NUM]:
            cls_sum_obj = next(
                filter(lambda x: x['id'] == infer_id, file_sum_obj['classes']), None)
            if cls_sum_obj is None:
                self.logger.info(
                    f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nThe class is not found in this file.")
                return {
                    'is_found': False,
                    'need_backtrack': False,
                }

            res = self._retrieve_in_cls(
                des, cls_sum_obj, f"{path}/{cls_sum_obj['name']}")

            if res['is_found'] or not res['need_backtrack']:
                return res

        return {
            'is_found': False,
            'need_backtrack': True,
        }

    def _retrieve_in_dir(self, des: str, dir_sum_obj: dict, path: str) -> dict:
        '''
            Retrieve the method according to the description and the summary of the directory.
            return {is_found: bool, need_backtrack: bool, path: str | None}, path is str only when is_found is True.
        '''
        user_input_text = f"Method Description: {des}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(dir_sum_obj['subdirectories']) == 0 and len(dir_sum_obj['files']) == 0:
            self.logger.info(
                f"INSUFFICIENT CONTEXT{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nNo file and subdirectory in this directory.")
            return {
                'is_found': False,
                'need_backtrack': True,
            }

        # concat summary of subdirectories to context
        for sub_dir_sum_obj in dir_sum_obj['subdirectories']:
            temp_obj = {
                'id': sub_dir_sum_obj['id'],
                'name': sub_dir_sum_obj['name'],
                'summary': sub_dir_sum_obj['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if not self._is_legal_input_text(RET_SCOPE_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'need_backtrack': False,
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
            if not self._is_legal_input_text(RET_SCOPE_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'need_backtrack': False,
                }

            user_input_text += temp_str

        # infer the subdirectiry or file
        infer_obj = self._infer_scope(dir_sum_obj['id'], user_input_text)

        # error occurred during generation
        if infer_obj == None:
            return {
                'is_found': False,
                'need_backtrack': False,
            }

        # try ids in turn
        for infer_id in infer_obj['ids'][:RET_SCOPE_MAX_TRY_NUM]:
            file_sum_obj = None
            sub_dir_sum_obj = None
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
                    'need_backtrack': False,
                }
            elif file_sum_obj is not None:
                res = self._retrieve_in_file(
                    des, file_sum_obj, f"{path}/{file_sum_obj['name']}")
            elif sub_dir_sum_obj is not None:
                res = self._retrieve_in_dir(
                    des, sub_dir_sum_obj, f"{path}/{sub_dir_sum_obj['name']}")

            if res['is_found'] or not res['need_backtrack']:
                return res

        return {
            'is_found': False,
            'need_backtrack': True,
        }

    def retrieve_in_repo(self, des: str, repo_sum_obj: dict) -> dict:
        '''
            Retrieve the method according to the description and the summary of the entire repo.
            return {is_found: bool, path: str, method_name: str}.
        '''
        start_time = time.time()

        res = self._retrieve_in_dir(des, repo_sum_obj, repo_sum_obj['name'])

        self.logger.info(f"COMPLETION{LOG_SEPARATOR}")
        self.logger.info(f"Token Used: {self.token_used_count}")
        self.logger.info(
            f"Retrieval time cost: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")

        if res['is_found']:
            return {
                'is_found': True,
                'method_name': res['path'].split('/')[-1],
                'path': res['path'],
            }
        else:
            return {
                'is_found': False,
                'method_name': "",
                'path': "",
            }
