from typing import List
import torch
from transformers import AutoTokenizer, AutoModel


class CodeSimCalculator:
    '''Calculate similarities between a query(text) and a list of code snippets'''

    def __init__(self):
        self.device = torch.device(
            'mps' if torch.backends.mps.is_available() else 'cpu')

        model_name = 'Salesforce/codet5p-220m-bimodal'
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, trust_remote_code=True)
        self.tokenizer.enc_token_id = self.tokenizer.convert_tokens_to_ids(
            '[ENC]')
        self.model = AutoModel.from_pretrained(
            model_name, trust_remote_code=True)

        self.model = self.model.to(self.device)
        self.model.eval()

    def get_embeds(self, texts: List[str], max_length: int):
        embeds = []

        for text in texts:
            encoded = self.tokenizer(text, padding='max_length', truncation=True, max_length=max_length,
                                     return_tensors="pt").to(self.device)
            output = self.model.encoder(encoded.input_ids, attention_mask=encoded.attention_mask,
                                        return_dict=True)
            embed = torch.nn.functional.normalize(
                self.model.proj(output.last_hidden_state[:, 0, :]), dim=-1)
            embeds.append(embed)

        embeds = torch.cat(embeds, dim=0)

        return embeds

    def calc_similarities(self, query: str, codes: List[str]) -> List[float]:
        if len(codes) == 0:
            return []

        query_embeds = self.get_embeds([query], 128)
        code_embeds = self.get_embeds(codes, 512)

        with torch.no_grad():
            sims_matrix = query_embeds @ code_embeds.t()
            similarities = sims_matrix.tolist()[0]
            print(similarities)

        return [round(sim, 3) for sim in similarities]


if __name__ == "__main__":
    code_sim_calculator = CodeSimCalculator()
    query = "Parse a list of type parameters into TypeParameter objects."
    infos = [
        {'id': 348, 'name': 'parseList', 'code': 'List<TypeParameter> parseList(final Parser parser, final String definingClassName){ if (parser.peek() != \'<\') { return Collections.emptyList(); } parser.expect(\'<\'); final List<TypeParameter> typeParams = new ArrayList<>(1); while (parser.peek() != \'>\') { if (!parser.hasMore()) { throw new ParseException(parser, "Missing \'>\'"); } if (!TypeUtils.getIdentifierToken(parser)) { throw new ParseException(parser, "Could not parse identifier token"); } final String identifier = parser.currToken(); // classBound may be null final ReferenceTypeSignature classBound = ReferenceTypeSignature.parseClassBound(parser, definingClassName); List<ReferenceTypeSignature> interfaceBounds; if (parser.peek() == \':\') { interfaceBounds = new ArrayList<>(); while (parser.peek() == \':\') { parser.expect(\':\'); final ReferenceTypeSignature interfaceTypeSignature = ReferenceTypeSignature.parseReferenceTypeSignature(parser, definingClassName); if (interfaceTypeSignature == null) { throw new ParseException(parser, "Missing interface type signature"); } interfaceBounds.add(interfaceTypeSignature); } } else { interfaceBounds = Collections.emptyList(); } typeParams.add(new TypeParameter(identifier, classBound, interfaceBounds)); } parser.expect(\'>\'); return typeParams; }'},
        {'id': 352, 'name': 'findReferencedClassNames',
            'code': 'void findReferencedClassNames(final Set<String> classNameListOut){ if (classBound != null) { classBound.findReferencedClassNames(classNameListOut); } for (final ReferenceTypeSignature typeSignature : interfaceBounds) { typeSignature.findReferencedClassNames(classNameListOut); } }'},
        {'id': 351, 'name': 'setScanResult',
            'code': 'void setScanResult(final ScanResult scanResult){ super.setScanResult(scanResult); if (this.classBound != null) { this.classBound.setScanResult(scanResult); } if (interfaceBounds != null) { for (final ReferenceTypeSignature referenceTypeSignature : interfaceBounds) { referenceTypeSignature.setScanResult(scanResult); } } }'},
        {'id': 350, 'name': 'getClassInfo',
            'code': 'ClassInfo getClassInfo(){ throw new IllegalArgumentException("getClassInfo() cannot be called here"); }'},
        {'id': 349, 'name': 'getClassName', 'code': 'String getClassName(){ // getClassInfo() is not valid for this type, so getClassName() does not need to be implemented throw new IllegalArgumentException("getClassName() cannot be called here"); }'},
    ]

    codes = [info['code'] for info in infos]
    similarities = code_sim_calculator.calc_similarities(query, codes)

    for i, info in enumerate(infos):
        info['similarity'] = similarities[i]

    infos.sort(key=lambda x: x['similarity'], reverse=True)

    for info in infos:
        print(info['name'], info['similarity'])
