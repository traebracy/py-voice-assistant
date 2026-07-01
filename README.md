# Voice Assistant

A Python desktop voice assistant designed for Windows. It listens for a wake word, records speech, recognizes commands, speaks responses, and uses the OpenAI API for conversational fallback responses.

This project is one of my larger Python practice builds because it combines a user interface, audio recording, speech recognition, text-to-speech, web actions, timer commands, and API integration.

## Features

- Desktop interface built with Tkinter
- Wake-word listening for Jarvis-style commands
- Speech recognition from recorded microphone input
- Text-to-speech responses using `pyttsx3`
- OpenAI API integration for natural responses
- Built-in commands for time, timers, YouTube search, Google search, and Spotify search
- Threading so the assistant can listen while the UI stays responsive
- Conversation mode for short follow-up responses

## Concepts Practiced

- Python classes
- Tkinter UI design
- Threading and queues
- Speech recognition
- Text-to-speech
- API usage
- Command parsing
- Error handling
- Desktop automation basics

## How to Run

Install the required packages first:

```bash
pip install openai pyttsx3 pygame sounddevice scipy SpeechRecognition
```

Then run:

```bash
python jarvisvoiceassistant.py
```

You will also need to add your own OpenAI API key before using GPT responses.

## What I Learned

This project helped me connect several Python libraries into one interactive program. I practiced organizing a larger script into methods, keeping a desktop UI responsive, and turning spoken commands into useful actions.
