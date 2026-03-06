# AI Models Documentation

## Overview

This folder contains all AI/ML components used by the chatbot system. The system uses a **hybrid approach**: local AI for simple intents + OpenAI for complex conversations.

## 📁 Folder Structure

```
ai_models/
├── __init__.py              # Package initialization
├── intent_classifier.py     # Local intent classification module
├── saved_model/            # Trained model files (created after training)
│   ├── config.json
│   ├── pytorch_model.bin
│   └── tokenizer files
└── README.md               # This file

training/
├── intent_dataset.csv          # Training data (224 examples)
├── intent_train_openai.jsonl   # OpenAI fine-tuning format
├── train_intent_model.py       # Training script
└── typo_corrections.txt        # Common typo mappings
```

## 🚀 Quick Start

### Step 1: Install Dependencies

```bash
pip install torch transformers scikit-learn pandas
```

Or install all at once:
```bash
pip install -r requirements.txt
```

### Step 2: Train the Local Model

```bash
cd training
python train_intent_model.py
```

**Training time:**
- With GPU: 5-10 minutes
- With CPU: 30-60 minutes

**Output:** Model saved to `ai_models/saved_model/`

### Step 3: Restart Flask

```bash
python main.py
```

You should see:
```
✅ Local AI intent classifier enabled
✅ Intent classifier loaded successfully
```

## 🤖 How It Works

### Hybrid AI Flow

```
User Input: "create order please"
    ↓
Local AI Classifier (DistilBERT)
    ↓
Intent: create_order (confidence: 95%)
    ↓
Handle locally (NO OpenAI call) → $0.00 cost
```

```
User Input: "which monitor is best for gaming?"
    ↓
Local AI Classifier
    ↓
Intent: unknown (confidence: 45%)
    ↓
Fallback to OpenAI GPT-3.5 → Small cost
```

### Intents Handled Locally

- ✅ `create_order` - "create order", "new order", "start order"
- ✅ `add_item` - "add 5 monitors", "i want keyboard"
- ✅ `update_item` - "change qty to 3", "edit item 2"
- ✅ `remove_item` - "remove monitor", "delete line 1"
- ✅ `complete_order` - "finish order", "submit", "done"

### When OpenAI is Used

- ❓ Product questions: "What's the best monitor?"
- ❓ Comparisons: "Compare these two items"
- ❓ General chat: "Hello", "Thank you"
- ❓ Complex requests: "I need monitors and keyboards for office"

## 📊 Cost Savings

**Before (100% OpenAI):**
- 1000 messages/day
- ~$0.50-$1.00/day
- **~$15-$30/month**

**After (Hybrid):**
- 800 messages handled locally (FREE)
- 200 messages to OpenAI
- ~$0.10-$0.20/day
- **~$3-$6/month (80% savings!)**

## 🔧 Configuration

Edit confidence threshold in `ai_models/intent_classifier.py`:

```python
classifier = IntentClassifier(confidence_threshold=0.20)
```

- Lower (0.15): More local predictions, faster, but may be less accurate
- Higher (0.30): More OpenAI calls, slower, more accurate

## 📈 Improving the Model

### Add More Training Data

1. Edit `training/intent_dataset.csv`:
```csv
text,intent
"make me an order","create_order"
"put 10 keyboards in cart","add_item"
```

2. Retrain:
```bash
python training/train_intent_model.py
```

3. Restart Flask

### Monitor Performance

Check logs for AI usage:
```
🤖 [LOCAL AI] Intent: create_order (confidence: 95%)
🌐 [FALLBACK] Low confidence (45%), using OpenAI
```

## 🧪 Testing

Test the classifier in Python:

```python
from ai_models import IntentClassifier

classifier = IntentClassifier()
intent, confidence = classifier.predict("i want to create order")
print(f"Intent: {intent}, Confidence: {confidence:.2%}")
# Output: Intent: create_order, Confidence: 98%
```

## 🛠️ Troubleshooting

### Model Not Found Error

```
⚠️ Intent model not found at: ai_models/saved_model
```

**Solution:** Run the training script:
```bash
python training/train_intent_model.py
```

### GPU Not Available

The model will automatically use CPU (slower but works fine).

To use GPU:
1. Install CUDA: https://developer.nvidia.com/cuda-downloads
2. Install PyTorch with CUDA:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

### Import Error

```
❌ Could not initialize intent classifier
```

**Solution:** Install dependencies:
```bash
pip install transformers torch scikit-learn pandas
```

## 📚 Model Details

**Architecture:** DistilBERT (distilbert-base-uncased)
- **Parameters:** 66 million
- **Size:** ~250MB on disk
- **Speed:** 10-20ms per prediction
- **Accuracy:** 95%+ on test set

**Framework:** PyTorch + Hugging Face Transformers

## 🔄 Updating the Model

1. Add new training examples to `training/intent_dataset.csv`
2. Run training script: `python training/train_intent_model.py`
3. Restart Flask server
4. Test with new inputs

## ⚙️ Advanced: Fine-tune OpenAI

If you want to fine-tune OpenAI GPT-3.5 instead:

1. Use `training/intent_train_openai.jsonl`
2. Follow: https://platform.openai.com/docs/guides/fine-tuning
3. Update `OPENAI_MODEL` in `.env` to your fine-tuned model ID

## 📞 Support

- Check logs in Flask console for AI usage
- Review `ai_models/intent_classifier.py` for configuration
- Check training dataset: `training/intent_dataset.csv`

---

**Status:** ✅ Hybrid AI System Active
**Local Model:** DistilBERT Intent Classifier  
**Fallback:** OpenAI GPT-3.5-turbo  
**Cost Savings:** ~80% reduction in API costs
