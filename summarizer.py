from concurrent.futures import ThreadPoolExecutor
import logging
import time
from typing import List
from tqdm import tqdm
from transformers import CodeLlamaTokenizer

from ie_client import IEClient
from constants import GENERATION_FAILED, INPUT_SEPARATOR, INSUFFICIENT_CONTEXT, LOG_SEPARATOR


class Summarizer:
    def __init__(self, logger: logging.Logger, ie_client: IEClient):
        self.logger = logger
        self.tokenizer = CodeLlamaTokenizer.from_pretrained(
            ie_client.model_name)

        self.ie_client = ie_client
        self.gen_err_count = 0  # number of generation error

        self.SPECIAL_TOKEN_NUM = 5
        self.MAX_NUMBER_OF_TOKENS = ie_client.max_number_of_tokens

    def _is_legal_input_text(self, input_text: str, max_output_length: int) -> bool:
        '''
            Check if the input text is legal, excluding special tokens and max output length
        '''
        encoded = self.tokenizer.encode(
            input_text, add_special_tokens=False, padding=False, truncation=False)

        return len(encoded) <= self.MAX_NUMBER_OF_TOKENS - self.SPECIAL_TOKEN_NUM - max_output_length

    def _build_input(self, node_id: int, prompt: str, context: str, max_output_length: int) -> str:
        '''
            Concat promp and context, add special tokens, truncate if exceeds the token limit
        '''
        input_text = f"{prompt}\n{INPUT_SEPARATOR}\n{context}"

        if not self._is_legal_input_text(input_text, max_output_length):
            max_input_length = self.MAX_NUMBER_OF_TOKENS - \
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
                'output_text': GENERATION_FAILED
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

    def summarize_methods(self, method_objs: List[dict]) -> List[dict]:
        '''
            Generate for methods according to func body.
            method_objs: a list of method_obj
            return: a list of {id: int, input_text: str, output_text: str}
        '''
        PROMPT = "Summarize the Java method below in about 30 words."
        MAX_OUTPUT_LENGTH = 60

        if len(method_objs) == 0:
            return []

        input_dicts = []
        res_dicts = []

        for method_obj in method_objs:
            if method_obj["body"] != "":
                context = method_obj["signature"] + method_obj["body"]
                input_dicts.append({
                    'id': method_obj['id'],
                    'input_text': self._build_input(method_obj['id'], PROMPT, context, MAX_OUTPUT_LENGTH)
                })
            else:
                res_dicts.append({
                    'id': method_obj['id'],
                    'input_text': "",
                    'output_text': INSUFFICIENT_CONTEXT
                })
                self.logger.info(
                    f"METHOD{LOG_SEPARATOR}\nNode ID: {method_obj['id']}\nOutput:\n{INSUFFICIENT_CONTEXT}")

        output_dicts = self._batch_summarize(input_dicts, MAX_OUTPUT_LENGTH)

        for output in output_dicts:
            res_dicts.append(output)
            self.logger.info(
                f"METHOD{LOG_SEPARATOR}\nNode ID: {output['id']}\nInput:\n{output['input_text']}\nOutput:\n{output['output_text']}")

        self.pbar.update(len(method_objs))

        return res_dicts

    def summarize_cls(self, cls_obj: dict) -> str:
        '''
            generate summary for class/interface/enum according to its methods.
            methods in one class can be processed in batch.
        '''
        PROMPT = f"Summarize the Java {cls_obj['type']} below in about 50 words, don't include examples and details."
        MAX_OUTPUT_LENGTH = 100

        ignore_log = ""
        context = cls_obj["signature"] + " {\n"

        if len(cls_obj["methods"]) > 0:
            # process methods in batch
            bs = self.ie_client.max_batch_size
            method_objs = cls_obj["methods"]
            is_continue = True  # whether to continue generating batch of summary

            for idx in range(0, len(method_objs), bs):
                # get method_objs slice
                method_obj_slice = []
                if idx + bs > len(method_objs):
                    method_obj_slice = method_objs[idx:]
                else:
                    method_obj_slice = method_objs[idx: idx+bs]

                # get summary of methods
                output_dicts = self.summarize_methods(method_obj_slice)

                # concat summary to context
                for output_dict in output_dicts:
                    method_obj_idx = method_obj_slice.index(
                        next(filter(lambda x: x['id'] == output_dict['id'], method_obj_slice)))
                    method_obj = method_objs[method_obj_idx]

                    tmp_str = f"\t{method_obj['signature']};\n"

                    if output_dict['output_text'] != GENERATION_FAILED and output_dict['output_text'] != INSUFFICIENT_CONTEXT:
                        tmp_str = f"\t{method_obj['signature']}; // {output_dict['output_text']}\n"

                    # ignore methods that exceed the token limit
                    if not self._is_legal_input_text(f"{PROMPT}\n{INPUT_SEPARATOR}\n{context + tmp_str}", MAX_OUTPUT_LENGTH):
                        # the progress bar may be updated incorrectly due to the omission of some nodes
                        ignore_log = f"Number of ignored method: {str(len(method_objs) - method_obj_idx)}"
                        is_continue = False
                        break

                    context += tmp_str

                if not is_continue:
                    break

        context += "}"

        input_text = self._build_input(
            cls_obj['id'], PROMPT, context, MAX_OUTPUT_LENGTH)
        summary = self._summarize(
            cls_obj['id'], input_text, MAX_OUTPUT_LENGTH)['output_text']

        self.logger.info(
            f"CLASS{LOG_SEPARATOR}\nNode ID: {cls_obj['id']}\nInput:\n{input_text}\nOutput:\n{summary}")
        if ignore_log != "":
            self.logger.info(f"Ignore:\n{ignore_log}")
        self.pbar.update(1)

        return summary

    def summarize_file(self, file_obj: dict) -> dict:
        '''
            generate summary for Java file according to its class / interface / enum.
        '''
        PROMPT = "Summarize the file below in about 50 words, don't include examples and details."
        MAX_OUTPUT_LENGTH = 100

        valid_context_num = 0  # number of valid context
        summary = INSUFFICIENT_CONTEXT
        ignore_log = ""
        input_text = ""
        context = f"File name: {file_obj['name']}.\n"

        if len(file_obj["classes"]) > 0:
            context += "The following is the class or interface or enum in the file and the corresponding summary:\n"

            # concat summary to context
            for idx, cls_obj in enumerate(file_obj["classes"]):
                cls_sum = self.summarize_cls(cls_obj)
                if cls_sum == INSUFFICIENT_CONTEXT or cls_sum == GENERATION_FAILED:
                    continue

                tmp_str = f"- The summary of Java {cls_obj['type']} named {cls_obj['name']}: {cls_sum}\n"

                if not self._is_legal_input_text(f"{PROMPT}\n{INPUT_SEPARATOR}\n{context + tmp_str}", MAX_OUTPUT_LENGTH):
                    # the progress bar may be updated incorrectly due to the omission of some nodes
                    ignore_log = f"Number of ignored class: {str(len(file_obj['classes']) - idx)}"
                    break

                valid_context_num += 1
                context += tmp_str

        if valid_context_num != 0:
            input_text = self._build_input(
                file_obj['id'], PROMPT, context, MAX_OUTPUT_LENGTH)
            summary = self._summarize(file_obj['id'], input_text, MAX_OUTPUT_LENGTH)[
                'output_text']

        self.logger.info(
            f"FILE{LOG_SEPARATOR}\nNode ID: {file_obj['id']}\nInput:\n{input_text}\nOutput:\n{summary}")
        if ignore_log != "":
            self.logger.info(f"Ignore:\n{ignore_log}")
        self.pbar.update(1)

        return {
            "id": file_obj["id"],
            "name": file_obj["name"],
            "summary": summary,
            "path": file_obj["path"]
        }

    def summarize_dir(self, dir_obj: dict) -> dict:
        '''
            generate summary for directory according to its subdirectories and files.
        '''
        PROMPT = "Summarize the directory below in about 100 words, don't include examples and details."
        MAX_OUTPUT_LENGTH = 200

        # if current directory only has one subdirectory(no file),
        # concat directory name, only generate one node.
        if (len(dir_obj["subDirectories"]) == 1 and len(dir_obj["files"]) == 0):
            child_dir_obj = dir_obj['subDirectories'][0]
            child_dir_obj['name'] = f"{dir_obj['name']}/{child_dir_obj['name']}"
            return self.summarize_dir(child_dir_obj)

        valid_context_num = 0  # number of valid context
        summary = INSUFFICIENT_CONTEXT
        ignore_log = ""
        input_text = ""
        context = f"Directory name: {dir_obj['name']}.\n"

        # handle subdirectories recursively
        sub_dir_nodes = []
        for sub_dir_obj in dir_obj["subDirectories"]:
            sub_dir_nodes.append(self.summarize_dir(sub_dir_obj))

        # part of subdirectories
        if len(sub_dir_nodes) > 0:
            context += "The following is the subdirectory in the directory and the corresponding summary:\n"

            # concat summary to context
            for idx, sub_dir_node in enumerate(sub_dir_nodes):
                if sub_dir_node['summary'] == INSUFFICIENT_CONTEXT or sub_dir_node['summary'] == GENERATION_FAILED:
                    continue

                tmp_str = f"- The summary of directory named {sub_dir_node['name']}: {sub_dir_node['summary']}\n"

                if not self._is_legal_input_text(f"{PROMPT}\n{INPUT_SEPARATOR}\n{context + tmp_str}", MAX_OUTPUT_LENGTH):
                    # the progress bar may be updated incorrectly due to the omission of some nodes
                    ignore_log = f"Number of ignored subdirectory: {str(len(sub_dir_nodes) - idx)}"
                    break

                valid_context_num += 1
                context += tmp_str

        # part of files
        file_nodes = []
        if len(dir_obj["files"]) > 0:
            context += "The following is the file in the directory and the corresponding summary:\n"

            # concat summary to context
            for idx, file_obj in enumerate(dir_obj["files"]):
                file_node = self.summarize_file(file_obj)
                file_nodes.append(file_node)
                if file_node['summary'] == INSUFFICIENT_CONTEXT or file_node['summary'] == GENERATION_FAILED:
                    continue

                tmp_str = f"- The summary of file named {file_node['name']}: {file_node['summary']}\n"

                if not self._is_legal_input_text(f"{PROMPT}\n{INPUT_SEPARATOR}\n{context + tmp_str}", MAX_OUTPUT_LENGTH):
                    # the progress bar may be updated incorrectly due to the omission of some nodes
                    ignore_log = f"Number of ignored file: {str(len(dir_obj['files']) - idx)}"
                    break

                valid_context_num += 1
                context += tmp_str

        if valid_context_num != 0:
            input_text = self._build_input(
                dir_obj['id'], PROMPT, context, MAX_OUTPUT_LENGTH)
            summary = self._summarize(dir_obj['id'], input_text, MAX_OUTPUT_LENGTH)[
                'output_text']

        self.logger.info(
            f"DIRECTORY{LOG_SEPARATOR}\nNode ID: {dir_obj['id']}\nInput:\n{input_text}\nOutput:\n{summary}")
        if ignore_log != "":
            self.logger.info(f"Ignore:\n{ignore_log}")
        self.pbar.update(1)

        return {
            "id": dir_obj["id"],
            "name": dir_obj["name"],
            "summary": summary,
            "subDirectories": sub_dir_nodes,
            "files": file_nodes,
            "path": dir_obj["path"]
        }

    def summarize_repo(self, repo_obj: dict) -> dict:
        start_time = time.time()

        with tqdm(total=repo_obj['nodeCount']) as pbar:
            pbar.set_description("Summarizing repo...")
            self.pbar = pbar

            result = self.summarize_dir(repo_obj['mainDirectory'])

            self.logger.info(f"COMPLETION{LOG_SEPARATOR}")
            self.logger.info(
                f"Number of generation error: {self.gen_err_count}")
            self.logger.info(
                f"Summarization time cost: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")

            return result
