"""
IMPROVED Intent Classifier Training Script - Production Version
================================================================
This version addresses the 65% accuracy and low confidence issues through:

1. Much larger training dataset (750+ examples vs 171)
2. Better class weight balancing for imbalanced data
3. Optimized hyperparameters (more epochs, better learning rate)
4. Improved model architecture decisions
5. Better preprocessing and tokenization
6. Enhanced evaluation during training

Key Improvements:
- 5 epochs instead of 3 (more training time)
- Class weights to handle imbalanced data
- Warmup ratio instead of fixed steps
- Better batch size (32 instead of 16)
- Longer max_length (128 tokens instead of 64)
- Learning rate 2e-5 (better for fine-tuning)
- Gradient accumulation for effective larger batch
- Early stopping to prevent overfitting
- Detailed metrics logging

Usage:
    python training/train_intent_model_improved.py

Expected Results:
   - Accuracy: 85-95% (vs previous 65%)
   - Confidence: 60-95% (vs previous 18-29%)
   - Better recall for create_order and remove_item
   - Less confusion between intents
"""

import os
import pandas as pd
import numpy as np
import json
import torch
from collections import Counter
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support
from sklearn.utils.class_weight import compute_class_weight
from transformers import (
    DistilBertTokenizer,
    DistilBertForSequenceClassification,
    Trainer,
    TrainingArguments,
    EarlyStoppingCallback
)
from torch.utils.data import Dataset

# ===========================================================================
# CONFIGURATION
# ===========================================================================

# Paths
DATASET_PATH = os.path.join(os.path.dirname(__file__), 'intent_dataset_production.csv')
MODEL_SAVE_PATH = os.path.join(os.path.dirname(__file__), '..', 'ai_models', 'saved_model')

# Intent labels (DO NOT CHANGE - keep your existing labels)
INTENT_LABELS = {
    'create_order': 0,
    'add_item': 1,
    'update_item': 2,
    'remove_item': 3,
    'complete_order': 4,
    'none': 5
}
LABEL_TO_INTENT = {v: k for k, v in INTENT_LABELS.items()}

# Training hyperparameters (OPTIMIZED FOR BETTER PERFORMANCE)
TRAINING_CONFIG = {
    'num_epochs': 6,                    # Increased from 3 to 6 for better learning
    'batch_size': 32,                   # Increased from 16 to 32 for stability
    'learning_rate': 2e-5,              # Optimized for DistilBERT fine-tuning
    'warmup_ratio': 0.1,                # 10% of training for warmup
    'weight_decay': 0.01,               # L2 regularization
    'max_length': 128,                  # Increased from 64 to handle longer inputs
    'gradient_accumulation_steps': 2,   # Effective batch size = 32 * 2 = 64
    'eval_strategy': 'epoch',           # Evaluate after each epoch
    'save_strategy': 'epoch',           # Save after each epoch
    'fp16': False,                      # Mixed precision (set True if GPU available)
    'seed': 42                          # Reproducibility
}

# ===========================================================================
# DATASET CLASS WITH IMPROVED PREPROCESSING
# ===========================================================================

class IntentDataset(Dataset):
    """
    Custom dataset for intent classification with improved preprocessing.
    
    Features:
    - Lowercases text for consistency
    - Strips extra whitespace
    - Handles longer sequences (128 tokens)
    - Better tokenization parameters
    """
    
    def __init__(self, texts, labels, tokenizer, max_length=128):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        # Preprocess text: lowercase and strip whitespace
        text = str(self.texts[idx]).lower().strip()
        label = self.labels[idx]
        
        # Tokenize with padding and truncation
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

# ===========================================================================
# DATA LOADING AND PREPROCESSING
# ===========================================================================

def load_and_prepare_dataset():
    """
    Load dataset and prepare for training with class weight calculation.
    
    Returns:
        df: DataFrame with text and labels
        class_weights: Tensor of class weights for imbalanced data
    """
    print(f"\n📂 Loading production dataset from: {DATASET_PATH}")
    
    # Check if file exists
    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}\n"
            f"Please ensure intent_dataset_production.csv exists."
        )
    
    # Load dataset
    df = pd.read_csv(DATASET_PATH)
    
    # Convert intent strings to numeric labels
    df['label'] = df['intent'].map(INTENT_LABELS)
    
    # Check for missing labels
    if df['label'].isnull().any():
        print("⚠️  Warning: Some intents not recognized. Check INTENT_LABELS mapping.")
        df = df.dropna(subset=['label'])
    
    # Convert labels to integers
    df['label'] = df['label'].astype(int)
    
    print(f"✅ Loaded {len(df)} total examples")
    print(f"\n📊 Intent distribution:")
    intent_counts = df['intent'].value_counts()
    for intent, count in intent_counts.items():
        percentage = (count / len(df)) * 100
        print(f"   {intent:<20} {count:>4} examples ({percentage:>5.1f}%)")
    
    # Calculate class weights for imbalanced data
    # This helps the model pay more attention to underrepresented classes
    class_weights = compute_class_weight(
        class_weight='balanced',
        classes=np.unique(df['label']),
        y=df['label']
    )
    class_weights = torch.tensor(class_weights, dtype=torch.float)
    
    print(f"\n⚖️  Class weights (to handle imbalance):")
    for idx, weight in enumerate(class_weights):
        intent = LABEL_TO_INTENT[idx]
        print(f"   {intent:<20} weight: {weight:.3f}")
    
    return df, class_weights

# ===========================================================================
# CUSTOM TRAINER WITH CLASS WEIGHTS
# ===========================================================================

class WeightedTrainer(Trainer):
    """
    Custom trainer that applies class weights to the loss function.
    This helps improve performance on underrepresented classes.
    """
    
    def __init__(self, class_weights=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights
    
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.get("labels")
        outputs = model(**inputs)
        logits = outputs.get('logits')
        
        # Apply class weights to loss
        loss_fct = torch.nn.CrossEntropyLoss(weight=self.class_weights)
        loss = loss_fct(logits.view(-1, self.model.config.num_labels), labels.view(-1))
        
        return (loss, outputs) if return_outputs else loss

# ===========================================================================
# TRAINING FUNCTION
# ===========================================================================

def train_model():
    """
    Main training function with improved pipeline.
    
    Steps:
    1. Load and prepare data with class weights
    2. Split into train/validation sets (stratified)
    3. Initialize tokenizer and model
    4. Create datasets with improved preprocessing
    5. Set up training arguments with better hyperparameters
    6. Train with class weight balancing
    7. Evaluate and save model
    8. Test on sample predictions
    """
    
    print("\n" + "="*70)
    print("🚀 IMPROVED INTENT CLASSIFIER TRAINING - Production Version")
    print("="*70)
    print(f"\nTarget: 85-95% accuracy (vs previous 65%)")
    print(f"Target: 60-95% confidence (vs previous 18-29%)")
    print(f"Target: Better recall for all intents\n")
    
    # Load data with class weights
    df, class_weights = load_and_prepare_dataset()
    
    # Stratified split to maintain class distribution
    # 80% train, 20% validation
    print(f"\n📚 Splitting dataset (stratified 80/20 split)...")
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        df['text'].tolist(),
        df['label'].tolist(),
        test_size=0.2,
        random_state=TRAINING_CONFIG['seed'],
        stratify=df['label']  # Maintain class distribution in both sets
    )
    
    print(f"   Training set:   {len(train_texts)} examples")
    print(f"   Validation set: {len(val_texts)} examples")
    
    # Check distribution in train set
    train_dist = Counter(train_labels)
    print(f"\n📊 Training set distribution:")
    for label_id in sorted(train_dist.keys()):
        intent = LABEL_TO_INTENT[label_id]
        count = train_dist[label_id]
        percentage = (count / len(train_labels)) * 100
        print(f"   {intent:<20} {count:>4} ({percentage:>5.1f}%)")
    
    # Load tokenizer and model
    print(f"\n🤖 Loading DistilBERT model and tokenizer...")
    tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')
    model = DistilBertForSequenceClassification.from_pretrained(
        'distilbert-base-uncased',
        num_labels=len(INTENT_LABELS)
    )
    
    print("✅ Model loaded successfully")
    
    # Create datasets with improved preprocessing
    print(f"\n📦 Creating datasets with max_length={TRAINING_CONFIG['max_length']}...")
    train_dataset = IntentDataset(
        train_texts, 
        train_labels, 
        tokenizer, 
        max_length=TRAINING_CONFIG['max_length']
    )
    val_dataset = IntentDataset(
        val_texts, 
        val_labels, 
        tokenizer, 
        max_length=TRAINING_CONFIG['max_length']
    )
    
    # Training arguments with optimized hyperparameters
    print(f"\n⚙️  Setting up training configuration...")
    print(f"   Epochs: {TRAINING_CONFIG['num_epochs']}")
    print(f"   Batch size: {TRAINING_CONFIG['batch_size']}")
    print(f"   Learning rate: {TRAINING_CONFIG['learning_rate']}")
    print(f"   Effective batch size: {TRAINING_CONFIG['batch_size'] * TRAINING_CONFIG['gradient_accumulation_steps']}")
    
    training_args = TrainingArguments(
        output_dir=MODEL_SAVE_PATH,
        num_train_epochs=TRAINING_CONFIG['num_epochs'],
        per_device_train_batch_size=TRAINING_CONFIG['batch_size'],
        per_device_eval_batch_size=TRAINING_CONFIG['batch_size'],
        learning_rate=TRAINING_CONFIG['learning_rate'],
        warmup_ratio=TRAINING_CONFIG['warmup_ratio'],
        weight_decay=TRAINING_CONFIG['weight_decay'],
        gradient_accumulation_steps=TRAINING_CONFIG['gradient_accumulation_steps'],
        logging_dir='./logs',
        logging_steps=10,
        eval_strategy=TRAINING_CONFIG['eval_strategy'],
        save_strategy=TRAINING_CONFIG['save_strategy'],
        load_best_model_at_end=True,
        metric_for_best_model='eval_loss',
        save_total_limit=2,  # Keep only 2 best checkpoints
        seed=TRAINING_CONFIG['seed'],
        fp16=TRAINING_CONFIG['fp16'],
        report_to='none'  # Disable wandb/tensorboard logging
    )
    
    # Move class weights to same device as model
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    class_weights = class_weights.to(device)
    
    print(f"\n💻 Using device: {device}")
    
    # Initialize custom trainer with class weights
    trainer = WeightedTrainer(
        class_weights=class_weights,
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)]
    )
    
    # Train
    print(f"\n🏋️  Training model...")
    print(f"   This will take 10-20 minutes depending on your hardware")
    print(f"   Watch for improving validation loss each epoch\n")
    
    trainer.train()
    
    # Evaluate
    print(f"\n📊 Final evaluation on validation set...")
    results = trainer.evaluate()
    print(f"   Validation Loss: {results['eval_loss']:.4f}")
    
    # Save model and tokenizer
    print(f"\n💾 Saving model to: {MODEL_SAVE_PATH}")
    model.save_pretrained(MODEL_SAVE_PATH)
    tokenizer.save_pretrained(MODEL_SAVE_PATH)
    
    # Save intent label mapping
    intent_label_path = os.path.join(MODEL_SAVE_PATH, "intent_labels.json")
    with open(intent_label_path, "w") as f:
        json.dump(LABEL_TO_INTENT, f, indent=2)
    print(f"   Intent label mapping saved")
    
    # Save training config for reference
    config_path = os.path.join(MODEL_SAVE_PATH, "training_config.json")
    with open(config_path, "w") as f:
        json.dump(TRAINING_CONFIG, f, indent=2)
    print(f"   Training config saved")
    
    # Test predictions on sample inputs
    print(f"\n🧪 Testing predictions on sample inputs:")
    print(f"   (These should show higher confidence than before)\n")
    
    test_samples = [
        # create_order examples
        "create order",
        "start new order",
        "open order please",
        
        # add_item examples
        "add 3 chairs",
        "i want to add 5 monitors",
        "put 2 tables in order",
        
        # update_item examples
        "change quantity to 5",
        "update item 1",
        "modify the first item",
        
        # remove_item examples
        "remove the chairs",
        "delete item 2",
        "take out the lamp",
        
        # complete_order examples
        "complete order",
        "finish my order",
        "submit it now",
        
        # none examples
        "hello",
        "whats the weather",
        "show me dashboard"
    ]
    
    model.eval()
    model.to(device)
    
    correct_predictions = 0
    high_confidence_count = 0
    
    for text in test_samples:
        inputs = tokenizer(
            text.lower(), 
            return_tensors='pt', 
            padding=True, 
            truncation=True, 
            max_length=TRAINING_CONFIG['max_length']
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = model(**inputs)
            prediction = torch.argmax(outputs.logits, dim=1).item()
            intent = LABEL_TO_INTENT[prediction]
            confidence = torch.softmax(outputs.logits, dim=1)[0][prediction].item()
            
            # Color code confidence
            if confidence >= 0.7:
                conf_color = "✅"
                high_confidence_count += 1
            elif confidence >= 0.5:
                conf_color = "⚠️"
            else:
                conf_color = "❌"
                
            print(f"   {conf_color} '{text:<30}' → {intent:<15} (confidence: {confidence:.1%})")
    
    print(f"\n📈 Test results:")
    print(f"   High confidence (≥70%): {high_confidence_count}/{len(test_samples)} predictions")
    
    print(f"\n✅ Training complete!")
    print(f"📁 Model saved to: {MODEL_SAVE_PATH}")
    print(f"\n💡 Next steps:")
    print(f"   1. Run evaluation: python training/evaluate_model_improved.py")
    print(f"   2. Expected: 85-95% accuracy, 60-95% confidence")
    print(f"   3. If results good, update your chatbot to use this model")
    print(f"   4. The model will automatically fallback to OpenAI for low confidence")
    
    return model, tokenizer

# ===========================================================================
# MAIN EXECUTION
# ===========================================================================

if __name__ == '__main__':
    try:
        train_model()
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
    except Exception as e:
        print(f"\n❌ Error during training: {e}")
        print(f"   Full error:")
        import traceback
        traceback.print_exc()
