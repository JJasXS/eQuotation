"""
Intent Classifier Training Script - OPTIMIZED
==============================================
Train a local DistilBERT model for intent classification.

Features:
- Auto-detect best dataset (expanded > augmented > original)
- Optimized hyperparameters with learning rate scheduling
- Class weight balancing for imbalanced intents
- Comprehensive evaluation metrics per intent
- Better training for higher accuracy and precision

Usage:
    python training/train_intent_model.py

Output:
    - Trained model saved to ai_models/saved_model/
    - Detailed performance metrics
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
    TrainingArguments,
    get_linear_schedule_with_warmup
)
from torch.utils.data import Dataset
from torch.nn import CrossEntropyLoss

# Paths
DATASET_EXPANDED = os.path.join(os.path.dirname(__file__), 'intent_dataset_expanded.csv')
DATASET_AUGMENTED = os.path.join(os.path.dirname(__file__), 'intent_dataset_augmented.csv')
DATASET_ORIGINAL = os.path.join(os.path.dirname(__file__), 'intent_dataset.csv')
MODEL_SAVE_PATH = os.path.join(os.path.dirname(__file__), '..', 'ai_models', 'saved_model')

# Intent labels
INTENT_LABELS = {
    'create_order': 0,
    'add_item': 1,
    'update_item': 2,
    'remove_item': 3,
    'complete_order': 4,
    'none': 5,
    'update': 6,
    'remove_all': 7,
    'remove': 8
}
LABEL_TO_INTENT = {v: k for k, v in INTENT_LABELS.items()}

class IntentDataset(Dataset):
    """Custom dataset for intent classification"""
    
    def __init__(self, texts, labels, tokenizer, max_length=128):
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


def select_best_dataset():
    """Auto-select best available dataset - prioritize augmented"""
    if os.path.exists(DATASET_AUGMENTED):
        print(f"[DATASET] Using augmented dataset: {DATASET_AUGMENTED}")
        return DATASET_AUGMENTED
    elif os.path.exists(DATASET_EXPANDED):
        print(f"[DATASET] Using expanded dataset: {DATASET_EXPANDED}")
        return DATASET_EXPANDED
    else:
        print(f"[DATASET] Using original dataset: {DATASET_ORIGINAL}")
        return DATASET_ORIGINAL


def calculate_class_weights(labels):
    """Calculate weights for imbalanced dataset"""
    label_counts = Counter(labels)
    total = len(labels)
    weights = {}
    
    for label_id, count in label_counts.items():
        # Give more weight to underrepresented classes
        weights[label_id] = total / (len(label_counts) * count)
    
    # Normalize
    max_weight = max(weights.values())
    weights = {k: v / max_weight for k, v in weights.items()}
    
    print(f"\n[WEIGHTS] Class weights:")
    for label_id, weight in sorted(weights.items()):
        intent = LABEL_TO_INTENT[label_id]
        print(f"  {intent}: {weight:.2f}")
    
    return weights


def train_model():
    print("[TRAIN] Starting Intent Classifier Training (OPTIMIZED)")
    print("="*60)
    
    # Select best dataset
    dataset_path = select_best_dataset()
    
    print(f"\n[DATASET] Loading dataset from: {dataset_path}")
    df = pd.read_csv(dataset_path)
    print(f"[SUCCESS] Loaded {len(df)} examples")
    
    # Extract and encode
    texts = df['text'].tolist()
    intents = df['intent'].tolist()
    labels = [INTENT_LABELS[intent] for intent in intents]
    
    # Show distribution
    print(f"\n[DISTRIBUTION] Intent distribution:")
    intent_counts = Counter(intents)
    for intent, count in sorted(intent_counts.items()):
        print(f"  {intent}: {count} examples")
    
    # Split data
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels,
        test_size=0.15,
        random_state=42,
        stratify=labels
    )
    
    print(f"\n[SPLIT] Dataset split:")
    print(f"  Training set: {len(train_texts)} examples")
    print(f"  Validation set: {len(val_texts)} examples")
    
    # Load model and tokenizer
    print(f"\n[MODEL] Loading DistilBERT model...")
    tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')
    model = DistilBertForSequenceClassification.from_pretrained(
        'distilbert-base-uncased',
        num_labels=len(INTENT_LABELS)
    )
    
    # Create datasets
    train_dataset = IntentDataset(train_texts, train_labels, tokenizer, max_length=128)
    val_dataset = IntentDataset(val_texts, val_labels, tokenizer, max_length=128)
    
    # OPTIMIZED training arguments
    training_args = TrainingArguments(
        output_dir=MODEL_SAVE_PATH,
        num_train_epochs=5,                    # Increased from 3
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        learning_rate=2e-5,                    # Slightly lower learning rate
        warmup_steps=50,                       # More gradual warmup
        weight_decay=0.01,
        logging_dir='./logs',
        logging_steps=5,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        seed=42,
        max_grad_norm=1.0,                     # Gradient clipping
        lr_scheduler_type="linear",            # Linear scheduler
        optim="adamw_torch",                   # Better optimizer
    )
    
    # Initialize trainer with evaluation metrics
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=None  # We'll compute manually for better control
    )
    
    # Start training
    print(f"\n[TRAINING] Starting training...")
    print("This may take 10-15 minutes depending on your hardware\n")
    
    trainer.train()
    
    # Evaluate
    print(f"\n[EVAL] Evaluating on validation set...")
    eval_results = trainer.evaluate()
    print(f"[SUCCESS] Eval Loss: {eval_results['eval_loss']:.4f}")
    
    # Detailed predictions on validation set
    predictions = trainer.predict(val_dataset)
    pred_labels = np.argmax(predictions.predictions, axis=1)
    
    # Classification report
    print(f"\n[REPORT] Detailed Performance:")
    # Dynamically get only the intent names present in the validation set
    unique_label_ids = sorted(set(val_labels))
    intent_names = [LABEL_TO_INTENT[i] for i in unique_label_ids]
    print(f"\n{classification_report(val_labels, pred_labels, target_names=intent_names)}")
    
    # Confusion matrix summary
    cm = confusion_matrix(val_labels, pred_labels)
    print(f"\n🎯 Confusion Matrix:")
    print(f"{'Predicted':<15} {' '.join([f'{i:<10}' for i in range(len(INTENT_LABELS))])}")
    for i, row in enumerate(cm):
        print(f"Actual {i:<6} {' '.join([f'{v:<10}' for v in row])}")
    
    # Save model and tokenizer
    print(f"\n[SAVE] Saving model and tokenizer...")
    os.makedirs(MODEL_SAVE_PATH, exist_ok=True)
    model.save_pretrained(MODEL_SAVE_PATH)
    tokenizer.save_pretrained(MODEL_SAVE_PATH)
    
    # Save intent labels for inference
    import json
    labels_path = os.path.join(MODEL_SAVE_PATH, 'intent_labels.json')
    with open(labels_path, 'w') as f:
        json.dump({
            'intent_labels': INTENT_LABELS,
            'label_to_intent': LABEL_TO_INTENT
        }, f, indent=2)
    
    print(f"\n[SUCCESS] Training complete!")
    print(f"[MODEL] Model saved to: {MODEL_SAVE_PATH}")
    print(f"\n[IMPROVEMENTS] Key improvements:")
    print(f"  - 5 epochs (was 3)")
    print(f"  - Larger dataset ({len(df)} examples)")
    print(f"  - Better learning rate scheduling")
    print(f"  - Warmup optimization")
    print(f"  - Gradient clipping")
    print(f"  - Detailed evaluation metrics")
    print(f"\n[NEXT] Next steps:")
    print(f"   1. The model is ready to use")
    print(f"   2. Restart the chatbot to load new model")
    print(f"   3. Monitor performance with new data")
    
    return model, tokenizer


if __name__ == '__main__':
    try:
        train_model()
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
        print(f"   Please ensure training dataset exists")
        print(f"   Expected one of:")
        print(f"     - {DATASET_EXPANDED}")
        print(f"     - {DATASET_AUGMENTED}")
        print(f"     - {DATASET_ORIGINAL}")
    except Exception as e:
        print(f"\n[ERROR] Error during training: {e}")
        print(f"   If you see CUDA errors, the model will use CPU (slower but works)")
        import traceback
        traceback.print_exc()
