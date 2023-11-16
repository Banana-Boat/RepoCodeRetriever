import logging

from openai_client import OpenAIClient


class Retriever:
    def __init__(self, logger: logging.Logger, openai_client: OpenAIClient):
        self.logger = logger

        self.openai_client = openai_client

        self.MAX_NUMBER_OF_TOKENS = openai_client.max_number_of_tokens

    def _is_legal_input_text(self, input_text: str, max_output_length: int) -> bool:
        pass

    def _build_input(self, prompt: str, context: str, max_output_length: int) -> str:
        pass

    def _infer(self, input_text: str, max_output_length: int) -> int:
        pass

    def retrieve(self, sum_obj: dict, query: str) -> dict:
        pass
