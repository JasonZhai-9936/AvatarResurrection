import spacy

nlp = spacy.load("en_core_web_sm")

def get_emphasized_words(text):
    doc = nlp(text)
    emphasized = []
    for token in doc:
        # Simple heuristic rules
        if token.pos_ in {"ADJ", "ADV"}:           # modifiers
            emphasized.append(token.text)
        elif token.dep_ in {"ROOT"}:               # main verb or root word
            emphasized.append(token.text)
        elif token.tag_ in {"NNP"}:                # proper nouns
            emphasized.append(token.text)
    return emphasized

text = "Greetings, how are you doing today? My name is Charles Darwin"
print(get_emphasized_words(text))
# → ['really', 'love', 'new']
