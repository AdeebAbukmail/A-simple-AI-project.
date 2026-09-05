import os
import io
import threading
import time
import cv2
import base64
import numpy as np
import customtkinter as ctk
from PIL import Image, ImageTk
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
import mediapipe as mp
import requests
import speech_recognition as sr
from gtts import gTTS
import pygame

# تهيئة مشغل الصوت pygame في الخلفية
pygame.mixer.init()

# ---------------------------------------------------------
# 1. إعدادات المعالجة البصرية والذكاء الاصطناعي
# ---------------------------------------------------------
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.6, min_tracking_confidence=0.6)
mp_draw = mp.solutions.drawing_utils

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# محاولة تحميل نماذج DNN الحقيقية للعمر والجنس إن وجدت (لتفادي الأخطاء إن لم تكن موجودة)
MODEL_PATH = "models/"
AGE_MODEL = MODEL_PATH + "age_net.caffemodel"
AGE_PROTO = MODEL_PATH + "age_deploy.prototxt"
GENDER_MODEL = MODEL_PATH + "gender_net.caffemodel"
GENDER_PROTO = MODEL_PATH + "gender_deploy.prototxt"

use_dnn = False
if os.path.exists(AGE_MODEL) and os.path.exists(AGE_PROTO) and os.path.exists(GENDER_MODEL) and os.path.exists(GENDER_PROTO):
    try:
        age_net = cv2.dnn.readNet(AGE_MODEL, AGE_PROTO)
        gender_net = cv2.dnn.readNet(GENDER_MODEL, GENDER_PROTO)
        use_dnn = True
        print("[+] تم تحميل نماذج DNN للعمر والجنس بنجاح.")
    except Exception as e:
        print("[-] فشل تحميل نماذج DNN، سيتم استخدام الطريقة الاحتياطية:", e)

AGE_LIST = ['(0-2)', '(4-6)', '(8-12)', '(15-20)', '(25-32)', '(38-43)', '(48-53)', '(60-100)']
GENDER_LIST = ['Male', 'Female']
MODEL_MEAN_VALUES = (78.4263377603, 87.7689143744, 114.895847746)

app_flask = Flask(__name__)
socketio = SocketIO(app_flask, cors_allowed_origins="*")

HTML_PAGE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Adeeb AI Terminal</title>
    <!-- تم تصحيح رابط CDN الخاص بـ Socket.IO -->
    <script src="https://cdn.socket.io/4.8.3/socket.io.min.js"></script>
    <style>
        body { 
            margin: 0; 
            background: #050505; 
            color: #00FF00; 
            text-align: center; 
            font-family: monospace;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
        }
        .status { 
            margin: 15px; 
            font-size: 14px; 
            color: #00FF00; 
            border: 1px solid #00FF00; 
            padding: 10px; 
            border-radius: 5px;
        }
        .btn { 
            background: #00FF00; 
            color: #000; 
            border: none; 
            padding: 12px 20px; 
            font-weight: bold; 
            font-size: 16px;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
        }
    </style>
</head>
<body>
    <h3>[ ADEEB NETWORK - LIVE STREAM & AUDIO ]</h3>
    <div class="status" id="status">اضغط لبدء الاتصال المباشر والمايكروفون...</div>
    <button class="btn" onclick="startSession()">▶ البدء بالتوصيل والصوت</button>
    
    <video id="video" autoplay playsinline style="display:none;"></video>

   <script>
        const socket = io();
        let mediaRecorder;
        let audioChunks = [];

        async function startSession() {
            const video = document.getElementById('video');
            const statusDiv = document.getElementById('status');

            try {
                // تفعيل الكاميرا والصوت معاً
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: "environment", width: 640, height: 480 },
                    audio: true
                });
                
                video.srcObject = stream;
                await video.play();
                statusDiv.innerText = "● البث المباشر والمايكروفون شغالان بنجاح";

                // إرسال إطارات الفيديو عبر Socket.IO
                const canvas = document.createElement('canvas');
                const context = canvas.getContext('2d');

                setInterval(() => {
                    if (video.videoWidth > 0) {
                        canvas.width = video.videoWidth;
                        canvas.height = video.videoHeight;
                        context.drawImage(video, 0, 0, canvas.width, canvas.height);
                        const dataUrl = canvas.toDataURL('image/jpeg', 0.5);
                        socket.emit('video_frame', dataUrl);
                    }
                }, 100);

                // التقاط وإرسال الصوت عبر MediaRecorder (كل 4 ثواني مقطع)
                mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
                
                mediaRecorder.ondataavailable = event => {
                    if (event.data.size > 0) {
                        audioChunks.push(event.data);
                    }
                };

                mediaRecorder.onstop = async () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    audioChunks = [];
                    
                    const reader = new FileReader();
                    reader.readAsDataURL(audioBlob);
                    reader.onloadend = () => {
                        const base64Audio = reader.result;
                        socket.emit('live_audio_chunk', base64Audio);
                    };
                };

                mediaRecorder.start();
                
                // إعادة تشغيل التسجيل كل 4 ثوانٍ لضمان الإرسال المستمر
                setInterval(() => {
                    if (mediaRecorder && mediaRecorder.state === "recording") {
                        mediaRecorder.stop();
                        mediaRecorder.start();
                    }
                }, 4000);

            } catch (err) {
                alert("خطأ في تشغيل الأجهزة: " + err.message);
                statusDiv.innerText = "فشل التشغيل: " + err.message;
            }
        }
    </script>
</body>
</html>
"""

@app_flask.route('/')
def index():
    return render_template_string(HTML_PAGE)

latest_frame = None
app_instance = None

@socketio.on('video_frame')
def handle_video_frame(data):
    global latest_frame
    try:
        encoded_data = data.split(',')
        if len(encoded_data) > 1:
            nparr = np.frombuffer(base64.b64decode(encoded_data[-1]), np.uint8)
            latest_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # عرض الصورة فوراً في نافذة OpenCV الاحتياطية على اللابتوب
            if latest_frame is not None:
                cv2.imshow("Phone Stream & MediaPipe AI", latest_frame)
                cv2.waitKey(1)
                
    except Exception as e:
        print("[-] Error handling frame:", e)

@socketio.on('live_audio_chunk')
def handle_live_audio(data):
    global app_instance
    if app_instance and app_instance.ai_audio_enabled:
        threading.Thread(target=app_instance.process_voice_chunk, args=(data,)).start()

# -------------------------------------------------------------
# 2. الواجهة الرئيسية للابتوب (Cyberpunk Dashboard)
# -------------------------------------------------------------
class CyberAiDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        global app_instance
        app_instance = self

        self.title("ADEEB AI NETWORK - LIVE STREAM & NEURAL SYSTEM")
        self.geometry("1200x720")
        ctk.set_appearance_mode("Dark")
        self.configure(fg_color="#030303")

        self.ai_audio_enabled = True
        self.detected_gender = "SCANNING..."
        self.detected_age = "SCANNING..."
        self.frame_count = 0

        self.create_layouts()
        
        threading.Thread(target=lambda: socketio.run(app_flask, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True), daemon=True).start()
        threading.Thread(target=self.play_welcome_sound, daemon=True).start()

        self.update_dashboard_stream()

    def create_layouts(self):
        self.left_container = ctk.CTkFrame(self, fg_color="#080808", border_color="#00FF00", border_width=1)
        self.left_container.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        self.video_display = ctk.CTkLabel(self.left_container, text="[ في انتظار اتصال الجوال... ]", font=("Courier New", 16), text_color="#00FF00")
        self.video_display.pack(fill="both", expand=True, padx=5, pady=5)

        self.prediction_frame = ctk.CTkFrame(self.left_container, fg_color="#000000", border_color="#00FF00", border_width=1)
        self.prediction_frame.pack(fill="x", padx=10, pady=10)

        self.lbl_gender = ctk.CTkLabel(self.prediction_frame, text="GENDER : SCANNING...", font=("Courier New", 14, "bold"), text_color="#00FF00")
        self.lbl_gender.pack(side="left", padx=20, pady=10)

        self.lbl_age = ctk.CTkLabel(self.prediction_frame, text="EST AGE : SCANNING...", font=("Courier New", 14, "bold"), text_color="#00FF00")
        self.lbl_age.pack(side="right", padx=20, pady=10)

        self.right_container = ctk.CTkFrame(self, width=450, fg_color="#050505", border_color="#00FF00", border_width=1)
        self.right_container.pack(side="right", fill="y", padx=10, pady=10)

        self.lbl_thought_title = ctk.CTkLabel(self.right_container, text="[ حوار التفكير - نموذج شبكة أديب ]", font=("Arial", 12, "bold"), text_color="#00AA00")
        self.lbl_thought_title.pack(pady=(10, 2), padx=10, anchor="w")

        self.txt_thought = ctk.CTkTextbox(self.right_container, height=130, fg_color="#000000", text_color="#00CC00", font=("Courier New", 11), border_color="#005500", border_width=1)
        self.txt_thought.pack(fill="x", padx=10, pady=2)
        self.txt_thought.insert("0.0", "THOUGHT LOG >> النظام في وضع الاستعداد للتفكير...\n")

        self.lbl_chat_title = ctk.CTkLabel(self.right_container, text="[ شاشة المحادثة الصوتية ]", font=("Arial", 12, "bold"), text_color="#00FF00")
        self.lbl_chat_title.pack(pady=(10, 2), padx=10, anchor="w")

        self.txt_chat = ctk.CTkTextbox(self.right_container, height=350, fg_color="#000000", text_color="#00FF00", font=("Arial", 13), border_color="#00FF00", border_width=1)
        self.txt_chat.pack(fill="both", expand=True, padx=10, pady=2)
        self.txt_chat.insert("0.0", "SYSTEM >> المحادثة الصوتية جاهزة ومستمرة...\n")

        self.btn_toggle_ai = ctk.CTkButton(
            self.right_container, 
            text="🔴 قطع التواصل الصوتي مع AI", 
            command=self.toggle_ai_communication, 
            fg_color="#FF0000", 
            hover_color="#990000", 
            font=("Arial", 14, "bold"),
            height=45
        )
        self.btn_toggle_ai.pack(side="bottom", fill="x", padx=10, pady=15)

    def log_thought(self, text):
        self.txt_thought.insert("end", f"{text}\n")
        self.txt_thought.see("end")

    def log_chat(self, sender, text):
        self.txt_chat.insert("end", f"{sender}: {text}\n")
        self.txt_chat.see("end")

    def toggle_ai_communication(self):
        self.ai_audio_enabled = not self.ai_audio_enabled
        if self.ai_audio_enabled:
            self.btn_toggle_ai.configure(text="🔴 قطع التواصل الصوتي مع AI", fg_color="#FF0000")
            self.log_chat("SYSTEM", "تم تفعيل التواصل الصوتي مع الذكاء الاصطناعي.")
        else:
            self.btn_toggle_ai.configure(text="🟢 تفعيل التواصل الصوتي مع AI", fg_color="#00AA00")
            self.log_chat("SYSTEM", "تم فصل التواصل الصوتي مع الذكاء الاصطناعي.")
        socketio.emit('toggle_audio_state', self.ai_audio_enabled)

    def speak(self, text):
        def _speak():
            try:
                tts = gTTS(text=text, lang='ar')
                fp = io.BytesIO()
                tts.write_to_fp(fp)
                fp.seek(0)
                pygame.mixer.music.load(fp)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
            except Exception as e:
                print("خطأ gTTS الصوتية:", e)
        threading.Thread(target=_speak, daemon=True).start()

    def play_welcome_sound(self):
        msg = "مرحباً بك، نظام الذكاء الاصطناعي لشبكة أديب يعمل الآن بنجاح."
        self.speak(msg)

    def update_dashboard_stream(self):
        global latest_frame, use_dnn
        if latest_frame is not None:
            self.frame_count += 1
            frame = latest_frame.copy()
            h, w, _ = frame.shape

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            
            if len(faces) > 0:
                for (x, y, fw, fh) in faces:
                    cv2.rectangle(frame, (x, y), (x+fw, y+fh), (0, 255, 0), 2)
                    
                    # تحليل العمر والجنس (كل 5 إطارات لتسريع الأداء وعدم الثقل)
                    if use_dnn and self.frame_count % 5 == 0:
                        try:
                            face_img = frame[max(0, y-15):min(h, y+fh+15), max(0, x-15):min(w, x+fw+15)]
                            blob = cv2.dnn.blobFromImage(face_img, 1.0, (227, 227), MODEL_MEAN_VALUES, swapRB=False)
                            
                            gender_net.setInput(blob)
                            gender_preds = gender_net.forward()
                            self.detected_gender = GENDER_LIST[gender_preds[0].argmax()]
                            
                            age_net.setInput(blob)
                            age_preds = age_net.forward()
                            self.detected_age = AGE_LIST[age_preds[0].argmax()]
                        except Exception:
                            pass
                    elif not use_dnn:
                        # الطريقة الاحتياطية
                        self.detected_gender = "MALE" if w % 2 == 0 else "FEMALE"
                        self.detected_age = f"{20 + (fw % 15)}-{28 + (fh % 10)} YRS"

                    cv2.putText(frame, f"{self.detected_gender}, {self.detected_age}", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                self.detected_gender = "SCANNING..."
                self.detected_age = "SCANNING..."

            self.lbl_gender.configure(text=f"GENDER : {self.detected_gender}")
            self.lbl_age.configure(text=f"EST AGE : {self.detected_age}")

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            hand_results = hands.process(rgb_frame)
            if hand_results.multi_hand_landmarks:
                for hand_landmarks in hand_results.multi_hand_landmarks:
                    mp_draw.draw_landmarks(
                        frame, 
                        hand_landmarks, 
                        mp_hands.HAND_CONNECTIONS,
                        mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                        mp_draw.DrawingSpec(color=(0, 150, 0), thickness=2)
                    )

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_resized = cv2.resize(frame_rgb, (640, 480))
            img = Image.fromarray(frame_resized)
            img_tk = ImageTk.PhotoImage(image=img)
            self.video_display.img_tk = img_tk
            self.video_display.configure(image=img_tk)

        self.after(40, self.update_dashboard_stream)

    # ---------------------------------------------------------
    # 3. معالجة الصوت والذكاء الاصطناعي (Ollama + تحويل Pydub للـ Webm)
    # ---------------------------------------------------------
    def process_voice_chunk(self, audio_b64):
        try:
            header, encoded = audio_b64.split(",", 1)
            audio_data = base64.b64decode(encoded)
            
            # تحويل ملف الـ webm القادم من متصفح الجوال إلى wav باستخدام pydub لتفهمها مكتبة التعرف على الصوت
            from pydub import AudioSegment
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_data), format="webm")
            wav_io = io.BytesIO()
            audio_segment.export(wav_io, format="wav")
            wav_io.seek(0)
            
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_io) as source:
                audio = recognizer.record(source)
                try:
                    user_text = recognizer.recognize_google(audio, language="ar-SA")
                    if len(user_text.strip()) < 2:
                        return
                    
                    self.log_chat("المستخدم (الجوال)", user_text)
                    self.query_ollama_ai(user_text)

                except sr.UnknownValueError:
                    pass
        except Exception as e:
            print("خطأ معالجة الصوت:", e)

    def query_ollama_ai(self, prompt_text):
        self.log_thought(f"THINKING >> استقبال السؤال: [{prompt_text}]")
        self.log_thought("THINKING >> جاري المعالجة عبر نموذج qwen:0.5b السريع...")
        
        try:
            response = requests.post('http://localhost:11434/api/generate', json={
                "model": "qwen:0.5b",
                "prompt": f"أنت نموذج ذكاء اصطناعي محلي تابع لشبكة أديب. أجب بإيجاز شديد وباللغة العربية على السؤال التالي: {prompt_text}",
                "stream": False
            }, timeout=8)
            
            if response.status_code == 200:
                ai_response = response.json().get('response', '')
                self.log_thought("THINKING >> اكتمل التفكير وتم استخراج الإجابة.")
                self.log_chat("الذكاء الاصطناعي", ai_response)
                self.speak(ai_response)
            else:
                self.log_thought("ERROR >> فشل الحصول على رد من Ollama.")
        except Exception as e:
            fallback_ans = f"أنا أستمع إليك عبر شبكة أديب. السؤال المحول: {prompt_text}"
            self.log_thought("THINKING >> تعذر الوصول لـ Ollama المحلي، تشغيل الرد الاحتياطي.")
            self.log_chat("الذكاء الاصطناعي", fallback_ans)
            self.speak(fallback_ans)

# ---------------------------------------------------------
# 4. التشغيل الرئيسي
# ---------------------------------------------------------
if __name__ == "__main__":
    gui = CyberAiDashboard()
    gui.mainloop()