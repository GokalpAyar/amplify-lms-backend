import speech_recognition as sr

def get_speech_input() -> str:
    """
    Records audio from the user's microphone and converts it to text.
    
    This function:
    1. Initializes the speech recognizer
    2. Records audio from the default microphone
    3. Converts the speech to text using Google's speech recognition service
    4. Returns the transcribed text
    
    Returns:
        str: The transcribed text from the speech input
        Empty string if speech couldn't be understood or an error occurred
    """
    # Initialize the speech recognizer
    recognizer = sr.Recognizer()
    
    with sr.Microphone() as source:
        print("Listening... Speak your answer")
        # Adjust for ambient noise to improve recognition accuracy
        recognizer.adjust_for_ambient_noise(source)
        # Record audio from the microphone
        audio = recognizer.listen(source)
        
        try:
            # Convert speech to text using Google's speech recognition
            text = recognizer.recognize_google(audio)
            return text
        except sr.UnknownValueError:
            print("Could not understand audio")
            return ""
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
            return "" 