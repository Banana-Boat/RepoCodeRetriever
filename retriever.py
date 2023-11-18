import json
import logging
import time

import tiktoken
from constants import LOG_SEPARATOR, RET_MAX_OUTPUT_LENGTH, RET_METHOD_SYSTEM_PROMPT, RET_SCOPE_SYSTEM_PROMPT

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

    def _infer(self, node_id: int, system_input_text: str, user_input_text: str) -> dict:
        '''
            Generate inference through API calls.
            return: {id: int, reason: str}
        '''
        try:
            total_tokens, output_text = self.openai_client.generate(
                system_input_text, user_input_text, RET_MAX_OUTPUT_LENGTH)
            self.token_used_count += total_tokens

            try:
                # check if the inference result is formatted
                res_obj = json.load(output_text)
                if 'id' not in res_obj or 'reason' not in res_obj:
                    raise Exception()

                self.logger.info(
                    f"INFERENCE{LOG_SEPARATOR}\nNode ID: {node_id}\nUser Input:\n{user_input_text}\nOutput:\n{res_obj}")

                return res_obj
            except Exception as e:
                self.logger.error(
                    f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nThe inference result is not formatted, output text: {output_text}")
                return {
                    'id': -1,
                    'reason': "",
                }
        except Exception as e:
            self.logger.error(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nAn Error occurred during generation API call:\n{e}")
            return {
                'id': -1,
                'reason': "",
            }

    def _retrieve_in_cls(self, des: str, cls_sum_obj: dict, path: str) -> dict:
        '''
            Retrieve the method according to the description and the summary of the class.
            return {is_found: bool, path: str, method_name: str | None}
        '''
        user_input_text = f"Method Description: {des}\n{LOG_SEPARATOR}\nSummary:\n"

        # check number of valid context
        if len(cls_sum_obj['methods']) == 0:
            self.logger.info(
                f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {cls_sum_obj['id']}\nNo method in this class.")
            return {
                'is_found': False,
                'path': path,
            }

        # concat summary of methods to context
        for method_sum_obj in cls_sum_obj['methods']:
            temp_obj = {
                'id': method_sum_obj['id'],
                'name': method_sum_obj['name'],
                'summary': method_sum_obj['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if self._is_legal_input_text(RET_METHOD_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {cls_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'path': path,
                }

            user_input_text += temp_str

        # infer the method
        res_obj = self._infer(
            cls_sum_obj['id'], RET_METHOD_SYSTEM_PROMPT, user_input_text)

        if res_obj['id'] == -1:
            return {
                'is_found': False,
                'path': path,
            }

        # get method_sum_obj according to res_obj['id']
        method_sum_obj = next(
            filter(lambda x: x['id'] == res_obj['id'], cls_sum_obj['methods']), None)
        if method_sum_obj is None:
            self.logger.info(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {cls_sum_obj['id']}\nThe method is not found in this class.")
            return {
                'is_found': False,
                'path': path,
            }

        # return the result of retrieval
        return {
            'is_found': True,
            'path': f"{path}.{method_sum_obj['name']}",
            'method_name': f"{cls_sum_obj['name']}.{method_sum_obj['name']}",
        }

    def _retrieve_in_file(self, des: str, file_sum_obj: dict, path: str) -> dict:
        '''
            Retrieve the method according to the description and the summary of the file.
            return {is_found: bool, path: str, method_name: str | None}
        '''
        user_input_text = f"Method Description: {des}\n{LOG_SEPARATOR}\nSummary:\n"

        # check number of valid context
        if len(file_sum_obj['classes']) == 0:
            self.logger.info(
                f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nNo class in this file.")
            return {
                'is_found': False,
                'path': path,
            }

        # concat summary of classes to context
        for cls_sum_obj in file_sum_obj['classes']:
            temp_obj = {
                'id': cls_sum_obj['id'],
                'name': cls_sum_obj['name'],
                'summary': cls_sum_obj['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if self._is_legal_input_text(RET_SCOPE_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'path': path,
                }

            user_input_text += temp_str

        # infer the class
        res_obj = self._infer(
            file_sum_obj['id'], RET_SCOPE_SYSTEM_PROMPT, user_input_text)

        if res_obj['id'] == -1:
            return {
                'is_found': False,
                'path': path,
            }

        # get cls_sum_obj according to res_obj['id']
        cls_sum_obj = next(
            filter(lambda x: x['id'] == res_obj['id'], file_sum_obj['classes']), None)
        if cls_sum_obj is None:
            self.logger.info(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nThe class is not found in this file.")
            return {
                'is_found': False,
                'path': path,
            }

        # dive into next hierarchy
        return self._retrieve_in_cls(des, cls_sum_obj, f"{path}/{cls_sum_obj['name']}")

    def _retrieve_in_dir(self, des: str, dir_sum_obj: dict, path: str) -> dict:
        '''
            Retrieve the method according to the description and the summary of the directory.
            return {is_found: bool, path: str, method_name: str | None}
        '''
        user_input_text = f"Method Description: {des}\n{LOG_SEPARATOR}\nSummary:\n"

        # check number of valid context
        if len(dir_sum_obj['subdirectories']) == 0 and len(dir_sum_obj['files']) == 0:
            self.logger.info(
                f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nNo file and subdirectory in this directory.")
            return {
                'is_found': False,
                'path': path,
            }

        # concat summary of subdirectories to context
        for sub_dir_sum_obj in dir_sum_obj['subdirectories']:
            temp_obj = {
                'id': sub_dir_sum_obj['id'],
                'name': sub_dir_sum_obj['name'],
                'summary': sub_dir_sum_obj['summary'],
            }
            temp_str = f"{temp_obj}\n"
            if self._is_legal_input_text(RET_SCOPE_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'path': path,
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
            if self._is_legal_input_text(RET_SCOPE_SYSTEM_PROMPT, user_input_text + temp_str):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nInput text length exceeds the model limit.")
                return {
                    'is_found': False,
                    'path': path,
                }

            user_input_text += temp_str

        # infer the subdirectiry or file
        res_obj = self._infer(
            dir_sum_obj['id'], RET_SCOPE_SYSTEM_PROMPT, user_input_text)

        if res_obj['id'] == -1:
            return {
                'is_found': False,
                'path': path,
            }

        # get next_sum_obj according to res_obj['id'], dive into next hierarchy
        next_sum_obj = None

        next_sum_obj = next(
            filter(lambda x: x['id'] == res_obj['id'], dir_sum_obj['subdirectories']), None)
        if next_sum_obj is not None:
            return self._retrieve_in_file(des, next_sum_obj, f"{path}/{next_sum_obj['name']}")

        next_sum_obj = next(
            filter(lambda x: x['id'] == res_obj['id'], dir_sum_obj['subdirectories']), None)
        if next_sum_obj is not None:
            return self._retrieve_in_dir(des, next_sum_obj, f"{path}/{next_sum_obj['name']}")

        # can't find next_sum_obj
        self.logger.info(
            f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nThe file or subdirectory is not found in this directory.")
        return {
            'is_found': False,
            'path': path,
        }

    def retrieve_in_repo(self, des: str, repo_sum_obj: dict) -> dict:
        '''
            Retrieve the method according to the description and the summary of the entire repo.
            return {is_found: bool, path: str, method_name: str | None}
        '''
        start_time = time.time()

        result = self._retrieve_in_dir(des, repo_sum_obj, repo_sum_obj['name'])

        self.logger.info(f"COMPLETION{LOG_SEPARATOR}")
        self.logger.info(f"Token Used: {self.token_used_count}")
        self.logger.info(
            f"Retrieval time cost: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")

        return result
