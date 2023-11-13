import logging
import os
from typing import Tuple
from tqdm import tqdm
from transformers import CodeLlamaTokenizer

from ie_client import IEClient


NO_SUMMARY = "*** No enough context for summarization ***"
SEPARATOR = "======================================================"


class Summarizer:
    sum_logs = []

    def __init__(self, logger: logging.Logger, ie_client: IEClient):
        self.logger = logger

        self.SPECIAL_TOKEN_NUM = 5
        self.MAX_INPUT_TOKEN_NUM = 4096 - self.SPECIAL_TOKEN_NUM

        self.tokenizer = CodeLlamaTokenizer.from_pretrained(
            "codellama/CodeLlama-13b-Instruct-hf")

        self.ie_client = ie_client

    def generate_summary(self, input_text: str) -> str:
        '''
            get summary through API calls.
        '''

        return self.ie_client.generate(input_text)

    def isLegalInputText(self, input_text: str):
        '''
            check if the input text is legal, excluding special tokens
        '''

        encoded = self.tokenizer.encode(
            input_text, add_special_tokens=False, padding=False, truncation=False)

        return len(encoded) <= self.MAX_INPUT_TOKEN_NUM

    def build_input(self, prompt: str, context: str) -> str:
        '''
            add special tokens, truncate if exceeds the token limit
        '''

        input_text = f"{prompt}\n{SEPARATOR}\n{context}"

        if not self.isLegalInputText(input_text):
            encoded = self.tokenizer.encode(
                input_text,
                add_special_tokens=False,
                padding=False, truncation=True,
                max_length=self.MAX_INPUT_TOKEN_NUM  # max length don't include special tokens
            )

            input_text = self.tokenizer.decode(
                encoded, skip_special_tokens=False)

        return f"<s>[INST] {input_text} [/INST]"

    def summarize_method(self, method_json) -> str:
        '''
            generate summary for method.
        '''
        PROMPT = "Summarize the method below in about 50 words"

        context = method_json["signature"] + method_json["body"]

        input_text = self.build_input(PROMPT, context)
        summary = self.generate_summary(input_text)

        self.sum_logs.append(
            f"METHOD{SEPARATOR}\n{summary}\n<=\n{input_text}"
        )
        self.pbar.update(1)

        return summary

    def summarize_cls(self, cls_json) -> str:
        '''
            generate summary for class/interface/enum according to its methods.
        '''
        PROMPT = f"Summarize the Java {cls_json['type']} below in about 50 words"

        input_text = ""
        summary = NO_SUMMARY
        ignore_log = ""

        if len(cls_json["methods"]) > 0:
            context = cls_json["signature"] + " {\n"

            for idx, method_json in enumerate(cls_json["methods"]):
                method_sum = self.summarize_method(method_json)
                tmp_str = f"\t{method_json['signature']}; // {method_sum}\n"

                # ignore methods that exceed the token limit
                if not self.isLegalInputText(f"{PROMPT}\n{SEPARATOR}\n{context + tmp_str}"):
                    # the progress bar may be updated incorrectly due to the omission of some nodes

                    ignore_log += f"Number of ignored method: {str(len(cls_json['methods']) - idx)}\n"
                    break

                context += tmp_str

            context += "}"

            input_text = self.build_input(PROMPT, context)
            summary = self.generate_summary(input_text)

        self.sum_logs.append(
            f"CLASS{SEPARATOR}\n{summary}\n<=\n{input_text}\n{ignore_log}")
        self.pbar.update(1)

        return summary

    def summarize_file(self, file_json) -> dict:
        '''
            generate summary for Java file according to its class / interface / enum.
        '''
        PROMPT = "Summarize the Java file below in about 50 words"

        valid_context_num = 0  # number of valid context
        summary = NO_SUMMARY
        ignore_log = ""
        input_text = ""
        context = f"File name: {file_json['name']}.\n"

        if len(file_json["classes"]) > 0:
            context += "The following is the class or interface or enum in the file and the corresponding summary:\n"

            for idx, cls_json in enumerate(file_json["classes"]):
                cls_sum = self.summarize_cls(cls_json)

                if cls_sum == NO_SUMMARY:
                    continue

                tmp_str = f"{valid_context_num + 1}. The summary of Java {cls_json['type']} named {cls_json['name']}: {cls_sum}\n"

                if not self.isLegalInputText(f"{PROMPT}\n{SEPARATOR}\n{context + tmp_str}"):
                    # the progress bar may be updated incorrectly due to the omission of some nodes

                    ignore_log += f"Number of ignored class: {str(len(file_json['classes']) - idx)}\n"
                    break

                valid_context_num += 1
                context += tmp_str

        if valid_context_num != 0:
            input_text = self.build_input(PROMPT, context)
            summary = self.generate_summary(input_text)

        self.sum_logs.append(
            f"FILE{SEPARATOR}\n{summary}\n<=\n{input_text}\n{ignore_log}")
        self.pbar.update(1)

        return {
            "name": file_json["name"],
            "summary": summary,
        }

    def summarize_dir(self, dir_json) -> dict:
        '''
            generate summary for directory according to its subdirectories and files.
        '''
        PROMPT = "Summarize the directory below in about 50 words"

        # if current directory only has one subdirectory(no file),
        # concat directory name, only generate one node.
        if (len(dir_json["subDirectories"]) == 1 and len(dir_json["files"]) == 0):
            child_dir_json = dir_json['subDirectories'][0]
            child_dir_json['name'] = f"{dir_json['name']}/{child_dir_json['name']}"
            return self.summarize_dir(child_dir_json)

        valid_context_num = 0  # number of valid context
        summary = NO_SUMMARY
        ignore_log = ""
        input_text = ""
        context = f"Directory name: {dir_json['name']}.\n"

        # handle subdirectories recursively
        sub_dir_nodes = []
        for sub_dir_json in dir_json["subDirectories"]:
            sub_dir_nodes.append(self.summarize_dir(sub_dir_json))

        # part of subdirectories
        if len(sub_dir_nodes) > 0:
            context += "The following is the subdirectory in the directory and the corresponding summary:\n"

            for idx, sub_dir_node in enumerate(sub_dir_nodes):
                if sub_dir_node['summary'] == NO_SUMMARY:
                    continue

                tmp_str = f"{valid_context_num + 1}. The summary of directory named {sub_dir_node['name']}: {sub_dir_node['summary']}\n"

                if not self.isLegalInputText(f"{PROMPT}\n{SEPARATOR}\n{context + tmp_str}"):
                    # the progress bar may be updated incorrectly due to the omission of some nodes

                    ignore_log += f"Number of ignored subdirectory: {str(len(sub_dir_nodes) - idx)}\n"
                    break

                valid_context_num += 1
                context += tmp_str

        # part of files
        file_nodes = []
        if len(dir_json["files"]) > 0:
            context += "The following is the file in the directory and the corresponding summary:\n"

            for idx, file_json in enumerate(dir_json["files"]):
                file_node = self.summarize_file(file_json)
                file_nodes.append(file_node)

                if file_node['summary'] == NO_SUMMARY:
                    continue

                tmp_str = f"{valid_context_num + 1}. The summary of file named {file_node['name']}: {file_node['summary']}\n"

                if not self.isLegalInputText(f"{PROMPT}\n{SEPARATOR}\n{context + tmp_str}"):
                    # the progress bar may be updated incorrectly due to the omission of some nodes

                    ignore_log += f"Number of ignored file: {str(len(dir_json['files']) - idx)}\n"
                    break

                valid_context_num += 1
                context += tmp_str

        if valid_context_num != 0:
            input_text = self.build_input(PROMPT, context)
            summary = self.generate_summary(input_text)

        self.sum_logs.append(
            f"DIRECTORY{SEPARATOR}\n{summary}\n<=\n{input_text}\n{ignore_log}")
        self.pbar.update(1)

        return {
            "name": dir_json["name"],
            "summary": summary,
            "subDirectories": sub_dir_nodes,
            "files": file_nodes
        }

    def summarize_repo(self, repo_json) -> Tuple[list, dict]:
        with tqdm(total=repo_json['nodeCount']) as pbar:
            pbar.set_description("Summarizing repo({})".format(
                repo_json['mainDirectory']['path']))
            self.pbar = pbar

            return self.sum_logs, self.summarize_dir(repo_json['mainDirectory'])
