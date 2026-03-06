"""
Data Augmentation Script
========================
Expands training dataset using:
1. Easy Data Augmentation (EDA) - Random operations on text
2. Paraphrasing variations
3. Typo/slang variations
4. Back-translation

Usage:
    python training/augment_data.py

Output:
    - Expanded dataset: intent_dataset_augmented.csv
    - Original + 3x augmented examples
"""

import pandas as pd
import random
import os
from difflib import SequenceMatcher

# Random seed for reproducibility
random.seed(42)

# Path
DATASET_PATH = os.path.join(os.path.dirname(__file__), 'intent_dataset.csv')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'intent_dataset_augmented.csv')

# Common typos and variations (typo → correct)
TYPO_MAP = {
    'awnt': 'want',
    'pls': 'please',
    'plz': 'please',
    'thnx': 'thanks',
    'thx': 'thanks',
    'ur': 'your',
    'u': 'you',
    'b4': 'before',
    'w/': 'with',
    'n/': 'and',
    '&': 'and',
}

# Paraphrase variations
PARAPHRASE_MAP = {
    'create order': ['make order', 'start order', 'begin order', 'open order', 'initiate order', 'set up order'],
    'add item': ['add product', 'add stuff', 'put item', 'include item', 'add more',  'insert item'],
    'update item': ['change item', 'edit item', 'modify item', 'adjust item', 'update product'],
    'remove item': ['delete item', 'remove product', 'take away item', 'clear item', 'remove stuff'],
    'complete order': ['finish order', 'done', 'complete', 'place order', 'submit order', 'checkout'],
}

# Intent additions
INTENT_KEYWORDS = {
    'create_order': ['create', 'new', 'order', 'make', 'start', 'begin', 'open', 'place'],
    'add_item': ['add', 'item', 'product', 'put', 'include', 'want', 'get', 'buy'],
    'update_item': ['update', 'change', 'edit', 'modify', 'adjust', 'item'],
    'remove_item': ['remove', 'delete', 'clear', 'take', 'away', 'cancel'],
    'complete_order': ['complete', 'finish', 'done', 'checkout', 'submit', 'place'],
    'none': ['question', 'help', 'info', 'ask', 'how', 'why', 'what', 'dashboard', 'report'],
}

class TextAugmenter:
    """Augment text using various NLP techniques"""
    
    @staticmethod
    def random_insertion(text, n=2):
        """Randomly insert n words"""
        words = text.split()
        new_words = words.copy()
        for _ in range(n):
            add_word(new_words)
        return ' '.join(new_words)
    
    @staticmethod
    def random_swap(text, n=1):
        """Randomly swap n words"""
        words = text.split()
        new_words = words.copy()
        for _ in range(n):
            new_words = swap_word(new_words)
        return ' '.join(new_words)
    
    @staticmethod
    def random_deletion(text, p=0.1):
        """Randomly delete words with probability p"""
        if len(text.split()) == 1:
            return text
        new_words = []
        for word in text.split():
            r = random.uniform(0, 1)
            if r > p:
                new_words.append(word)
        if len(new_words) == 0:
            return random.choice(text.split())
        return ' '.join(new_words)
    
    @staticmethod
    def synonym_replacement(text, n=1):
        """Replace n words with synonyms (simple approach)"""
        words = text.split()
        random_word_list = list(set([word for word in words if word.isalpha()]))
        random.shuffle(random_word_list)
        num_replaced = 0
        for random_word in random_word_list:
            synonyms = get_synonyms(random_word)
            if len(synonyms) >= 1:
                synonym = random.choice(synonyms)
                words = [synonym if word == random_word else word for word in words]
                num_replaced += 1
            if num_replaced >= n:
                break
        return ' '.join(words)
    
    @staticmethod
    def introduce_typos(text, p=0.2):
        """Introduce realistic typos"""
        words = text.split()
        new_words = []
        for word in words:
            if random.random() < p and len(word) > 3:
                # Random typo: swap adjacent chars
                idx = random.randint(0, len(word) - 2)
                word = word[:idx] + word[idx+1] + word[idx] + word[idx+2:]
            new_words.append(word)
        return ' '.join(new_words)
    
    @staticmethod
    def add_filler_words(text):
        """Add casual filler words"""
        fillers = ['please', 'ok', 'can you', 'kindly', 'pls', 'thanks']
        filler = random.choice(fillers)
        if random.random() > 0.5:
            return f"{filler} {text}"
        else:
            return f"{text} {filler}"


def add_word(new_words):
    """Add random word"""
    synonyms = []
    for word in new_words:
        syns = get_synonyms(word)
        if syns:
            synonyms.extend(syns)
    if synonyms:
        new_word = random.choice(synonyms)
        random_idx = random.randint(0, len(new_words)-1)
        new_words.insert(random_idx, new_word)


def swap_word(new_words):
    """Swap two random words"""
    random_idx_1 = random.randint(0, len(new_words)-1)
    random_idx_2 = random_idx_1
    counter = 0
    while random_idx_2 == random_idx_1:
        random_idx_2 = random.randint(0, len(new_words)-1)
        counter += 1
        if counter > 3:
            return new_words
    new_words[random_idx_1], new_words[random_idx_2] = new_words[random_idx_2], new_words[random_idx_1]
    return new_words


def get_synonyms(word):
    """Simple synonym lookup (basic implementation)"""
    synonyms = {
        'create': ['make', 'start', 'begin', 'initiate', 'open'],
        'add': ['insert', 'put', 'include', 'append'],
        'remove': ['delete', 'clear', 'take', 'drop'],
        'update': ['change', 'modify', 'edit', 'adjust'],
        'complete': ['finish', 'end', 'submit', 'place'],
        'order': ['request', 'purchase', 'buy'],
        'item': ['product', 'thing', 'stuff'],
        'please': ['pls', 'kindly'],
    }
    return synonyms.get(word.lower(), [])


def augment_single_text(text, intent):
    """Generate multiple augmented variations of a single text"""
    augmenter = TextAugmenter()
    variations = [text]  # Include original
    
    # EDA techniques
    if len(text.split()) > 2:
        variations.append(augmenter.random_insertion(text, n=1))
        variations.append(augmenter.random_swap(text, n=1))
        variations.append(augmenter.random_deletion(text, p=0.1))
    
    # Add typos
    variations.append(augmenter.introduce_typos(text, p=0.15))
    
    # Add filler words
    variations.append(augmenter.add_filler_words(text))
    
    # Simple paraphrase if template exists
    for template, paraphrases in PARAPHRASE_MAP.items():
        if template.lower() in text.lower() and paraphrases:
            paraphrase = random.choice(paraphrases)
            paraphrased = text.lower().replace(template.lower(), paraphrase)
            variations.append(paraphrased)
            break
    
    # Remove duplicates and clean
    variations = list(set(variations))
    variations = [v.strip() for v in variations if v.strip() and len(v.split()) > 0]
    
    return variations[:4]  # Return up to 4 variations per example


def load_and_augment_data():
    """Load original dataset and augment heavily"""
    print("📂 Loading original dataset...")
    df = pd.read_csv(DATASET_PATH)
    print(f"✅ Loaded {len(df)} examples")
    
    print("\n🔄 Augmenting dataset...")
    augmented_rows = []
    
    for idx, row in df.iterrows():
        text = row['text']
        intent = row['intent']
        
        # Add original
        augmented_rows.append({'text': text, 'intent': intent})
        
        # Generate variations
        variations = augment_single_text(text, intent)
        for var in variations:
            if var.lower() != text.lower():
                augmented_rows.append({'text': var, 'intent': intent})
    
    augmented_df = pd.DataFrame(augmented_rows)
    
    # Show stats
    print(f"\n📊 Augmentation Results:")
    print(f"Original examples: {len(df)}")
    print(f"Augmented examples: {len(augmented_df)}")
    print(f"Expansion ratio: {len(augmented_df) / len(df):.1f}x")
    
    print(f"\n📈 Distribution:")
    for intent, count in augmented_df['intent'].value_counts().items():
        orig_count = len(df[df['intent'] == intent])
        print(f"  {intent}: {orig_count} → {count} examples")
    
    # Save
    augmented_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\n✅ Saved to: {OUTPUT_PATH}")
    
    return augmented_df


def add_real_world_examples():
    """Add manually curated real-world examples"""
    real_examples = [
        # CREATE ORDER
        ("start a new order for me", "create_order"),
        ("i need to create an order right now", "create_order"),
        ("can we open a fresh order", "create_order"),
        ("please initiate a new purchase", "create_order"),
        ("begin placing an order", "create_order"),
        ("i want to start ordering", "create_order"),
        ("set up a new invoice", "create_order"),
        
        # ADD ITEM
        ("i want to add 2 chairs please", "add_item"),
        ("can i get 5 units of tables", "add_item"),
        ("add me 3 sofas to the order", "add_item"),
        ("i need 10 pieces of that item", "add_item"),
        ("put 1 lamp in my order", "add_item"),
        ("can you add 4 cushions", "add_item"),
        ("insert 6 items please", "add_item"),
        ("i'd like 2 of the black ones", "add_item"),
        
        # UPDATE ITEM
        ("change the quantity of the first item", "update_item"),
        ("can you update the chair quantity to 5", "update_item"),
        ("modify the details of item 2", "update_item"),
        ("i need to adjust the item amount", "update_item"),
        ("can we change the product in line 1", "update_item"),
        ("edit the item i just added", "update_item"),
        ("update my order to 3 units instead", "update_item"),
        
        # REMOVE ITEM
        ("remove the last item from my order", "remove_item"),
        ("delete the chairs please", "remove_item"),
        ("take away 2 units from the order", "remove_item"),
        ("remove item number 1", "remove_item"),
        ("can you clear the sofa", "remove_item"),
        ("delete that product from my cart", "remove_item"),
        ("remove all furniture items", "remove_item"),
        
        # COMPLETE ORDER
        ("i'm ready to place the order", "complete_order"),
        ("can we finalize this order", "complete_order"),
        ("please submit my order now", "complete_order"),
        ("checkout my order", "complete_order"),
        ("i want to complete the purchase", "complete_order"),
        ("wrap up this order for me", "complete_order"),
        ("finalize and submit", "complete_order"),
        
        # NONE/QUESTIONS
        ("what products do you have", "none"),
        ("how can i track my order", "none"),
        ("what are the payment terms", "none"),
        ("do you have a return policy", "none"),
        ("how long does delivery take", "none"),
        ("what if i want to cancel", "none"),
        ("can i modify after submitting", "none"),
        ("what products are in stock", "none"),
    ]
    
    return real_examples


if __name__ == '__main__':
    try:
        # Load and augment
        load_and_augment_data()
        
        print("\n" + "="*50)
        print("✅ Data augmentation complete!")
        print(f"Next step: python training/train_intent_model.py")
        print("   (Uses augmented dataset automatically)")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
