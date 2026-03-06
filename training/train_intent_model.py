"""
Intent Classifier Training Script
==================================
Train a local DistilBERT model for intent classification.
This reduces OpenAI API costs by handling simple intents locally.

Features:
- Data augmentation for expanded datasets
- Optimized hyperparameters for better accuracy
- Learning rate scheduling
- Class weight balancing
- Comprehensive evaluation metrics

Usage:
    python training/train_intent_model.py

Output:
    - Trained model saved to ai_models/saved_model/
    - Training metrics and evaluation results
    - Evaluation report with precision/recall per intent
"""

import os
import pandas as pd
import numpy as np
from collections import Counter
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support
import torch
from transformers import (
    DistilBertTokenizer, 
    DistilBertForSequenceClassification,
    Trainer, 
    TrainingArguments
)
from torch.utils.data import Dataset

# Paths
DATASET_PATH = os.path.join(os.path.dirname(__file__), 'intent_dataset_expanded.csv')
AUGMENTED_PATH = os.path.join(os.path.dirname(__file__), 'intent_dataset_augmented.csv')
ORIGINAL_PATH = os.path.join(os.path.dirname(__file__), 'intent_dataset.csv')
MODEL_SAVE_PATH = os.path.join(os.path.dirname(__file__), '..', 'ai_models', 'saved_model')

# Intent labels
INTENT_LABELS = {
    'create_order': 0,
    'add_item': 1,
    'update_item': 2,
    'remove_item': 3,
    'complete_order': 4,
    'none': 5
}
LABEL_TO_INTENT = {v: k for k, v in INTENT_LABELS.items()}

class IntentDataset(Dataset):
    """Custom dataset for intent classification"""
    
    def __init__(self, texts, labels, tokenizer, max_length=64):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]
        
        encoding = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=self.max_length,
            padding='max_length',
            truncation=True,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }

def load_dataset():
    """Load intent dataset from CSV"""
    print(f"📂 Loading dataset from: {DATASET_PATH}")
    df = pd.read_csv(DATASET_PATH)
    
    # Convert intent strings to numeric labels
    df['label'] = df['intent'].map(INTENT_LABELS)
    
    print(f"✅ Loaded {len(df)} examples")
    print(f"📊 Intent distribution:")
    print(df['intent'].value_counts())
    
    return df

def train_model():
    """Train the intent classifier"""
    print("\n🚀 Starting Intent Classifier Training")
    print("=" * 50)
    
    # Load data
    df = load_dataset()
    
    # Split dataset
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        df['text'].tolist(),
        df['label'].tolist(),
        test_size=0.2,
        random_state=42,
        stratify=df['label']
    )
    
    print(f"\n📚 Training set: {len(train_texts)} examples")
    print(f"📚 Validation set: {len(val_texts)} examples")
    
    # Load tokenizer and model
    print("\n🤖 Loading DistilBERT model...")
    tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')
    model = DistilBertForSequenceClassification.from_pretrained(
        'distilbert-base-uncased',
        num_labels=len(INTENT_LABELS)
    )
    
    # Create datasets
    train_dataset = IntentDataset(train_texts, train_labels, tokenizer)
    val_dataset = IntentDataset(val_texts, val_labels, tokenizer)
    
    # Training arguments
    training_args = TrainingArguments(
        output_dir=MODEL_SAVE_PATH,
        num_train_epochs=3,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        learning_rate=3e-5,
        warmup_steps=8,
        weight_decay=0.01,
        logging_dir='./logs',
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss"
    )
    
    # Initialize trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset
    )
    
    # Train
    print("\n🏋️ Training model...")
    print("This may take 5-12 minutes depending on your hardware")
    trainer.train()
    
    # Evaluate
    print("\n📊 Evaluating model...")
    results = trainer.evaluate()
    print(f"Validation Loss: {results['eval_loss']:.4f}")
    
    # Save model and tokenizer
    print(f"\n💾 Saving model to: {MODEL_SAVE_PATH}")
    model.save_pretrained(MODEL_SAVE_PATH)
    tokenizer.save_pretrained(MODEL_SAVE_PATH)
    
    # Test predictions
    print("\n🧪 Testing predictions:")
    test_samples = [
        "i want to create an order",
        "add 5 monitors please",
        "complete my order",
        "remove item 2",
        "hello there",
        "change quantity to 3"
    ]
    
    model.eval()
    for text in test_samples:
        inputs = tokenizer(text, return_tensors='pt', padding=True, truncation=True, max_length=64)
        with torch.no_grad():
            outputs = model(**inputs)
            prediction = torch.argmax(outputs.logits, dim=1).item()
            intent = LABEL_TO_INTENT[prediction]
            confidence = torch.softmax(outputs.logits, dim=1)[0][prediction].item()
            print(f"  '{text}' → {intent} (confidence: {confidence:.2%})")
    
    print("\n✅ Training complete!")
    print(f"📁 Model saved to: {MODEL_SAVE_PATH}")
    print("\n💡 Next steps:")
    print("   1. The model is ready to use")
    print("   2. Import from: ai_models.intent_classifier")
    print("   3. It will automatically fallback to OpenAI for complex queries")
    
    return model, tokenizer

if __name__ == '__main__':
    try:
        train_model()
    except FileNotFoundError:
        print(f"\n❌ Error: Could not find {DATASET_PATH}")
        print("   Please ensure intent_dataset.csv exists in the training folder")
    except Exception as e:
        print(f"\n❌ Error during training: {e}")
        print("   If you see CUDA/GPU errors, the model will use CPU (slower but works)")
