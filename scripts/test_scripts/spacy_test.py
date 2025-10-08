import spacy

nlp = spacy.load("en_core_web_sm")


# Finds words likely to be emphasized in speech using spaCy's linguistic features:
# - ADJ / ADV / VERB / INTJ → adjectives, adverbs, verbs, or interjections (descriptive or emotional words)
# - dep_ in {'ROOT','attr','acomp'} → main verb or key complement of the sentence
# - ent_type_ != "" → named entities like people, places, or organizations
# - tag_ in {'JJR','JJS','RBR','RBS'} → comparative or superlative forms (e.g., "better", "most", "faster")
# The function returns these words as likely emphasis points without needing any predefined vocabulary.

def get_emphasized_words(text):
    doc = nlp(text)
    emphasized = []
    for token in doc:
        if (
            token.pos_ in {"ADJ", "ADV", "VERB", "INTJ"}
            or token.dep_ in {"ROOT", "attr", "acomp"}
            or token.ent_type_ != ""
            or token.tag_ in {"JJR", "JJS", "RBR", "RBS"}
        ):
            emphasized.append(token.text)
    return emphasized


text = "The Beagle voyage was an amazing adventure. I learned much about the intricacies of evolution and the greater world. It was an experience I will never forget."
print(get_emphasized_words(text))
# ->['Beagle', 'was', 'amazing', 'adventure', 'learned', 'much', 'greater', 'was', 'experience', 'never', 'forget']
