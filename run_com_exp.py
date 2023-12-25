'''
 * Copyright (c) 2023, salesforce.com, inc.
 * All rights reserved.
 * SPDX-License-Identifier: BSD-3-Clause
 * For full license text, see LICENSE.txt file in the repo root or https://opensource.org/licenses/BSD-3-Clause
 * By Yue Wang
'''
import argparse
import logging
import os
import time
import datetime
import json
import numpy as np
from tqdm import tqdm
import torch
from transformers import AutoTokenizer, AutoModel
from torch.utils.data import DataLoader, Dataset


class TextDataset(Dataset):
    def __init__(self, test_data_objs, code_data_objs):
        self.texts = []
        self.codes = []
        text2path = {}  # text idx -> path
        path2code = {}  # path -> code idx

        for idx, obj in enumerate(test_data_objs):
            self.texts.append(obj['query'])
            text2path[idx] = obj['path']

        for idx, obj in enumerate(code_data_objs):
            self.codes.append(obj['code'])
            path2code[obj['path']] = idx

        self.text2code = {}  # text idx -> code idx

        # TODO: function with same name
        for text_id, _ in enumerate(self.texts):
            self.text2code[text_id] = path2code[text2path[text_id]]

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, index):
        return self.texts[index]


class CodeDataset(Dataset):
    def __init__(self, code_data_objs):
        self.codes = [obj['code'] for obj in code_data_objs]

    def __len__(self):
        return len(self.codes)

    def __getitem__(self, index):
        return self.codes[index]


def create_dataset(test_data_objs, code_data_objs):
    test_dataset = TextDataset(test_data_objs, code_data_objs)
    codebase_dataset = CodeDataset(code_data_objs)

    return test_dataset, codebase_dataset


def create_dataloader(datasets, batch_size, num_worker):
    loaders = []
    for dataset in datasets:
        loader = DataLoader(
            dataset,
            batch_size=batch_size,
            num_workers=num_worker,
            pin_memory=True,
            shuffle=False,
            drop_last=False,
        )
        loaders.append(loader)
    return loaders


@torch.no_grad()
def get_feats(model, tokenizer, data_loader, max_length, device, modality='text'):
    text_ids = []
    text_embeds = []
    text_atts = []
    text_outputs = []

    for text in tqdm(data_loader, total=len(data_loader)):
        text_input = tokenizer(text, padding='max_length', truncation=True, max_length=max_length,
                               return_tensors="pt").to(device)
        text_output = model.encoder(text_input.input_ids, attention_mask=text_input.attention_mask,
                                    return_dict=True)
        text_embed = torch.nn.functional.normalize(
            model.proj(text_output.last_hidden_state[:, 0, :]), dim=-1)

        text_ids.append(text_input.input_ids)
        text_atts.append(text_input.attention_mask)
        text_embeds.append(text_embed)
        if modality == 'text':
            text_outputs.append(text_output.last_hidden_state.cpu())

    text_ids = torch.cat(text_ids, dim=0)
    text_atts = torch.cat(text_atts, dim=0)
    text_embeds = torch.cat(text_embeds, dim=0)
    if modality == 'text':
        text_outputs = torch.cat(text_outputs, dim=0)
    return text_ids, text_atts, text_embeds, text_outputs


def get_eos_vec(hidden_state, source_ids, eos_token_id):
    eos_mask = source_ids.eq(eos_token_id)
    if len(torch.unique(eos_mask.sum(1))) > 1:
        raise ValueError(
            "All examples must have the same number of <eos> tokens.")
    dec_vec = hidden_state[eos_mask, :].view(
        hidden_state.size(0), -1, hidden_state.size(-1))[:, -1, :]
    return dec_vec


@torch.no_grad()
def match_evaluation(model, text_feats, code_feats, tokenizer, device, top_k, img2txt):
    start_time = time.time()

    text_ids, text_atts, text_embeds, text_outputs = text_feats
    code_ids, code_atts, code_embeds, _ = code_feats
    code_ids[:, 0] = tokenizer.enc_token_id

    sims_matrix = text_embeds @ code_embeds.t()
    score_matrix_i2t = torch.full(
        (text_ids.size(0), code_ids.size(0)), -100.0).to(device)

    for i, sims in enumerate(tqdm(sims_matrix, desc=f'Evaluate text-code matching with top {top_k} candidates:')):
        topk_sim, topk_idx = sims.topk(k=top_k, dim=0)
        encoder_output = text_outputs[i].repeat(top_k, 1, 1).to(device)
        encoder_att = text_atts[i].repeat(top_k, 1).to(device)
        code_ids[:, 0] = tokenizer.enc_token_id
        output = model.decoder(code_ids[topk_idx],
                               attention_mask=code_atts[topk_idx],
                               encoder_hidden_states=encoder_output,
                               encoder_attention_mask=encoder_att,
                               return_dict=True,
                               )
        output_vec = get_eos_vec(
            output.last_hidden_state, code_ids[topk_idx], tokenizer.eos_token_id)
        score = model.itm_head(output_vec)[:, 1]
        score_matrix_i2t[i, topk_idx] = score + topk_sim

    total_time = time.time() - start_time
    total_time_str = str(datetime.timedelta(seconds=int(total_time)))
    print('Evaluation time {}'.format(total_time_str))

    scores_i2t = score_matrix_i2t.cpu().numpy()

    ranks = np.ones(scores_i2t.shape[0]) * -1
    for index, score in enumerate(scores_i2t):
        inds = np.argsort(score)[::-1]
        ranks[index] = np.where(inds == img2txt[index])[0][0]

    # Compute metrics
    tr1 = 100.0 * len(np.where(ranks < 1)[0]) / len(ranks)
    tr5 = 100.0 * len(np.where(ranks < 5)[0]) / len(ranks)
    tr10 = 100.0 * len(np.where(ranks < 10)[0]) / len(ranks)
    mrr = 100.0 * np.mean(1 / (ranks + 1))

    eval_result = {'r1': tr1,
                   'r5': tr5,
                   'r10': tr10,
                   'mrr': mrr}
    return eval_result


def get_code_data_objs(parse_out_path):
    def traverse_file(file_obj, path_arr):
        for method_obj in file_obj['methods']:
            path_arr.append(method_obj['name'])
            data_objs.append({
                'path': "/".join(path_arr),
                'code': method_obj['signature'] + method_obj['body']
            })
            path_arr.pop()

    def traverse_dir(dir_obj, path_arr):
        for sub_dir_obj in dir_obj['subdirectories']:
            path_arr.append(sub_dir_obj['name'])
            traverse_dir(sub_dir_obj, path_arr)
            path_arr.pop()

        for file_obj in dir_obj['files']:
            path_arr.append(file_obj['name'])
            traverse_file(file_obj, path_arr)
            path_arr.pop()

    data_objs = []
    with open(parse_out_path, "r") as f_parse_out:
        parse_obj = json.load(f_parse_out)
        # does not include repo name
        traverse_dir(parse_obj['mainDirectory'], [])

    return data_objs


def main(args):
    data_file_path = "./eval_data/filtered/data_final.jsonl"
    sum_result_root_path = "./eval_data/sum_result"

    logging.basicConfig(level=logging.INFO,
                        format='%(name)s - %(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%m/%d/%Y %H:%M:%S')
    pipeline_logger = logging.getLogger("pipeline")

    # split data for different repo
    data_dict = {}
    with open(data_file_path, "r") as f_data:
        data_objs = [json.loads(line) for line in f_data.readlines()]
        for data_obj in data_objs:
            repo_name = data_obj['repo'].split('/')[-1]
            if repo_name not in data_dict:
                data_dict[repo_name] = []
            data_dict[repo_name].append(data_obj)

    # load model
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_name, trust_remote_code=True)
    tokenizer.enc_token_id = tokenizer.convert_tokens_to_ids('[ENC]')
    model = AutoModel.from_pretrained(
        args.model_name, trust_remote_code=True)

    device = torch.device(args.device)
    model = model.to(device)
    model.eval()

    # calc recall for each repo
    for idx, repo_name in enumerate(data_dict):
        if idx != 3:
            continue

        test_data_objs = data_dict[repo_name]
        pipeline_logger.info(f"Start evaluating {idx}th repo: {repo_name}")

        # get code data objs from parse output
        parse_out_path = os.path.join(
            sum_result_root_path, repo_name, f"parse_out_{repo_name}.json")
        if not os.path.exists(parse_out_path):
            raise Exception("Parse output path does not exist.")
        code_data_objs = get_code_data_objs(parse_out_path)

        # load data
        test_dataset, code_dataset = create_dataset(
            test_data_objs, code_data_objs)
        test_loader, code_loader = create_dataloader(
            [test_dataset, code_dataset], args.batch_size, 4)

        # get feats
        text_feats = get_feats(model, tokenizer, test_loader,
                               args.max_text_len, device, modality='text')
        code_feats = get_feats(model, tokenizer, code_loader,
                               args.max_code_len, device, modality='code')

        # evaluate
        test_result = match_evaluation(model, text_feats, code_feats, tokenizer, device, args.top_k,
                                       test_loader.dataset.text2code)
        print(f'Test result of {repo_name}: {test_result}')

    logging.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--model_name', default='Salesforce/codet5p-220m-bimodal', type=str)
    parser.add_argument('--batch_size', default=256, type=int)
    parser.add_argument('--top_k', default=32, type=int)
    parser.add_argument('--max_text_len', default=128, type=int)
    parser.add_argument('--max_code_len', default=512, type=int)
    parser.add_argument('--device', default='mps', type=str)

    main(parser.parse_args())
