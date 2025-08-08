#!/bin/bash
# Start the phone chatbot system

echo "🎭 Phone Chatbot System"
echo "======================"
echo ""
echo "Personalities available:"
echo "  1. The Philosopher"
echo "  2. The Comedian"
echo "  3. The Child"
echo "  4. The Detective"
echo "  5. The Mystic"
echo "  6. The Scientist"
echo "  7. The Pirate"
echo "  8. The Zen Master"
echo "  9. The Robot"
echo "  10. The Therapist"
echo ""
echo "Instructions:"
echo "  1. Pick up the phone (you'll hear a dial tone)"
echo "  2. Dial 1-10 to select a personality"
echo "  3. Start talking after the greeting"
echo "  4. Hang up to end the conversation"
echo ""

# Generate dial tone if needed
python generate_dial_tone.py

# Start the phone chatbot
python src/phone_chatbot.py