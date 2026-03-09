"""
Quick Test Script for Intent Classifier
========================================
Run this after training to quickly verify the model works correctly.

Usage:
    python test_intent_classifier.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.intent_classifier_with_fallback import IntentClassifier

def test_classifier():
    """Test the classifier with various examples."""
    
    print("\n" + "="*70)
    print("🧪 QUICK INTENT CLASSIFIER TEST")
    print("="*70)
    
    print("\nInitializing classifier...")
    try:
        classifier = IntentClassifier(confidence_threshold=0.50)
        print("✅ Classifier initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize classifier: {e}")
        print("\nMake sure you've trained the model first:")
        print("   python training/train_intent_model_improved.py")
        return
    
    # Test cases with expected intents
    test_cases = [
        # create_order
        ("create new order", "create_order"),
        ("start order", "create_order"),
        ("open new order please", "create_order"),
        
        # add_item
        ("add 5 chairs", "add_item"),
        ("put 3 monitors in my order", "add_item"),
        ("i want to add tables", "add_item"),
        
        # update_item
        ("change quantity to 10", "update_item"),
        ("update item 1", "update_item"),
        ("modify the chairs to 5", "update_item"),
        
        # remove_item
        ("remove the chairs", "remove_item"),
        ("delete item 2", "remove_item"),
        ("take out the lamp", "remove_item"),
        
        # complete_order
        ("complete order", "complete_order"),
        ("finish my order", "complete_order"),
        ("submit it", "complete_order"),
        
        # none
        ("hello", "none"),
        ("whats the status", "none"),
        ("help me", "none"),
    ]
    
    print(f"\n📝 Testing {len(test_cases)} examples...\n")
    
    correct = 0
    high_confidence_count = 0
    distilbert_count = 0
    openai_count = 0
    
    for text, expected_intent in test_cases:
        intent, confidence, source = classifier.predict(text)
        
        # Check correctness
        is_correct = (intent == expected_intent)
        if is_correct:
            correct += 1
            status = "✅"
        else:
            status = f"❌"
        
        # Track source
        if source == "distilbert":
            distilbert_count += 1
        else:
            openai_count += 1
        
        # Track confidence
        if confidence and confidence >= 0.70:
            high_confidence_count += 1
            conf_marker = "🟢"
        elif confidence and confidence >= 0.50:
            conf_marker = "🟡"
        else:
            conf_marker = "🔴"
        
        # Format confidence
        conf_str = f"{confidence:.1%}" if confidence else "N/A"
        
        # Print result
        print(f"{status} {conf_marker} [{source:>10}] {conf_str:>5} | '{text:<30}' → {intent:<15} (expected: {expected_intent})")
    
    # Summary
    accuracy = (correct / len(test_cases)) * 100
    distilbert_pct = (distilbert_count / len(test_cases)) * 100
    openai_pct = (openai_count / len(test_cases)) * 100
    
    print("\n" + "="*70)
    print("📊 RESULTS SUMMARY")
    print("="*70)
    print(f"\n✅ Accuracy: {correct}/{len(test_cases)} ({accuracy:.1f}%)")
    print(f"🟢 High confidence (≥70%): {high_confidence_count}/{distilbert_count}")
    print(f"🤖 Used DistilBERT: {distilbert_count}/{len(test_cases)} ({distilbert_pct:.1f}%)")
    print(f"🌐 Used OpenAI: {openai_count}/{len(test_cases)} ({openai_pct:.1f}%)")
    
    print("\n💡 Assessment:")
    if accuracy >= 90:
        print("   🎉 EXCELLENT! Model is working very well.")
    elif accuracy >= 80:
        print("   ✅ GOOD! Model is working well.")
    elif accuracy >= 70:
        print("   ⚠️  ACCEPTABLE. Some improvements needed.")
    else:
        print("   ❌ POOR. Model needs retraining with more data.")
    
    if distilbert_pct >= 80:
        print("   💰 Cost-effective: Most predictions use local model (free)")
    else:
        print("   💸 High OpenAI usage: Consider lowering confidence threshold")
    
    print("\n📄 Detailed logs saved to: logs/intent_predictions.log")
    print("\n✅ Test complete!")

def interactive_test():
    """Interactive mode - test your own inputs."""
    print("\n" + "="*70)
    print("🎮 INTERACTIVE TEST MODE")
    print("="*70)
    print("\nType messages to test intent classification.")
    print("Type 'quit' or 'exit' to stop.\n")
    
    try:
        classifier = IntentClassifier(confidence_threshold=0.50)
    except Exception as e:
        print(f"❌ Failed to initialize classifier: {e}")
        return
    
    while True:
        try:
            text = input("You: ").strip()
            
            if text.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            if not text:
                continue
            
            intent, confidence, source = classifier.predict(text)
            
            # Format output
            conf_str = f"{confidence:.1%}" if confidence else "N/A"
            source_emoji = "🤖" if source == "distilbert" else "🌐"
            
            print(f"{source_emoji} Intent: {intent:<15} | Confidence: {conf_str:>5} | Source: {source}")
            print()
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}\n")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test intent classifier')
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive mode'
    )
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_test()
    else:
        test_classifier()
