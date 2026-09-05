# A-simple-AI-project.
Artificial Intelligence Project Developed in Python

Project Concept

The project consists of an artificial intelligence system developed using the Python programming language.

The main idea is to turn the computer into a server that receives a live video stream from a mobile phone at a rate of 10 frames per second (FPS) over the local network using the computer's local IP address.

The video is analyzed in real time using artificial intelligence. Any face detected in the video is automatically surrounded by a bounding box, and the system attempts to estimate the person's gender and age in real time.

In addition, the system detects the hand joints and key landmarks using the MediaPipe library, providing a visual representation of the detected hand structure.

Project Limitations and Issues

- There is currently an issue with transmitting and receiving audio in real time between the mobile phone and the computer.
- The voice-based artificial intelligence component, which was intended to allow the user to communicate with the system directly through voice using an Ollama model, does not currently function because of the limited computational capabilities of the available computer.
- The gender and age estimation is only an AI-based prediction and should not be considered necessarily accurate or representative of the person's actual gender or age.

How to Run the Project

1. Obtain the Computer's Local IPv4 Address

First, obtain the computer's IPv4 address on the local network.

2. Configure Chrome on the Mobile Phone

On the mobile phone, open Google Chrome and enter the following address in the address bar:

"chrome://flags/#unsafely-treat-insecure-origin-as-secure"

Then locate the option:

Insecure origins treated as secure

In the corresponding text box, enter the computer's local IP address using the "http" protocol and port "5000".

For example:

"http://16.91.66.315:5000"

Then select Enabled and restart Chrome by pressing Relaunch.

3. Access the Project

After Chrome has restarted, enter the same project address that was added to the Insecure origins treated as secure field, including the "http" protocol and port number.

When prompted, grant the website permission to access the camera and microphone.

The mobile phone can then transmit the live video stream to the computer over the local network, where it is processed by the AI system in real time.
