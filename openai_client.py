import os
import random
from time import sleep
from typing import Tuple
from dotenv import load_dotenv
import requests


class OpenAIClient:
    def __init__(self):
        token = os.getenv('OPENAI_TOKEN')
        model_name = os.getenv('OPENAI_MODEL_NAME')
        max_number_of_tokens = os.getenv('OPENAI_MAX_NUMBER_OF_TOKENS')

        if token == None or model_name == None or max_number_of_tokens == None:
            raise Exception("Cannot get value in .env file.")

        # get form openai login API, and used for account's credit checking
        self.token = token
        self.model_name = model_name
        # = context window = max_input_length + max_output_length
        self.max_number_of_tokens = int(max_number_of_tokens)

    def generate(self, system_input_text: str, user_input_text: str, max_output_length: int) -> Tuple[int, str]:
        '''
            return: (total_tokens, output_text)
            raise Exception if error occurs.
        '''
        error_msg = ""
        for _ in range(5):
            try:
                messages = [{
                    "role": "user",
                    "content": user_input_text
                }]
                if system_input_text != "":
                    messages.insert(0, {
                        "role": "system",
                        "content": system_input_text
                    })

                res = requests.post("https://api.openai.com/v1/chat/completions",
                                    timeout=20,
                                    headers={
                                        "Authorization": f"Bearer {self.token}",
                                        "Content-Type": "application/json"
                                    },
                                    json={
                                        "model": self.model_name,
                                        "messages": messages,
                                        "max_tokens": max_output_length,
                                        "n": 1,
                                        "temperature": 0.2,
                                    })

                if res.status_code != 200:
                    raise Exception(
                        f"OpenAI API error code: {res.status_code}\n{res.json()}")

                return res.json()['usage']['total_tokens'], res.json()['choices'][0]['message']['content']
            except Exception as e:
                error_msg = e
                # wait random time to reduce pressure on server
                sleep(random.randint(5, 15))
                continue

        raise Exception(error_msg)


if __name__ == '__main__':
    load_dotenv()

    try:
        openai_client = OpenAIClient()
    except Exception as e:
        print(e)
        exit(-1)
