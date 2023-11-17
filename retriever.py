import logging
import time

import tiktoken
from constants import LOG_SEPARATOR

from openai_client import OpenAIClient


class Retriever:
    def __init__(self, logger: logging.Logger, openai_client: OpenAIClient):
        self.logger = logger
        self.tokenizer = tiktoken.encoding_for_model(openai_client.model_name)

        self.openai_client = openai_client

    def _is_legal_input_text(self, input_text: str, max_output_length: int) -> bool:
        '''
            Check if the input text length is less than model limit.
        '''
        encoded_text = self.tokenizer.encode(input_text)
        return len(encoded_text) <= self.openai_client.max_number_of_tokens - max_output_length

    def _build_input(self, prompt: str, context: str, max_output_length: int) -> str:
        pass

    def _infer(self, input_text: str, max_output_length: int) -> dict:
        pass

    def _retrieve_cls(self, query: str, cls_sum_obj: dict, path: str) -> dict:
        '''
            Retrieve method according to the query from class.
            return {is_found: bool, path: str, method_name: str | None}
        '''
        PROMPT = ""

        context = ""

        # concat summary of methods to context

        # infer the method

        if False:
            return {
                'is_found': False,
                'path': path,
            }

        method_sum_obj = {}

        self.logger.info(f"CLASS{LOG_SEPARATOR}")

        return {
            'is_found': True,
            'path': f"{path}.{method_sum_obj['name']}",
            'method_name': f"{cls_sum_obj['name']}.{method_sum_obj['name']}",
        }

    def _retrieve_file(self, query: str, file_sum_obj: dict, path: str) -> dict:
        '''
            Retrieve method according to the query from file.
            return {is_found: bool, path: str, method_name: str | None}
        '''
        PROMPT = ""

        context = ""

        # concat summary of classes to context

        # infer the class

        if False:
            return {
                'is_found': False,
                'path': path,
            }

        cls_sum_obj = {}

        self.logger.info(f"FILE{LOG_SEPARATOR}")

        # dive into next level
        return self._retrieve_cls(query, cls_sum_obj, f"{path}/{cls_sum_obj['name']}")

    def _retrieve_dir(self, query: str, dir_sum_obj: dict, path: str) -> dict:
        '''
            Retrieve method according to the query from directory.
            return {is_found: bool, path: str, method_name: str | None}
        '''
        PROMPT = ""

        context = ""

        # concat summary of subdirectories to context

        # concat summary of files to context

        # infer the next step(the id of dir or file node)

        if False:
            return {
                'is_found': False,
                'path': path,
            }

        next_sum_obj = {}

        is_dir = False

        self.logger.info(f"DIRECTORY{LOG_SEPARATOR}")

        # dive into next level
        if is_dir:
            return self._retrieve_dir(query, next_sum_obj, f"{path}/{next_sum_obj['name']}")
        else:
            return self._retrieve_file(query, next_sum_obj, f"{path}/{next_sum_obj['name']}")

    def retrieve_repo(self, query: str, repo_sum_obj: dict) -> dict:
        '''
            Retrieve method according to the query from the entire repo.
            return {is_found: bool, path: str, method_name: str | None}
        '''
        start_time = time.time()

        result = self._retrieve_dir(query, repo_sum_obj, repo_sum_obj['name'])

        self.logger.info(f"COMPLETION{LOG_SEPARATOR}")
        self.logger.info(
            f"Retrieval time cost: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")

        return result
