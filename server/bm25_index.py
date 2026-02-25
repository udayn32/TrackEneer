import math
from collections import defaultdict

class BM25Index:
    def __init__(self):
        self.index_data = defaultdict(list)
        self.doc_lengths = {} 
        self.doc_count = 0
        self.total_length = 0  # Added this
        self.k1 = 1.5          # Standard constant
        self.b = 0.75          # Standard constant

    def tokenize(self, text):
        return text.lower().split()

    def index(self, doc_id, text):
        words = self.tokenize(text)
        length = len(words)
        self.doc_lengths[doc_id] = length
        self.doc_count += 1
        self.total_length += length # Track total words for avgdl
        
        counts = defaultdict(int)
        for word in words:
            counts[word] += 1
            
        for word, count in counts.items():
            self.index_data[word].append({"id": doc_id, "tf": count})

    def get_avgdl(self):
        if self.doc_count == 0: return 0
        return self.total_length / self.doc_count

    def search(self, query, top_k=5):
        query_words = self.tokenize(query)
        scores = defaultdict(float) # doc_id -> score
        avgdl = self.get_avgdl()

        for word in query_words:
            # 1. Calculate IDF for this word
            # How many docs contain this word?
            docs_with_word = len(self.index_data.get(word, []))
            if docs_with_word == 0: continue
            
            # Simplified IDF formula
            idf = math.log((self.doc_count - docs_with_word + 0.5) / (docs_with_word + 0.5) + 1)

            # 2. Calculate score contribution for each doc that has this word
            for entry in self.index_data.get(word, []):
                doc_id = entry["id"]
                tf = entry["tf"]
                d_len = self.doc_lengths[doc_id]
                
                # The BM25 Formula part
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (d_len / avgdl))
                
                scores[doc_id] += idf * (numerator / denominator)

        # Sort scores from highest to lowest
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_k]