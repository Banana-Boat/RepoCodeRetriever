from concurrent.futures import ThreadPoolExecutor
import logging
import time
from typing import List
from tqdm import tqdm
from transformers import CodeLlamaTokenizer

from ie_client import IEClient
from constants import INPUT_SEPARATOR, LOG_SEPARATOR, NO_SUMMARY, SUM_CLS, SUM_DIR, SUM_FILE, SUM_METHOD


class Summarizer:
    def __init__(self, logger: logging.Logger, ie_client: IEClient):
        self.logger = logger
        self.tokenizer = CodeLlamaTokenizer.from_pretrained(
            ie_client.model_name)

        self.ie_client = ie_client
        self.gen_err_count = 0  # number of generation error
        self.total_ignore_count = 0  # number of ignored nodes
        self.truncation_count = 0  # number of truncated nodes

        self.SPECIAL_TOKEN_NUM = 5

    def _is_legal_input_text(self, input_text: str, max_output_length: int) -> bool:
        '''
            Check if the input text length is less than model limit.
        '''
        encoded = self.tokenizer.encode(
            input_text, add_special_tokens=False, padding=False, truncation=False)

        return len(encoded) <= self.ie_client.max_number_of_tokens - self.SPECIAL_TOKEN_NUM - max_output_length

    def _build_input(self, node_id: int, prompt: str, context: str, max_output_length: int) -> str:
        '''
            Concat promp and context, add special tokens, truncate if exceeds the token limit
        '''
        input_text = f"{prompt}\n{INPUT_SEPARATOR}\n{context}"

        if not self._is_legal_input_text(input_text, max_output_length):
            max_input_length = self.ie_client.max_number_of_tokens - \
                self.SPECIAL_TOKEN_NUM - max_output_length
            encoded = self.tokenizer.encode(
                input_text,
                add_special_tokens=False,
                padding=False, truncation=True,
                max_length=max_input_length
            )

            truncated_input_text = self.tokenizer.decode(
                encoded, skip_special_tokens=False)
            self.logger.warning(
                f"TRUNCATION{LOG_SEPARATOR}\nNode ID: {node_id}\nInput text exceeds the token limit, truncates from:\n{input_text}\nto:\n{truncated_input_text}")

            input_text = truncated_input_text

        return f"<s>[INST] {input_text} [/INST]"

    def _summarize(self, node_id: int, input_text: str, max_output_length: int) -> dict:
        '''
            Generate summary through API calls.
            return: a list of {id: int, input_text: str, output_text: str}
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
                f"GENERATION FAILED{LOG_SEPARATOR}\nNode ID: {node_id}\nFailed to generate summary for:\n{e}")
            return {
                'id': node_id,
                'input_text': input_text,
                'output_text': NO_SUMMARY
            }

    def _batch_summarize(self, input_dicts: List[dict], max_output_length: int) -> List[dict]:
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
                        lambda x: self._summarize(
                            x['id'], x['input_text'], max_output_length),
                        input_dicts
                    )
                )

            res_dicts = list(
                executor.map(
                    lambda x: self._summarize(
                        x['id'], x['input_text'], max_output_length),
                    input_dicts[:max_bs]
                )
            )
            res_dicts.extend(
                self._batch_summarize(
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
        PROMPT = SUM_METHOD['prompt']
        MAX_OUTPUT_LENGTH = SUM_METHOD['max_output_length']

        if len(method_objs) == 0:
            return []

        # assemble input dicts
        input_dicts = []
        for method_obj in method_objs:
            if method_obj["body"] != "":  # ignore methods that have no body
                context = method_obj["signature"] + method_obj["body"]
                input_dicts.append({
                    'id': method_obj['id'],
                    'input_text': self._build_input(method_obj['id'], PROMPT, context, MAX_OUTPUT_LENGTH)
                })

        # generate summary
        output_dicts = self._batch_summarize(input_dicts, MAX_OUTPUT_LENGTH)

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

    def _summarize_cls(self, cls_obj: dict) -> dict:
        '''
            Summarize for class/interface/enum according to its methods.
            methods in one class can be processed in batch.
        '''
        PROMPT = SUM_CLS['prompt'].format(cls_obj['type'])
        MAX_OUTPUT_LENGTH = SUM_CLS['max_output_length']

        ignore_method_count = 0
        context = cls_obj["signature"] + " {\n"

        # handle all methods
        method_nodes = self._summarize_methods(cls_obj["methods"])

        # concat summary of methods to context
        for idx, method_node in enumerate(method_nodes):
            tmp_str = f"\t{method_node['signature']};\n"

            if method_node['summary'] != NO_SUMMARY:
                tmp_str = f"\t{method_node['signature']}; // {method_node['summary']}\n"

            # ignore methods that exceed the token limit
            if not self._is_legal_input_text(f"{PROMPT}\n{INPUT_SEPARATOR}\n{context + tmp_str}", MAX_OUTPUT_LENGTH):
                ignore_method_count = len(method_nodes) - idx
                break

            context += tmp_str

        context += "}"

        input_text = self._build_input(
            cls_obj['id'], PROMPT, context, MAX_OUTPUT_LENGTH)
        summary = self._summarize(
            cls_obj['id'], input_text, MAX_OUTPUT_LENGTH)['output_text']

        self.logger.info(
            f"CLASS{LOG_SEPARATOR}\nNode ID: {cls_obj['id']}\nInput:\n{input_text}\nOutput:\n{summary}")
        if ignore_method_count != 0:
            self.logger.info(
                f"Number of ignored method: {ignore_method_count}")
        self.pbar.update(1)

        return {
            "id": cls_obj["id"],
            "name": cls_obj["name"],
            "summary": summary,
            "methods": method_nodes,
            "type": cls_obj["type"],
        }

    def _summarize_file(self, file_obj: dict) -> dict:
        '''
            Summarize for Java file according to its class / interface / enum.
        '''
        PROMPT = SUM_FILE['prompt']
        MAX_OUTPUT_LENGTH = SUM_FILE['max_output_length']

        valid_context_count = 0
        summary = NO_SUMMARY
        ignore_cls_count = 0
        input_text = ""
        context = f"File name: {file_obj['name']}.\n"

        # handle all classes/interfaces/enums
        cls_nodes = []
        for cls_obj in file_obj["classes"]:
            cls_nodes.append(self._summarize_cls(cls_obj))

        # concat summary of classes to context
        if len(cls_nodes) > 0:
            context += "The following is the class or interface or enum in the file and the corresponding summary:\n"

            for idx, cls_node in enumerate(cls_nodes):
                if cls_node['summary'] == NO_SUMMARY:
                    continue

                tmp_str = f"- The summary of Java {cls_node['type']} named {cls_node['name']}: {cls_node['summary']}\n"

                if not self._is_legal_input_text(f"{PROMPT}\n{INPUT_SEPARATOR}\n{context + tmp_str}", MAX_OUTPUT_LENGTH):
                    ignore_cls_count = len(cls_nodes) - idx
                    break

                valid_context_count += 1
                context += tmp_str

        if valid_context_count != 0:
            input_text = self._build_input(
                file_obj['id'], PROMPT, context, MAX_OUTPUT_LENGTH)
            summary = self._summarize(file_obj['id'], input_text, MAX_OUTPUT_LENGTH)[
                'output_text']

        self.logger.info(
            f"FILE{LOG_SEPARATOR}\nNode ID: {file_obj['id']}\nInput:\n{input_text}\nOutput:\n{summary}")
        if ignore_cls_count != 0:
            self.logger.info(f"Number of ignored class: {ignore_cls_count}")
        self.pbar.update(1)

        return {
            "id": file_obj["id"],
            "name": file_obj["name"],
            "summary": summary,
            "classes": cls_nodes,
            "path": file_obj["path"],
        }

    def _summarize_dir(self, dir_obj: dict) -> dict:
        '''
            Summarize for directory according to its subdirectories and files.
        '''
        PROMPT = SUM_DIR['prompt']
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
        input_text = ""
        context = f"Directory name: {dir_obj['name']}.\n"

        # handle all subdirectories recursively
        sub_dir_nodes = []
        for sub_dir_obj in dir_obj["subdirectories"]:
            sub_dir_nodes.append(self._summarize_dir(sub_dir_obj))

        # concat summary of subdirectories to context
        if len(sub_dir_nodes) > 0:
            context += "The following is the subdirectory in the directory and the corresponding summary:\n"

            for idx, sub_dir_node in enumerate(sub_dir_nodes):
                if sub_dir_node['summary'] == NO_SUMMARY:
                    continue

                tmp_str = f"- The summary of directory named {sub_dir_node['name']}: {sub_dir_node['summary']}\n"

                if not self._is_legal_input_text(f"{PROMPT}\n{INPUT_SEPARATOR}\n{context + tmp_str}", MAX_OUTPUT_LENGTH):
                    # the progress bar may be updated incorrectly due to the omission of some nodes
                    ignore_sub_dir_count = len(sub_dir_nodes) - idx
                    break

                valid_context_count += 1
                context += tmp_str

        # handle all files
        file_nodes = []
        for file_obj in dir_obj["files"]:
            file_nodes.append(self._summarize_file(file_obj))

        # concat summary of files to context
        if len(file_nodes) > 0:
            context += "The following is the file in the directory and the corresponding summary:\n"

            for idx, file_node in enumerate(file_nodes):
                if file_node['summary'] == NO_SUMMARY:
                    continue

                tmp_str = f"- The summary of file named {file_node['name']}: {file_node['summary']}\n"

                if not self._is_legal_input_text(f"{PROMPT}\n{INPUT_SEPARATOR}\n{context + tmp_str}", MAX_OUTPUT_LENGTH):
                    ignore_file_count = len(file_nodes) - idx
                    break

                valid_context_count += 1
                context += tmp_str

        if valid_context_count != 0:
            input_text = self._build_input(
                dir_obj['id'], PROMPT, context, MAX_OUTPUT_LENGTH)
            summary = self._summarize(dir_obj['id'], input_text, MAX_OUTPUT_LENGTH)[
                'output_text']

        self.logger.info(
            f"DIRECTORY{LOG_SEPARATOR}\nNode ID: {dir_obj['id']}\nInput:\n{input_text}\nOutput:\n{summary}")
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
            "path": dir_obj["path"],
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
            self.logger.info(
                f"Summarization time cost: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")

            return result
