import tkinter as tk
from tkinter import scrolledtext
import threading
import queue
import datetime
import webbrowser
import os
import tempfile
import urllib.parse
import time
import re

import sounddevice as sd
from scipy.io.wavfile import write
import speech_recognition as sr

import pygame

from openai import OpenAI  # GPT integration
import pyttsx3  # local TTS


# ---------- API KEYS ----------
OPENAI_API_KEY = "KEY"

gpt_client = OpenAI(api_key=OPENAI_API_KEY)

WAKE_WORDS = ["hey jarvis", "okay jarvis", "yo jarvis", "jarvis"]
TEMP_WAV = "temp_input.wav"


class JarvisApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Jarvis Voice Assistant")
        self.root.geometry("600x450")

        self.status_label = tk.Label(root, text="Status: Idle", font=("Arial", 12))
        self.status_label.pack(pady=5)

        self.log_box = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=15, state=tk.DISABLED)
        self.log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=5)

        self.start_button = tk.Button(btn_frame, text="Initiate Jarvis", command=self.start_listening, width=12)
        self.start_button.grid(row=0, column=0, padx=5)

        self.stop_button = tk.Button(btn_frame, text="Stop Jarvis", command=self.stop_listening, state=tk.DISABLED, width=12)
        self.stop_button.grid(row=0, column=1, padx=5)

        self.quit_button = tk.Button(btn_frame, text="Quit", command=self.quit_app, width=12)
        self.quit_button.grid(row=0, column=2, padx=5)

        pygame.mixer.init()
        self.recognizer = sr.Recognizer()

        self.running = False
        self.thread = None
        # Background listener threads write here; the Tkinter UI reads it safely on the main thread.
        self.log_queue = queue.Queue()
        self.root.after(100, self.process_logs)

        # Tracks short follow-up conversations so the user does not need to repeat the wake word.
        self.conversation_mode = False
        self.followup_timeout = 0

        self.log("Jarvis ready.")

    # ---------- Logging ----------
    def log(self, msg):
        self.log_queue.put(msg)

    def process_logs(self):
        # Tkinter widgets should be updated from the main thread, so logs are drained here.
        while not self.log_queue.empty():
            line = self.log_queue.get_nowait()
            self.log_box.config(state=tk.NORMAL)
            self.log_box.insert(tk.END, line + "\n")
            self.log_box.see(tk.END)
            self.log_box.config(state=tk.DISABLED)
        self.root.after(100, self.process_logs)

    # ---------- TTS Worker (pyttsx3) ----------
    def tts_worker(self, text):
        # pyttsx3 can block while speaking, so each response is spoken on a background thread.
        try:
            engine = pyttsx3.init()
            # Optional tweaks:
            # engine.setProperty("rate", 190)
            # engine.setProperty("volume", 1.0)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            self.log(f"TTS error (pyttsx3): {e}")

    # ---------- Speak ----------
    def speak(self, text):
        self.log(f"Jarvis: {text}")

        threading.Thread(target=self.tts_worker, args=(text,), daemon=True).start()

        # ------------------------------------------------------------------

    # ---------- Recording ----------
    def record_to_wav(self, seconds=4, show_log=True):
        try:
            fs = 16000
            if show_log:
                self.log(f"🎧 Recording {seconds} seconds…")

            audio = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype='int16')
            sd.wait()
            # SpeechRecognition reads from a file, so the microphone sample is saved temporarily.
            write(TEMP_WAV, fs, audio)
            return TEMP_WAV
        except Exception as e:
            self.log(f"Microphone error: {e}")
            return ""

    def listen(self, seconds=4, show_log=True):
        wav = self.record_to_wav(seconds, show_log)
        if not wav:
            return ""

        try:
            with sr.AudioFile(wav) as source:
                audio = self.recognizer.record(source)

            text = self.recognizer.recognize_google(audio).lower()
            if show_log:
                self.log(f"You said: {text}")

            return text

        except:
            if show_log:
                self.log("Inaudible Speech error!")
            return ""

    # ---------- GPT ----------
    def ask_gpt(self, text):
        try:
            # The prompt keeps GPT responses short enough for a desktop voice assistant.
            prompt = (
                "You are Jarvis, a friendly desktop assistant. "
                "Respond briefly and naturally.\n\nUser: " + text
            )
            resp = gpt_client.responses.create(
                model="gpt-4o-mini",
                input=prompt
            )
            return resp.output[0].content[0].text.strip()
        except Exception as e:
            self.log(f"GPT error: {e}")
            return ""

    # ---------- Timer Parsing ----------
    def parse_timer_duration(self, cmd):
        text = cmd.lower()

        # Supports both digit-based timers ("5 minutes") and short word-based timers ("five minutes").
        m = re.search(r'(\d+)\s*(second|seconds|minute|minutes|hour|hours)', text)
        amount = None
        unit = None

        if m:
            amount = int(m.group(1))
            unit = m.group(2)
        else:
            wordnums = {
                "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
            }
            for w, n in wordnums.items():
                if w in text:
                    for u in ["second", "seconds", "minute", "minutes", "hour", "hours"]:
                        if u in text:
                            amount = n
                            unit = u
                            break
                if amount:
                    break

        if not amount or not unit:
            return None

        label = f"{amount} {unit}"
        return amount, label

    def handle_timer_command(self, cmd):
        parsed = self.parse_timer_duration(cmd)
        if not parsed:
            return False

        amount, label = parsed
        self.speak(f"Opening Windows timer for {label}.")
        try:
            os.system("start ms-clock:timer")
        except:
            self.speak("I couldn't open the Windows timer app.")

        return True

    # ---------- Command Processing ----------
    def handle_command(self, cmd):
        if not cmd:
            self.speak("I didn't catch that.")
            self.conversation_mode = False
            return

        # By default, assume no follow-up unless GPT asks a question
        self.conversation_mode = False

        # Timers
        if "timer" in cmd or "alarm" in cmd:
            if self.handle_timer_command(cmd):
                return
            self.speak("Try saying: set a timer for five minutes.")
            return

        # Time
        if "time" in cmd:
            now = datetime.datetime.now()
            pretty = now.strftime("%I:%M %p").lstrip("0")
            self.speak(f"The time is {pretty}.")
            return

        # YouTube search
        if "youtube" in cmd and "search" in cmd:
            query = self.extract_search_query(cmd, ["youtube", "on youtube", "in youtube"])
            if query:
                self.speak(f"Searching YouTube for {query}.")
                webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}")
            else:
                self.speak("What should I search for on YouTube?")
            return

        # Google search
        if ("google" in cmd or "web" in cmd) and "search" in cmd:
            query = self.extract_search_query(cmd, ["google", "web", "on google", "the web"])
            if query:
                self.speak(f"Searching the web for {query}.")
                webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
            else:
                self.speak("What should I search for?")
            return

        # Spotify search
        if "spotify" in cmd and "search" in cmd:
            query = self.extract_search_query(cmd, ["spotify", "on spotify", "in spotify"])
            if query:
                self.speak(f"Searching Spotify for {query}.")
                webbrowser.open(f"https://open.spotify.com/search/{urllib.parse.quote(query)}")
            else:
                webbrowser.open("https://open.spotify.com")
                self.speak("Opening Spotify search.")
            return

        # Shutdown Jarvis
        if "shutdown" in cmd or "shut down" in cmd or "power off" in cmd:
            self.speak("Shutting down systems.")
            self.running = False
            self.root.after(500, self.root.destroy)
            os.system("taskkill /f /im pycharm64.exe")
            os.system("taskkill /f /im pycharm.exe")
            return

        # GPT fallback
        reply = self.ask_gpt(cmd)
        if reply:
            self.speak(reply)

            # If GPT asks a question, keep listening briefly for a natural follow-up answer.
            if reply.strip().endswith("?"):
                self.conversation_mode = True
                self.followup_timeout = time.time() + 12  # 20 seconds to answer
            else:
                self.conversation_mode = False
        else:
            self.speak(f"You said: {cmd}")
            self.conversation_mode = False

    # ---------- Searching Extract ----------
    def extract_search_query(self, cmd, service_keywords):
        text = cmd.lower()
        # Remove wake words and service names so only the user's actual search phrase remains.
        for wake in WAKE_WORDS:
            text = text.replace(wake, "")

        replacements = [
            ("search the web for", "search for"),
            ("search the web", "search for"),
            ("search youtube for", "search for"),
            ("youtube search for", "search for"),
            ("youtube search", "search for"),
            ("search spotify for", "search for"),
            ("spotify search for", "search for"),
            ("spotify search", "search for"),
        ]
        for old, new in replacements:
            text = text.replace(old, new)

        if "search for" in text:
            text = text.split("search for", 1)[1]
        elif "search" in text:
            text = text.split("search", 1)[1]

        for phrase in service_keywords + ["please"]:
            text = text.replace(phrase, "")

        return " ".join(text.split()).strip()

    # ---------- Listening Loop ----------
    def listen_loop(self):
        self.speak("Jarvis online.")

        while self.running:
            # Conversation mode listens for a direct answer before returning to wake-word mode.
            if self.conversation_mode and time.time() < self.followup_timeout:
                cmd = self.listen(seconds=5, show_log=True)
                self.handle_command(cmd)
                # handle_command will decide whether to remain in conversation_mode
                continue
            else:
                # timeout or not expecting follow-up anymore
                self.conversation_mode = False

            # Normal mode stays quiet until the wake word is detected.
            heard = self.listen(seconds=3, show_log=False)
            if not self.running:
                break

            if "jarvis" in (heard or "").lower():
                self.speak("Yes?")
                cmd = self.listen(seconds=5, show_log=True)
                self.handle_command(cmd)

        self.log("Stopped listening.")

    # ---------- UI Buttons ----------
    def start_listening(self):
        if self.running:
            return

        self.running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="Status: Listening…")

        self.thread = threading.Thread(target=self.listen_loop, daemon=True)
        self.thread.start()

    def stop_listening(self):
        self.running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="Status: Idle")

    def quit_app(self):
        self.running = False
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = JarvisApp(root)
    root.mainloop()

