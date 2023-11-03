import logging
from typing import Tuple
import torch
from enum import Enum
from tqdm import tqdm
from transformers import (AutoTokenizer, T5Config,
                          T5ForConditionalGeneration, PegasusForConditionalGeneration)


class MODEL_TAG(Enum):
    CODE = "CODE"
    TEXT = "TEXT"


NO_SUMMARY = "*** No enough context for summarization ***"


class Summarizer:
    sum_logs = []

    model_dict = {
        MODEL_TAG.CODE: {
            "name": "Salesforce/codet5-base-multi-sum",
            "max_source_length": 512,
            "max_target_length": 30,  # TODO: choose a proper value
        },
        MODEL_TAG.TEXT: {
            "name": "google/pegasus-large",
            "max_source_length": 1024,
            "max_target_length": 100,  # TODO: choose a proper value
        },
    }

    def __init__(self, logger: logging.Logger):
        self.logger = logger

        # load models
        for tag, val in tqdm(self.model_dict.items(), desc="Loading models..."):
            if tag == MODEL_TAG.CODE:
                model_config = T5Config.from_pretrained(val["name"])
                model = T5ForConditionalGeneration.from_pretrained(
                    val["name"], config=model_config)
                tokenizer = AutoTokenizer.from_pretrained(val["name"])
            elif tag == MODEL_TAG.TEXT:
                model = PegasusForConditionalGeneration.from_pretrained(
                    val["name"])
                tokenizer = AutoTokenizer.from_pretrained(val["name"])

            model.eval()
            self.model_dict[tag]["model"] = model
            self.model_dict[tag]["tokenizer"] = tokenizer

    def isLegalSource(self, source, model_tag: MODEL_TAG):
        '''
            check if the number of tokens is legal
        '''

        model_obj = self.model_dict[model_tag]

        encoded = model_obj['tokenizer'].encode(
            source, add_special_tokens=True)
        return len(encoded) <= model_obj['max_source_length']

    def summarize_by_llm(self, source: str, model_tag: MODEL_TAG) -> str:
        model_obj = self.model_dict[model_tag]
        generated_text = ""

        encoded_code = model_obj['tokenizer'](source, return_tensors='pt',
                                              max_length=model_obj['max_source_length'],
                                              padding=True, verbose=False,
                                              add_special_tokens=True, truncation=True)

        generated_texts_ids = model_obj['model'].generate(input_ids=encoded_code['input_ids'],
                                                          attention_mask=encoded_code['attention_mask'],
                                                          max_length=model_obj['max_target_length'])

        generated_text = model_obj['tokenizer'].decode(generated_texts_ids[0],
                                                       skip_special_tokens=True, clean_up_tokenization_spaces=False)

        return generated_text

    def summarize_code_snippet(self, code_snippet_json) -> str:
        '''
            generate summarization for code snippet.
            if there is a placeholder <BLOCK>, replace it with the summarization of the corresponding code snippet
            TODO: design the content to replace <BLOCK>
        '''

        source = code_snippet_json["content"]
        summarization = ""

        # summarize the code snippet in order, and replace <BLOCK> in 'source'
        for code_snippet_json in code_snippet_json["codeSnippets"]:
            code_snippet_sum = self.summarize_code_snippet(code_snippet_json)
            source = source.replace(
                "<BLOCK>", "// TODO: " + code_snippet_sum + '\n', 1)

        summarization = self.summarize_by_llm(source, MODEL_TAG.CODE)

        self.sum_logs.append(
            "{}\n{}\n<=\n{}".format("CODE======================================================",
                                    summarization, source))
        self.pbar.update(1)

        return summarization

    def summarize_method(self, method_json) -> str:
        '''
            generate summarization for method.
            if there is a placeholder <BLOCK>, replace it with the summarization of the corresponding code snippet
            TODO: design the content to replace <BLOCK>
        '''

        source = method_json["signature"] + method_json["body"]
        summarization = ""

        # summarize the code snippet in order, and replace <BLOCK> in 'source'
        for code_snippet_json in method_json["codeSnippets"]:
            code_snippet_sum = self.summarize_code_snippet(code_snippet_json)
            source = source.replace(
                "<BLOCK>", "// TODO: " + code_snippet_sum + '\n', 1)

        summarization = self.summarize_by_llm(source, MODEL_TAG.CODE)

        self.sum_logs.append(
            "{}\n{}\n<=\n{}".format("METHOD======================================================",
                                    summarization, source))
        self.pbar.update(1)

        return summarization

    def summarize_cls(self, cls_json) -> str:
        '''
            generate summarization for class according to its methods.
            TODO: design the source content for summarization
        '''

        source = cls_json["signature"]
        summarization = NO_SUMMARY
        ignore_log = ""

        if len(cls_json["methods"]) > 0:
            source += " {\n"

            for idx, method_json in enumerate(cls_json["methods"]):
                method_sum = self.summarize_method(method_json)
                tmp_str = "\t" + method_json["signature"] + \
                    "; // " + method_sum + "\n"

                # ignore methods that exceed the token limit
                if not self.isLegalSource(source + tmp_str, MODEL_TAG.TEXT):
                    # the progress bar may be updated incorrectly due to the omission of some nodes

                    ignore_log += "\nNumber of ignored method: " + \
                        str(len(cls_json["methods"]) - idx)
                    break

                source += tmp_str

            source += "}"

            summarization = self.summarize_by_llm(source, MODEL_TAG.TEXT)

        self.sum_logs.append(
            "{}\n{}\n<=\n{}".format("CLASS======================================================",
                                    summarization, source) + ignore_log)

        self.pbar.update(1)

        return summarization

    def summarize_file(self, file_json) -> dict:
        '''
            generate summarization for file according to its classes(class / interface / enum).
            TODO: design the source content for summarization
        '''

        valid_context_num = 0  # number of valid context

        summarization = NO_SUMMARY
        ignore_log = ""
        source = 'File: ' + file_json['name'] + '\n'

        if len(file_json["classes"]) > 0:
            source += '\nClasses or Interfaces or Enums: \n'

        for idx, cls_json in enumerate(file_json["classes"]):
            cls_sum = self.summarize_cls(cls_json)

            if cls_sum == NO_SUMMARY:
                continue

            tmp_str = 'The Class named ' + cls_json['name'] + \
                'is mainly responsible for: ' + cls_sum + '\n'

            if not self.isLegalSource(source + tmp_str, MODEL_TAG.TEXT):
                # the progress bar may be updated incorrectly due to the omission of some nodes

                ignore_log += "\nNumber of ignored class: " + \
                    str(len(file_json["classes"]) - idx)
                break

            valid_context_num += 1
            source += tmp_str

        if valid_context_num != 0:
            summarization = self.summarize_by_llm(source, MODEL_TAG.TEXT)

        self.sum_logs.append("{}\n{}\n<=\n{}".format("FILE======================================================",
                                                     summarization, source) + ignore_log)
        self.pbar.update(1)

        return {
            "name": file_json["name"],
            "summarization": summarization,
        }

    def summarize_dir(self, dir_json) -> dict:
        '''
            generate summarization for directory according to its subdirectories and files.
            TODO: design the source content for summarization
        '''

        valid_context_num = 0  # number of valid context

        # handle subdirectories recursively
        sub_dir_nodes = []
        for sub_dir_json in dir_json["subDirectories"]:
            sub_dir_nodes.append(self.summarize_dir(sub_dir_json))

        summarization = NO_SUMMARY
        ignore_log = ""
        source = 'Directory: ' + dir_json['name'] + '\n'

        # part of subdirectories
        if len(sub_dir_nodes) > 0:
            source += '\nSubdirectories: \n'

        for idx, sub_dir_node in enumerate(sub_dir_nodes):
            if sub_dir_node['summarization'] == NO_SUMMARY:
                continue

            tmp_str = 'The subdirectory named ' + sub_dir_node['name'] + \
                'is mainly responsible for: ' + \
                sub_dir_node['summarization'] + '\n'

            # ignore subdirectories that exceeds the character limit
            if not self.isLegalSource(source + tmp_str, MODEL_TAG.TEXT):
                ignore_log += "\nNumber of ignored subdirectory: " + \
                    str(len(sub_dir_nodes) - idx)
                break

            valid_context_num += 1
            source += tmp_str

        # part of files
        if len(dir_json["files"]) > 0:
            source += '\nFiles: \n'

        file_nodes = []
        for idx, file_json in enumerate(dir_json["files"]):
            file_node = self.summarize_file(file_json)
            file_nodes.append(file_node)

            if file_node['summarization'] == NO_SUMMARY:
                continue

            tmp_str = 'The file named ' + file_node['name'] + \
                'is mainly responsible for: ' + \
                file_node['summarization'] + '\n'

            # ignore files that exceeds the character limit
            if not self.isLegalSource(source + tmp_str, MODEL_TAG.TEXT):
                # the progress bar may be updated incorrectly due to the omission of some nodes

                ignore_log += "\nNumber of ignored file: " + \
                    str(len(dir_json["files"]) - idx)
                break

            valid_context_num += 1
            source += tmp_str

        if valid_context_num != 0:
            summarization = self.summarize_by_llm(source, MODEL_TAG.TEXT)

        self.sum_logs.append("{}\n{}\n<=\n{}".format("DIRECTORY======================================================",
                                                     summarization, source) + ignore_log)
        self.pbar.update(1)

        return {
            "name": dir_json["name"],
            "summarization": summarization,
            "subDirectories": sub_dir_nodes,
            "files": file_nodes
        }

    def summarize_repo(self, repo_json) -> Tuple[list, dict]:
        with tqdm(total=repo_json['nodeCount']) as pbar:
            pbar.set_description("Summarizing repo({})".format(
                repo_json['mainDirectory']['path']))
            self.pbar = pbar

            return self.sum_logs, self.summarize_dir(repo_json['mainDirectory'])
