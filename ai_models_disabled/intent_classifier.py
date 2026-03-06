"""
Intent Classifier Module
========================
Local AI model for classifying user intents.
Reduces OpenAI API costs by handling simple intents locally.

Usage:
    from ai_models import IntentClassifier
    
    classifier = IntentClassifier()
    intent, confidence = classifier.predict("create order please")
    # Returns: ('create_order', 0.95)
"""

import os
import torch
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification

class IntentClassifier:
    """
    Local intent classifier using DistilBERT.
    Handles common intents: create_order, add_item, update_item, remove_item, complete_order
    """
    
    # Intent mappings
    INTENT_LABELS = {
        'create_order': 0,
        'add_item': 1,
        'update_item': 2,
        'remove_item': 3,
        'complete_order': 4,
        'none': 5
    }
    
    LABEL_TO_INTENT = {v: k for k, v in INTENT_LABELS.items()}
    
    # Intents that can be handled locally (don't need OpenAI)
    LOCAL_INTENTS = {'create_order', 'add_item', 'update_item', 'remove_item', 'complete_order'}
    
    def __init__(self, model_path=None, confidence_threshold=0.20):
        """
        Initialize the intent classifier.
        
        Args:
            model_path: Path to saved model (default: ai_models/saved_model)
            confidence_threshold: Minimum confidence to use local prediction (default: 0.20)
        """
        if model_path is None:
            model_path = os.path.join(
                os.path.dirname(__file__), 
                'saved_model'
            )
        
        self.model_path = model_path
        self.loaded_model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.tokenizer = None
        self.is_loaded = False
        
        # Try to load model
        self._load_model()

    def _get_latest_checkpoint_path(self):
        """Return latest checkpoint path if available (e.g. checkpoint-36)."""
        try:
            if not os.path.isdir(self.model_path):
                return None

            checkpoint_dirs = []
            for name in os.listdir(self.model_path):
                if not name.startswith('checkpoint-'):
                    continue
                full_path = os.path.join(self.model_path, name)
                if not os.path.isdir(full_path):
                    continue
                try:
                    step = int(name.split('-', 1)[1])
                except Exception:
                    continue
                checkpoint_dirs.append((step, full_path))

            if not checkpoint_dirs:
                return None

            checkpoint_dirs.sort(key=lambda item: item[0], reverse=True)
            return checkpoint_dirs[0][1]
        except Exception:
            return None
    
    def _load_model(self):
        """Load the trained model and tokenizer"""
        try:
            if not os.path.exists(self.model_path):
                print(f"⚠️  Intent model not found at: {self.model_path}")
                print("   Run: python training/train_intent_model.py")
                print("   Falling back to OpenAI for all requests")
                return False

            load_path = self._get_latest_checkpoint_path() or self.model_path
            self.loaded_model_path = load_path

            print(f"📦 Loading intent classifier from: {load_path}")

            # Tokenizer may exist only in root model_path, while weights can be in checkpoint dir.
            tokenizer_source = self.model_path if os.path.exists(os.path.join(self.model_path, 'tokenizer_config.json')) else load_path
            self.tokenizer = DistilBertTokenizer.from_pretrained(tokenizer_source)
            self.model = DistilBertForSequenceClassification.from_pretrained(load_path)
            self.model.eval()  # Set to evaluation mode
            
            self.is_loaded = True
            print("✅ Intent classifier loaded successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error loading intent classifier: {e}")
            print("   Falling back to OpenAI for all requests")
            return False
    
    def predict(self, text):
        """
        Predict the intent of user input.
        
        Args:
            text: User input text
        
        Returns:
            tuple: (intent, confidence)
            - intent: 'create_order', 'add_item', etc. or 'unknown' if uncertain
            - confidence: float between 0 and 1
        """
        if not self.is_loaded:
            return 'unknown', 0.0
        
        try:
            # Tokenize input
            inputs = self.tokenizer(
                text,
                return_tensors='pt',
                padding=True,
                truncation=True,
                max_length=64
            )
            
            # Get prediction
            with torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = torch.softmax(outputs.logits, dim=1)
                confidence, predicted_class = torch.max(probabilities, dim=1)
                
                predicted_class = predicted_class.item()
                confidence = confidence.item()
            
            # Map to intent name
            intent = self.LABEL_TO_INTENT.get(predicted_class, 'unknown')
            
            # If confidence is too low, return unknown
            if confidence < self.confidence_threshold:
                return 'unknown', confidence
            
            return intent, confidence
            
        except Exception as e:
            print(f"Error during prediction: {e}")
            return 'unknown', 0.0
    
    def should_use_local(self, intent, confidence):
        """
        Determine if this intent should be handled locally or sent to OpenAI.
        
        Args:
            intent: Predicted intent
            confidence: Prediction confidence
        
        Returns:
            bool: True if should handle locally, False if should use OpenAI
        """
        return (
            self.is_loaded and 
            intent in self.LOCAL_INTENTS and 
            confidence >= self.confidence_threshold
        )
    
    def get_stats(self):
        """Get classifier statistics"""
        return {
            'is_loaded': self.is_loaded,
            'model_path': self.model_path,
            'loaded_model_path': self.loaded_model_path,
            'confidence_threshold': self.confidence_threshold,
            'local_intents': list(self.LOCAL_INTENTS)
        }


# Singleton instance for app-wide use
_classifier_instance = None

def get_intent_classifier():
    """Get or create the global intent classifier instance"""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance
