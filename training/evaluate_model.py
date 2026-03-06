"""
Model Evaluation Script
=======================
Evaluate trained intent classifier on test data.

Shows:
- Overall accuracy
- Precision, recall, F1 per intent
- Confusion matrix
- Example predictions
- Performance by intent

Usage:
    python training/evaluate_model.py
"""

import os
import json
import pandas as pd
import numpy as np
import torch
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report, 
    confusion_matrix, 
    accuracy_score,
    precision_recall_fscore_support
)
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification

# Paths
DATASET_EXPANDED = os.path.join(os.path.dirname(__file__), 'intent_dataset_expanded.csv')
MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'ai_models', 'saved_model')

# Device
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"[GPU/CPU]  Using device: {device}")

class ModelEvaluator:
    def __init__(self, model_path):
        print(f"\n[MODEL] Loading trained model from: {model_path}")
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found at {model_path}")
        
        # Load tokenizer
        self.tokenizer = DistilBertTokenizer.from_pretrained(model_path)
        
        # Load model
        self.model = DistilBertForSequenceClassification.from_pretrained(model_path)
        self.model.to(device)
        self.model.eval()
        
        # Load intent labels
        labels_path = os.path.join(model_path, 'intent_labels.json')
        with open(labels_path, 'r') as f:
            labels_data = json.load(f)
        
        self.intent_labels = labels_data['intent_labels']
        self.label_to_intent = labels_data['label_to_intent']
        
        print(f"✅ Model loaded successfully")
        print(f"📊 Intents: {', '.join(self.intent_labels.keys())}")
    
    def predict(self, text):
        """Predict intent for single text"""
        encoding = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=128,
            padding='max_length',
            truncation=True,
            return_tensors='pt'
        )
        
        input_ids = encoding['input_ids'].to(device)
        attention_mask = encoding['attention_mask'].to(device)
        
        with torch.no_grad():
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
        
        logits = outputs.logits
        pred_label = torch.argmax(logits, dim=1).item()
        confidence = torch.nn.functional.softmax(logits, dim=1)[0][pred_label].item()
        
        return pred_label, confidence
    
    def predict_batch(self, texts):
        """Predict intents for multiple texts"""
        predictions = []
        confidences = []
        
        for text in texts:
            pred, conf = self.predict(text)
            predictions.append(pred)
            confidences.append(conf)
        
        return predictions, confidences


def main():
    print("="*70)
    print("📊 MODEL EVALUATION")
    print("="*70)
    
    # Load evaluator
    try:
        evaluator = ModelEvaluator(MODEL_PATH)
    except Exception as e:
        print(f"\n❌ Error loading model: {e}")
        return
    
    # Load dataset
    print(f"\n📂 Loading test dataset...")
    if not os.path.exists(DATASET_EXPANDED):
        print(f"❌ Dataset not found: {DATASET_EXPANDED}")
        return
    
    df = pd.read_csv(DATASET_EXPANDED)
    print(f"✅ Loaded {len(df)} examples")
    
    # Prepare data
    texts = df['text'].tolist()
    intents = df['intent'].tolist()
    true_labels = [evaluator.intent_labels[intent] for intent in intents]
    
    # Split for evaluation (use validation split)
    _, test_texts, _, test_labels = train_test_split(
        texts, true_labels,
        test_size=0.2,
        random_state=42,
        stratify=true_labels
    )
    
    print(f"📊 Test set size: {len(test_texts)} examples")
    
    # Make predictions
    print(f"\n🔮 Making predictions...")
    predictions, confidences = evaluator.predict_batch(test_texts)
    
    # Calculate metrics
    print(f"\n" + "="*70)
    print(f"📈 OVERALL PERFORMANCE")
    print(f"="*70)
    
    accuracy = accuracy_score(test_labels, predictions)
    print(f"\n🎯 Overall Accuracy: {accuracy:.2%}")
    
    # Per-intent metrics
    print(f"\n" + "="*70)
    print(f"📊 PER-INTENT PERFORMANCE")
    print(f"="*70)
    
    precision, recall, f1, support = precision_recall_fscore_support(
        test_labels, predictions, average=None
    )
    
    print(f"\n{'Intent':<20} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Support':<8}")
    print("-" * 70)
    
    for idx, label_id_str in enumerate(sorted(evaluator.label_to_intent.keys())):
        label_id = int(label_id_str)
        intent = evaluator.label_to_intent[label_id_str]
        print(f"{intent:<20} {precision[idx]:>10.2%}  {recall[idx]:>10.2%}  {f1[idx]:>10.2%}  {support[idx]:>6}")
    
    # Classification report
    print(f"\n" + "="*70)
    print(f"📋 DETAILED CLASSIFICATION REPORT")
    print(f"="*70 + "\n")
    
    target_names = [evaluator.label_to_intent[str(i)] for i in sorted(evaluator.label_to_intent.keys())]
    print(classification_report(test_labels, predictions, target_names=target_names))
    
    # Confusion matrix
    print(f"="*70)
    print(f"🔀 CONFUSION MATRIX")
    print(f"="*70)
    
    cm = confusion_matrix(test_labels, predictions)
    
    # Pretty print confusion matrix
    max_intent_len = max(len(name) for name in target_names)
    header = "Predicted →"
    print(f"\n{'Actual':<{max_intent_len + 2}} {header:<60}")
    print(f"{' ':<{max_intent_len + 2}} " + " ".join([f"{name:>8}" for name in target_names]))
    print("-" * (max_intent_len + 2 + len(target_names) * 10))
    
    for i, intent in enumerate(target_names):
        row_str = f"{intent:<{max_intent_len + 2}} " + " ".join([f"{cm[i][j]:>8}" for j in range(len(target_names))])
        print(row_str)
    
    # Correct vs incorrect predictions
    correct = sum(1 for t, p in zip(test_labels, predictions) if t == p)
    incorrect = len(test_labels) - correct
    
    print(f"\n" + "="*70)
    print(f"✅ CORRECT: {correct}/{len(test_labels)} ({correct/len(test_labels):.2%})")
    print(f"❌ INCORRECT: {incorrect}/{len(test_labels)} ({incorrect/len(test_labels):.2%})")
    print(f"="*70)
    
    # Show some examples
    print(f"\n" + "="*70)
    print(f"💡 SAMPLE PREDICTIONS")
    print(f"="*70)
    
    # Correct predictions
    print(f"\n✅ Correct Predictions (showing 5):")
    print("-" * 70)
    shown = 0
    for text, true_label, pred, conf in zip(test_texts, test_labels, predictions, confidences):
        if true_label == pred and shown < 5:
            true_intent = evaluator.label_to_intent[str(true_label)]
            print(f'Text: "{text}"')
            print(f'Predicted: {true_intent} ({conf:.2%} confidence)')
            print()
            shown += 1
    
    # Incorrect predictions
    print(f"\n❌ Incorrect Predictions (showing 5):")
    print("-" * 70)
    shown = 0
    for text, true_label, pred, conf in zip(test_texts, test_labels, predictions, confidences):
        if true_label != pred and shown < 5:
            true_intent = evaluator.label_to_intent[str(true_label)]
            pred_intent = evaluator.label_to_intent[str(pred)]
            print(f'Text: "{text}"')
            print(f'True: {true_intent}')
            print(f'Predicted: {pred_intent} ({conf:.2%} confidence)')
            print()
            shown += 1
    
    # Summary
    print(f"\n" + "="*70)
    print(f"✨ EVALUATION COMPLETE")
    print(f"="*70)
    print(f"\n📌 Key Findings:")
    
    # Identify best and worst intents
    f1_scores = {}
    for idx, label_id_str in enumerate(sorted(evaluator.label_to_intent.keys())):
        intent = evaluator.label_to_intent[label_id_str]
        f1_scores[intent] = f1[idx]
    
    best_intent = max(f1_scores, key=f1_scores.get)
    worst_intent = min(f1_scores, key=f1_scores.get)
    
    print(f"  • Best performing: {best_intent} (F1: {f1_scores[best_intent]:.2%})")
    print(f"  • Needs improvement: {worst_intent} (F1: {f1_scores[worst_intent]:.2%})")
    print(f"  • Overall accuracy: {accuracy:.2%}")
    
    if accuracy >= 0.90:
        print(f"\n  🎉 Excellent performance! Model is ready for production.")
    elif accuracy >= 0.80:
        print(f"\n  👍 Good performance. Consider adding more training data for weak intents.")
    else:
        print(f"\n  📚 Fair performance. Add more training examples, especially for {worst_intent}.")
    
    print(f"\n" + "="*70)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
