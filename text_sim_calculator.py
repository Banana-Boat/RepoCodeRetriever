from typing import List
import torch
from sentence_transformers import SentenceTransformer, util


class TextSimCalculator:
    '''Calculate similarities between a query(text) and a list of summaries(text)'''

    def __init__(self):
        self.device = torch.device(
            'mps' if torch.backends.mps.is_available() else 'cpu')
        self.model = SentenceTransformer(
            'sentence-transformers/all-MiniLM-L6-v2', device=self.device)

    def calc_similarities(self, query: str, sentences: List[str]) -> List[float]:
        if len(sentences) == 0:
            return []

        query_embedding = self.model.encode(
            [query], convert_to_tensor=True, device=self.device, show_progress_bar=False)
        sentences_embeddings = self.model.encode(
            sentences, convert_to_tensor=True, device=self.device, show_progress_bar=False)

        similarities = util.pytorch_cos_sim(
            query_embedding, sentences_embeddings)[0]

        return [round(sim.item(), 3) for sim in similarities]


if __name__ == "__main__":
    text_sim_calculator = TextSimCalculator()
    query = "Acquire on object instance of type T, either by reusing a previously recycled instance if possible, or if there are no currently-unused instances, by allocating a new instance."
    infos = [
        {'id': 515, 'name': 'ArrayTypeSignature.java', 'summary': 'The `ArrayTypeSignature` class extends `ReferenceTypeSignature` and provides methods to work with array type signatures. It includes methods to get the number of dimensions of the array, set the scan result, find referenced class names, compare with other type signatures, and parse array type signatures from a string. The class also includes a method to return a string representation of the array type.'},
        {'id': 150, 'name': 'TypeVariableSignature.java', 'summary': 'The `TypeVariableSignature` class extends `ClassRefOrTypeVariableSignature` and provides methods for resolving type parameters, parsing type variable signatures, getting class names, finding referenced class names, comparing type signatures, and generating string representations. The `resolve()` method resolves the type variable against the containing method or class, while the `parse()` method parses a type variable signature. The class also includes methods for finding referenced class names, comparing type signatures, and generating string representations.'},
        {'id': 22, 'name': 'ClassTypeSignature.java', 'summary': 'The `ClassTypeSignature` class extends `HierarchicalTypeSignature` and includes a `parse` method to parse a type descriptor into a `ClassTypeSignature` object. It also has methods to get the class name, set the scan result, and find referenced class names. The `parse` method uses a `Parser` object to extract information from the type descriptor, and the `findReferencedClassNames` method adds referenced class names to a set by iterating over type parameters and superinterface signatures.'},
        {'id': 347, 'name': 'TypeArgument.java', 'summary': 'The `TypeArgument` class extends `HierarchicalTypeSignature` and provides methods for parsing type arguments, getting class names, setting scan results, finding referenced class names, and generating string representations of the type signature. It includes methods such as `parse` for parsing type arguments, `getClassName` for retrieving the class name, and `toStringWithSimpleNames` for generating a string representation using simple names. Some methods throw `IllegalArgumentException` if called inappropriately.'},
        {'id': 353, 'name': 'TypeParameter.java', 'summary': 'The `TypeParameter` class extends `HierarchicalTypeSignature` and includes methods to parse a list of type parameters, get the class name, retrieve class information, set scan results, and find referenced class names. It also includes a method to find referenced class names by calling the same method on the `classBound` field if it is not null. The `getClassName()` method is not implemented in this class.'},
        {'id': 298, 'name': 'ClassGraph.java', 'summary': 'The `ClassGraph` Java class provides methods for scanning and retrieving information about classes, fields, methods, annotations, and modules. It allows for customization of the scanning process, including enabling or disabling specific scanning features, whitelisting or blacklisting packages, classes, jars, and modules, and retrieving classpath information. The class also supports asynchronous scanning and real-time logging.'}
    ]

    summaries = [info['summary'] for info in infos]
    similarities = text_sim_calculator.calc_similarities(query, summaries)

    for i, info in enumerate(infos):
        info['similarity'] = similarities[i]

    infos.sort(key=lambda x: x['similarity'], reverse=True)

    for info in infos:
        print(info['name'], info['similarity'])
