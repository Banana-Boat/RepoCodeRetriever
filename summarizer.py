from concurrent.futures import ThreadPoolExecutor
import logging
import time
from typing import List
import tiktoken
from tqdm import tqdm
from transformers import CodeLlamaTokenizer

from ie_client import IEClient
from constants import INPUT_SEPARATOR, LOG_SEPARATOR, NO_SUMMARY, SUM_DIR, SUM_FILE, SUM_METHOD
from openai_client import OpenAIClient


class Summarizer:
    def __init__(self, logger: logging.Logger, ie_client: IEClient, openai_client: OpenAIClient):
        self.logger = logger
        self.codellama_tokenizer = CodeLlamaTokenizer.from_pretrained(
            ie_client.model_name)
        self.openai_tokenizer = tiktoken.encoding_for_model(
            openai_client.model_name)

        self.ie_client = ie_client
        self.openai_client = openai_client

        self.gen_err_count = 0  # number of generation error
        self.total_ignore_count = 0  # number of ignored nodes
        self.truncation_count = 0  # number of truncated nodes
        self.token_used_count = 0

        self.SPECIAL_TOKEN_NUM = 30

    def _is_legal_openai_input(self, system_input_text: str, user_input_text: str, max_output_length: int) -> bool:
        '''
            Check if the input text length exceeds the model limit.
        '''
        encoded_text = self.openai_tokenizer.encode(
            system_input_text + user_input_text)

        return len(encoded_text) <= self.openai_client.max_number_of_tokens - max_output_length

    def _is_legal_codellama_input(self, system_input_text: str, user_input_text: str, max_output_length: int) -> bool:
        '''
            Check if the input text length is less than model limit.
        '''
        encoded = self.codellama_tokenizer.encode(
            system_input_text + user_input_text,
            add_special_tokens=False, padding=False, truncation=False)

        return len(encoded) <= self.ie_client.max_number_of_tokens - self.SPECIAL_TOKEN_NUM - max_output_length

    def _build_codellama_input(self, node_id: int, system_input_text: str, user_input_text: str, max_output_length: int) -> str:
        '''
            Concat promp and context, add special tokens, truncate if exceeds the token limit
        '''

        if not self._is_legal_codellama_input(system_input_text, user_input_text, max_output_length):
            encoded_system_input = self.codellama_tokenizer.encode(
                system_input_text,
                add_special_tokens=False,
                padding=False, truncation=False
            )
            max_user_input_length = self.ie_client.max_number_of_tokens - len(encoded_system_input) - \
                self.SPECIAL_TOKEN_NUM - max_output_length
            encoded_user_input = self.codellama_tokenizer.encode(
                user_input_text,
                add_special_tokens=False,
                padding=False, truncation=True,
                max_length=max_user_input_length
            )
            truncated_user_input_text = self.codellama_tokenizer.decode(
                encoded_user_input, skip_special_tokens=False)

            self.logger.warning(
                f"TRUNCATION{LOG_SEPARATOR}\nNode ID: {node_id}\nInput text exceeds the token limit, truncates user input text from:\n{user_input_text}\nto:\n{truncated_user_input_text}")

            user_input_text = truncated_user_input_text

        return f"<s>[INST]<<SYS>>\n{system_input_text}\n<</SYS>>\n{user_input_text}\n[/INST]"

    def _openai_summarize(self, node_id: int, system_input_text: str, user_input_text: str, max_output_length: int) -> str:
        '''
            Generate summary through API calls.
        '''
        try:
            total_tokens, output_text = self.openai_client.generate(
                system_input_text, user_input_text, max_output_length)
            self.token_used_count += total_tokens
            return output_text
        except Exception as e:
            self.gen_err_count += 1
            self.logger.error(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nFailed to generate summary for:\n{e}")
            return NO_SUMMARY

    def _codellama_summarize(self, node_id: int, input_text: str, max_output_length: int) -> dict:
        '''
            Generate summary through API calls.
            return: {id: int, input_text: str, output_text: str}
            the purpose of returning input_text is to facilitate logging
        '''
        try:
            return {
                'id': node_id,
                'input_text': input_text,
                'output_text': self.ie_client.generate(input_text, max_output_length)
            }
        except Exception as e:
            self.gen_err_count += 1
            self.logger.error(
                f"GENERATION ERROR{LOG_SEPARATOR}\nNode ID: {node_id}\nFailed to generate summary for:\n{e}")
            return {
                'id': node_id,
                'input_text': input_text,
                'output_text': NO_SUMMARY
            }

    def _codellama_batch_summarize(self, input_dicts: List[dict], max_output_length: int) -> List[dict]:
        '''
            Generate a batch of summary through async API calls, call API concurrently in max batch size.
            input_dicts: a list of {id: int, input_text: str}
            return: a list of {id: int, input_text: str, output_text: str}
        '''
        if len(input_dicts) == 0:
            return []

        max_bs = self.ie_client.max_batch_size
        bs = min(len(input_dicts), max_bs)

        with ThreadPoolExecutor(max_workers=bs) as executor:
            if len(input_dicts) <= max_bs:
                return list(
                    executor.map(
                        lambda x: self._codellama_summarize(
                            x['id'], x['input_text'], max_output_length),
                        input_dicts
                    )
                )

            res_dicts = list(
                executor.map(
                    lambda x: self._codellama_summarize(
                        x['id'], x['input_text'], max_output_length),
                    input_dicts[:max_bs]
                )
            )
            res_dicts.extend(
                self._codellama_batch_summarize(
                    input_dicts[max_bs:],
                    max_output_length
                )
            )

            return res_dicts

    def _summarize_methods(self, method_objs: List[dict]) -> List[dict]:
        '''
            Summarize for methods in one class, methods can be processed in batch.
            method_objs: a list of method_obj
            return: a list of {id: int, name: str, signature: str, summary: str}
        '''
        SYSTEM_PROMPT = SUM_METHOD['system_prompt']
        MAX_OUTPUT_LENGTH = SUM_METHOD['max_output_length']

        if len(method_objs) == 0:
            return []

        # assemble input dicts
        input_dicts = []
        for method_obj in method_objs:
            if method_obj["body"] != "":  # ignore methods that have no body
                user_input_text = method_obj["signature"] + method_obj["body"]
                input_dicts.append({
                    'id': method_obj['id'],
                    'input_text': self._build_codellama_input(method_obj['id'], SYSTEM_PROMPT, user_input_text, MAX_OUTPUT_LENGTH)
                })

        # generate summary
        output_dicts = self._codellama_batch_summarize(
            input_dicts, MAX_OUTPUT_LENGTH)

        # assemble method nodes
        method_nodes = []
        for method_obj in method_objs:
            output_dict = next(
                filter(lambda x: x['id'] == method_obj['id'], output_dicts), None)

            if output_dict != None:
                method_nodes.append({
                    'id': method_obj['id'],
                    'name': method_obj['name'],
                    'summary': output_dict['output_text'],
                    'signature': method_obj['signature'],
                })
                self.logger.info(
                    f"METHOD{LOG_SEPARATOR}\nNode ID: {method_obj['id']}\nInput:\n{output_dict['input_text']}\nOutput:\n{output_dict['output_text']}")
            else:
                method_nodes.append({
                    'id': method_obj['id'],
                    'name': method_obj['name'],
                    'summary': NO_SUMMARY,
                    'signature': method_obj['signature'],
                })
                self.logger.info(
                    f"METHOD{LOG_SEPARATOR}\nNode ID: {method_obj['id']}\nOutput:\n{NO_SUMMARY}")

        self.pbar.update(len(method_objs))

        return method_nodes

    def _summarize_file(self, file_obj: dict) -> dict:
        '''
            Summarize for class with the same name as the file according to its methods.
            methods in one class can be processed in batch.
        '''
        SYSTEM_PROMPT = SUM_FILE['system_prompt']
        MAX_OUTPUT_LENGTH = SUM_FILE['max_output_length']

        ignore_method_count = 0
        user_input_text = file_obj["signature"] + " {\n"

        # handle all methods
        method_nodes = self._summarize_methods(file_obj["methods"])

        # concat summary of methods to user_input_text
        for idx, method_node in enumerate(method_nodes):
            tmp_str = f"\t{method_node['signature']};\n"

            if method_node['summary'] != NO_SUMMARY:
                tmp_str = f"\t{method_node['signature']}; // {method_node['summary']}\n"

            # ignore methods that exceed the token limit
            if not self._is_legal_codellama_input(SYSTEM_PROMPT, user_input_text + tmp_str, MAX_OUTPUT_LENGTH):
                ignore_method_count = len(method_nodes) - idx
                break

            user_input_text += tmp_str

        user_input_text += "}"

        input_text = self._build_codellama_input(
            file_obj['id'], SYSTEM_PROMPT, user_input_text, MAX_OUTPUT_LENGTH)
        summary = self._codellama_summarize(
            file_obj['id'], input_text, MAX_OUTPUT_LENGTH)['output_text']

        self.logger.info(
            f"FILE{LOG_SEPARATOR}\nNode ID: {file_obj['id']}\nInput:\n{input_text}\nOutput:\n{summary}")
        if ignore_method_count != 0:
            self.logger.info(
                f"Number of ignored method: {ignore_method_count}")
        self.pbar.update(1)

        return {
            "id": file_obj["id"],
            "name": file_obj["name"],
            "summary": summary,
            "methods": method_nodes,
        }

    def _summarize_dir(self, dir_obj: dict) -> dict:
        '''
            Summarize for directory according to its subdirectories and files.
        '''
        SYSTEM_PROMPT = SUM_DIR['system_prompt']
        MAX_OUTPUT_LENGTH = SUM_DIR['max_output_length']

        # if current directory only has one subdirectory(no file),
        # concat directory name, only generate one node.
        if (len(dir_obj["subdirectories"]) == 1 and len(dir_obj["files"]) == 0):
            child_dir_obj = dir_obj['subdirectories'][0]
            child_dir_obj['name'] = f"{dir_obj['name']}/{child_dir_obj['name']}"
            return self._summarize_dir(child_dir_obj)

        valid_context_count = 0
        summary = NO_SUMMARY
        ignore_sub_dir_count = 0
        ignore_file_count = 0
        user_input_text = f"Directory name: {dir_obj['name']}.\n{INPUT_SEPARATOR}\nInformation list:\n"

        # handle all subdirectories recursively
        sub_dir_nodes = []
        for sub_dir_obj in dir_obj["subdirectories"]:
            sub_dir_nodes.append(self._summarize_dir(sub_dir_obj))

        # concat summary of subdirectories to user_input_text
        if len(sub_dir_nodes) > 0:
            for idx, sub_dir_node in enumerate(sub_dir_nodes):
                temp_obj = {
                    'id': sub_dir_node['id'],
                    'type': 'directory',
                    'name': sub_dir_node['name'],
                    'summary': sub_dir_node['summary'],
                }
                temp_str = f"{temp_obj}\n"
                if not self._is_legal_openai_input(SYSTEM_PROMPT, user_input_text + temp_str, MAX_OUTPUT_LENGTH):
                    ignore_sub_dir_count = len(sub_dir_nodes) - idx
                    break

                user_input_text += temp_str
                valid_context_count += 1

        # handle all files
        file_nodes = []
        for file_obj in dir_obj["files"]:
            file_nodes.append(self._summarize_file(file_obj))

        # concat summary of files to user_input_text
        if len(file_nodes) > 0:
            for idx, file_node in enumerate(file_nodes):
                temp_obj = {
                    'id': file_node['id'],
                    'type': 'file',
                    'name': file_node['name'],
                    'summary': file_node['summary'],
                }
                temp_str = f"{temp_obj}\n"
                if not self._is_legal_openai_input(SYSTEM_PROMPT, user_input_text + temp_str, MAX_OUTPUT_LENGTH):
                    ignore_file_count = len(file_nodes) - idx
                    break

                user_input_text += temp_str
                valid_context_count += 1

        if valid_context_count != 0:
            summary = self._openai_summarize(
                dir_obj['id'], SYSTEM_PROMPT, user_input_text, MAX_OUTPUT_LENGTH)

        self.logger.info(
            f"DIRECTORY{LOG_SEPARATOR}\nNode ID: {dir_obj['id']}\nSystem Input:\n{SYSTEM_PROMPT}\nUser Input:\n{user_input_text}\nOutput:\n{summary}")
        if ignore_file_count != 0:
            self.logger.info(f"Number of ignored file: {ignore_file_count}")
        if ignore_sub_dir_count != 0:
            self.logger.info(
                f"Number of ignored subdirectory: {ignore_sub_dir_count}")
        self.pbar.update(1)

        return {
            "id": dir_obj["id"],
            "name": dir_obj["name"],
            "summary": summary,
            "subdirectories": sub_dir_nodes,
            "files": file_nodes,
        }

    def summarize_repo(self, repo_obj: dict) -> dict:
        '''
            Generate the summary tree for the entire repo.
        '''
        start_time = time.time()

        with tqdm(total=repo_obj['nodeCount']) as pbar:
            pbar.set_description("Summarizing repo...")
            self.pbar = pbar

            result = self._summarize_dir(repo_obj['mainDirectory'])

            self.logger.info(f"COMPLETION{LOG_SEPARATOR}")
            self.logger.info(
                f"Number of generation error: {self.gen_err_count}")
            self.logger.info(
                f"Number of ignored node: {self.total_ignore_count}")
            self.logger.info(
                f"Number of truncated node: {self.truncation_count}")
            self.logger.info(f"Token Used: {self.token_used_count}")

            self.logger.info(
                f"Summarization time cost: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")

            return result
