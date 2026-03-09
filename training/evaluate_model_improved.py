"""
IMPROVED Intent Classifier Evaluation Script - Production Version
==================================================================
This script provides comprehensive evaluation metrics to assess model quality.

Features:
1. Overall accuracy, precision, recall, F1 scores
2. Per-intent detailed metrics (precision, recall, F1 for each intent)
3. Confidence distribution analysis (low/medium/high confidence counts)
4. Low-confidence example identification (to find problematic inputs)
5. Confusion matrix with detailed error analysis
6. Example predictions showing where model fails
7. Production readiness assessment

Expected Results with Improved Model:
- Accuracy: 85-95% (vs previous 65%)
- create_order recall: 80-95% (vs previous 20%)
- remove_item recall: 80-95% (vs previous 20%)
- Average confidence: 60-95% (vs previous 18-29%)
- Minimal confusion between intents

Usage:
    python training/evaluate_model_improved.py
"""

import os
import pandas as pd
import numpy as np
import json
import torch
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    confusion_matrix,
    classification_report
)
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
from collections import defaultdict, Counter

# ===========================================================================
# CONFIGURATION
# ===========================================================================

# Paths
DATASET_PATH = os.path.join(os.path.dirname(__file__), 'intent_dataset_production.csv')
MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'ai_models', 'saved_model')
INTENT_LABEL_PATH = os.path.join(MODEL_PATH, "intent_labels.json")

# Confidence thresholds for analysis
CONFIDENCE_THRESHOLDS = {
    'high': 0.70,      # ≥70% = high confidence, good to use
    'medium': 0.50,    # 50-70% = medium confidence, acceptable but monitor
    'low': 0.50        # <50% = low confidence, should fallback to OpenAI
}

# Intent labels (same as training)
INTENT_LABELS = {
    'create_order': 0,
    'add_item': 1,
    'update_item': 2,
    'remove_item': 3,
    'complete_order': 4,
    'none': 5
}

# ===========================================================================
# LOAD MODEL AND DATA
# ===========================================================================

def load_model_and_tokenizer():
    """Load trained model, tokenizer, and intent label mapping."""
    print(f"\n📂 Loading model from: {MODEL_PATH}")
    
    # Check if model exists
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Model not found: {MODEL_PATH}\n"
            f"Please train the model first using train_intent_model_improved.py"
        )
    
    # Load tokenizer and model
    tokenizer = DistilBertTokenizer.from_pretrained(MODEL_PATH)
    model = DistilBertForSequenceClassification.from_pretrained(MODEL_PATH)
    
    # Load intent label mapping
    with open(INTENT_LABEL_PATH, 'r') as f:
        label_to_intent = json.load(f)
    # Convert keys to int (JSON stores keys as strings)
    label_to_intent = {int(k): v for k, v in label_to_intent.items()}
    
    print("✅ Model and tokenizer loaded successfully")
    
    return model, tokenizer, label_to_intent

def load_test_data():
    """Load and prepare test dataset."""
    print(f"\n📂 Loading test dataset from: {DATASET_PATH}")
    
    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")
    
    # Load data
    df = pd.read_csv(DATASET_PATH)
    df['label'] = df['intent'].map(INTENT_LABELS)
    df['label'] = df['label'].astype(int)
    
    # Use same split as training (20% for validation/test)
    _, test_texts, _, test_labels = train_test_split(
        df['text'].tolist(),
        df['label'].tolist(),
        test_size=0.2,
        random_state=42,
        stratify=df['label']
    )
    
    print(f"✅ Loaded {len(test_texts)} test examples")
    
    return test_texts, test_labels

# ===========================================================================
# PREDICTION FUNCTION
# ===========================================================================

def predict_with_confidence(texts, model, tokenizer, device, max_length=128):
    """
    Make predictions on texts and return predictions, confidences, and probabilities.
    
    Returns:
        predictions: List of predicted label IDs
        confidences: List of confidence scores (0-1) for predicted labels
        all_probs: List of probability distributions for all labels
    """
    model.eval()
    model.to(device)
    
    predictions = []
    confidences = []
    all_probs = []
    
    for text in texts:
        # Tokenize input
        inputs = tokenizer(
            text.lower().strip(),
            return_tensors='pt',
            padding=True,
            truncation=True,
            max_length=max_length
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        # Predict
        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=1)[0]
            
            prediction = torch.argmax(probs).item()
            confidence = probs[prediction].item()
            
            predictions.append(prediction)
            confidences.append(confidence)
            all_probs.append(probs.cpu().numpy())
    
    return predictions, confidences, all_probs

# ===========================================================================
# EVALUATION METRICS
# ===========================================================================

def calculate_overall_metrics(y_true, y_pred, label_to_intent):
    """Calculate and print overall accuracy and per-intent metrics."""
    print("\n" + "="*70)
    print("📊 OVERALL METRICS")
    print("="*70)
    
    # Overall accuracy
    accuracy = accuracy_score(y_true, y_pred)
    print(f"\n🎯 Overall Accuracy: {accuracy:.2%}")
    
    # Per-intent metrics
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, average=None, zero_division=0
    )
    
    print(f"\n📋 Per-Intent Metrics:")
    print(f"{'Intent':<20} {'Precision':<12} {'Recall':<12} {'F1-Score':<12} {'Support'}")
    print("-" * 70)
    
    for idx in range(len(label_to_intent)):
        intent = label_to_intent[idx]
        print(f"{intent:<20} {precision[idx]:>10.1%}  {recall[idx]:>10.1%}  {f1[idx]:>10.1%}  {support[idx]:>7}")
    
    # Macro averages (unweighted average across all intents)
    macro_precision = np.mean(precision)
    macro_recall = np.mean(recall)
    macro_f1 = np.mean(f1)
    
    print("-" * 70)
    print(f"{'Macro Average':<20} {macro_precision:>10.1%}  {macro_recall:>10.1%}  {macro_f1:>10.1%}")
    
    # Assessment
    print(f"\n💡 Assessment:")
    if accuracy >= 0.85:
        print(f"   ✅ Excellent accuracy ({accuracy:.1%}) - Production ready!")
    elif accuracy >= 0.75:
        print(f"   ⚠️  Good accuracy ({accuracy:.1%}) - Acceptable but can improve")
    else:
        print(f"   ❌ Poor accuracy ({accuracy:.1%}) - Needs more training data or tuning")
    
    # Check weak intents (recall < 70%)
    weak_intents = [label_to_intent[i] for i, r in enumerate(recall) if r < 0.70]
    if weak_intents:
        print(f"   ⚠️  Weak intents (recall <70%): {', '.join(weak_intents)}")
    else:
        print(f"   ✅ All intents have strong recall (≥70%)")

def analyze_confidence_distribution(confidences, y_true, y_pred, label_to_intent):
    """Analyze confidence score distribution."""
    print("\n" + "="*70)
    print("🎲 CONFIDENCE DISTRIBUTION ANALYSIS")
    print("="*70)
    
    confidences = np.array(confidences)
    
    # Overall confidence stats
    print(f"\nConfidence Statistics:")
    print(f"   Mean:   {np.mean(confidences):.1%}")
    print(f"   Median: {np.median(confidences):.1%}")
    print(f"   Min:    {np.min(confidences):.1%}")
    print(f"   Max:    {np.max(confidences):.1%}")
    
    # Confidence buckets
    high_conf_mask = confidences >= CONFIDENCE_THRESHOLDS['high']
    med_conf_mask = (confidences >= CONFIDENCE_THRESHOLDS['low']) & (confidences < CONFIDENCE_THRESHOLDS['high'])
    low_conf_mask = confidences < CONFIDENCE_THRESHOLDS['low']
    
    high_count = np.sum(high_conf_mask)
    med_count = np.sum(med_conf_mask)
    low_count = np.sum(low_conf_mask)
    total = len(confidences)
    
    print(f"\nConfidence Distribution:")
    print(f"   High (≥{CONFIDENCE_THRESHOLDS['high']:.0%}):  {high_count:>4} ({high_count/total:>5.1%}) ✅")
    print(f"   Medium ({CONFIDENCE_THRESHOLDS['low']:.0%}-{CONFIDENCE_THRESHOLDS['high']:.0%}): {med_count:>4} ({med_count/total:>5.1%}) ⚠️")
    print(f"   Low (<{CONFIDENCE_THRESHOLDS['low']:.0%}):    {low_count:>4} ({low_count/total:>5.1%}) ❌")
    
    # Accuracy by confidence level
    print(f"\nAccuracy by Confidence Level:")
    if high_count > 0:
        high_acc = accuracy_score(
            np.array(y_true)[high_conf_mask],
            np.array(y_pred)[high_conf_mask]
        )
        print(f"   High confidence:   {high_acc:.1%}")
    if med_count > 0:
        med_acc = accuracy_score(
            np.array(y_true)[med_conf_mask],
            np.array(y_pred)[med_conf_mask]
        )
        print(f"   Medium confidence: {med_acc:.1%}")
    if low_count > 0:
        low_acc = accuracy_score(
            np.array(y_true)[low_conf_mask],
            np.array(y_pred)[low_conf_mask]
        )
        print(f"   Low confidence:    {low_acc:.1%}")
    
    # Assessment
    print(f"\n💡 Assessment:")
    if high_count / total >= 0.70:
        print(f"   ✅ Excellent: {high_count/total:.1%} predictions are high confidence")
    elif high_count / total >= 0.50:
        print(f"   ⚠️  Good: {high_count/total:.1%} predictions are high confidence")
    else:
        print(f"   ❌ Poor: Only {high_count/total:.1%} predictions are high confidence")
    
    if low_count > 0:
        print(f"   ⚠️  {low_count} predictions will fallback to OpenAI (<{CONFIDENCE_THRESHOLDS['low']:.0%} confidence)")

def identify_low_confidence_examples(texts, y_true, y_pred, confidences, label_to_intent, top_n=15):
    """Identify and display lowest confidence predictions."""
    print("\n" + "="*70)
    print("🔍 LOW CONFIDENCE EXAMPLES (potential problem areas)")
    print("="*70)
    
    # Sort by confidence (lowest first)
    sorted_indices = np.argsort(confidences)[:top_n]
    
    print(f"\nShowing {top_n} lowest confidence predictions:")
    print(f"(These examples may need fallback to OpenAI)\n")
    
    for i, idx in enumerate(sorted_indices, 1):
        text = texts[idx]
        true_intent = label_to_intent[y_true[idx]]
        pred_intent = label_to_intent[y_pred[idx]]
        conf = confidences[idx]
        
        # Color code correctness
        if true_intent == pred_intent:
            status = "✅ Correct"
        else:
            status = "❌ Wrong"
        
        print(f"{i:>2}. [{conf:>5.1%}] {status}")
        print(f"    Text: \"{text}\"")
        print(f"    True: {true_intent:<15} | Predicted: {pred_intent}")
        print()

def analyze_confusion_matrix(y_true, y_pred, label_to_intent):
    """Analyze confusion matrix to identify common errors."""
    print("\n" + "="*70)
    print("🔀 CONFUSION MATRIX ANALYSIS")
    print("="*70)
    
    cm = confusion_matrix(y_true, y_pred)
    
    print(f"\nConfusion Matrix:")
    print(f"(Rows = True Intent, Columns = Predicted Intent)\n")
    
    # Header
    intent_names = [label_to_intent[i] for i in range(len(label_to_intent))]
    header = "True \\ Pred".ljust(15) + "  ".join(f"{name[:6]:>6}" for name in intent_names)
    print(header)
    print("-" * len(header))
    
    # Rows
    for i, intent in enumerate(intent_names):
        row = f"{intent[:13]:<15}"
        for j in range(len(intent_names)):
            count = cm[i][j]
            if i == j:  # Diagonal (correct predictions)
                row += f"  {count:>6}"
            else:  # Off-diagonal (errors)
                if count > 0:
                    row += f"  {count:>6}"  # Show errors
                else:
                    row += f"  {'':>6}"
        print(row)
    
    # Find most common confusions (off-diagonal with highest counts)
    print(f"\n🔄 Most Common Confusions:")
    confusions = []
    for i in range(len(intent_names)):
        for j in range(len(intent_names)):
            if i != j and cm[i][j] > 0:
                confusions.append((cm[i][j], intent_names[i], intent_names[j]))
    
    confusions.sort(reverse=True)
    
    if confusions:
        for count, true_intent, pred_intent in confusions[:5]:  # Top 5 confusions
            print(f"   {count:>3}x  {true_intent:<15} → {pred_intent:<15}")
    else:
        print(f"   ✅ No significant confusions (perfect classification!)")

def show_example_predictions(texts, y_true, y_pred, confidences, label_to_intent, samples_per_intent=3):
    """Show example predictions for each intent."""
    print("\n" + "="*70)
    print("📝 EXAMPLE PREDICTIONS PER INTENT")
    print("="*70)
    
    # Group by true intent
    by_intent = defaultdict(list)
    for idx in range(len(texts)):
        true_intent = label_to_intent[y_true[idx]]
        by_intent[true_intent].append(idx)
    
    for intent in sorted(by_intent.keys()):
        indices = by_intent[intent][:samples_per_intent]
        
        print(f"\n{intent.upper()} Examples:")
        for idx in indices:
            text = texts[idx]
            pred_intent = label_to_intent[y_pred[idx]]
            conf = confidences[idx]
            
            if intent == pred_intent:
                status = "✅"
            else:
                status = f"❌ (predicted: {pred_intent})"
            
            print(f"   [{conf:>5.1%}] {status} \"{text}\"")

def assess_production_readiness(accuracy, confidences, recall_scores):
    """Provide overall production readiness assessment."""
    print("\n" + "="*70)
    print("🚀 PRODUCTION READINESS ASSESSMENT")
    print("="*70)
    
    # Criteria
    criteria = {
        'Accuracy ≥85%': accuracy >= 0.85,
        'All intent recall ≥70%': np.all(recall_scores >= 0.70),
        'Mean confidence ≥60%': np.mean(confidences) >= 0.60,
        '≥70% high confidence': np.sum(np.array(confidences) >= 0.70) / len(confidences) >= 0.70
    }
    
    print(f"\nProduction Readiness Criteria:")
    passed = 0
    for criterion, result in criteria.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status}  {criterion}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(criteria)} criteria passed")
    
    if passed == len(criteria):
        print(f"\n🎉 MODEL IS PRODUCTION READY!")
        print(f"   Deploy with confidence. Use fallback for predictions <50% confidence.")
    elif passed >= len(criteria) - 1:
        print(f"\n⚠️  MODEL IS ALMOST READY")
        print(f"   Can deploy with caution. Monitor low-confidence predictions carefully.")
    else:
        print(f"\n❌ MODEL NEEDS MORE WORK")
        print(f"   - Add more training examples for weak intents")
        print(f"   - Increase training epochs")
        print(f"   - Check for data quality issues")

# ===========================================================================
# MAIN EVALUATION FUNCTION
# ===========================================================================

def evaluate_model():
    """Main evaluation function."""
    print("\n" + "="*70)
    print("🔬 IMPROVED INTENT CLASSIFIER EVALUATION - Production Version")
    print("="*70)
    
    # Load model and data
    model, tokenizer, label_to_intent = load_model_and_tokenizer()
    test_texts, test_labels = load_test_data()
    
    # Make predictions
    print(f"\n🔮 Making predictions on {len(test_texts)} test examples...")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"💻 Using device: {device}")
    
    predictions, confidences, all_probs = predict_with_confidence(
        test_texts, model, tokenizer, device
    )
    
    print(f"✅ Predictions complete")
    
    # Run all analyses
    calculate_overall_metrics(test_labels, predictions, label_to_intent)
    analyze_confidence_distribution(confidences, test_labels, predictions, label_to_intent)
    identify_low_confidence_examples(test_texts, test_labels, predictions, confidences, label_to_intent)
    analyze_confusion_matrix(test_labels, predictions, label_to_intent)
    show_example_predictions(test_texts, test_labels, predictions, confidences, label_to_intent)
    
    # Final assessment
    _, recall, _, _ = precision_recall_fscore_support(test_labels, predictions, average=None, zero_division=0)
    accuracy = accuracy_score(test_labels, predictions)
    assess_production_readiness(accuracy, confidences, recall)
    
    print(f"\n✅ Evaluation complete!")
    print(f"\n💡 Next steps:")
    print(f"   1. If production ready: Update chatbot to use this model")
    print(f"   2. If not ready: Review low-confidence examples and add more training data")
    print(f"   3. Set confidence threshold at 50-60% for OpenAI fallback")

# ===========================================================================
# MAIN EXECUTION
# ===========================================================================

if __name__ == '__main__':
    try:
        evaluate_model()
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
    except Exception as e:
        print(f"\n❌ Error during evaluation: {e}")
        import traceback
        traceback.print_exc()
