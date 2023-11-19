import os
import random
from time import sleep
from typing import Tuple
import requests
from dotenv import load_dotenv

from constants import RET_MAX_OUTPUT_LENGTH, RET_SCOPE_SYSTEM_PROMPT


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
                                    timeout=10,
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
                    error_msg = f"OpenAI API error code: {res.status_code}\n{res.json()}"
                    # wait random time to reduce pressure on server
                    sleep(random.randint(5, 15))
                    continue

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

    if openai_client.get_credit_grants() < 2.0:
        print("Not enough credits to retrieval.")
        exit(1)

    user_input_text = '''Method Description: Returns true if there is at least one message to read in the pipe.
Summary:
{'id': 72, 'name': 'pipe', 'summary': ' The directory contains several Java classes and interfaces related to pipes and queues. The main classes are YPipeBase, YPipe, YQueue, Pipe, and DBuffer. YPipeBase is an interface that provides methods for writing, reading, and flushing data through a pipe. YPipe is a class that implements YPipeBase and provides methods for writing, unwriting, flushing, and reading values from a queue. YQueue is a data structure that implements a queue using a circular array. Pipe is a bi-directional communication channel between two peers. DBuffer is a double-ended queue that allows for efficient reading and writing of messages. YPipeConflate is a class that implements YPipeBase and provides a buffered pipe for writing and reading values.'}
{'id': 422, 'name': 'poll', 'summary': ' The directory contains several Java classes related to polling. The PollerBase class provides a basic framework for implementing a polling mechanism, while the Poller class manages a Selector object and a HashMap of selected keys. The PollItem class wraps a SelectableChannel object and provides methods for checking the readiness of a socket. The IPollEvents interface defines five methods that are not implemented and throw an UnsupportedOperationException when called.'}
{'id': 120, 'name': 'ZObject.java', 'summary': ' The file ZObject.java contains an abstract class named ZObject that provides methods for processing commands and managing endpoints. The class has methods for registering and unregistering endpoints, finding endpoints, and sending commands to other threads. It also has methods for processing various types of commands, such as processActivateRead, processActivateWrite, and processStop. The class has abstract methods that must be implemented by any subclass.'}
{'id': 162, 'name': 'Msg.java', 'summary': ' The file contains three classes: Msg, Builder, and Type. The Msg class represents a message in a byte buffer and provides methods for reading and writing data, checking the type and flags, and copying data. The Builder class extends Msg and provides methods for building a message. The Type enum is an empty enumeration used to define named constants for different types of data.'}
{'id': 189, 'name': 'Ctx.java', 'summary': ' The file contains four classes and one enum:\n\n* Ctx is a context object in the ZeroMQ library that manages sockets and endpoints.\n* Endpoint is a Java class that represents a network endpoint.\n* PendingConnection is a placeholder for a connection that is being established.\n* Side is an empty enumeration that represents the two sides of an object.'}
{'id': 254, 'name': 'SocketBase.java', 'summary': ' The file contains three classes: SocketBase, EndpointPipe, and SimpleURI. SocketBase is an abstract class that provides a base implementation for various socket types. EndpointPipe represents a pipe that connects two endpoints, and SimpleURI provides a simple way to create a SimpleURI object from a String value representing a URI.'}
{'id': 258, 'name': 'Command.java', 'summary': ' The file contains a Java class named Command and an enum named Type. The Command class has a single method process() that calls the processCommand() method on an object of type destination passing this as an argument. The Type enum is an empty enum in Java used to define a set of named constants that can be used to represent different types of data.'}
'''

    output = openai_client.generate(
        RET_SCOPE_SYSTEM_PROMPT, user_input_text, RET_MAX_OUTPUT_LENGTH)

    print(output)
