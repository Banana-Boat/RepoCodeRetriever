import logging
import time
from tqdm import tqdm
from transformers import CodeLlamaTokenizer

from ie_client import IEClient


NO_SUMMARY = "*** Not enough context for summarization ***"
ERROR_SUMMARY = "*** Error occurred during summarization ***"
SEPARATOR = "######################################################"
LOG_SEPARATOR = "============================================================================================================"


class Summarizer:
    def __init__(self, logger: logging.Logger, ie_client: IEClient):
        self.logger = logger
        self.ie_client = ie_client

        self.SPECIAL_TOKEN_NUM = 5
        self.MAX_INPUT_TOKEN_NUM = ie_client.max_input_length - self.SPECIAL_TOKEN_NUM

        self.tokenizer = CodeLlamaTokenizer.from_pretrained(
            ie_client.model_name)

    def generate_summary(self, input_text: str, max_output_length: int) -> str:
        '''
            get summary through API calls.
        '''
        try:
            return self.ie_client.generate(input_text, max_output_length)
        except Exception as e:
            self.logger.error(f"Failed to generate summary: {e}")
            return ERROR_SUMMARY

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

            truncated_input_text = self.tokenizer.decode(
                encoded, skip_special_tokens=False)
            self.logger.warning(
                f"Input text exceeds the token limit, truncates from:\n{input_text}\nto:\n{truncated_input_text}")

            input_text = truncated_input_text

        return f"<s>[INST] {input_text} [/INST]"

    def summarize_method(self, method_obj) -> str:
        '''
            generate summary for method according to func body.
        '''
        PROMPT = "Summarize the method below in about 30 words."

        summary = NO_SUMMARY
        input_text = ""

        if method_obj["body"] != "":
            context = method_obj["signature"] + method_obj["body"]
            input_text = self.build_input(PROMPT, context)
            summary = self.generate_summary(input_text, 60)

            self.logger.info(
                f"Input:\n{input_text}\nOutput:\n{summary}\nMETHOD{LOG_SEPARATOR}\n")

        self.pbar.update(1)

        return summary

    def summarize_cls(self, cls_obj) -> str:
        '''
            generate summary for class/interface/enum according to its methods.
        '''
        PROMPT = f"Summarize the Java {cls_obj['type']} below in about 50 words, don't include examples and details."

        ignore_log = ""
        context = cls_obj["signature"] + " {\n"

        for idx, method_obj in enumerate(cls_obj["methods"]):
            tmp_str = f"\t{method_obj['signature']};\n"

            method_sum = self.summarize_method(method_obj)
            if method_sum != ERROR_SUMMARY and method_sum != NO_SUMMARY:
                tmp_str = f"\t{method_obj['signature']}; // {method_sum}\n"

            # ignore methods that exceed the token limit
            if not self.isLegalInputText(f"{PROMPT}\n{SEPARATOR}\n{context + tmp_str}"):
                # the progress bar may be updated incorrectly due to the omission of some nodes
                ignore_log += f"Number of ignored method: {str(len(cls_obj['methods']) - idx)}\n"
                break

            context += tmp_str

        context += "}"

        input_text = self.build_input(PROMPT, context)
        summary = self.generate_summary(input_text, 100)

        self.logger.info(f"Input:\n{input_text}\nOutput:\n{summary}")
        if ignore_log != "":
            self.logger.info(f"Ignore:\n{ignore_log}")
        self.logger.info(f"CLASS{LOG_SEPARATOR}\n")
        self.pbar.update(1)

        return summary

    def summarize_file(self, file_obj) -> dict:
        '''
            generate summary for Java file according to its class / interface / enum.
        '''
        PROMPT = "Summarize the Java file below in about 50 words, don't include examples and details."

        valid_context_num = 0  # number of valid context
        summary = NO_SUMMARY
        ignore_log = ""
        input_text = ""
        context = f"File name: {file_obj['name']}.\n"

        if len(file_obj["classes"]) > 0:
            context += "The following is the class or interface or enum in the file and the corresponding summary:\n"

            for idx, cls_obj in enumerate(file_obj["classes"]):
                cls_sum = self.summarize_cls(cls_obj)
                if cls_sum == NO_SUMMARY or cls_sum == ERROR_SUMMARY:
                    continue

                tmp_str = f"\t- The summary of Java {cls_obj['type']} named {cls_obj['name']}: {cls_sum}\n"

                if not self.isLegalInputText(f"{PROMPT}\n{SEPARATOR}\n{context + tmp_str}"):
                    # the progress bar may be updated incorrectly due to the omission of some nodes
                    ignore_log += f"Number of ignored class: {str(len(file_obj['classes']) - idx)}\n"
                    break

                valid_context_num += 1
                context += tmp_str

        if valid_context_num != 0:
            input_text = self.build_input(PROMPT, context)
            summary = self.generate_summary(input_text, 100)

        self.logger.info(f"Input:\n{input_text}\nOutput:\n{summary}")
        if ignore_log != "":
            self.logger.info(f"Ignore:\n{ignore_log}")
        self.logger.info(f"FILE{LOG_SEPARATOR}\n")
        self.pbar.update(1)

        return {
            "name": file_obj["name"],
            "summary": summary,
        }

    def summarize_dir(self, dir_obj) -> dict:
        '''
            generate summary for directory according to its subdirectories and files.
        '''
        PROMPT = "Summarize the directory below in about 100 words, don't include examples and details."

        # if current directory only has one subdirectory(no file),
        # concat directory name, only generate one node.
        if (len(dir_obj["subDirectories"]) == 1 and len(dir_obj["files"]) == 0):
            child_dir_obj = dir_obj['subDirectories'][0]
            child_dir_obj['name'] = f"{dir_obj['name']}/{child_dir_obj['name']}"
            return self.summarize_dir(child_dir_obj)

        valid_context_num = 0  # number of valid context
        summary = NO_SUMMARY
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

            for idx, sub_dir_node in enumerate(sub_dir_nodes):
                if sub_dir_node['summary'] == NO_SUMMARY or sub_dir_node['summary'] == ERROR_SUMMARY:
                    continue

                tmp_str = f"\t- The summary of directory named {sub_dir_node['name']}: {sub_dir_node['summary']}\n"

                if not self.isLegalInputText(f"{PROMPT}\n{SEPARATOR}\n{context + tmp_str}"):
                    # the progress bar may be updated incorrectly due to the omission of some nodes
                    ignore_log += f"Number of ignored subdirectory: {str(len(sub_dir_nodes) - idx)}\n"
                    break

                valid_context_num += 1
                context += tmp_str

        # part of files
        file_nodes = []
        if len(dir_obj["files"]) > 0:
            context += "The following is the file in the directory and the corresponding summary:\n"

            for idx, file_obj in enumerate(dir_obj["files"]):
                file_node = self.summarize_file(file_obj)
                file_nodes.append(file_node)
                if file_node['summary'] == NO_SUMMARY or file_node['summary'] == ERROR_SUMMARY:
                    continue

                tmp_str = f"\t- The summary of file named {file_node['name']}: {file_node['summary']}\n"

                if not self.isLegalInputText(f"{PROMPT}\n{SEPARATOR}\n{context + tmp_str}"):
                    # the progress bar may be updated incorrectly due to the omission of some nodes
                    ignore_log += f"Number of ignored file: {str(len(dir_obj['files']) - idx)}\n"
                    break

                valid_context_num += 1
                context += tmp_str

        if valid_context_num != 0:
            input_text = self.build_input(PROMPT, context)
            summary = self.generate_summary(input_text, 200)

        self.logger.info(f"Input:\n{input_text}\nOutput:\n{summary}")
        if ignore_log != "":
            self.logger.info(f"Ignore:\n{ignore_log}")
        self.logger.info(f"DIRECTORY{LOG_SEPARATOR}\n")
        self.pbar.update(1)

        return {
            "name": dir_obj["name"],
            "summary": summary,
            "subDirectories": sub_dir_nodes,
            "files": file_nodes
        }

    def summarize_repo(self, repo_obj) -> dict:
        start_time = time.time()

        with tqdm(total=repo_obj['nodeCount']) as pbar:
            pbar.set_description("Summarizing repo...")
            self.pbar = pbar

            result = self.summarize_dir(repo_obj['mainDirectory'])

            self.logger.info(
                f"Time cost: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))}")

            return result
