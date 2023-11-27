from typing import List, Tuple
import torch
from transformers import BertTokenizer, BertModel


class SimCaculator:
    def __init__(self):
        self.device = torch.device(
            'mps' if torch.backends.mps.is_available() else 'cpu')
        self.tokenizer = BertTokenizer.from_pretrained('bert-large-cased')
        self.model = BertModel.from_pretrained(
            'bert-large-cased').to(self.device)
        self.model.eval()

    def calc_similarities(self, query: str, texts: List[str]) -> List[float]:
        if len(texts) == 0:
            return []

        with torch.no_grad():
            query_encoded = torch.tensor(self.tokenizer.encode(query)
                                         ).unsqueeze(0).to(self.device)
            query_embedding = self.model(query_encoded)[0][:, 0, :]

            texts_encoded = self.tokenizer.batch_encode_plus(
                texts, padding=True, return_tensors='pt').to(self.device)
            texts_embedding = self.model(**texts_encoded)[0][:, 0, :]

            similarities = torch.nn.functional.cosine_similarity(
                query_embedding, texts_embedding)

            return [round(similarity.item(), 3) for similarity in similarities]
