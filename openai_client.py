import os
import random
from time import sleep
from typing import Tuple
import requests
from dotenv import load_dotenv

from constants import RET_MAX_OUTPUT_LENGTH


class OpenAIClient:
    def __init__(self):
        session_id = os.getenv('OPENAI_SESSION_ID')
        token = os.getenv('OPENAI_TOKEN')
        model_name = os.getenv('OPENAI_MODEL_NAME')
        max_number_of_tokens = os.getenv('OPENAI_MAX_NUMBER_OF_TOKENS')

        if session_id == None or token == None or model_name == None or max_number_of_tokens == None:
            raise Exception("Cannot get value in .env file.")

        # get form openai login API, and used for account's credit checking
        self.session_id = session_id
        self.token = token
        self.model_name = model_name
        # = context window = max_input_length + max_output_length
        self.max_number_of_tokens = int(max_number_of_tokens)

    def get_credit_grants(self) -> float:
        '''
            get available credit grants(USD) of the account
        '''
        res = requests.get(
            "https://api.openai.com/dashboard/billing/credit_grants",
            headers={
                "Authorization": f"Bearer {self.session_id}"
            })

        if res.status_code != 200:
            return -1.0

        return res.json()['total_available']

    def generate(self, system_input_text: str, user_input_text: str, max_output_length: int) -> Tuple[int, str]:
        '''
            return total_tokens and output_text
        '''
        error_msg = ""

        for _ in range(3):  # retry 3 times at most when a error occurred
            try:
                res = requests.post("https://api.openai.com/v1/chat/completions",
                                    timeout=20,
                                    headers={
                                        "Authorization": f"Bearer {self.token}",
                                        "Content-Type": "application/json"
                                    },
                                    json={
                                        "model": self.model_name,
                                        "messages": [
                                            {
                                                "role": "system",
                                                "content": system_input_text
                                            },
                                            {
                                                "role": "user",
                                                "content": user_input_text
                                            }
                                        ],
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
        exit(1)

    system_input_text = '''You will be provided with a description of a Java method in a Java code repository, as well as a information list of directories or files or Java classes/interfaces/enums in this repository in JSON format as follows:
{"id": <PLACEHOLDER>, "name": <PLACEHOLDER>, "summary": <PLACEHOLDER>}
A directory contains files and subdirectories, a file contains Java classes/interfaces/enums, and a Java class/interface/enum contains methods.
You need to follow the steps below:
- Step 1: Calculate the probability that these directories or files or Java classes/interfaces/enums contain this method directly or indirectly.
NOTICE: If a directory or file contains interfaces or enums but no class, the probability should be the lowest.
- Step 2: Sort them from high to low according to the probability, return the option ID list.
- Step 3: Give a reason of about 50 words.
You need to give a JSON object that can be parsed directly as follows:
{"ids": [<PLACEHOLDER>...], "reason": <PLACEHOLDER>}
'''

    user_input_text = '''Method Description: Removes an element from the front end of the queue.
##################################################################
Information List:
{'id': 8, 'name': 'YPipeBase.java', 'summary': '  The file `YPipeBase.java` contains an interface named `YPipeBase` that provides methods for writing, reading, and flushing data through a pipe. The interface defines methods for writing data to the pipe, undoing the last write, flushing the pipe, checking if there is data available to read, reading data from the pipe, and probing the pipe.'}
{'id': 16, 'name': 'YPipe.java', 'summary': '  The YPipe.java file contains a Java class named YPipe that implements the YPipeBase interface and provides methods for writing, unwriting, flushing, and reading values from a queue. It also has a probe() method that checks if the queue is empty and returns the front element if it is not.'}
{'id': 26, 'name': 'YQueue.java', 'summary': '  The YQueue class is a data structure that implements a queue using a circular array. It has methods to add and remove elements from the front and back of the queue, as well as methods to retrieve the front and back elements. The queue is implemented using a combination of two chunks, with the frontChunk containing the front elements and the backChunk containing the back elements. The frontPos and backPos variables keep track of the position.'}
{'id': 55, 'name': 'Pipe.java', 'summary': '  The Pipe class is a bi-directional communication channel between two peers. It has methods for reading and writing messages, handling hiccups and termination requests, and setting high and low water marks. The class extends the ZObject class and implements the IPipeEvents interface. The IPipeEvents interface defines four methods that are called when certain events occur in a pipe.'}
{'id': 63, 'name': 'DBuffer.java', 'summary': '  The DBuffer class is a double-ended queue (deque) that allows for efficient reading and writing of messages. It has methods for adding and retrieving messages, as well as a probe() method that allows for peeking at the front element of the queue without removing it. The class also has a checkRead() method that checks a boolean flag hasMsg and returns the result after acquiring and releasing a lock on a shared resource.'}
{'id': 71, 'name': 'YPipeConflate.java', 'summary': '  The `YPipeConflate` class implements the `YPipeBase` interface and provides a buffered pipe for writing and reading values. It has methods for writing, returning `null`, flushing, and checking if the buffer has been read.'}
'''

    output = openai_client.generate(
        system_input_text, user_input_text, RET_MAX_OUTPUT_LENGTH)

    print(output)
