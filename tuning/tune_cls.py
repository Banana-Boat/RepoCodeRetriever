# coding=utf-8
# Copyright 2018 The Google AI Language Team Authors and The HuggingFace Inc. team.
# Copyright (c) 2018, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import absolute_import
import datetime
import os
import time

import torch
import random
import logging
import argparse
import numpy as np
from io import open
from tqdm import tqdm
from torch.utils.data import DataLoader, SequentialSampler, RandomSampler, TensorDataset
from torch.utils.data.distributed import DistributedSampler
from transformers import (AdamW, get_linear_schedule_with_warmup,
                          AutoTokenizer, T5ForConditionalGeneration)

import bleu
from utils import read_examples, convert_examples_to_features, get_elapse_time


def set_seed(seed=42):
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True


def read_arguments():
    parser = argparse.ArgumentParser()

    # path
    parser.add_argument("--log_dir", default="./log", type=str, required=False)
    parser.add_argument("--output_dir", default="./model", type=str, required=False,
                        help="The output directory where the model predictions and checkpoints will be written.")
    parser.add_argument("--data_dir", default="./data", type=str)
    parser.add_argument("--load_model_path", type=str,
                        help="Path to trained model: Should contain the .bin files")

    # training
    parser.add_argument("--num_train_epochs", default=24, type=int,
                        help="Total number of training epochs to perform.")
    parser.add_argument("--train_batch_size", default=22, type=int,
                        help="Batch size per GPU/CPU for training.")
    parser.add_argument("--eval_batch_size", default=11, type=int,
                        help="Batch size per GPU/CPU for evaluation.")
    parser.add_argument("--max_source_length", default=512, type=int,
                        help="The maximum total source sequence length after tokenization. Sequences longer "
                             "than this will be truncated, sequences shorter will be padded.")
    parser.add_argument("--max_target_length", default=50, type=int,
                        help="The maximum total target sequence length after tokenization. Sequences longer "
                             "than this will be truncated, sequences shorter will be padded.")

    parser.add_argument('--gradient_accumulation_steps', type=int, default=2,
                        help="Number of updates steps to accumulate before performing a backward/update pass.")
    parser.add_argument("--warm_up_ratio", default=0.1, type=float)
    parser.add_argument("--learning_rate", default=5e-5, type=float,
                        help="The initial learning rate for Adam.")
    parser.add_argument("--weight_decay", default=0.0, type=float,
                        help="Weight decay if we apply some.")
    parser.add_argument("--adam_epsilon", default=1e-8, type=float,
                        help="Epsilon for Adam optimizer.")
    parser.add_argument('--early_stop_threshold', type=int, default=8)
    parser.add_argument('--seed', type=int, default=42,
                        help="random seed for initialization")

    # gpu
    parser.add_argument('--visible_gpu', type=str, default="0",
                        help="gpu number")
    parser.add_argument("--local_rank", type=int, default=-1,
                        help="For distributed training: local_rank")

    # task
    parser.add_argument("--do_train", action='store_true', default=True,
                        help="Whether to run training.")
    parser.add_argument("--do_eval", action='store_true', default=True,
                        help="Whether to run eval on the dev set.")
    parser.add_argument("--do_test", action='store_true', default=True,
                        help="Whether to run eval on the dev set.")

    args = parser.parse_args()

    return args


def main(args):
    set_seed(args.seed)
    model_name = "Salesforce/codet5p-770m"
    # data path
    train_filename = args.data_dir + "/train_cls.jsonl"
    dev_filename = args.data_dir + "/valid_cls.jsonl"
    test_filename = args.data_dir + "/test_cls.jsonl"

    # Setup CUDA, GPU & distributed training
    os.environ["CUDA_VISIBLE_DEVICES"] = args.visible_gpu

    if args.local_rank == -1:
        device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")
        args.n_gpu = torch.cuda.device_count()
    # Initializes the distributed backend which will take care of synchronizing nodes/GPUs
    else:
        torch.cuda.set_device(args.local_rank)
        device = torch.device("cuda", args.local_rank)
        torch.distributed.init_process_group(backend='nccl')
        args.n_gpu = 1

    logger.info("Model_name: %s, device: %s, process rank: %s, n_gpu: %s, distributed training: %s",
                model_name, device, args.local_rank, args.n_gpu, bool(args.local_rank != -1))

    args.device = device

    # make dir if output_dir not exist
    if os.path.exists(args.output_dir) is False:
        os.makedirs(args.output_dir)

    # read model --------------------------------------------------------------
    model = T5ForConditionalGeneration.from_pretrained(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    if args.load_model_path is not None:
        logger.info("reload model from {}".format(args.load_model_path))
        model.load_state_dict(torch.load(os.path.join(
            args.load_model_path, 'pytorch_model.bin')))

    model.to(device)

    # parallel or distribute setting
    if args.local_rank != -1:
        # Distributed training
        try:
            # from apex.parallel import DistributedDataParallel as DDP
            from torch.nn.parallel import DistributedDataParallel as DDP
        except ImportError:
            raise ImportError(
                "Please install apex from https://www.github.com/nvidia/apex to use distributed and fp16 training.")

        model = DDP(model)
    elif args.n_gpu > 1:
        # multi-gpu training
        model = torch.nn.DataParallel(model)

    # train part --------------------------------------------------------------
    if args.do_train:
        # Prepare training data loader
        train_examples = read_examples(train_filename, args)
        logger.info("Total {} training instances ".format(len(train_examples)))
        train_features = convert_examples_to_features(
            train_examples, tokenizer, args, stage='train')

        all_source_ids = train_features['source_ids']
        all_source_mask = train_features['source_mask']
        all_target_ids = train_features['target_ids']
        all_target_mask = train_features['target_mask']

        train_data = TensorDataset(
            all_source_ids, all_source_mask, all_target_ids, all_target_mask)

        if args.local_rank == -1:
            train_sampler = RandomSampler(train_data)
        else:
            train_sampler = DistributedSampler(train_data)

        train_dataloader = DataLoader(train_data, sampler=train_sampler,
                                      batch_size=args.train_batch_size // args.gradient_accumulation_steps,
                                      num_workers=2)

        # Prepare optimizer and schedule (linear warmup and decay)
        no_decay = ['bias', 'LayerNorm.weight']
        optimizer_grouped_parameters = [
            {'params': [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)],
             'weight_decay': args.weight_decay},
            {'params': [p for n, p in model.named_parameters() if any(
                nd in n for nd in no_decay)], 'weight_decay': 0.0}
        ]
        t_total = (len(train_dataloader) //
                   args.gradient_accumulation_steps) * args.num_train_epochs
        optimizer = AdamW(optimizer_grouped_parameters,
                          lr=args.learning_rate, eps=args.adam_epsilon)
        scheduler = get_linear_schedule_with_warmup(optimizer,
                                                    num_warmup_steps=int(
                                                        t_total * args.warm_up_ratio),
                                                    num_training_steps=t_total)

        # Start training
        logger.info("***** Running training *****")
        logger.info("  Num examples = %d", len(train_examples))
        logger.info("  Batch size = %d", args.train_batch_size)
        logger.info("  Num epoch = %d", args.num_train_epochs)

        # used to save tokenized data
        dev_dataset = {}
        nb_tr_examples, nb_tr_steps, global_step, best_bleu, best_loss = 0, 0, 0, 0, 1e6
        early_stop_threshold = args.early_stop_threshold

        early_stop_count = 0
        for epoch in range(args.num_train_epochs):

            model.train()
            tr_loss = 0.0
            train_loss = 0.0

            # progress bar
            bar = tqdm(train_dataloader, total=len(train_dataloader))

            for batch in bar:
                batch = tuple(t.to(device) for t in batch)
                source_ids, source_mask, target_ids, target_mask = batch

                labels = [
                    [(label if label != tokenizer.pad_token_id else -100) for label in labels_example] for
                    labels_example in target_ids
                ]
                labels = torch.tensor(labels).to(device)

                out = model(input_ids=source_ids,
                            attention_mask=source_mask, labels=labels)
                loss = out.loss

                if args.n_gpu > 1:
                    loss = loss.mean()  # mean() to average on multi-gpu.
                if args.gradient_accumulation_steps > 1:
                    loss = loss / args.gradient_accumulation_steps

                tr_loss += loss.item()
                train_loss = round(
                    tr_loss * args.gradient_accumulation_steps / (nb_tr_steps + 1), 4)
                bar.set_description(
                    "epoch {} loss {}".format(epoch, train_loss))

                nb_tr_examples += source_ids.size(0)
                nb_tr_steps += 1
                loss.backward()

                if nb_tr_steps % args.gradient_accumulation_steps == 0:
                    # Update parameters
                    optimizer.step()
                    optimizer.zero_grad()
                    scheduler.step()
                    global_step += 1

            # to help early stop
            this_epoch_best = False

            if args.do_eval:
                # Eval model with dev dataset
                nb_tr_examples, nb_tr_steps = 0, 0

                if 'dev_loss' in dev_dataset:
                    eval_examples, eval_data = dev_dataset['dev_loss']
                else:
                    eval_examples = read_examples(dev_filename, args)
                    eval_features = convert_examples_to_features(
                        eval_examples, tokenizer, args, stage='dev')

                    all_source_ids = eval_features['source_ids']
                    all_source_mask = eval_features['source_mask']
                    all_target_ids = eval_features['target_ids']
                    all_target_mask = eval_features['target_mask']

                    eval_data = TensorDataset(
                        all_source_ids, all_source_mask, all_target_ids, all_target_mask)
                    dev_dataset['dev_loss'] = eval_examples, eval_data

                eval_sampler = SequentialSampler(eval_data)
                eval_dataloader = DataLoader(eval_data, sampler=eval_sampler, batch_size=args.eval_batch_size,
                                             num_workers=2)

                logger.info("\n***** Running evaluation *****")
                logger.info("  Num examples = %d", len(eval_examples))
                logger.info("  Batch size = %d", args.eval_batch_size)

                # Start Evaluating model
                model.eval()
                eval_loss, tokens_num = 0, 0

                for batch in eval_dataloader:
                    batch = tuple(t.to(device) for t in batch)
                    source_ids, source_mask, target_ids, target_mask = batch

                    with torch.no_grad():
                        labels = [
                            [(label if label != tokenizer.pad_token_id else -100) for label in labels_example] for
                            labels_example in target_ids
                        ]
                        labels = torch.tensor(labels).to(device)

                        tokens_num += torch.tensor([(labels_example != -100).sum().item()
                                                   for labels_example in labels]).sum().item()

                        loss = model(
                            input_ids=source_ids, attention_mask=source_mask, labels=labels).loss

                    eval_loss += loss.sum().item()

                # print loss of dev dataset
                eval_loss = eval_loss/tokens_num
                result = {'epoch': epoch,
                          'eval_ppl': round(np.exp(eval_loss), 5),
                          'global_step': global_step + 1,
                          'train_loss': round(train_loss, 5)}

                for key in sorted(result.keys()):
                    logger.info("  %s = %s", key, str(result[key]))
                logger.info("  " + "*" * 20)

                # save last checkpoint
                last_output_dir = os.path.join(
                    args.output_dir, 'checkpoint-last')
                if not os.path.exists(last_output_dir):
                    os.makedirs(last_output_dir)

                # Only save the model it-self
                model_to_save = model.module if hasattr(
                    model, 'module') else model

                output_model_file = os.path.join(
                    last_output_dir, "pytorch_model.bin")
                torch.save(model_to_save.state_dict(), output_model_file)

                logger.info("Previous best ppl:%s",
                            round(np.exp(best_loss), 5))

                # save best checkpoint
                if eval_loss < best_loss:
                    this_epoch_best = True

                    logger.info("Achieve Best ppl:%s",
                                round(np.exp(eval_loss), 5))
                    logger.info("  " + "*" * 20)
                    best_loss = eval_loss
                    # Save best checkpoint for best ppl
                    output_dir = os.path.join(
                        args.output_dir, 'checkpoint-best-ppl')
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    output_model_file = os.path.join(
                        output_dir, "pytorch_model.bin")
                    torch.save(model_to_save.state_dict(), output_model_file)

                # Calculate bleu
                this_bleu, dev_dataset = calculate_bleu(
                    dev_filename, args, tokenizer, device, model, is_test=False, dev_dataset=dev_dataset, best_bleu=best_bleu)

                if this_bleu > best_bleu:
                    this_epoch_best = True

                    logger.info(" Achieve Best bleu:%s", this_bleu)
                    logger.info("  " + "*" * 20)
                    best_bleu = this_bleu
                    # Save best checkpoint for best bleu
                    output_dir = os.path.join(
                        args.output_dir, 'checkpoint-best-bleu')
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    model_to_save = model.module if hasattr(
                        model, 'module') else model  # Only save the model it-self
                    output_model_file = os.path.join(
                        output_dir, "pytorch_model.bin")
                    torch.save(model_to_save.state_dict(), output_model_file)

            # whether to stop
            if this_epoch_best:
                early_stop_count = 0
            else:
                early_stop_count += 1
                if early_stop_count == early_stop_threshold:
                    logger.warning("early stopping!!!")
                    break

    # use dev file and test file ( if exist) to calculate bleu
    if args.do_test:
        files = []
        if dev_filename is not None:
            files.append(dev_filename)
        if test_filename is not None:
            files.append(test_filename)

        for idx, file in enumerate(files):
            calculate_bleu(file, args, tokenizer, device, model,
                           file_postfix=str(idx), is_test=True)


def calculate_bleu(file_name, args, tokenizer, device, model, file_postfix=None, is_test=False, dev_dataset=None,
                   best_bleu=None):
    logger.info("BLEU file: {}".format(file_name))

    # whether append postfix to result file
    if file_postfix is not None:
        file_postfix = "_" + file_postfix
    else:
        file_postfix = ""

    if is_test:
        file_prefix = "test"
    else:
        file_prefix = "dev"

    # if dev dataset has been saved
    if (not is_test) and ('dev_bleu' in dev_dataset):
        eval_examples, eval_data = dev_dataset['dev_bleu']
    else:
        # read texts
        eval_examples = read_examples(file_name, args)

        # only use a part for dev
        if not is_test:
            eval_examples = random.sample(
                eval_examples, min(1000, len(eval_examples)))

        # tokenize data
        eval_features = convert_examples_to_features(
            eval_examples, tokenizer, args, stage='test')

        all_source_ids = eval_features['source_ids']
        all_source_mask = eval_features['source_mask']

        eval_data = TensorDataset(all_source_ids, all_source_mask)

        if not is_test:
            dev_dataset['dev_bleu'] = eval_examples, eval_data

    # get dataloader
    eval_sampler = SequentialSampler(eval_data)
    eval_dataloader = DataLoader(eval_data, sampler=eval_sampler, batch_size=args.eval_batch_size,
                                 num_workers=2)

    model.eval()

    # generate texts by source
    generated_texts = []
    for batch in tqdm(eval_dataloader, total=len(eval_dataloader)):
        batch = tuple(t.to(device) for t in batch)
        source_ids, source_mask = batch
        with torch.no_grad():
            generated_texts_ids = model.generate(input_ids=source_ids, attention_mask=source_mask,
                                                 max_length=args.max_target_length)

            for text_ids in generated_texts_ids:
                text = tokenizer.decode(
                    text_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
                generated_texts.append(text)

    # write to file
    predictions = []

    with open(os.path.join(args.output_dir, file_prefix + "{}.output".format(file_postfix)), 'w') as f, open(
            os.path.join(args.output_dir, file_prefix + "{}.gold".format(file_postfix)), 'w') as f1:

        for ref, gold in zip(generated_texts, eval_examples):
            predictions.append(str(gold.idx) + '\t' + ref)
            f.write(str(gold.idx) + '\t' + ref + '\n')
            f1.write(str(gold.idx) + '\t' + gold.target + '\n')

    # compute bleu
    (goldMap, predictionMap) = bleu.computeMaps(predictions,
                                                os.path.join(args.output_dir, file_prefix + "{}.gold".format(file_postfix)))
    this_bleu = round(bleu.bleuFromMaps(goldMap, predictionMap)[0], 2)

    if is_test:
        logger.info("  %s = %s " % ("bleu-4", str(this_bleu)))
    else:
        logger.info("  %s = %s \t Previous best bleu %s" %
                    ("bleu-4", str(this_bleu), str(best_bleu)))

    logger.info("  " + "*" * 20)

    return this_bleu, dev_dataset


if __name__ == "__main__":
    my_args = read_arguments()

    begin_time = time.time()

    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(name)s -   %(message)s',
                        datefmt='%m/%d/%Y %H:%M:%S',
                        level=logging.INFO)
    logger = logging.getLogger(__name__)

    # write to file
    if os.path.exists(my_args.log_dir) is False:
        os.makedirs(my_args.log_dir)
    handler = logging.FileHandler(
        my_args.log_dir +
        "/tune_cls_{}.log".format(
            datetime.datetime.now().strftime("%m%d_%H%M")),
        "w", encoding="utf-8"
    )
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)

    # write to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logger.addHandler(console)

    logger.info(my_args)

    main(my_args)

    logger.info("Finish task and take %s", get_elapse_time(begin_time))
