import json
import logging
from typing import Tuple
from dotenv import load_dotenv

import tiktoken
from constants import EXP_DOC, EXP_MAX_REF_COUNT, EXP_QUERY, INPUT_SEPARATOR, LOG_SEPARATOR

from openai_client import OpenAIClient
from sim_caculator import SimCaculator


class QueryExpander:
    def __init__(self, logger: logging.Logger, openai_client: OpenAIClient, sim_caculator: SimCaculator) -> None:
        self.logger = logger

        self.openai_tokenizer = tiktoken.encoding_for_model(
            openai_client.model_name)
        self.openai_client = openai_client
        self.token_used_count = 0

        self.sim_caculator = sim_caculator

        self.query = ""  # query, set every retrieval
        self.collected_sum_objs = []  # summaries, reset every retrieval

    def _is_legal_input(self, system_input_text: str, user_input_text: str, max_output_length: int) -> bool:
        '''Check if the input text length exceeds the model limit.'''
        encoded_text = self.openai_tokenizer.encode(
            system_input_text + user_input_text)

        return len(encoded_text) <= self.openai_client.max_number_of_tokens - max_output_length

    def _collect_in_dir(self, dir_sum_obj: dict):
        '''Collect summaries in a directory.'''
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
        similarities = self.sim_caculator.calc_similarities(
            self.query, summaries)

        for i, info in enumerate(infos):
            info['similarity'] = similarities[i]
        infos.sort(key=lambda x: x['similarity'], reverse=True)

        # collect the summary of subdirectory or file with the highest similarity
        for info in infos[:EXP_MAX_REF_COUNT]:
            sub_dir_sum_obj = next(
                filter(lambda x: x['id'] == info['id'], dir_sum_obj['subdirectories']), None)
            if sub_dir_sum_obj is not None:
                self._retrieve_in_dir(sub_dir_sum_obj)

            self.collected_sum_objs.append(info)

    def _generate_doc(self, repo_sum_obj: dict) -> str:
        '''
            Traverse the summary tree to collect summaries with high similarity to query.
            Generate a pseudo relevance doc with the collected summaries.
            raise Exception if error occurs.
        '''
        SYSTEM_PROMPT = EXP_DOC['system_prompt']
        MAX_OUTPUT_LENGTH = EXP_DOC['max_output_length']
        user_input_text = ""

        self.collected_sum_objs.append({
            'id': repo_sum_obj['id'],
            'summary': repo_sum_obj['summary'],
        })
        self._collect_in_dir(repo_sum_obj)

        for sum_obj in self.collected_sum_objs:
            user_input_text += f"{sum_obj['summary']}\n"
        collected_ids = [sum_obj['id'] for sum_obj in self.collected_sum_objs]

        if not self._is_legal_input(SYSTEM_PROMPT, user_input_text, MAX_OUTPUT_LENGTH):
            raise Exception("Input text length exceeds the model limit.")

        total_tokens, output_text = self.openai_client.generate(
            SYSTEM_PROMPT, user_input_text, MAX_OUTPUT_LENGTH)
        self.token_used_count += total_tokens

        self.logger.info(
            f"DOC GENERATION{LOG_SEPARATOR}\nCollected Nodes: {collected_ids}\nSystem Input:\n{SYSTEM_PROMPT}\nUser Input:\n{user_input_text}\nOutput:\n{output_text}")

        return output_text

    def _generate_query(self, doc: str) -> str:
        '''
            Expand the query with the given doc.
            raise Exception if error occurs.
        '''
        SYSTEM_PROMPT = EXP_QUERY['system_prompt']
        MAX_OUTPUT_LENGTH = EXP_QUERY['max_output_length']
        user_input_text = f"Query: {self.query}\n{INPUT_SEPARATOR}\nDocument:\n{doc}"

        if not self._is_legal_input(SYSTEM_PROMPT, user_input_text, MAX_OUTPUT_LENGTH):
            raise Exception("Input text length exceeds the model limit.")

        total_tokens, output_text = self.openai_client.generate(
            SYSTEM_PROMPT, user_input_text, MAX_OUTPUT_LENGTH)
        self.token_used_count += total_tokens

        self.logger.info(
            f"QUERY GENERATION{LOG_SEPARATOR}\nSystem Input:\n{SYSTEM_PROMPT}\nUser Input:\n{user_input_text}\nOutput:\n{output_text}")

        return output_text

    def get_expanded_query(self, query: str, repo_sum_obj: dict) -> Tuple[bool, str]:
        '''
            Get the expanded query.
            return: (is_error, expanded_query)
        '''
        self.query = query
        self.collected_sum_objs = []

        try:
            doc = self._generate_doc(query, repo_sum_obj)
            expanded_query = self._generate_query(doc, query)
        except:
            self.logger.error(f"EXPANSION ERROR{LOG_SEPARATOR}\n{e}")
            return True, ""

        self.logger.info(f"EXPANSION COMPLETION{LOG_SEPARATOR}")
        self.logger.info(f"Token Used: {self.token_used_count}")

        return False, expanded_query


if __name__ == "__main__":
    load_dotenv()

    query = "Create a new Recycler for ZipFileSliceReader instances."
    sum_out_path = "./eval_data/sum_result/classgraph/sum_out_classgraph.json"

    try:
        openai_client = OpenAIClient()
    except Exception as e:
        print(e)
        exit(1)

    sim_calculator = SimCaculator()

    ret_logger = logging.getLogger(__name__)
    ret_logger.addHandler(
        logging.FileHandler("log_test.txt", "w", "utf-8")
    )
    ret_logger.propagate = False

    query_expander = QueryExpander(ret_logger, openai_client, sim_calculator)

    with open(sum_out_path, "r") as f_sum_out:
        repo_sum_obj = json.load(f_sum_out)
        res = query_expander.get_expanded_query(query, repo_sum_obj)

        print(res)

    logging.shutdown()
