"""
Intent Classification with Confidence Threshold and OpenAI Fallback
====================================================================
This module provides intelligent intent classification that:
1. Uses the trained DistilBERT model for fast, local predictions
2. Falls back to OpenAI GPT when confidence is too low
3. Logs all predictions for monitoring and improvement

Architecture:
- Primary: DistilBERT model (fast, local, cost-free)
- Fallback: OpenAI GPT-4 (accurate but costs per request)
- Decision: Compare confidence threshold (default 50%)

Usage in your chatbot (main.py):
    from utils.intent_classifier_with_fallback import IntentClassifier
    
    classifier = IntentClassifier(confidence_threshold=0.50)
    
    intent, confidence, source = classifier.predict("add 5 chairs to order")
    # Returns: ("add_item", 0.89, "distilbert") or ("add_item", None, "openai")

Benefits:
- Fast: Most predictions use local model (no API latency)
- Cost-effective: Only pay for OpenAI when needed
- Accurate: Falls back to GPT for uncertain cases
- Monitored: Logs help identify weak areas for retraining
"""

import os
import json
import torch
import logging
from typing import Tuple, Optional
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
from openai import OpenAI

# ===========================================================================
# CONFIGURATION
# ===========================================================================

# Paths
MODEL_PATH = os.path.join(os.path.dirname(__file__), '..', 'ai_models', 'saved_model')
INTENT_LABEL_PATH = os.path.join(MODEL_PATH, "intent_labels.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), '..', 'logs', 'intent_predictions.log')

# Default confidence threshold
DEFAULT_CONFIDENCE_THRESHOLD = 0.50  # 50%

# Intent definitions (for OpenAI prompt)
INTENT_DEFINITIONS = {
    'create_order': 'User wants to create a new order (start, begin, open, new order)',
    'add_item': 'User wants to add items to current order (add, include, put in order)',
    'update_item': 'User wants to modify existing items (change, update, edit quantity or details)',
    'remove_item': 'User wants to remove items from order (remove, delete, take out)',
    'complete_order': 'User wants to finish/submit order (complete, finish, submit, checkout, done)',
    'none': 'Question, greeting, or unrelated to order operations (hello, help, status, info)'
}

# ===========================================================================
# LOGGING SETUP
# ===========================================================================

# Create logs directory if doesn't exist
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)

# ===========================================================================
# INTENT CLASSIFIER WITH FALLBACK
# ===========================================================================

class IntentClassifier:
    """
    Intent classifier with confidence-based OpenAI fallback.
    
    Attributes:
        model: Trained DistilBERT model
        tokenizer: DistilBERT tokenizer
        label_to_intent: Mapping from label IDs to intent names
        confidence_threshold: Minimum confidence to use DistilBERT (default 0.50)
        openai_client: OpenAI client for fallback
        device: CPU or CUDA device
    """
    
    def __init__(self, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD):
        """
        Initialize the classifier.
        
        Args:
            confidence_threshold: Minimum confidence (0-1) to use DistilBERT.
                                 Predictions below this use OpenAI fallback.
                                 Default 0.50 (50%)
        """
        self.confidence_threshold = confidence_threshold
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        logger.info(f"Initializing IntentClassifier with threshold={confidence_threshold:.0%}")
        logger.info(f"Device: {self.device}")
        
        # Load DistilBERT model
        self._load_distilbert_model()
        
        # Initialize OpenAI client
        self._initialize_openai()
        
        logger.info("IntentClassifier ready")
    
    def _load_distilbert_model(self):
        """Load the trained DistilBERT model and tokenizer."""
        try:
            logger.info(f"Loading DistilBERT model from: {MODEL_PATH}")
            
            # Check if model exists
            if not os.path.exists(MODEL_PATH):
                raise FileNotFoundError(
                    f"Model not found: {MODEL_PATH}\n"
                    f"Please train the model first using train_intent_model_improved.py"
                )
            
            # Load tokenizer and model
            self.tokenizer = DistilBertTokenizer.from_pretrained(MODEL_PATH)
            self.model = DistilBertForSequenceClassification.from_pretrained(MODEL_PATH)
            self.model.to(self.device)
            self.model.eval()  # Set to evaluation mode
            
            # Load intent label mapping
            with open(INTENT_LABEL_PATH, 'r') as f:
                self.label_to_intent = json.load(f)
            # Convert keys to int (JSON stores keys as strings)
            self.label_to_intent = {int(k): v for k, v in self.label_to_intent.items()}
            
            logger.info(f"DistilBERT model loaded successfully with {len(self.label_to_intent)} intents")
            
        except Exception as e:
            logger.error(f"Failed to load DistilBERT model: {e}")
            raise
    
    def _initialize_openai(self):
        """Initialize OpenAI client for fallback."""
        try:
            # Get API key from environment variable
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                logger.warning("OPENAI_API_KEY not found in environment. Fallback will not work.")
                self.openai_client = None
            else:
                self.openai_client = OpenAI(api_key=api_key)
                logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.openai_client = None
    
    def predict_with_distilbert(self, text: str, max_length: int = 128) -> Tuple[str, float]:
        """
        Predict intent using DistilBERT model.
        
        Args:
            text: User input text
            max_length: Maximum token length
            
        Returns:
            intent: Predicted intent name
            confidence: Confidence score (0-1)
        """
        # Preprocess text
        text = text.lower().strip()
        
        # Tokenize
        inputs = self.tokenizer(
            text,
            return_tensors='pt',
            padding=True,
            truncation=True,
            max_length=max_length
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Predict
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=1)[0]
            
            prediction_id = torch.argmax(probs).item()
            confidence = probs[prediction_id].item()
        
        intent = self.label_to_intent[prediction_id]
        
        return intent, confidence
    
    def predict_with_openai(self, text: str) -> str:
        """
        Predict intent using OpenAI GPT as fallback.
        
        Args:
            text: User input text
            
        Returns:
            intent: Predicted intent name
        """
        if not self.openai_client:
            logger.error("OpenAI client not initialized. Cannot use fallback.")
            return 'none'  # Default fallback
        
        try:
            # Create prompt with intent definitions
            intent_list = "\n".join([f"- {k}: {v}" for k, v in INTENT_DEFINITIONS.items()])
            
            prompt = f"""You are an intent classifier for an order management chatbot.
Classify the user's message into ONE of these intents:

{intent_list}

User message: "{text}"

Respond with ONLY the intent name (e.g., "add_item"). Nothing else."""
            
            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Fast and cost-effective model
                messages=[
                    {"role": "system", "content": "You are an intent classification assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,  # Deterministic output
                max_tokens=20
            )
            
            # Extract intent
            intent = response.choices[0].message.content.strip().lower()
            
            # Validate intent
            if intent not in INTENT_DEFINITIONS:
                logger.warning(f"OpenAI returned invalid intent: {intent}. Defaulting to 'none'")
                intent = 'none'
            
            return intent
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return 'none'  # Default fallback on error
    
    def predict(self, text: str) -> Tuple[str, Optional[float], str]:
        """
        Predict intent with confidence-based fallback.
        
        Flow:
        1. Try DistilBERT prediction
        2. If confidence >= threshold: Use DistilBERT result
        3. If confidence < threshold: Fallback to OpenAI
        
        Args:
            text: User input text
            
        Returns:
            intent: Predicted intent name
            confidence: Confidence score (0-1) or None if used OpenAI
            source: "distilbert" or "openai"
        """
        # First, try DistilBERT
        distilbert_intent, distilbert_confidence = self.predict_with_distilbert(text)
        
        # Check confidence threshold
        if distilbert_confidence >= self.confidence_threshold:
            # High confidence - use DistilBERT result
            logger.info(
                f"[DistilBERT] '{text}' → {distilbert_intent} "
                f"(confidence: {distilbert_confidence:.1%})"
            )
            return distilbert_intent, distilbert_confidence, "distilbert"
        else:
            # Low confidence - fallback to OpenAI
            logger.info(
                f"[Low Confidence] '{text}' → {distilbert_intent} "
                f"(confidence: {distilbert_confidence:.1%}) - Falling back to OpenAI"
            )
            
            openai_intent = self.predict_with_openai(text)
            
            logger.info(
                f"[OpenAI Fallback] '{text}' → {openai_intent}"
            )
            
            return openai_intent, None, "openai"
    
    def predict_batch(self, texts: list) -> list:
        """
        Predict intents for multiple texts.
        
        Args:
            texts: List of user input texts
            
        Returns:
            List of tuples (intent, confidence, source)
        """
        results = []
        for text in texts:
            results.append(self.predict(text))
        return results

# ===========================================================================
# CONVENIENCE FUNCTIONS
# ===========================================================================

# Global classifier instance (singleton pattern)
_classifier_instance = None

def get_classifier(confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> IntentClassifier:
    """
    Get or create the global IntentClassifier instance.
    
    This implements a singleton pattern so the model is only loaded once.
    
    Args:
        confidence_threshold: Confidence threshold for fallback
        
    Returns:
        IntentClassifier instance
    """
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier(confidence_threshold)
    return _classifier_instance

def classify_intent(text: str, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> Tuple[str, Optional[float], str]:
    """
    Convenience function to classify a single text.
    
    Usage:
        intent, confidence, source = classify_intent("add 5 chairs")
        
    Args:
        text: User input text
        confidence_threshold: Confidence threshold for fallback
        
    Returns:
        intent: Predicted intent name
        confidence: Confidence score or None
        source: "distilbert" or "openai"
    """
    classifier = get_classifier(confidence_threshold)
    return classifier.predict(text)

# ===========================================================================
# TESTING
# ===========================================================================

if __name__ == '__main__':
    """Test the classifier with sample inputs."""
    print("\n" + "="*70)
    print("🧪 TESTING INTENT CLASSIFIER WITH FALLBACK")
    print("="*70)
    
    # Test samples (mix of clear and ambiguous)
    test_samples = [
        # Clear examples (should use DistilBERT)
        "create new order",
        "add 5 chairs to my order",
        "change quantity to 10",
        "remove the lamp",
        "complete my order",
        "hello how are you",
        
        # Ambiguous examples (may fallback to OpenAI)
        "i changed my mind",
        "actually make that 3",
        "never mind that",
        "what about price",
        "is it ready?",
        "plz do it",
    ]
    
    print(f"\nTesting with {len(test_samples)} samples...")
    print(f"Confidence threshold: {DEFAULT_CONFIDENCE_THRESHOLD:.0%}\n")
    
    classifier = get_classifier()
    
    for text in test_samples:
        intent, confidence, source = classifier.predict(text)
        
        # Format output
        conf_str = f"{confidence:.1%}" if confidence else "N/A"
        source_emoji = "🤖" if source == "distilbert" else "🌐"
        
        print(f"{source_emoji} [{source:>10}] [{conf_str:>5}] '{text:<30}' → {intent}")
    
    print(f"\n✅ Testing complete")
    print(f"📄 Check logs at: {LOG_PATH}")
