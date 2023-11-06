from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

if __name__ == '__main__':

    model_obj = {
        "name": "Salesforce/codet5p-2b",
        "max_source_length": 2048,
        "max_target_length": 50,
    }

    model = AutoModelForSeq2SeqLM.from_pretrained(
        model_obj['name'], trust_remote_code=True)
    tokenizer = AutoTokenizer.from_pretrained(
        model_obj['name'])

    source = '''
    Class ReloadingFileBasedConfigurationBuilder<T extends FileBasedConfiguration> {
        ReloadingFileBasedConfigurationBuilder<T> configure​(BuilderParameters... params); // Appends the content of the specified BuilderParameters objects to the current initialization parameters.
        protected ReloadingDetector createReloadingDetector​(FileHandler handler, FileBasedBuilderParametersImpl fbparams); // Creates a ReloadingDetector which monitors the passed in FileHandler.
        ReloadingController getReloadingController(); // Gets the ReloadingController associated with this builder.
        protected void initFileHandler​(FileHandler handler); // Initializes the new current FileHandler.
    }
    '''

    encoded_prompt = tokenizer("// Summarization: ", return_tensors='pt')
    encoded_code = tokenizer(source, return_tensors='pt',
                             max_length=model_obj['max_source_length'],
                             padding=True, verbose=False,
                             add_special_tokens=True, truncation=True)

    generated_texts_ids = model.generate(
        input_ids=encoded_code['input_ids'],
        attention_mask=encoded_code['attention_mask'],
        decoder_input_ids=encoded_prompt['input_ids'].clone(),
        max_length=model_obj['max_target_length']
    )

    generated_text = tokenizer.decode(generated_texts_ids[0],
                                      skip_special_tokens=True, clean_up_tokenization_spaces=False)

    print(generated_text)

    # tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    # model = AutoModelForSeq2SeqLM.from_pretrained(checkpoint,
    #                                               torch_dtype=torch.float16,
    #                                               low_cpu_mem_usage=True,
    #                                               trust_remote_code=True).to(device)

    # encoding = tokenizer("def print_hello_world():",
    #                      return_tensors="pt").to(device)
    # encoding['decoder_input_ids'] = encoding['input_ids'].clone()
    # outputs = model.generate(**encoding, max_length=15)
    # print(tokenizer.decode(outputs[0], skip_special_tokens=True))
