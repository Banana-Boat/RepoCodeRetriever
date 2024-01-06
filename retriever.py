import json
import logging
import re
from enum import Enum
from typing import List, Tuple

import tiktoken
from constants import EXP_MAX_REF_COUNT, EXP_QUERY, INPUT_SEPARATOR, LOG_SEPARATOR, RET_DIR_SYSTEM_PROMPT, RET_DIR_MAX_INFO_LENGTH, RET_FILE_MAX_INFO_LENGTH, RET_MAX_OUTPUT_LENGTH, RET_FILE_SYSTEM_PROMPT, RET_MAX_BACKTRACK_COUNT

from openai_client import OpenAIClient
from text_sim_calculator import TextSimCalculator


class InferType(Enum):
    FILE = 0  # retrieve in file
    DIR = 1  # retrieve in directory


class Retriever:
    def __init__(self, openai_client: OpenAIClient, text_sim_calculator: TextSimCalculator):
        self.openai_tokenizer = tiktoken.encoding_for_model(
            openai_client.model_name)
        self.openai_client = openai_client
        self.token_used_count = 0

        self.text_sim_calculator = text_sim_calculator

    def _reset(self):
        '''Reset variables.'''
        self.result_path = []
        self.most_probable_path = []
        self.is_first_try = True
        self.ret_times = 0

    def _is_legal_input(self, system_input_text: str, user_input_text: str, max_output_length: int) -> bool:
        '''Check if the input text length exceeds the model limit.'''
        encoded_text = self.openai_tokenizer.encode(
            system_input_text + user_input_text)

        return len(encoded_text) <= self.openai_client.max_number_of_tokens - max_output_length

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

    def _retrieve_in_file(self, file_sum_obj: dict) -> Tuple[bool, bool]:
        '''
            Retrieve the method according to its description and the summary of the file.
            return: (is_error: bool, is_found: bool)
        '''
        user_input_text = f"Method Description: {self.query}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(file_sum_obj['methods']) == 0:
            self.logger.info(
                f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nNo method in this file.")
            return True, False

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
        similarities = self.text_sim_calculator.calc_similarities(
            self.query, summaries)

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
            if not self._is_legal_input(RET_FILE_SYSTEM_PROMPT, user_input_text + temp_str, RET_MAX_OUTPUT_LENGTH):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nInput text length exceeds the model limit.")
                return True, False

            user_input_text += temp_str

        # infer the method
        infer_obj = self._infer(
            file_sum_obj['id'], InferType.FILE, user_input_text)

        # error occurred during generation
        if infer_obj == None:
            return True, False

        # no method was selected in this class
        if infer_obj['id'] == -1:
            self.is_first_try = False
            return False, False

        # get method_sum_obj according to infer_obj['id']
        method_sum_obj = next(
            filter(lambda x: x['id'] == infer_obj['id'], file_sum_obj['methods']), None)
        if method_sum_obj is None:
            self.logger.info(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {file_sum_obj['id']}\nThe method is not found in this class.")
            return True, False

        # return the result of retrieval
        self.result_path.append(method_sum_obj['name'])
        return False, True

    def _retrieve_in_dir(self, dir_sum_obj: dict) -> Tuple[bool, bool]:
        '''
            Retrieve the method according to its description and the summary of the directory.
            return: (is_error: bool, is_found: bool)
        '''
        user_input_text = f"Method Description: {self.query}\n{INPUT_SEPARATOR}\nInformation List:\n"

        # check number of valid context
        if len(dir_sum_obj['subdirectories']) == 0 and len(dir_sum_obj['files']) == 0:
            self.logger.info(
                f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nNo file or subdirectory in this directory.")
            return True, False

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
        similarities = self.text_sim_calculator.calc_similarities(
            self.query, summaries)

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
            if not self._is_legal_input(RET_DIR_SYSTEM_PROMPT, user_input_text + temp_str, RET_MAX_OUTPUT_LENGTH):
                self.logger.info(
                    f"CONTEXT ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nInput text length exceeds the model limit.")
                return True, False

            user_input_text += temp_str

        # infer the subdirectiry or file
        infer_obj = self._infer(
            dir_sum_obj['id'], InferType.DIR, user_input_text)

        # error occurred during generation
        if infer_obj == None:
            return True, False

        # try ids in turn
        for infer_id in infer_obj['ids'][:RET_MAX_BACKTRACK_COUNT]:
            file_sum_obj = None
            sub_dir_sum_obj = None
            next_sum_obj = None
            is_error = False
            is_found = False

            # find next_sum_obj according to infer_id
            file_sum_obj = next(
                filter(lambda x: x['id'] == infer_id, dir_sum_obj['files']), None)
            sub_dir_sum_obj = next(
                filter(lambda x: x['id'] == infer_id, dir_sum_obj['subdirectories']), None)

            if file_sum_obj is None and sub_dir_sum_obj is None:
                # can't find next_sum_obj
                self.logger.info(
                    f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {dir_sum_obj['id']}\nThe file or subdirectory is not found in this directory.")
                return True, False

            if file_sum_obj is not None:
                next_sum_obj = file_sum_obj
                if self.is_first_try:
                    # add to most probable path if it is the first try
                    self.most_probable_path.append(next_sum_obj['name'])

                is_error, is_found = self._retrieve_in_file(file_sum_obj)
            elif sub_dir_sum_obj is not None:
                next_sum_obj = sub_dir_sum_obj
                if self.is_first_try:
                    # add to most probable path if it is the first try
                    self.most_probable_path.append(next_sum_obj['name'])

                is_error, is_found = self._retrieve_in_dir(sub_dir_sum_obj)

            if is_found or is_error:
                self.result_path.append(next_sum_obj['name'])
                return is_error, is_found

        return False, False

    def _collect_in_dir(self, dir_sum_obj: dict) -> List[dict]:
        '''
            Collect summaries in a directory.
            return: list of collected summary object.
        '''
        result = []

        # get information list of subdirectory and file
        infos = []
        for sub_dir_sum_obj in dir_sum_obj['subdirectories']:
            infos.append({
                'id': sub_dir_sum_obj['id'],
                'summary': sub_dir_sum_obj['summary'],
            })

        for file_sum_obj in dir_sum_obj['files']:
            infos.append({
                'id': file_sum_obj['id'],
                'summary': file_sum_obj['summary'],
            })

        # calculate similarity, and sort infos according to similarity
        summaries = [info['summary'] for info in infos]
        similarities = self.text_sim_calculator.calc_similarities(
            self.query, summaries)

        for i, info in enumerate(infos):
            info['similarity'] = similarities[i]
        infos.sort(key=lambda x: x['similarity'], reverse=True)

        # collect the summary of subdirectory or file with the highest similarity
        for info in infos[:EXP_MAX_REF_COUNT]:
            sub_dir_sum_obj = next(
                filter(lambda x: x['id'] == info['id'], dir_sum_obj['subdirectories']), None)
            if sub_dir_sum_obj is not None:
                result.extend(self._collect_in_dir(sub_dir_sum_obj))

            result.append(info)

        return result

    def _expand_query(self, repo_sum_obj: dict) -> Tuple[bool, str]:
        '''
            Traverse the summary tree to collect summaries with high similarity to query.
            Concat these summaries as a pseudo relevance doc.
            Expand the query with the given doc.
            return: (is_error: bool, expanded_query: str)
        '''
        SYSTEM_PROMPT = EXP_QUERY['system_prompt']
        MAX_OUTPUT_LENGTH = EXP_QUERY['max_output_length']

        user_input_text = f"Query: {self.query}\n{INPUT_SEPARATOR}\nDocument:\n"
        ignore_start_idx = -1
        selected_sum_ids = []

        # collect the summaries
        collected_sum_objs = [{
            'id': repo_sum_obj['id'],
            'summary': repo_sum_obj['summary'],
        }]
        collected_sum_objs.extend(self._collect_in_dir(repo_sum_obj))

        # concat the summaries
        for idx, sum_obj in enumerate(collected_sum_objs):
            temp_str = f"{sum_obj['summary']}\n"

            if not self._is_legal_input(SYSTEM_PROMPT, user_input_text + temp_str, MAX_OUTPUT_LENGTH):
                ignore_start_idx = idx
                break

            user_input_text += temp_str
            selected_sum_ids.append(sum_obj['id'])

        # expand the query
        try:
            total_tokens, output_text = self.openai_client.generate(
                SYSTEM_PROMPT, user_input_text, MAX_OUTPUT_LENGTH)
            self.token_used_count += total_tokens
        except Exception as e:
            self.logger.error(f"QUERY EXPANSION ERROR{LOG_SEPARATOR}\n{e}")
            return True, ""

        # check if the result is formatted
        try:
            match = re.search(r'\{.*\}', output_text, re.DOTALL)
            if not match:
                raise Exception("The result is not formatted.")
            json_text = match.group(0)

            res_obj = json.loads(json_text)
            if 'expanded_query' not in res_obj or \
                    not isinstance(res_obj['expanded_query'], str):
                raise Exception("The result is not formatted.")
        except Exception as e:
            self.logger.error(f"QUERY EXPANSION ERROR{LOG_SEPARATOR}\n{e}")
            return True, ""

        self.logger.info(
            f"QUERY EXPANSION{LOG_SEPARATOR}\nCollected IDs: {selected_sum_ids}\nSystem Input:\n{SYSTEM_PROMPT}\nUser Input:\n{user_input_text}\nOutput:\n{output_text}")
        if ignore_start_idx != -1:
            self.logger.info(
                f"Ignored Summaries: {collected_sum_objs[ignore_start_idx:]}")

        return False, res_obj['expanded_query']

    def retrieve(self, query: str, repo_sum_obj: dict, logger: logging.Logger) -> Tuple[bool, dict]:
        '''
            Retrieve the method according to its description and the summary of the entire repo.
            return: (is_error: bool, {is_found: bool, is_query_expanded: bool, path: List[str], ret_times: int}).
            If is_found is False, path is the search path of the most probability.
        '''
        self.query = query
        self.logger = logger
        self._reset()

        is_query_expanded = False

        # retrieve with original query
        is_error, is_found = self._retrieve_in_dir(repo_sum_obj)

        # retrieve again with expanded query
        if not is_error and not is_found:
            is_query_expanded = True
            is_error, expanded_query = self._expand_query(repo_sum_obj)

            if not is_error:
                self.query = expanded_query
                is_error, is_found = self._retrieve_in_dir(repo_sum_obj)

        self.logger.info(f"RETRIEVAL COMPLETION{LOG_SEPARATOR}")
        self.logger.info(f"Token Used: {self.token_used_count}")

        # assemble result
        res = {'is_found': is_found, 'is_query_expanded': is_query_expanded}
        if is_found:
            self.result_path.reverse()
            res['path'] = self.result_path
        else:
            res['path'] = self.most_probable_path

        res['ret_times'] = self.ret_times

        return is_error, res
